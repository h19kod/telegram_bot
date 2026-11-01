from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from core.models import TenantModel
from core.text import normalize_arabic


class Availability(models.TextChoices):
    AVAILABLE = "available"
    OUT_OF_STOCK = "out_of_stock"
    HIDDEN = "hidden"


class Product(TenantModel):
    category = models.ForeignKey(
        "categories.Category", on_delete=models.PROTECT, related_name="products"
    )
    name_ar = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150, blank=True)
    description_ar = models.TextField(blank=True, max_length=3000)
    description_en = models.TextField(blank=True, max_length=3000)
    sku = models.CharField(max_length=64, blank=True)
    price = models.BigIntegerField(validators=[MinValueValidator(0)])
    compare_at_price = models.BigIntegerField(null=True, blank=True)
    availability = models.CharField(
        max_length=16, choices=Availability.choices, default=Availability.AVAILABLE
    )
    track_stock = models.BooleanField(default=False)
    stock_quantity = models.IntegerField(null=True, blank=True)
    prep_time_min = models.PositiveIntegerField(null=True, blank=True)
    tags = ArrayField(models.CharField(max_length=32), default=list, blank=True)
    sort_order = models.IntegerField(default=0)
    is_archived = models.BooleanField(default=False)
    search_text = models.TextField(blank=True, editable=False)

    class Meta:
        ordering = ["sort_order", "created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="product_price_non_negative"),
            models.CheckConstraint(
                condition=Q(compare_at_price__isnull=True) | Q(compare_at_price__gt=F("price")),
                name="product_compare_at_gt_price",
            ),
            models.CheckConstraint(
                condition=Q(stock_quantity__isnull=True) | Q(stock_quantity__gte=0),
                name="product_stock_non_negative",
            ),
            models.UniqueConstraint(
                fields=["business", "sku"], condition=~Q(sku=""), name="product_unique_sku"
            ),
        ]
        indexes = [
            models.Index(fields=["business", "category", "availability"]),
            GinIndex(
                name="product_search_trgm", fields=["search_text"], opclasses=["gin_trgm_ops"]
            ),
        ]

    def __str__(self) -> str:
        return self.name_ar

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.search_text = normalize_arabic(
            " ".join(
                filter(
                    None,
                    [
                        self.name_ar,
                        self.name_en,
                        self.description_ar,
                        self.description_en,
                        " ".join(self.tags or []),
                    ],
                )
            )
        )
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "search_text"}
        super().save(*args, **kwargs)

    @property
    def is_orderable(self) -> bool:
        if self.is_archived or self.availability != Availability.AVAILABLE:
            return False
        return not (self.track_stock and (self.stock_quantity or 0) <= 0)


class ProductImage(TenantModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    thumbnail = models.ImageField(upload_to="products/thumbs/", blank=True)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    sort_order = models.IntegerField(default=0)
    alt_ar = models.CharField(max_length=150, blank=True)
    alt_en = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["sort_order", "created_at"]


class SelectionType(models.TextChoices):
    SINGLE = "single"
    MULTIPLE = "multiple"


class OptionGroup(TenantModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="option_groups")
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True)
    selection_type = models.CharField(
        max_length=8, choices=SelectionType.choices, default=SelectionType.SINGLE
    )
    is_required = models.BooleanField(default=False)
    min_select = models.PositiveSmallIntegerField(default=0)
    max_select = models.PositiveSmallIntegerField(default=1)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(min_select__lte=F("max_select")), name="optgroup_min_le_max"
            ),
            models.CheckConstraint(
                condition=~Q(selection_type="single") | Q(max_select=1),
                name="optgroup_single_max_one",
            ),
            models.CheckConstraint(condition=Q(max_select__gte=1), name="optgroup_max_ge_one"),
        ]

    @property
    def effective_min(self) -> int:
        return max(self.min_select, 1 if self.is_required else 0)


class Option(TenantModel):
    group = models.ForeignKey(OptionGroup, on_delete=models.CASCADE, related_name="options")
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True)
    price_delta = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    is_available = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(price_delta__gte=0), name="option_delta_non_neg")
        ]
