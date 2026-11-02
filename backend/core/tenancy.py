"""Tenant resolution for business-scoped API views.

Every dashboard tenant URL is /api/v1/b/<business_id>/...; the caller's membership in that
business is resolved once per request. No membership → 404 (never reveal other tenants).
"""

from __future__ import annotations

from typing import Any

from django.db.models import Model, QuerySet
from rest_framework import serializers, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.businesses.models import Business
from apps.staff.services import get_membership
from core.errors import ForbiddenError, NotFoundError
from core.middleware import set_business_context


def resolve_business(request: Request, business_id: Any) -> None:
    if getattr(request, "business", None) is not None:
        return
    membership = get_membership(request.user, business_id)
    if membership is None:
        raise NotFoundError()
    request.business = membership.business  # type: ignore[attr-defined]
    request.membership = membership  # type: ignore[attr-defined]
    set_business_context(membership.business_id)


class IsBusinessMember(BasePermission):
    """Resolves tenant + membership and checks `required_permissions[action]` on the view."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        resolve_business(request, view.kwargs.get("business_id"))
        needed = required_for(view, request)
        missing = [p for p in needed if not request.membership.has_perm(p)]  # type: ignore[attr-defined]
        if missing:
            raise ForbiddenError({"required": missing})
        return True


def required_for(view: Any, request: Request) -> list[str]:
    perms: dict[str, Any] = getattr(view, "required_permissions", {})
    action = getattr(view, "action", None) or request.method.lower()
    value = perms.get(action, perms.get("*", []))
    if isinstance(value, str):
        value = [value]
    if action not in perms and request.method not in ("GET", "HEAD", "OPTIONS"):
        value = list(value) + list(perms.get("write", []))
    return list(value)


class TenantViewSet(viewsets.ModelViewSet):
    """Querysets are always scoped to request.business; `business` is injected server-side."""

    permission_classes = [IsBusinessMember]
    model: type[Model]

    @property
    def business(self) -> Business:
        # OpenAPI generation runs without a tenant: for_business(None) yields an empty queryset.
        return getattr(self.request, "business", None)  # type: ignore[return-value]

    @property
    def membership(self) -> Any:
        return self.request.membership  # type: ignore[attr-defined]

    def base_queryset(self) -> QuerySet:
        return self.model.objects.for_business(self.business)  # type: ignore[attr-defined]

    def get_queryset(self) -> QuerySet:
        return self.base_queryset()

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        if hasattr(self.request, "business"):
            ctx["business"] = self.request.business  # type: ignore[attr-defined]
        return ctx

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        serializer.save(business=self.business)


class TenantPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """A FK input field that only accepts objects of the current business."""

    def get_queryset(self) -> QuerySet:
        qs = super().get_queryset()
        business = self.context.get("business")
        if business is None:
            return qs.none()
        return qs.filter(business=business)


def require(request: Request, *codenames: str) -> None:
    missing = [c for c in codenames if not request.membership.has_perm(c)]  # type: ignore[attr-defined]
    if missing:
        raise ForbiddenError({"required": missing})
