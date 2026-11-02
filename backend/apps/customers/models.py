from __future__ import annotations

from django.db import models

from core.models import Language, TenantModel


class Customer(TenantModel):
    """A Telegram user as seen by one business. Identified only via validated Telegram data."""

    telegram_user_id = models.BigIntegerField()
    telegram_username = models.CharField(max_length=64, blank=True)
    first_name = models.CharField(max_length=128, blank=True)
    last_name = models.CharField(max_length=128, blank=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=16, blank=True)
    # Set only when `phone` was proven: a WhatsApp code or the user's own Telegram contact.
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.AR)
    is_blocked = models.BooleanField(default=False)
    blocked_reason = models.CharField(max_length=200, blank=True)
    first_order_at = models.DateTimeField(null=True, blank=True)
    last_order_at = models.DateTimeField(null=True, blank=True)
    orders_count = models.PositiveIntegerField(default=0)
    total_spent = models.BigIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "telegram_user_id"], name="customer_unique_tg"
            )
        ]
        indexes = [models.Index(fields=["business", "last_order_at"])]

    def __str__(self) -> str:
        return self.full_name or self.first_name or str(self.telegram_user_id)

    @property
    def display_name(self) -> str:
        return (
            self.full_name
            or " ".join(p for p in (self.first_name, self.last_name) if p)
            or (f"@{self.telegram_username}" if self.telegram_username else "")
        )

    @property
    def phone_verified(self) -> bool:
        return bool(self.phone and self.phone_verified_at)


class PhoneVerification(TenantModel):
    """One WhatsApp code sent to `phone` for `customer`. Only an HMAC of the code is stored."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="+")
    phone = models.CharField(max_length=16)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["phone", "created_at"]),
        ]


class AddressLabel(models.TextChoices):
    HOME = "home"
    WORK = "work"
    OTHER = "other"


class CustomerAddress(TenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=8, choices=AddressLabel.choices, default=AddressLabel.HOME)
    zone = models.ForeignKey(
        "delivery.DeliveryZone",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    area = models.CharField(max_length=120, blank=True)
    street = models.CharField(max_length=200, blank=True)
    landmark = models.CharField(max_length=200, blank=True)
    building = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)
