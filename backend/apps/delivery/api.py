from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.businesses.models import Branch
from apps.businesses.services import default_branch
from apps.delivery.models import DeliveryZone
from core.tenancy import TenantPrimaryKeyRelatedField, TenantViewSet
from core.text import normalize_arabic


class DeliveryZoneSerializer(serializers.ModelSerializer):
    branch = TenantPrimaryKeyRelatedField(queryset=Branch.objects.all(), required=False)
    areas = serializers.ListField(
        child=serializers.CharField(max_length=120), required=False, max_length=200
    )

    class Meta:
        model = DeliveryZone
        fields = [
            "id",
            "branch",
            "name_ar",
            "name_en",
            "governorate",
            "areas",
            "fee",
            "min_order",
            "free_delivery_threshold",
            "eta_min",
            "eta_max",
            "is_active",
            "sort_order",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        lo = attrs.get("eta_min", getattr(self.instance, "eta_min", None))
        hi = attrs.get("eta_max", getattr(self.instance, "eta_max", None))
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"eta_max": "must be >= eta_min"})
        if "areas" in attrs:
            attrs["areas"] = [a.strip() for a in attrs["areas"] if a.strip()]
        return attrs


class DeliveryZoneViewSet(TenantViewSet):
    model = DeliveryZone
    serializer_class = DeliveryZoneSerializer
    required_permissions = {"list": [], "retrieve": [], "write": ["delivery.manage"]}
    pagination_class = None

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        branch = serializer.validated_data.pop("branch", None) or default_branch(self.business)
        serializer.save(business=self.business, branch=branch)


def match_zone(zones: list[DeliveryZone], text: str) -> DeliveryZone | None:
    """Best-effort match of a free-text area to a zone (used by the bot and AI)."""
    needle = normalize_arabic(text)
    if not needle:
        return None
    for z in zones:
        names = [z.name_ar, z.name_en, *z.areas]
        if any(normalize_arabic(n) and normalize_arabic(n) in needle for n in names):
            return z
    return None
