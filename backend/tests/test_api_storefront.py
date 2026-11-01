import uuid

import pytest

from apps.orders.models import Order
from tests.factories import make_business, make_option, make_option_group, make_product, make_zone
from tests.helpers import attach_bot, init_data

pytestmark = pytest.mark.django_db


@pytest.fixture
def store(api):
    b = make_business()
    attach_bot(b)
    return b


def session(api, b, **kw):
    r = api.post(f"/api/v1/store/{b.slug}/session", {"init_data": init_data(**kw)}, format="json")
    assert r.status_code == 200, r.json()
    api.credentials(HTTP_AUTHORIZATION=f"Customer {r.json()['token']}")
    return r.json()


def test_session_rejects_forged_init_data(api, store):
    r = api.post(
        f"/api/v1/store/{store.slug}/session",
        {"init_data": init_data(token="999:forged-token-abcdefghijklmnopqrstuvw")},
        format="json",
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_init_data"


def test_full_mini_app_flow(api, store):
    data = session(api, store, user_id=777, first_name="Zaid")
    assert data["business"]["slug"] == store.slug
    p = make_product(store, price=6000, name_ar="شاورمة", name_en="Shawarma")
    g = make_option_group(p, is_required=True, min_select=1)
    big = make_option(g, name_ar="كبير", price_delta=1000)
    zone = make_zone(store, fee=1500)
    base = f"/api/v1/store/{store.slug}"

    r = api.get(f"{base}/products?search=شاورمه")  # ة/ه normalisation
    assert [x["id"] for x in r.json()["results"]] == [str(p.id)]
    assert api.get(f"{base}/products/{p.id}").json()["option_groups"][0]["min_select"] == 1

    # Client-sent price is ignored entirely.
    r = api.post(
        f"{base}/cart/items",
        {"product_id": str(p.id), "option_ids": [str(big.id)], "quantity": 2, "price": 1},
        format="json",
    )
    assert r.status_code == 201
    assert r.json()["subtotal"] == 14000

    body = {
        "fulfilment": "delivery",
        "customer_name": "زيد",
        "customer_phone": "07801112233",
        "zone_id": str(zone.id),
        "address_area": "المنصور",
        "address_landmark": "قرب المول",
        "total": 1,
    }
    q = api.post(f"{base}/checkout/quote", body, format="json").json()
    assert q["total"] == 15500

    assert api.post(f"{base}/checkout", body, format="json").status_code == 400  # no key
    key = str(uuid.uuid4())
    r1 = api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    r2 = api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["total"] == 15500
    assert Order.objects.get().channel == "mini_app"

    orders = api.get(f"{base}/orders").json()
    assert len(orders) == 1
    assert orders[0]["can_cancel"] is True
    r = api.post(f"{base}/orders/{orders[0]['id']}/cancel", {}, format="json")
    assert r.json()["status"] == "cancelled"


def test_customer_token_bound_to_business(api, store):
    other = make_business()
    attach_bot(other, token="7000000002:AAotherTOKENabcdefghijklmnopqrstuvwx")
    session(api, store)
    assert api.get(f"/api/v1/store/{other.slug}/cart").status_code == 404


def test_customer_cannot_see_other_customers_orders(api, store):
    session(api, store, user_id=1)
    p = make_product(store)
    base = f"/api/v1/store/{store.slug}"
    api.post(f"{base}/cart/items", {"product_id": str(p.id)}, format="json")
    order = api.post(
        f"{base}/checkout",
        {"fulfilment": "pickup", "customer_name": "Ali", "customer_phone": "07701234567"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    ).json()
    session(api, store, user_id=2)
    assert api.get(f"{base}/orders/{order['id']}").status_code == 404
    assert api.post(f"{base}/orders/{order['id']}/cancel").status_code == 404


def test_tampered_customer_token(api, store):
    api.credentials(HTTP_AUTHORIZATION="Customer forged.token.value")
    assert api.get(f"/api/v1/store/{store.slug}/cart").status_code == 401


def test_english_localisation(api, store):
    session(api, store)
    make_product(store, name_ar="برغر", name_en="Burger")
    r = api.get(f"/api/v1/store/{store.slug}/products", HTTP_ACCEPT_LANGUAGE="en")
    assert r.json()["results"][0]["name"] == "Burger"
    r = api.get(f"/api/v1/store/{store.slug}/products", HTTP_ACCEPT_LANGUAGE="ar")
    assert r.json()["results"][0]["name"] == "برغر"
