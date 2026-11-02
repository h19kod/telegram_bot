"""Order placement. The only code path that creates orders — bot, Mini App and AI all use it."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.businesses.models import Branch, Business, BusinessSettings, PaymentMethod
from apps.businesses.services import ensure_can_take_orders, is_open
from apps.customers import services as customers
from apps.customers.models import Customer
from apps.delivery.models import DeliveryZone
from apps.notifications.outbox import enqueue
from apps.orders.models import (
    OPEN_STATUSES,
    Cart,
    CartStatus,
    Channel,
    EventSource,
    Fulfilment,
    Order,
    OrderCounter,
    OrderItem,
    OrderItemOption,
    OrderStatus,
    OrderStatusEvent,
)
from apps.orders.realtime import broadcast
from apps.orders.services.cart import PricedCart, get_active_cart, price_cart
from apps.products.models import Product
from apps.subscriptions import services as entitlements
from core.errors import DomainError, message_for
from core.phone import InvalidPhoneNumber, normalize_phone


@dataclass
class CheckoutInput:
    fulfilment: str
    customer_name: str
    customer_phone: str
    idempotency_key: uuid.UUID | None = None
    channel: str = Channel.BOT
    zone_id: Any = None
    address_area: str = ""
    address_street: str = ""
    address_landmark: str = ""
    address_building: str = ""
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    notes: str = ""
    payment_method: str = ""
    coupon_code: str = ""


@dataclass
class Quote:
    priced: PricedCart
    subtotal: int
    delivery_fee: int
    discount_total: int
    total: int
    currency: str
    zone: DeliveryZone | None
    phone: str
    payment_method: str
    coupon: Any = None
    warnings: list[str] = field(default_factory=list)


def _validate(
    business: Business,
    branch: Branch,
    customer: Customer,
    data: CheckoutInput,
    priced: PricedCart,
    for_quote: bool = False,
) -> Quote:
    ensure_can_take_orders(business)
    if customer.is_blocked:
        raise DomainError("customer_blocked", status_code=403)
    if not is_open(branch):
        raise DomainError("outside_working_hours")
    if not priced.lines:
        raise DomainError("cart_empty")
    if priced.has_problems:
        bad = [
            {"item_id": str(line.item.id), "reason": line.warning}
            for line in priced.lines
            if not line.available
        ]
        raise DomainError("product_unavailable", {"items": bad})

    cfg: BusinessSettings = business.settings
    if data.fulfilment not in Fulfilment.values:
        raise DomainError("fulfilment_unavailable", status_code=400)
    if data.fulfilment == Fulfilment.DELIVERY and not branch.accepts_delivery:
        raise DomainError("fulfilment_unavailable")
    if data.fulfilment == Fulfilment.PICKUP and not branch.accepts_pickup:
        raise DomainError("fulfilment_unavailable")

    phone = ""
    if not for_quote:  # quotes price the cart before contact details are entered
        name = data.customer_name.strip()
        if not 2 <= len(name) <= 150:
            raise DomainError("validation_error", {"customer_name": ["2-150 characters"]}, 400)
        try:
            phone = normalize_phone(data.customer_phone)
        except InvalidPhoneNumber:
            raise DomainError("invalid_phone", status_code=400) from None
        if customers.verification_required(business) and not customers.is_phone_verified(
            customer, phone
        ):
            raise DomainError(
                "phone_not_verified", {"customer_phone": [message_for("phone_not_verified")]}, 400
            )

    payment = data.payment_method or (
        PaymentMethod.CASH_ON_DELIVERY
        if data.fulfilment == Fulfilment.DELIVERY
        else PaymentMethod.PAY_AT_PICKUP
    )
    compatible = {
        Fulfilment.DELIVERY: {PaymentMethod.CASH_ON_DELIVERY},
        Fulfilment.PICKUP: {PaymentMethod.PAY_AT_PICKUP},
    }[Fulfilment(data.fulfilment)]
    if payment not in cfg.payment_methods or payment not in compatible:
        raise DomainError("payment_method_unavailable")

    if len(data.notes) > 500 or (data.notes and not cfg.allow_order_notes):
        raise DomainError("validation_error", {"notes": ["not allowed"]}, 400)

    subtotal = priced.subtotal
    zone: DeliveryZone | None = None
    delivery_fee = 0
    if data.fulfilment == Fulfilment.DELIVERY:
        if not data.zone_id:
            raise DomainError("delivery_zone_required", status_code=400)
        zone = (
            DeliveryZone.objects.for_business(business)
            .filter(id=data.zone_id, branch=branch, is_active=True)
            .first()
        )
        if zone is None:
            raise DomainError("delivery_zone_invalid", status_code=400)
        if not for_quote and (
            not data.address_area.strip()
            or not (data.address_street.strip() or data.address_landmark.strip())
        ):
            raise DomainError("address_required", status_code=400)
        if zone.min_order is not None and subtotal < zone.min_order:
            raise DomainError("below_minimum_order", {"minimum": zone.min_order})
        delivery_fee = zone.fee_for(subtotal)

    if subtotal < cfg.min_order_amount:
        raise DomainError("below_minimum_order", {"minimum": cfg.min_order_amount})

    discount_total, coupon = 0, None
    if data.coupon_code.strip():
        from apps.orders.services.coupons import resolve

        coupon, discount_total = resolve(
            business.id, customer, data.coupon_code, subtotal, lock=not for_quote
        )
    return Quote(
        priced=priced,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        discount_total=discount_total,
        total=subtotal + delivery_fee - discount_total,
        currency=business.currency,
        zone=zone,
        phone=phone,
        payment_method=payment,
        coupon=coupon,
    )


def quote(customer: Customer, branch: Branch, data: CheckoutInput) -> Quote:
    cart = get_active_cart(customer, branch, create=False)
    business = Business.objects.select_related("settings").get(pk=customer.business_id)
    return _validate(business, branch, customer, data, price_cart(cart), for_quote=True)


def _existing(customer: Customer, key: uuid.UUID) -> Order | None:
    return Order.objects.filter(
        business_id=customer.business_id, customer=customer, idempotency_key=key
    ).first()


def place_order(customer: Customer, branch: Branch, data: CheckoutInput) -> tuple[Order, bool]:
    """Create an order from the customer's cart. Returns (order, created).

    Idempotent per (customer, idempotency_key): retries return the original order.
    """
    if data.idempotency_key is None:
        raise DomainError("idempotency_key_required", status_code=400)
    if branch.business_id != customer.business_id:
        raise DomainError("business_unavailable")

    with transaction.atomic():
        # Serialise checkouts per customer: concurrent retries wait here, then see the order.
        Customer.objects.select_for_update().filter(pk=customer.pk).first()
        existing = _existing(customer, data.idempotency_key)
        if existing:
            return existing, False

        business = Business.objects.select_related("settings").get(pk=customer.business_id)
        open_orders = Order.objects.filter(
            business=business, customer=customer, status__in=OPEN_STATUSES
        ).count()
        if open_orders >= settings.MAX_OPEN_ORDERS_PER_CUSTOMER:
            raise DomainError("too_many_open_orders")

        cart = get_active_cart(customer, branch, create=False)
        if cart is None:
            raise DomainError("cart_empty")
        Cart.objects.select_for_update().filter(pk=cart.pk).first()
        product_ids = sorted({str(pid) for pid in cart.items.values_list("product_id", flat=True)})
        list(Product.objects.select_for_update().filter(id__in=product_ids).order_by("id"))

        q = _validate(business, branch, customer, data, price_cart(cart))
        entitlements.consume(business.id, "max_orders_per_month")

        counter = OrderCounter.objects.select_for_update().get(business=business)
        counter.last_number += 1
        counter.save(update_fields=["last_number"])

        now = timezone.now()
        is_delivery = data.fulfilment == Fulfilment.DELIVERY
        order = Order.objects.create(
            business=business,
            number=counter.last_number,
            branch=branch,
            customer=customer,
            channel=data.channel,
            fulfilment=data.fulfilment,
            idempotency_key=data.idempotency_key,
            customer_name=data.customer_name.strip(),
            customer_phone=q.phone,
            delivery_zone=q.zone,
            zone_name_snapshot=q.zone.name_ar if q.zone else "",
            address_area=data.address_area.strip()[:120] if is_delivery else "",
            address_street=data.address_street.strip()[:200] if is_delivery else "",
            address_landmark=data.address_landmark.strip()[:200] if is_delivery else "",
            address_building=data.address_building.strip()[:120] if is_delivery else "",
            latitude=data.latitude if is_delivery else None,
            longitude=data.longitude if is_delivery else None,
            notes=data.notes.strip(),
            payment_method=q.payment_method,
            currency=q.currency,
            language=customer.language,
            subtotal=q.subtotal,
            delivery_fee=q.delivery_fee,
            discount_total=q.discount_total,
            total=q.total,
            placed_at=now,
        )
        for line in q.priced.lines:
            product = line.item.product
            item = OrderItem.objects.create(
                business=business,
                order=order,
                product=product,
                product_name_ar=product.name_ar,
                product_name_en=product.name_en,
                unit_price=line.unit_price,
                quantity=line.item.quantity,
                line_total=line.line_total,
                note=line.item.note,
            )
            OrderItemOption.objects.bulk_create(
                [
                    OrderItemOption(
                        item=item,
                        option=opt,
                        group_name_ar=opt.group.name_ar,
                        group_name_en=opt.group.name_en,
                        option_name_ar=opt.name_ar,
                        option_name_en=opt.name_en,
                        price_delta=opt.price_delta,
                    )
                    for opt in line.options
                ]
            )
            if product.track_stock:
                updated = Product.objects.filter(
                    pk=product.pk, stock_quantity__gte=line.item.quantity
                ).update(stock_quantity=F("stock_quantity") - line.item.quantity)
                if not updated:
                    raise DomainError("insufficient_stock", {"product_id": str(product.pk)})

        if q.coupon is not None and q.discount_total:
            from apps.orders.services.coupons import redeem

            redeem(q.coupon, order, q.discount_total)

        OrderStatusEvent.objects.create(
            business=business,
            order=order,
            from_status="",
            to_status=OrderStatus.PENDING,
            actor_customer=customer,
            source=EventSource.CUSTOMER,
        )
        # A different (unverified) number replaces the old one and drops its verification.
        verified = {} if q.phone == customer.phone else {"phone_verified_at": None}
        Customer.objects.filter(pk=customer.pk).update(
            full_name=order.customer_name,
            phone=q.phone,
            **verified,
            orders_count=F("orders_count") + 1,
            last_order_at=now,
        )
        Customer.objects.filter(pk=customer.pk, first_order_at__isnull=True).update(
            first_order_at=now
        )
        cart.status = CartStatus.CONVERTED
        cart.save(update_fields=["status", "updated_at"])

        enqueue(
            "order.placed",
            business.id,
            {"order_id": str(order.id)},
            dedup_key=f"order:{order.id}:placed",
        )
        event = {
            "type": "order.created",
            "order_id": str(order.id),
            "number": order.number,
            "status": order.status,
            "version": order.version,
        }
        transaction.on_commit(lambda: broadcast(business.id, event))
    return order, True
