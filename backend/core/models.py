"""Shared model base classes: UUIDv7 ids, timestamps and tenant scoping."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models
from uuid6 import uuid7

if TYPE_CHECKING:
    from apps.businesses.models import Business


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    def for_business(self, business: Business | Any) -> TenantQuerySet:
        business_id = getattr(business, "pk", business)
        return self.filter(business_id=business_id)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    pass


class TenantModel(BaseModel):
    """Every row belongs to exactly one business. Never expose `business` as client input."""

    business = models.ForeignKey(
        "businesses.Business", on_delete=models.PROTECT, related_name="+", db_index=True
    )

    objects = TenantManager()

    class Meta:
        abstract = True


class Language(models.TextChoices):
    AR = "ar", "العربية"
    EN = "en", "English"


def localized(obj: Any, field: str, lang: str | None) -> str:
    """Return `<field>_<lang>` with fallback to Arabic, then English."""
    lang = lang if lang in ("ar", "en") else "ar"
    value = getattr(obj, f"{field}_{lang}", "") or ""
    if value:
        return value
    return getattr(obj, f"{field}_ar", "") or getattr(obj, f"{field}_en", "") or ""
