"""Customer tokens for the Mini App, issued only after server-side initData validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core import signing
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.customers.models import Customer
from core.errors import DomainError, NotFoundError
from core.middleware import set_business_context

SALT = "storefront.customer"
SCHEME = "Customer"


def issue_customer_token(customer: Customer) -> str:
    return signing.dumps({"c": str(customer.id), "b": str(customer.business_id)}, salt=SALT)


@dataclass
class CustomerPrincipal:
    customer: Customer
    is_authenticated: bool = True
    is_active: bool = True
    is_platform_admin: bool = False

    @property
    def pk(self) -> Any:
        return f"customer:{self.customer.pk}"


class CustomerTokenAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[CustomerPrincipal, str] | None:
        header = request.headers.get("Authorization", "")
        if not header.startswith(f"{SCHEME} "):
            return None
        token = header[len(SCHEME) + 1 :].strip()
        try:
            data = signing.loads(
                token, salt=SALT, max_age=settings.CUSTOMER_TOKEN_LIFETIME.total_seconds()
            )
        except signing.BadSignature:
            raise DomainError("not_authenticated", status_code=401) from None
        customer = (
            Customer.objects.select_related("business__settings")
            .filter(id=data["c"], business_id=data["b"])
            .first()
        )
        if customer is None:
            raise DomainError("not_authenticated", status_code=401)
        request.customer = customer  # type: ignore[attr-defined]
        set_business_context(customer.business_id)
        return CustomerPrincipal(customer), token

    def authenticate_header(self, request: Request) -> str:
        return SCHEME


class IsStoreCustomer(BasePermission):
    """The customer token must belong to the business named in the URL."""

    def has_permission(self, request: Request, view: Any) -> bool:
        customer = getattr(request, "customer", None)
        if customer is None:
            return False
        if customer.business.slug != view.kwargs.get("slug"):
            raise NotFoundError()
        return True
