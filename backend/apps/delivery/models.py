from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from core.models import TenantModel


class DeliveryZone(TenantModel):
    branch = models.ForeignKey(
        "businesses.Branch", on_delete=models.CASCADE, related_name="delivery_zones"
    )
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    governorate = models.ForeignKey(
        "businesses.Governorate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    areas = ArrayField(models.CharField(max_length=120), default=list, blank=True)
    fee = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    min_order = models.BigIntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    free_delivery_threshold = models.BigIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0)]
    )
    eta_min = models.PositiveIntegerField(null=True, blank=True)
    eta_max = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name_ar"]
        constraints = [
            models.CheckConstraint(condition=Q(fee__gte=0), name="zone_fee_non_negative")
        ]

    def __str__(self) -> str:
        return self.name_ar

    def fee_for(self, subtotal: int) -> int:
        if self.free_delivery_threshold is not None and subtotal >= self.free_delivery_threshold:
            return 0
        return self.fee
