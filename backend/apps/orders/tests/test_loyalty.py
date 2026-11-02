"""Loyalty points: earn on delivery, redeem at checkout, refund on cancel, ledger = balance."""

import uuid

import pytest
from django.db.models import Sum

from apps.customers.models import Customer, LoyaltyEntry
from apps.orders.models import EventSource
from apps.orders.services import cart as cart_svc
from apps.orders.services import loyalty
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.orders.services.transitions import transition
from core.errors import DomainError
from tests.factories import branch_of, make_business, make_customer, make_product
from tests.helpers import attach_bot, auth, init_data

pytestmark = pytest.mark.django_db


def loyal_shop(**cfg):
    b = make_business()
    s = b.settings
    s.loyalty_enabled = True
    s.loyalty_spend_per_point = cfg.get("spend", 1000)
    s.loyalty_point_value = cfg.get("value", 25)
    s.loyalty_min_redeem = cfg.get("min", 100)
    s.save()
    return b


def checkout(c, price=20000, redeem=0, **kw):
    b = c.business
    cart_svc.add_item(c, branch_of(b), make_product(b, price=price).id, [], 1)
    data = CheckoutInput(
        fulfilment="pickup",
        customer_name="Ali",
        customer_phone="07701234567",
        idempotency_key=uuid.uuid4(),
        redeem_points=redeem,
        **kw,
    )
    return place_order(c, branch_of(b), data)[0]


def move(order, *statuses, reason=""):
    for to in statuses:
        order = transition(
            business_id=order.business_id,
            order_id=order.id,
            to=to,
            source=EventSource.SYSTEM,
            expected_version=order.version,
            reason=reason,
        ).order
    return order


def balance(c) -> int:
    c.refresh_from_db()
    ledger = LoyaltyEntry.objects.filter(customer=c).aggregate(s=Sum("delta"))["s"] or 0
    assert ledger == c.points_balance  # the denormalised balance never drifts from the ledger
    return c.points_balance


def test_delivered_order_earns_once():
    c = make_customer(loyal_shop())
    o = checkout(c, price=20500)
    assert balance(c) == 0  # nothing before delivery
    o = move(o, "confirmed", "preparing", "ready", "delivered")
    assert balance(c) == 20  # 20,500 // 1,000
    loyalty.on_status_change(o)  # replay (e.g. a retried task) does not double-earn
    assert balance(c) == 20


def test_redeem_caps_at_payable_and_refunds_on_cancel():
    c = make_customer(loyal_shop())
    loyalty.adjust(c, 1000, "welcome gift")
    o = checkout(c, price=5000, redeem=1000)
    # 5,000 payable / 25 per point = 200 points used, not 1000
    assert (o.points_redeemed, o.points_discount, o.total) == (200, 5000, 0)
    assert balance(c) == 800
    move(o, "cancelled", reason="customer left")
    assert balance(c) == 1000


def test_redeem_rules():
    c = make_customer(loyal_shop(min=100))
    loyalty.adjust(c, 150, "x")
    with pytest.raises(DomainError) as e:
        checkout(c, redeem=50)
    assert e.value.code == "points_below_minimum"
    with pytest.raises(DomainError) as e:
        checkout(c, redeem=500)
    assert e.value.code == "not_enough_points"
    other = make_customer(make_business())
    with pytest.raises(DomainError) as e:
        checkout(other, redeem=100)
    assert e.value.code == "loyalty_unavailable"


def test_redeemed_order_earns_on_what_was_paid():
    c = make_customer(loyal_shop())
    loyalty.adjust(c, 200, "x")
    o = checkout(c, price=20000, redeem=200)  # 5,000 off → 15,000 paid
    o = move(o, "confirmed", "preparing", "ready", "delivered")
    assert balance(c) == 15


def test_adjust_needs_reason_and_cannot_go_negative():
    c = make_customer(loyal_shop())
    with pytest.raises(DomainError):
        loyalty.adjust(c, 10, " ")
    with pytest.raises(DomainError) as e:
        loyalty.adjust(c, -1, "oops")
    assert e.value.code == "not_enough_points"


def test_mini_app_quote_and_checkout_with_points(api):
    b = loyal_shop()
    attach_bot(b)
    r = api.post(
        f"/api/v1/store/{b.slug}/session", {"init_data": init_data(user_id=55)}, format="json"
    )
    assert r.json()["business"]["loyalty"] == {
        "spend_per_point": 1000,
        "point_value": 25,
        "min_redeem": 100,
    }
    api.credentials(HTTP_AUTHORIZATION=f"Customer {r.json()['token']}")
    c = Customer.objects.get(telegram_user_id=55)
    loyalty.adjust(c, 120, "x")
    assert api.get(f"/api/v1/store/{b.slug}/me").json()["points_balance"] == 120
    base = f"/api/v1/store/{b.slug}"
    p = make_product(b, price=10000)
    api.post(f"{base}/cart/items", {"product_id": str(p.id), "quantity": 1}, format="json")
    body = {
        "fulfilment": "pickup",
        "customer_name": "Ali",
        "customer_phone": "07701234567",
        "redeem_points": 120,
    }
    q = api.post(f"{base}/checkout/quote", body, format="json").json()
    assert (q["points_used"], q["points_discount"], q["total"]) == (120, 3000, 7000)
    r = api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 201, r.json()
    assert r.json()["points_redeemed"] == 120
    assert balance(c) == 0


def test_dashboard_points_history_and_adjust(api):
    from tests.factories import make_member

    b = loyal_shop()
    c = make_customer(b)
    auth(api, b.owner)
    url = f"/api/v1/b/{b.id}/customers/{c.id}/points"
    r = api.post(url, {"delta": 50, "note": "تعويض"}, format="json")
    assert r.status_code == 200, r.json()
    assert r.json()["points_balance"] == 50
    assert [e["reason"] for e in api.get(url).json()] == ["adjust"]
    auth(api, make_member(b, "Cashier").user)
    assert api.post(url, {"delta": 5, "note": "x"}, format="json").status_code == 403
    other = make_business()
    auth(api, other.owner)
    assert api.get(f"/api/v1/b/{other.id}/customers/{c.id}/points").status_code == 404
