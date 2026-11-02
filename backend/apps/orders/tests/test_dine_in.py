"""Dine-in: orders from a table QR, no phone needed, served from `ready`."""

import uuid

import pytest

from apps.businesses.services import store_link
from apps.orders.models import Order
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.orders.services.transitions import allowed_targets
from core.errors import DomainError
from tests.factories import branch_of, make_business, make_customer, make_product
from tests.helpers import attach_bot, auth

pytestmark = pytest.mark.django_db


def dine_in_shop():
    b = make_business()
    br = branch_of(b)
    br.accepts_dine_in = True
    br.save()
    return b


def place(customer, **kw):
    b = customer.business
    cart_svc.add_item(customer, branch_of(b), make_product(b, price=5000).id, [], 1)
    data = {
        "fulfilment": "dine_in",
        "customer_name": "Ali",
        "customer_phone": "",
        "table_label": "12",
        "idempotency_key": uuid.uuid4(),
        **kw,
    }
    return place_order(customer, branch_of(b), CheckoutInput(**data))[0]


def test_table_order_without_phone_even_when_verification_is_on(settings):
    settings.WHATSAPP_PROVIDER = "memory"  # verification required for delivery/pickup
    c = make_customer(dine_in_shop(), phone="+9647701234567")
    o = place(c)
    assert (o.fulfilment, o.table_label, o.customer_phone, o.delivery_fee) == (
        "dine_in",
        "12",
        "",
        0,
    )
    assert o.payment_method == "pay_at_pickup"
    from apps.notifications.render import staff_order_text

    text = staff_order_text(o)
    assert "طاولة 12" in text
    assert "📞" not in text
    c.refresh_from_db()
    assert c.phone == "+9647701234567"  # an order without phone keeps the known number
    Order.objects.filter(pk=o.pk).update(status="ready")
    o.refresh_from_db()
    assert allowed_targets(o) == ["delivered", "cancelled"]  # served, never "out for delivery"


def test_dine_in_needs_branch_switch_and_valid_table():
    c = make_customer(make_business())
    with pytest.raises(DomainError) as e:
        place(c)
    assert e.value.code == "fulfilment_unavailable"
    c = make_customer(dine_in_shop())
    for bad in ("", "1 2", "<b>", "12345678901"):
        with pytest.raises(DomainError) as e:
            place(c, table_label=bad)
        assert e.value.code == "table_required"


def test_dine_in_with_a_phone_validates_it():
    c = make_customer(dine_in_shop())
    with pytest.raises(DomainError) as e:
        place(c, customer_phone="123")
    assert e.value.code == "invalid_phone"
    assert place(c, customer_phone="07701234567").customer_phone == "+9647701234567"


def test_table_links_and_qr(api):
    b = dine_in_shop()
    attach_bot(b)
    assert store_link(b, "7") == f"https://t.me/{b.slug}_bot?start=-t7"
    auth(api, b.owner)
    r = api.get(f"/api/v1/b/{b.id}/qr?table=7&type=png")
    assert r.status_code == 200
    assert "table-7" in r["Content-Disposition"]
    assert api.get(f"/api/v1/b/{b.id}/qr?table=a b").status_code == 400


def test_storefront_exposes_dine_in_and_table(api):
    from tests.helpers import init_data

    b = dine_in_shop()
    attach_bot(b)
    r = api.post(f"/api/v1/store/{b.slug}/session", {"init_data": init_data()}, format="json")
    assert r.json()["business"]["accepts_dine_in"] is True
    api.credentials(HTTP_AUTHORIZATION=f"Customer {r.json()['token']}")
    base = f"/api/v1/store/{b.slug}"
    p = make_product(b, price=5000)
    api.post(f"{base}/cart/items", {"product_id": str(p.id), "quantity": 1}, format="json")
    body = {
        "fulfilment": "dine_in",
        "customer_name": "Ali",
        "customer_phone": "",
        "table_label": "A3",
    }
    r = api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 201, r.json()
    assert r.json()["table_label"] == "A3"
