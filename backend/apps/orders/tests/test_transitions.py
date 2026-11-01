import uuid
from datetime import timedelta

import pytest
import time_machine
from django.utils import timezone

from apps.notifications.models import NotificationOutbox
from apps.orders.models import EventSource, OrderStatus
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.orders.services.transitions import actions_for, auto_reject_stale, transition
from core.errors import ConflictError, DomainError, ForbiddenError, NotFoundError
from tests.factories import (
    branch_of,
    make_business,
    make_customer,
    make_member,
    make_product,
    make_zone,
    owner_membership,
)

pytestmark = pytest.mark.django_db
S = OrderStatus


def _order(b, fulfilment="delivery", stock=None):
    branch, customer = branch_of(b), make_customer(b)
    zone = make_zone(b)
    kw = {"track_stock": True, "stock_quantity": stock} if stock is not None else {}
    p = make_product(b, **kw)
    cart_svc.add_item(customer, branch, p.id, [], 1)
    data = CheckoutInput(
        fulfilment=fulfilment,
        customer_name="Ali",
        customer_phone="07701234567",
        idempotency_key=uuid.uuid4(),
        zone_id=zone.id,
        address_area="Karrada",
        address_landmark="near park",
    )
    order, _ = place_order(customer, branch, data)
    return order, p


def go(order, to, member, **kw):
    return transition(
        business_id=order.business_id,
        order_id=order.id,
        to=to,
        source=EventSource.DASHBOARD,
        membership=member,
        **kw,
    )


def test_full_delivery_lifecycle():
    b = make_business()
    owner = owner_membership(b)
    order, _ = _order(b)
    for to in (S.CONFIRMED, S.PREPARING, S.READY, S.OUT_FOR_DELIVERY, S.DELIVERED):
        res = go(order, to, owner)
        assert res.applied
    order.refresh_from_db()
    assert order.status == S.DELIVERED
    assert order.version == 6
    assert order.delivered_at and order.confirmed_at
    assert order.events.count() == 6
    assert NotificationOutbox.objects.filter(event_type="order.status_changed").count() == 5
    order.customer.refresh_from_db()
    assert order.customer.total_spent == order.total


def test_pickup_skips_out_for_delivery():
    b = make_business()
    owner = owner_membership(b)
    order, _ = _order(b, fulfilment="pickup")
    for to in (S.CONFIRMED, S.PREPARING, S.READY):
        go(order, to, owner)
    with pytest.raises(DomainError):
        go(order, S.OUT_FOR_DELIVERY, owner)
    assert go(order, S.DELIVERED, owner).applied


def test_invalid_transition():
    b = make_business()
    order, _ = _order(b)
    with pytest.raises(DomainError) as exc:
        go(order, S.DELIVERED, owner_membership(b))
    assert exc.value.code == "invalid_transition"


def test_duplicate_press_is_idempotent():
    b = make_business()
    owner = owner_membership(b)
    order, _ = _order(b)
    assert go(order, S.CONFIRMED, owner, expected_version=1).applied
    again = go(order, S.CONFIRMED, owner, expected_version=1)
    assert not again.applied
    assert again.order.version == 2
    assert order.events.count() == 2


def test_stale_button_conflict():
    b = make_business()
    owner = owner_membership(b)
    order, _ = _order(b)
    go(order, S.CONFIRMED, owner, expected_version=1)
    with pytest.raises(ConflictError) as exc:
        go(order, S.REJECTED, owner, expected_version=1, reason="late")
    assert exc.value.details["status"] == S.CONFIRMED


def test_role_permissions():
    b = make_business()
    kitchen = make_member(b, "Kitchen")
    cashier = make_member(b, "Cashier")
    order, _ = _order(b)
    with pytest.raises(ForbiddenError):
        go(order, S.CONFIRMED, kitchen)
    go(order, S.CONFIRMED, cashier)
    go(order, S.PREPARING, kitchen)
    with pytest.raises(ForbiddenError):
        go(order, S.CANCELLED, cashier, reason="x")
    order.refresh_from_db()
    assert S.READY in actions_for(order, kitchen)
    assert S.CANCELLED not in actions_for(order, kitchen)


def test_delivery_staff_scope_and_self_assign():
    b = make_business()
    owner = owner_membership(b)
    d1, d2 = make_member(b, "Delivery"), make_member(b, "Delivery")
    order, _ = _order(b)
    for to in (S.CONFIRMED, S.PREPARING, S.READY):
        go(order, to, owner)
    go(order, S.OUT_FOR_DELIVERY, d1)
    order.refresh_from_db()
    assert order.assigned_driver_id == d1.id
    with pytest.raises(NotFoundError):
        go(order, S.DELIVERED, d2)
    assert go(order, S.DELIVERED, d1).applied


def test_member_of_other_business_cannot_transition():
    a, b = make_business(), make_business()
    order, _ = _order(a)
    with pytest.raises(NotFoundError):
        transition(
            business_id=b.id,
            order_id=order.id,
            to=S.CONFIRMED,
            source=EventSource.DASHBOARD,
            membership=owner_membership(b),
        )
    with pytest.raises(NotFoundError):
        transition(
            business_id=a.id,
            order_id=order.id,
            to=S.CONFIRMED,
            source=EventSource.DASHBOARD,
            membership=owner_membership(b),
        )


def test_reject_requires_reason_and_restores_stock():
    b = make_business()
    owner = owner_membership(b)
    order, product = _order(b, stock=5)
    product.refresh_from_db()
    assert product.stock_quantity == 4
    with pytest.raises(DomainError) as exc:
        go(order, S.REJECTED, owner)
    assert exc.value.code == "reason_required"
    go(order, S.REJECTED, owner, reason="مسكرين")
    product.refresh_from_db()
    assert product.stock_quantity == 5


def test_customer_cancel_window():
    b = make_business()
    order, _ = _order(b)
    res = transition(
        business_id=b.id,
        order_id=order.id,
        to=S.CANCELLED,
        source=EventSource.CUSTOMER,
        customer=order.customer,
    )
    assert res.applied

    order2, _ = _order(b)
    with (
        time_machine.travel(timezone.now() + timedelta(minutes=10)),
        pytest.raises(DomainError) as exc,
    ):
        transition(
            business_id=b.id,
            order_id=order2.id,
            to=S.CANCELLED,
            source=EventSource.CUSTOMER,
            customer=order2.customer,
        )
    assert exc.value.code == "cancel_window_expired"


def test_customer_cannot_cancel_others_order():
    b = make_business()
    order, _ = _order(b)
    stranger = make_customer(b)
    with pytest.raises(NotFoundError):
        transition(
            business_id=b.id,
            order_id=order.id,
            to=S.CANCELLED,
            source=EventSource.CUSTOMER,
            customer=stranger,
        )


def test_auto_reject():
    b = make_business()
    b.settings.auto_reject_after_min = 15
    b.settings.save()
    order, _ = _order(b)
    assert auto_reject_stale(timezone.now() + timedelta(minutes=16)) == 1
    order.refresh_from_db()
    assert order.status == S.REJECTED
