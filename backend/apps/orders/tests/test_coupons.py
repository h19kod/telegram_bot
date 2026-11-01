import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import Coupon, EventSource
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order, quote
from apps.orders.services.transitions import transition
from core.errors import DomainError
from tests.factories import branch_of, make_business, make_customer, make_product, owner_membership
from tests.helpers import auth

pytestmark = pytest.mark.django_db


def setup(plan="pro", **coupon):
    b = make_business(plan=plan)
    c = make_customer(b)
    cart_svc.add_item(c, branch_of(b), make_product(b, price=10000).id, [], 2)
    coupon.setdefault("code", "SAVE10")
    coupon.setdefault("kind", "percent")
    coupon.setdefault("value", 10)
    cp = Coupon.objects.create(business=b, **coupon)
    return b, c, cp


def pickup(code, key=None):
    return CheckoutInput(
        fulfilment="pickup",
        customer_name="Ali",
        customer_phone="07701234567",
        idempotency_key=key or uuid.uuid4(),
        coupon_code=code,
    )


def test_percent_coupon_applied_and_counted():
    b, c, cp = setup()
    q = quote(c, branch_of(b), pickup(" save10 "))
    assert (q.subtotal, q.discount_total, q.total) == (20000, 2000, 18000)
    order, _ = place_order(c, branch_of(b), pickup("SAVE10"))
    assert order.discount_total == 2000
    assert order.total == 18000
    cp.refresh_from_db()
    assert cp.used_count == 1


def test_fixed_coupon_capped_by_subtotal_and_max_discount():
    b, c, cp = setup(code="BIG", kind="fixed", value=999999)
    assert quote(c, branch_of(b), pickup("BIG")).total == 0
    cp.kind, cp.value, cp.max_discount = "percent", 50, 3000
    cp.save()
    assert quote(c, branch_of(b), pickup("BIG")).discount_total == 3000


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"is_active": False}, "coupon_invalid"),
        ({"ends_at": "past"}, "coupon_expired"),
        ({"starts_at": "future"}, "coupon_expired"),
        ({"min_order": 50000}, "coupon_min_order"),
        ({"usage_limit": 0}, "coupon_exhausted"),
    ],
)
def test_coupon_rules(change, code):
    b, c, cp = setup()
    now = timezone.now()
    for k, v in change.items():
        setattr(
            cp,
            k,
            now - timedelta(days=1)
            if v == "past"
            else now + timedelta(days=1)
            if v == "future"
            else v,
        )
    cp.save()
    with pytest.raises(DomainError) as exc:
        place_order(c, branch_of(b), pickup("SAVE10"))
    assert exc.value.code == code


def test_per_customer_limit_and_release_on_cancel():
    b, c, cp = setup()
    order, _ = place_order(c, branch_of(b), pickup("SAVE10"))
    cart_svc.add_item(c, branch_of(b), make_product(b, price=5000).id, [], 1)
    with pytest.raises(DomainError) as exc:
        place_order(c, branch_of(b), pickup("SAVE10"))
    assert exc.value.code == "coupon_exhausted"
    transition(
        business_id=b.id,
        order_id=order.id,
        to="cancelled",
        source=EventSource.DASHBOARD,
        membership=owner_membership(b),
        reason="test",
    )
    cp.refresh_from_db()
    assert cp.used_count == 0
    order2, _ = place_order(c, branch_of(b), pickup("SAVE10"))
    assert order2.discount_total == 500


def test_coupon_of_other_business_rejected():
    b, c, _ = setup()
    Coupon.objects.create(business=make_business(), code="OTHER", kind="fixed", value=1000)
    with pytest.raises(DomainError) as exc:
        quote(c, branch_of(b), pickup("OTHER"))
    assert exc.value.code == "coupon_invalid"


def test_coupons_require_plan_feature(api):
    b, c, _ = setup(plan="free")
    with pytest.raises(DomainError) as exc:
        quote(c, branch_of(b), pickup("SAVE10"))
    assert exc.value.code == "feature_not_available"
    auth(api, b.owner)
    r = api.post(
        f"/api/v1/b/{b.id}/coupons", {"code": "NEW1", "kind": "fixed", "value": 500}, format="json"
    )
    assert r.status_code == 403


def test_dashboard_coupon_crud(api):
    b = make_business(plan="pro")
    auth(api, b.owner)
    url = f"/api/v1/b/{b.id}/coupons"
    r = api.post(url, {"code": "ramadan 25", "kind": "percent", "value": 25}, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["code"] == "RAMADAN25"
    assert (
        api.post(url, {"code": "X", "kind": "percent", "value": 150}, format="json").status_code
        == 400
    )
    assert (
        api.post(url, {"code": "RAMADAN25", "kind": "fixed", "value": 1}, format="json").status_code
        == 400
    )
    assert len(api.get(url).json()) == 1
