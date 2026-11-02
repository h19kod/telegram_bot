from __future__ import annotations

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from core.models import BaseModel, Language, TenantModel
from core.money import CURRENCY_CHOICES


class Governorate(models.Model):
    code = models.CharField(max_length=8, primary_key=True)
    name_ar = models.CharField(max_length=64)
    name_en = models.CharField(max_length=64)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return self.name_en


class BusinessType(models.TextChoices):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    BAKERY = "bakery"
    GROCERY = "grocery"
    PHARMACY = "pharmacy"
    RETAIL = "retail"
    OTHER = "other"


class BusinessStatus(models.TextChoices):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


slug_validator = RegexValidator(r"^[a-z0-9](?:[a-z0-9_]{1,48}[a-z0-9])$", "Invalid slug")


class Business(BaseModel):
    slug = models.CharField(max_length=50, unique=True, validators=[slug_validator])
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    description_ar = models.TextField(blank=True, max_length=2000)
    description_en = models.TextField(blank=True, max_length=2000)
    business_type = models.CharField(
        max_length=16, choices=BusinessType.choices, default=BusinessType.RESTAURANT
    )
    logo = models.ImageField(upload_to="businesses/logos/", blank=True)
    cover = models.ImageField(upload_to="businesses/covers/", blank=True)
    phone = models.CharField(max_length=16, blank=True)
    whatsapp = models.CharField(max_length=16, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="IQD")
    default_language = models.CharField(max_length=2, choices=Language.choices, default=Language.AR)
    timezone = models.CharField(max_length=64, default="Asia/Baghdad")
    status = models.CharField(
        max_length=16, choices=BusinessStatus.choices, default=BusinessStatus.ACTIVE
    )
    suspended_reason = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_businesses"
    )

    class Meta:
        verbose_name_plural = "businesses"

    def __str__(self) -> str:
        return self.slug

    @property
    def is_active(self) -> bool:
        return self.status == BusinessStatus.ACTIVE


class Branch(TenantModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="branches")
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    governorate = models.ForeignKey(
        Governorate, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    address = models.CharField(max_length=300, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    phone = models.CharField(max_length=16, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_temporarily_closed = models.BooleanField(default=False)
    accepts_delivery = models.BooleanField(default=True)
    accepts_pickup = models.BooleanField(default=True)
    accepts_dine_in = models.BooleanField(default=False)  # orders from table QR codes

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business"], condition=Q(is_default=True), name="one_default_branch"
            )
        ]

    def __str__(self) -> str:
        return self.name_ar


class WorkingHours(TenantModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="+")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="hours")
    weekday = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(6)], help_text="0=Monday"
    )
    opens_at = models.TimeField()
    closes_at = models.TimeField(help_text="<= opens_at means the interval crosses midnight")

    class Meta:
        ordering = ["weekday", "opens_at"]


class Closure(TenantModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="+")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="closures")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="closure_valid_range"
            )
        ]


class PaymentMethod(models.TextChoices):
    CASH_ON_DELIVERY = "cash_on_delivery"
    PAY_AT_PICKUP = "pay_at_pickup"


def default_payment_methods() -> list[str]:
    return [PaymentMethod.CASH_ON_DELIVERY, PaymentMethod.PAY_AT_PICKUP]


class BusinessSettings(TenantModel):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="settings")
    min_order_amount = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    customer_cancel_window_min = models.PositiveIntegerField(default=5)
    auto_reject_after_min = models.PositiveIntegerField(null=True, blank=True)
    allow_order_notes = models.BooleanField(default=True)
    # Customers must confirm their phone (WhatsApp code / Telegram contact) before ordering.
    require_verified_phone = models.BooleanField(default=True)
    # Loyalty: 1 point per `loyalty_spend_per_point` spent (delivered orders); a point is worth
    # `loyalty_point_value` (both minor units) when redeemed, from `loyalty_min_redeem` points.
    loyalty_enabled = models.BooleanField(default=False)
    loyalty_spend_per_point = models.BigIntegerField(
        default=1000, validators=[MinValueValidator(1)]
    )
    loyalty_point_value = models.BigIntegerField(default=25, validators=[MinValueValidator(1)])
    loyalty_min_redeem = models.PositiveIntegerField(default=100)
    payment_methods = ArrayField(
        models.CharField(max_length=32, choices=PaymentMethod.choices),
        default=default_payment_methods,
    )
    ai_enabled = models.BooleanField(default=False)
    ai_persona_note = models.TextField(blank=True, max_length=1000)
    welcome_message_ar = models.TextField(blank=True, max_length=1000)
    welcome_message_en = models.TextField(blank=True, max_length=1000)
    notification_chat_ids = ArrayField(models.BigIntegerField(), default=list, blank=True)


class WebhookStatus(models.TextChoices):
    PENDING = "pending"
    ACTIVE = "active"
    POLLING = "polling"
    ERROR = "error"


class TelegramBot(BaseModel):
    """A Telegram bot. `business` is null only for the shared platform bot."""

    business = models.OneToOneField(
        Business, on_delete=models.CASCADE, null=True, blank=True, related_name="telegram_bot"
    )
    is_shared_platform_bot = models.BooleanField(default=False)
    bot_telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=64)
    token_encrypted = models.BinaryField(editable=False)
    webhook_secret = models.CharField(max_length=64, editable=False)
    webhook_status = models.CharField(
        max_length=16, choices=WebhookStatus.choices, default=WebhookStatus.PENDING
    )
    last_error = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_shared_platform_bot"],
                condition=Q(is_shared_platform_bot=True),
                name="single_shared_bot",
            ),
            models.CheckConstraint(
                condition=Q(is_shared_platform_bot=True, business__isnull=True)
                | Q(is_shared_platform_bot=False, business__isnull=False),
                name="bot_business_xor_shared",
            ),
        ]

    def __str__(self) -> str:
        return f"@{self.username}"

    @property
    def token(self) -> str:
        from core.crypto import decrypt

        return decrypt(self.token_encrypted)
