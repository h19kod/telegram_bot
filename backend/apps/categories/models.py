from __future__ import annotations

from django.db import models

from core.models import TenantModel


class Category(TenantModel):
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["sort_order", "created_at"]
        indexes = [models.Index(fields=["business", "is_active", "sort_order"])]

    def __str__(self) -> str:
        return self.name_ar
