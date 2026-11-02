"""Multi-branch: the customer picks a branch; cart, zones and orders follow it; staff scoping."""

import uuid

import pytest

from apps.businesses.models import Branch
from apps.businesses.services import choose_branch, customer_branch
from apps.customers.models import Customer
from apps.delivery.models import DeliveryZone
from apps.orders.models import Order
from core.errors import NotFoundError
from tests.factories import branch_of, make_business, make_customer, make_member, make_product
from tests.helpers import attach_bot, auth, init_data, internal

pytestmark = pytest.mark.django_db


def two_branches():
    b = make_business(plan="pro")
    second = Branch.objects.create(business=b, name_ar="فرع المنصور", name_en="Mansour")
    return b, branch_of(b), second


def test_choice_falls_back_to_default_when_inactive_or_foreign():
    b, main, second = two_branches()
    c = make_customer(b)
    assert customer_branch(c) == main
    choose_branch(c, second.id)
    assert customer_branch(c) == second
    Branch.objects.filter(pk=second.pk).update(is_active=False)
    assert customer_branch(c) == main
    with pytest.raises(NotFoundError):
        choose_branch(c, second.id)  # inactive
    _other_b, other_main, _ = two_branches()
    with pytest.raises(NotFoundError):
        choose_branch(c, other_main.id)  # another tenant's branch


def test_mini_app_picks_branch_and_orders_from_it(api):
    b, main, second = two_branches()
    attach_bot(b)
    DeliveryZone.objects.create(business=b, branch=second, name_ar="المنصور", fee=1000)
    r = api.post(
        f"/api/v1/store/{b.slug}/session", {"init_data": init_data(user_id=8)}, format="json"
    )
    info = r.json()["business"]
    assert info["branch"]["id"] == str(main.id)
    assert [x["id"] for x in info["branches"]] == [str(main.id), str(second.id)]
    api.credentials(HTTP_AUTHORIZATION=f"Customer {r.json()['token']}")
    base = f"/api/v1/store/{b.slug}"
    assert api.get(f"{base}/delivery-zones").json() == []

    assert api.patch(f"{base}/me", {"branch_id": str(second.id)}, format="json").status_code == 200
    assert api.get(f"{base}/").json()["branch"]["name"] == "فرع المنصور"
    assert [z["name"] for z in api.get(f"{base}/delivery-zones").json()] == ["المنصور"]
    p = make_product(b, price=5000)
    api.post(f"{base}/cart/items", {"product_id": str(p.id), "quantity": 1}, format="json")
    body = {"fulfilment": "pickup", "customer_name": "Ali", "customer_phone": "07701234567"}
    r = api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 201, r.json()
    assert Order.objects.get(id=r.json()["id"]).branch == second

    foreign = branch_of(make_business())
    r = api.patch(f"{base}/me", {"branch_id": str(foreign.id)}, format="json")
    assert r.status_code == 404


def test_bot_branch_choice_and_zones(api):
    b, _main, second = two_branches()
    bot = attach_bot(b)
    DeliveryZone.objects.create(business=b, branch=second, name_ar="المنصور", fee=1000)
    internal(api, "POST", f"/internal/v1/bots/{bot.id}/session", {"user": {"id": 5}})
    c = f"/internal/v1/bots/{bot.id}/customers/5"
    assert internal(api, "GET", f"{c}/zones").json() == []
    r = internal(api, "PATCH", f"{c}/me", {"branch_id": str(second.id)})
    assert r.json()["branch_id"] == str(second.id)
    assert [z["name"] for z in internal(api, "GET", f"{c}/zones").json()] == ["المنصور"]
    r = internal(api, "POST", f"/internal/v1/bots/{bot.id}/session", {"user": {"id": 5}})
    assert r.json()["business"]["branch"]["id"] == str(second.id)
    assert Customer.objects.get(telegram_user_id=5).preferred_branch == second


def test_staff_tied_to_a_branch_only_sees_its_orders(api):
    from apps.orders.services import cart as cart_svc
    from apps.orders.services.checkout import CheckoutInput, place_order

    b, main, second = two_branches()
    ids = {}
    for br in (main, second):
        c = make_customer(b)
        cart_svc.add_item(c, br, make_product(b, price=5000).id, [], 1)
        o, _ = place_order(
            c,
            br,
            CheckoutInput(
                fulfilment="pickup",
                customer_name="Ali",
                customer_phone="07701234567",
                idempotency_key=uuid.uuid4(),
            ),
        )
        ids[br.id] = str(o.id)

    auth(api, b.owner)
    cashier = make_member(b, "Cashier")
    url = f"/api/v1/b/{b.id}/members/{cashier.id}"
    r = api.patch(url, {"branches": [str(second.id)]}, format="json")
    assert r.status_code == 200, r.json()
    assert r.json()["branches"] == [str(second.id)]
    foreign = branch_of(make_business())
    assert api.patch(url, {"branches": [str(foreign.id)]}, format="json").status_code == 400
    rows = api.get(f"/api/v1/b/{b.id}/orders?branch={main.id}").json()["results"]
    assert [x["id"] for x in rows] == [ids[main.id]]

    auth(api, cashier.user)
    rows = api.get(f"/api/v1/b/{b.id}/orders").json()["results"]
    assert [x["id"] for x in rows] == [ids[second.id]]
    assert api.get(f"/api/v1/b/{b.id}/orders/{ids[main.id]}").status_code == 404
