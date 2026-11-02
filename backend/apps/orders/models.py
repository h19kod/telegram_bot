from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from core.models import BaseModel, TenantModel


class CartStatus(models.TextChoices):
    ACTIVE = "active"
    CONVERTED = "converted"
    ABANDONED = "abandoned"


class Cart(TenantModel):
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="carts"
    )
    branch = models.ForeignKey("businesses.Branch", on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=CartStatus.choices, default=CartStatus.ACTIVE)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "branch"],
                condition=Q(status="active"),
                name="one_active_cart",
            )
        ]


class CartItem(TenantModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="+")
    options = models.ManyToManyField("products.Option", blank=True, related_name="+")
    options_fingerprint = models.CharField(max_length=64, default="")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(99)])
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product", "options_fingerprint", "note"], name="cart_line_unique"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1) & Q(quantity__lte=99), name="cart_qty_range"
            ),
        ]


class OrderStatus(models.TextChoices):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


TERMINAL_STATUSES = frozenset({OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REJECTED})
OPEN_STATUSES = frozenset(set(OrderStatus) - TERMINAL_STATUSES)


class Fulfilment(models.TextChoices):
    DELIVERY = "delivery"
    PICKUP = "pickup"
    DINE_IN = "dine_in"


class Channel(models.TextChoices):
    BOT = "bot"
    MINI_APP = "mini_app"
    AI = "ai"
    DASHBOARD = "dashboard"


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid"
    PAID = "paid"
    REFUNDED = "refunded"


class OrderCounter(models.Model):
    business = models.OneToOneField(
        "businesses.Business", on_delete=models.CASCADE, primary_key=True, related_name="+"
    )
    last_number = models.PositiveIntegerField(default=1000)


class Order(TenantModel):
    number = models.PositiveIntegerField()
    branch = models.ForeignKey("businesses.Branch", on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="orders"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    version = models.PositiveIntegerField(default=1)
    fulfilment = models.CharField(max_length=10, choices=Fulfilment.choices)
    idempotency_key = models.UUIDField()
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=16)
    delivery_zone = models.ForeignKey(
        "delivery.DeliveryZone",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    zone_name_snapshot = models.CharField(max_length=120, blank=True)
    table_label = models.CharField(max_length=10, blank=True)  # dine-in only
    address_area = models.CharField(max_length=120, blank=True)
    address_street = models.CharField(max_length=200, blank=True)
    address_landmark = models.CharField(max_length=200, blank=True)
    address_building = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    payment_method = models.CharField(max_length=32)
    payment_status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    currency = models.CharField(max_length=3)
    language = models.CharField(max_length=2, default="ar")
    subtotal = models.BigIntegerField()
    delivery_fee = models.BigIntegerField(default=0)
    discount_total = models.BigIntegerField(default=0)
    total = models.BigIntegerField()
    assigned_driver = models.ForeignKey(
        "staff.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_orders",
    )
    placed_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-placed_at"]
        constraints = [
            models.UniqueConstraint(fields=["business", "number"], name="order_number_unique"),
            models.UniqueConstraint(
                fields=["business", "customer", "idempotency_key"], name="order_idempotency"
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") + F("delivery_fee") - F("discount_total"))
                & Q(total__gte=0),
                name="order_total_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=["business", "status", "-placed_at"]),
            models.Index(fields=["business", "-placed_at"]),
            models.Index(fields=["business", "customer", "-placed_at"]),
        ]

    def __str__(self) -> str:
        return f"#{self.number}"


class OrderItem(TenantModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    product_name_ar = models.CharField(max_length=150)
    product_name_en = models.CharField(max_length=150, blank=True)
    unit_price = models.BigIntegerField(help_text="Base price + option deltas at order time")
    quantity = models.PositiveIntegerField()
    line_total = models.BigIntegerField()
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]


class OrderItemOption(BaseModel):
    item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="options")
    option = models.ForeignKey(
        "products.Option", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    group_name_ar = models.CharField(max_length=100)
    group_name_en = models.CharField(max_length=100, blank=True)
    option_name_ar = models.CharField(max_length=100)
    option_name_en = models.CharField(max_length=100, blank=True)
    price_delta = models.BigIntegerField()


class EventSource(models.TextChoices):
    DASHBOARD = "dashboard"
    TELEGRAM = "telegram"
    MINI_APP = "mini_app"
    SYSTEM = "system"
    CUSTOMER = "customer"


class OrderStatusEvent(TenantModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor_user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor_customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    source = models.CharField(max_length=12, choices=EventSource.choices)
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["created_at"]


class NotificationKind(models.TextChoices):
    STAFF = "staff"
    CUSTOMER = "customer"


class OrderNotificationMessage(TenantModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="tg_messages")
    bot = models.ForeignKey("businesses.TelegramBot", on_delete=models.CASCADE, related_name="+")
    chat_id = models.BigIntegerField()
    message_id = models.BigIntegerField()
    kind = models.CharField(max_length=10, choices=NotificationKind.choices)
    event_key = models.CharField(max_length=32, default="", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "chat_id", "kind", "event_key"], name="order_msg_unique_event"
            )
        ]


class CouponKind(models.TextChoices):
    PERCENT = "percent"
    FIXED = "fixed"


class Coupon(TenantModel):
    code = models.CharField(max_length=32)
    kind = models.CharField(max_length=8, choices=CouponKind.choices)
    value = models.PositiveIntegerField(help_text="Percent (1-100) or fixed amount in minor units")
    max_discount = models.BigIntegerField(null=True, blank=True)
    min_order = models.BigIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    per_customer_limit = models.PositiveIntegerField(null=True, blank=True, default=1)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["business", "code"], name="coupon_code_unique"),
            models.CheckConstraint(
                condition=~Q(kind="percent") | (Q(value__gte=1) & Q(value__lte=100)),
                name="coupon_percent_range",
            ),
        ]

    def __str__(self) -> str:
        return self.code

    def discount_for(self, subtotal: int) -> int:
        if self.kind == CouponKind.PERCENT:
            amount = subtotal * self.value // 100
            if self.max_discount is not None:
                amount = min(amount, self.max_discount)
        else:
            amount = self.value
        return max(0, min(amount, subtotal))


class CouponRedemption(TenantModel):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="coupon_redemption")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="+")
    amount = models.BigIntegerField()


class OrderReview(TenantModel):
    """The customer's rating of one delivered order, with an optional public reply."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="+")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.CharField(max_length=500, blank=True)
    reply = models.CharField(max_length=500, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    replied_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__gte=1) & Q(rating__lte=5), name="review_rating_range"
            )
        ]
        indexes = [models.Index(fields=["business", "-created_at"])]
