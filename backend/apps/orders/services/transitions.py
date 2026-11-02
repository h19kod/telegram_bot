"""The order state machine. Every status change goes through `transition`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.customers.models import Customer
from apps.notifications.outbox import enqueue
from apps.orders.models import (
    EventSource,
    Fulfilment,
    Order,
    OrderStatus,
    OrderStatusEvent,
)
from apps.orders.realtime import broadcast
from apps.products.models import Product
from apps.staff.models import Membership
from core.errors import ConflictError, DomainError, ForbiddenError, NotFoundError

S = OrderStatus

# (from, to) -> required permission
TRANSITIONS: dict[tuple[str, str], str] = {
    (S.PENDING, S.CONFIRMED): "orders.transition.confirmed",
    (S.PENDING, S.REJECTED): "orders.transition.rejected",
    (S.PENDING, S.CANCELLED): "orders.cancel",
    (S.CONFIRMED, S.PREPARING): "orders.transition.preparing",
    (S.CONFIRMED, S.CANCELLED): "orders.cancel",
    (S.PREPARING, S.READY): "orders.transition.ready",
    (S.PREPARING, S.CANCELLED): "orders.cancel",
    (S.READY, S.OUT_FOR_DELIVERY): "orders.transition.out_for_delivery",
    (S.READY, S.DELIVERED): "orders.transition.delivered",
    (S.READY, S.CANCELLED): "orders.cancel",
    (S.OUT_FOR_DELIVERY, S.DELIVERED): "orders.transition.delivered",
    (S.OUT_FOR_DELIVERY, S.CANCELLED): "orders.cancel",
}
REASON_REQUIRED = {S.REJECTED, S.CANCELLED}
_TIMESTAMP = {
    S.CONFIRMED: "confirmed_at",
    S.READY: "ready_at",
    S.DELIVERED: "delivered_at",
    S.CANCELLED: "cancelled_at",
    S.REJECTED: "cancelled_at",
}


def allowed_targets(order: Order) -> list[str]:
    out = []
    for frm, to in TRANSITIONS:
        if frm != order.status:
            continue
        if not _fulfilment_allows(order, frm, to):
            continue
        out.append(to)
    return out


def _fulfilment_allows(order: Order, frm: str, to: str) -> bool:
    if (frm, to) == (S.READY, S.OUT_FOR_DELIVERY):
        return order.fulfilment == Fulfilment.DELIVERY
    if (frm, to) == (S.READY, S.DELIVERED):  # handed over at the counter / served at the table
        return order.fulfilment in (Fulfilment.PICKUP, Fulfilment.DINE_IN)
    return True


def actions_for(order: Order, membership: Membership | None) -> list[str]:
    """Targets the member may apply now (used to render buttons)."""
    if membership is None:
        return []
    return [
        to
        for to in allowed_targets(order)
        if membership.has_perm(TRANSITIONS[(order.status, to)])
        and _driver_scope_ok(order, membership)
    ]


def _driver_scope_ok(order: Order, membership: Membership) -> bool:
    if not membership.has_perm("orders.view_assigned_only"):
        return True
    return order.assigned_driver_id in (None, membership.id)


@dataclass
class TransitionResult:
    order: Order
    applied: bool
    previous_status: str


def transition(
    *,
    business_id: Any,
    order_id: Any,
    to: str,
    source: str,
    membership: Membership | None = None,
    customer: Customer | None = None,
    expected_version: int | None = None,
    reason: str = "",
) -> TransitionResult:
    if to not in S.values:
        raise DomainError("invalid_transition", {"to": to}, 400)
    reason = (reason or "").strip()[:300]
    with transaction.atomic():
        order = (
            Order.objects.select_for_update().filter(business_id=business_id, id=order_id).first()
        )
        if order is None:
            raise NotFoundError()
        if membership is not None and not _driver_scope_ok(order, membership):
            raise NotFoundError()
        previous = order.status
        if order.status == to:
            return TransitionResult(order, False, previous)  # duplicate press: idempotent
        if expected_version is not None and expected_version != order.version:
            raise ConflictError(
                "stale_order_version", {"status": order.status, "version": order.version}
            )
        key = (order.status, to)
        if key not in TRANSITIONS or not _fulfilment_allows(order, *key):
            raise DomainError("invalid_transition", {"from": order.status, "to": to})

        if customer is not None:
            _check_customer_cancel(order, customer, to)
            actor_user = None
        elif membership is not None:
            if membership.business_id != order.business_id:
                raise NotFoundError()
            if not membership.has_perm(TRANSITIONS[key]):
                raise ForbiddenError({"required": TRANSITIONS[key]})
            actor_user = membership.user
        elif source != EventSource.SYSTEM:
            raise ForbiddenError()
        else:
            actor_user = None

        if to in REASON_REQUIRED and not reason and customer is None:
            raise DomainError("reason_required", status_code=400)

        now = timezone.now()
        order.status = to
        order.version += 1
        fields = ["status", "version", "updated_at"]
        ts = _TIMESTAMP.get(S(to))
        if ts:
            setattr(order, ts, now)
            fields.append(ts)
        if to in REASON_REQUIRED:
            order.cancel_reason = reason
            fields.append("cancel_reason")
        if (
            to == S.OUT_FOR_DELIVERY
            and membership is not None
            and membership.has_perm("orders.view_assigned_only")
            and order.assigned_driver_id is None
        ):
            order.assigned_driver = membership
            fields.append("assigned_driver")
        order.save(update_fields=fields)

        if to in (S.CANCELLED, S.REJECTED):
            from apps.orders.services.coupons import release

            _restore_stock(order)
            release(order)
        if to == S.DELIVERED:
            Customer.objects.filter(pk=order.customer_id).update(
                total_spent=F("total_spent") + order.total
            )
        if to in (S.DELIVERED, S.CANCELLED, S.REJECTED):
            from apps.orders.services.loyalty import on_status_change

            on_status_change(order)

        OrderStatusEvent.objects.create(
            business_id=order.business_id,
            order=order,
            from_status=previous,
            to_status=to,
            actor_user=actor_user,
            actor_customer=customer,
            source=source,
            reason=reason,
        )
        enqueue(
            "order.status_changed",
            order.business_id,
            {"order_id": str(order.id), "from": previous, "to": to, "version": order.version},
            dedup_key=f"order:{order.id}:v{order.version}",
        )
        by = (actor_user.full_name or str(actor_user)) if actor_user else ""
        event = {
            "type": "order.status_changed",
            "order_id": str(order.id),
            "number": order.number,
            "status": to,
            "version": order.version,
            "by": by,
        }
        business_id_ = order.business_id
        transaction.on_commit(lambda: broadcast(business_id_, event))
    return TransitionResult(order, True, previous)


def _check_customer_cancel(order: Order, customer: Customer, to: str) -> None:
    if order.customer_id != customer.id:
        raise NotFoundError()
    if to != S.CANCELLED or order.status != S.PENDING:
        raise DomainError("invalid_transition", {"from": order.status, "to": to})
    window = order.business.settings.customer_cancel_window_min
    if timezone.now() > order.placed_at + timedelta(minutes=window):
        raise DomainError("cancel_window_expired")


def customer_can_cancel(order: Order) -> bool:
    if order.status != S.PENDING:
        return False
    window = order.business.settings.customer_cancel_window_min
    return timezone.now() <= order.placed_at + timedelta(minutes=window)


def _restore_stock(order: Order) -> None:
    for item in order.items.select_related("product"):
        if item.product_id and item.product and item.product.track_stock:
            Product.objects.filter(pk=item.product_id).update(
                stock_quantity=F("stock_quantity") + item.quantity
            )


def assign_driver(order: Order, driver: Membership | None, actor: Membership) -> Order:
    if not actor.has_perm("orders.assign_driver"):
        raise ForbiddenError({"required": "orders.assign_driver"})
    if driver is not None and driver.business_id != order.business_id:
        raise NotFoundError()
    order.assigned_driver = driver
    order.save(update_fields=["assigned_driver", "updated_at"])
    return order


def auto_reject_stale(now: Any = None) -> int:
    from apps.businesses.models import BusinessSettings

    now = now or timezone.now()
    count = 0
    for cfg in BusinessSettings.objects.filter(auto_reject_after_min__isnull=False):
        cutoff = now - timedelta(minutes=cfg.auto_reject_after_min or 0)
        for order_id in Order.objects.filter(
            business_id=cfg.business_id, status=S.PENDING, placed_at__lt=cutoff
        ).values_list("id", flat=True):
            try:
                transition(
                    business_id=cfg.business_id,
                    order_id=order_id,
                    to=S.REJECTED,
                    source=EventSource.SYSTEM,
                    reason="auto_rejected_timeout",
                )
                count += 1
            except DomainError:
                continue
    return count
