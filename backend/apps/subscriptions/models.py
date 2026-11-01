from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import BaseModel, TenantModel
from core.money import CURRENCY_CHOICES


class ValueType(models.TextChoices):
    BOOL = "bool"
    INT = "int"


class ResetPeriod(models.TextChoices):
    NONE = "none"
    MONTH = "month"


class Feature(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    value_type = models.CharField(max_length=4, choices=ValueType.choices)
    default_value = models.JSONField(null=True, blank=True)
    is_metered = models.BooleanField(default=False)
    reset_period = models.CharField(
        max_length=8, choices=ResetPeriod.choices, default=ResetPeriod.NONE
    )
    description = models.CharField(max_length=200, blank=True)

    def __str__(self) -> str:
        return self.key


class Plan(BaseModel):
    code = models.SlugField(max_length=32, unique=True)
    name_ar = models.CharField(max_length=64)
    name_en = models.CharField(max_length=64)
    monthly_price = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="IQD")
    is_public = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    trial_days = models.PositiveIntegerField(default=0)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"], condition=Q(is_default=True), name="single_default_plan"
            )
        ]

    def __str__(self) -> str:
        return self.code


class PlanEntitlement(BaseModel):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="entitlements")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="+")
    value = models.JSONField(null=True, blank=True, help_text="bool, int, or null = unlimited")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "feature"], name="plan_feature_unique")
        ]


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


LIVE_SUBSCRIPTION_STATUSES = (
    SubscriptionStatus.TRIALING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAST_DUE,
)


class Subscription(TenantModel):
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=10, choices=SubscriptionStatus.choices)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField(null=True, blank=True)
    grace_until = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business"],
                condition=Q(status__in=["trialing", "active", "past_due"]),
                name="one_live_subscription",
            )
        ]


class PaymentMethodChoice(models.TextChoices):
    CASH = "cash"
    ZAINCASH = "zaincash"
    BANK_TRANSFER = "bank_transfer"
    OTHER = "other"


class SubscriptionPayment(TenantModel):
    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.BigIntegerField()
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    method = models.CharField(max_length=16, choices=PaymentMethodChoice.choices)
    reference = models.CharField(max_length=120, blank=True)
    months = models.PositiveSmallIntegerField(default=1)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    paid_at = models.DateTimeField()


class EntitlementOverride(TenantModel):
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="+")
    value = models.JSONField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "feature"], name="override_unique")
        ]


class UsageCounter(TenantModel):
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="+")
    period_start = models.DateField()
    used = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "feature", "period_start"], name="usage_unique_period"
            )
        ]
