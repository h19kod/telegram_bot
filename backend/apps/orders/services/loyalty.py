"""Loyalty points: earned on delivered orders, redeemed as a checkout discount.

Every change goes through `_post`, which locks the customer row and writes the ledger entry and
the denormalised balance together. Earning/refunding is idempotent per (order, reason).
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction

from apps.businesses.models import BusinessSettings
from apps.customers.models import Customer, LoyaltyEntry, LoyaltyReason
from apps.orders.models import Order
from core.errors import DomainError


def redeemable(
    cfg: BusinessSettings, balance: int, requested: int, payable: int
) -> tuple[int, int]:
    """(points used, discount) for redeeming `requested` points against `payable`.

    Never more than the balance, never more value than the order still costs (whole points).
    """
    if requested <= 0:
        return 0, 0
    if not cfg.loyalty_enabled:
        raise DomainError("loyalty_unavailable")
    if requested < cfg.loyalty_min_redeem:
        raise DomainError("points_below_minimum", {"minimum": cfg.loyalty_min_redeem})
    if requested > balance:
        raise DomainError("not_enough_points", {"balance": balance})
    points = min(requested, max(payable, 0) // cfg.loyalty_point_value)
    return points, points * cfg.loyalty_point_value


def _post(
    customer_id: Any,
    business_id: Any,
    delta: int,
    reason: str,
    order: Order | None = None,
    note: str = "",
) -> LoyaltyEntry | None:
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer_id, business_id=business_id)
        balance = customer.points_balance + delta
        if balance < 0:
            raise DomainError("not_enough_points", {"balance": customer.points_balance})
        try:
            with transaction.atomic():
                entry = LoyaltyEntry.objects.create(
                    business_id=business_id,
                    customer=customer,
                    order=order,
                    delta=delta,
                    reason=reason,
                    balance_after=balance,
                    note=note[:200],
                )
        except IntegrityError:
            return None  # this order already earned/redeemed/refunded: idempotent
        Customer.objects.filter(pk=customer.pk).update(points_balance=balance)
    return entry


def redeem_for_order(order: Order) -> None:
    """Called inside checkout's transaction once the order row exists."""
    if order.points_redeemed:
        _post(
            order.customer_id,
            order.business_id,
            -order.points_redeemed,
            LoyaltyReason.REDEEM,
            order,
        )


def on_status_change(order: Order) -> None:
    """Earn on delivery; give redeemed points back if the order is cancelled or rejected."""
    cfg = order.business.settings
    if order.status == "delivered" and cfg.loyalty_enabled:
        paid = order.subtotal - order.discount_total
        points = max(paid, 0) // cfg.loyalty_spend_per_point
        if points > 0:
            _post(order.customer_id, order.business_id, points, LoyaltyReason.EARN, order)
    elif order.status in ("cancelled", "rejected") and order.points_redeemed:
        _post(
            order.customer_id,
            order.business_id,
            order.points_redeemed,
            LoyaltyReason.REFUND,
            order,
        )


def adjust(customer: Customer, delta: int, note: str) -> LoyaltyEntry:
    """Manual correction by staff (goodwill points, mistakes). Must leave a reason."""
    if not delta or not note.strip():
        raise DomainError("validation_error", {"delta": ["non-zero"], "note": ["required"]}, 400)
    entry = _post(customer.pk, customer.business_id, delta, LoyaltyReason.ADJUST, None, note)
    if entry is None:  # pragma: no cover — only order-bound entries can be duplicates
        raise DomainError("conflict", status_code=409)
    return entry
