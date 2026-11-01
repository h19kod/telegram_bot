import io
import uuid

import pytest
from PIL import Image

from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from tests.factories import (
    branch_of,
    make_business,
    make_customer,
    make_member,
    make_product,
    owner_membership,
)
from tests.helpers import auth

pytestmark = pytest.mark.django_db


def _order(b):
    c = make_customer(b)
    cart_svc.add_item(c, branch_of(b), make_product(b, price=9000).id, [], 1)
    o, _ = place_order(
        c,
        branch_of(b),
        CheckoutInput(
            fulfilment="pickup",
            customer_name="Ali",
            customer_phone="07701234567",
            idempotency_key=uuid.uuid4(),
        ),
    )
    return o


def test_catalog_crud_and_permissions(api):
    b = make_business()
    base = f"/api/v1/b/{b.id}"
    auth(api, b.owner)
    cat = api.post(f"{base}/categories", {"name_ar": "مشروبات"}, format="json").json()
    r = api.post(
        f"{base}/products",
        {"category": cat["id"], "name_ar": "بيبسي", "price": 1000, "compare_at_price": 1500},
        format="json",
    )
    assert r.status_code == 201, r.json()
    pid = r.json()["id"]
    r = api.post(
        f"{base}/products/{pid}/option-groups",
        {"name_ar": "الحجم", "selection_type": "single", "is_required": True},
        format="json",
    )
    gid = r.json()["id"]
    assert r.json()["max_select"] == 1
    r = api.post(
        f"{base}/option-groups/{gid}/options",
        {"name_ar": "كبير", "price_delta": 250},
        format="json",
    )
    assert r.status_code == 201
    assert api.get(f"{base}/products?search=بيبسي").json()["count"] == 1
    r = api.post(
        f"{base}/products",
        {"category": cat["id"], "name_ar": "x", "price": 10, "compare_at_price": 5},
        format="json",
    )
    assert r.status_code == 400

    kitchen = make_member(b, "Kitchen")
    auth(api, kitchen.user)
    assert api.get(f"{base}/products").status_code == 200
    r = api.patch(f"{base}/products/{pid}", {"name_ar": "y"}, format="json")
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required"] == ["catalog.edit"]

    # Manager may edit catalog; a custom role without edit_prices cannot change prices.
    auth(api, b.owner)
    role = api.post(
        f"{base}/roles",
        {"name": "Editor", "permissions": ["catalog.view", "catalog.edit"]},
        format="json",
    ).json()
    editor = make_member(b, "Kitchen")
    api.patch(f"{base}/members/{editor.id}", {"role": role["id"]}, format="json")
    auth(api, editor.user)
    assert (
        api.patch(f"{base}/products/{pid}", {"name_ar": "بيبسي كولا"}, format="json").status_code
        == 200
    )
    assert api.patch(f"{base}/products/{pid}", {"price": 1}, format="json").status_code == 403

    auth(api, b.owner)
    assert api.delete(f"{base}/products/{pid}").status_code == 204
    assert api.get(f"{base}/products/{pid}").status_code == 404  # archived


def test_image_upload_validation(api):
    b = make_business()
    p = make_product(b)
    auth(api, b.owner)
    url = f"/api/v1/b/{b.id}/products/{p.id}/images"
    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), "red").save(buf, format="JPEG")
    buf.seek(0)
    buf.name = "x.jpg"
    r = api.post(url, {"image": buf}, format="multipart")
    assert r.status_code == 201, r.json()
    assert r.json()["image"].endswith(".webp")
    assert r.json()["width"] == 1200
    fake = io.BytesIO(b"<?php echo 'x'; ?>")
    fake.name = "x.jpg"
    r = api.post(url, {"image": fake}, format="multipart")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_image"


def test_orders_dashboard_flow_and_pii_masking(api):
    b = make_business()
    order = _order(b)
    base = f"/api/v1/b/{b.id}"
    auth(api, b.owner)
    r = api.get(f"{base}/orders?status=pending")
    assert r.json()["count"] == 1
    assert r.json()["results"][0]["customer_phone"] == "+9647701234567"
    assert api.get(f"{base}/orders?search=1001").json()["count"] == 1
    assert api.get(f"{base}/orders?search=07701234567").json()["count"] == 1
    d = api.get(f"{base}/orders/{order.id}").json()
    assert set(d["allowed_actions"]) == {"confirmed", "rejected", "cancelled"}
    r = api.post(
        f"{base}/orders/{order.id}/transition",
        {"to": "confirmed", "expected_version": 1},
        format="json",
    )
    assert r.json()["status"] == "confirmed"
    r = api.post(
        f"{base}/orders/{order.id}/transition",
        {"to": "rejected", "expected_version": 1, "reason": "x"},
        format="json",
    )
    assert r.status_code == 409

    kitchen = make_member(b, "Kitchen")
    auth(api, kitchen.user)
    row = api.get(f"{base}/orders").json()["results"][0]
    assert "*" in row["customer_phone"]


def test_delivery_staff_sees_only_assigned(api):
    b = make_business()
    o1, o2 = _order(b), _order(b)
    driver = make_member(b, "Delivery")
    auth(api, b.owner)
    r = api.post(
        f"/api/v1/b/{b.id}/orders/{o1.id}/assign-driver",
        {"driver_id": str(driver.id)},
        format="json",
    )
    assert r.status_code == 200
    auth(api, driver.user)
    ids = [o["id"] for o in api.get(f"/api/v1/b/{b.id}/orders").json()["results"]]
    assert ids == [str(o1.id)]
    assert api.get(f"/api/v1/b/{b.id}/orders/{o2.id}").status_code == 404


def test_analytics_and_export(api):
    from apps.orders.models import EventSource
    from apps.orders.services.transitions import transition

    b = make_business(plan="pro")
    owner = owner_membership(b)
    o = _order(b)
    for to in ("confirmed", "preparing", "ready", "delivered"):
        transition(
            business_id=b.id, order_id=o.id, to=to, source=EventSource.DASHBOARD, membership=owner
        )
    auth(api, b.owner)
    ov = api.get(f"/api/v1/b/{b.id}/analytics/overview").json()
    assert ov["total_sales"] == 9000
    assert ov["completed_orders"] == 1
    sales = api.get(f"/api/v1/b/{b.id}/analytics/sales").json()
    assert sum(x["sales"] for x in sales) == 9000
    top = api.get(f"/api/v1/b/{b.id}/analytics/top-products").json()
    assert top[0]["quantity"] == 1
    r = api.get(f"/api/v1/b/{b.id}/orders/export?format_type=csv")
    assert r.status_code == 200
    assert "1001" in r.content.decode("utf-8-sig")
    assert api.get(f"/api/v1/b/{b.id}/orders/export?format_type=xlsx").status_code == 200


def test_export_gated_by_plan(api):
    b = make_business(plan="free")
    auth(api, b.owner)
    r = api.get(f"/api/v1/b/{b.id}/orders/export")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "feature_not_available"


def test_owner_role_protection(api):
    b = make_business()
    manager = make_member(b, "Manager")
    owner = owner_membership(b)
    auth(api, manager.user)
    r = api.delete(f"/api/v1/b/{b.id}/members/{owner.id}")
    assert r.status_code == 403
    auth(api, b.owner)
    r = api.delete(f"/api/v1/b/{b.id}/members/{owner.id}")
    assert r.json()["error"]["code"] == "last_owner"


def test_onboarding_creates_business(api):
    from apps.accounts.models import User

    u = User.objects.create_user(email="new@x.com", password="Very-Strong-Pass-1")
    auth(api, u)
    r = api.post(
        "/api/v1/businesses", {"slug": "burger_house", "name_ar": "بيت البرغر"}, format="json"
    )
    assert r.status_code == 201
    m = api.get("/api/v1/auth/me/memberships").json()
    assert m[0]["business_slug"] == "burger_house"
    assert m[0]["is_owner"] is True
    assert (
        api.post(
            "/api/v1/businesses", {"slug": "burger_house", "name_ar": "x"}, format="json"
        ).status_code
        == 400
    )


def test_subscription_endpoint(api):
    b = make_business(plan="basic")
    auth(api, b.owner)
    d = api.get(f"/api/v1/b/{b.id}/subscription").json()
    assert d["subscription"]["plan"] == "basic"
    assert d["entitlements"]["max_products"] == 100
    assert d["usage"]["max_staff"] == 1
