"""Coupon validation. Discounts are computed server-side only, inside the checkout transaction."""

from __future__ import annotations

from typing import Any

from django.db.models import F
from django.utils import timezone

from apps.customers.models import Customer
from apps.orders.models import Coupon, CouponRedemption, Order
from apps.subscriptions import services as entitlements
from core.errors import DomainError


def normalize_code(code: str) -> str:
    return "".join(code.split()).upper()[:32]


def resolve(
    business_id: Any, customer: Customer, code: str, subtotal: int, lock: bool = False
) -> tuple[Coupon, int]:
    entitlements.require_feature(business_id, "coupons")
    qs = Coupon.objects.for_business(business_id).filter(code=normalize_code(code), is_active=True)
    if lock:
        qs = qs.select_for_update()
    coupon = qs.first()
    if coupon is None:
        raise DomainError("coupon_invalid", status_code=400)
    now = timezone.now()
    if (coupon.starts_at and now < coupon.starts_at) or (coupon.ends_at and now >= coupon.ends_at):
        raise DomainError("coupon_expired")
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        raise DomainError("coupon_exhausted")
    if coupon.per_customer_limit is not None:
        used = CouponRedemption.objects.filter(coupon=coupon, customer=customer).count()
        if used >= coupon.per_customer_limit:
            raise DomainError("coupon_exhausted")
    if subtotal < coupon.min_order:
        raise DomainError("coupon_min_order", {"minimum": coupon.min_order})
    return coupon, coupon.discount_for(subtotal)


def redeem(coupon: Coupon, order: Order, amount: int) -> None:
    CouponRedemption.objects.create(
        business_id=order.business_id,
        coupon=coupon,
        order=order,
        customer=order.customer,
        amount=amount,
    )
    Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)


def release(order: Order) -> None:
    """Cancelled/rejected orders give the coupon use back."""
    red = CouponRedemption.objects.filter(order=order).first()
    if red is None:
        return
    Coupon.objects.filter(pk=red.coupon_id, used_count__gt=0).update(used_count=F("used_count") - 1)
    red.delete()
