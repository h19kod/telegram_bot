import uuid

import pytest

from apps.accounts.models import User
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from core.errors import DomainError
from tests.factories import branch_of, make_business, make_customer, make_product
from tests.helpers import auth

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin(settings):
    settings.PLATFORM_ADMIN_REQUIRE_2FA = True
    u = User.objects.create_user(
        email="root@x.com", password="Very-Strong-Pass-1", is_platform_admin=True
    )
    u.totp_enabled = True
    u.save()
    return u


def test_requires_platform_admin_with_2fa(api, admin):
    normal = User.objects.create_user(email="n@x.com", password="Very-Strong-Pass-1")
    auth(api, normal)
    assert api.get("/api/v1/platform/businesses").status_code == 403
    admin.totp_enabled = False
    admin.save()
    auth(api, admin)
    assert api.get("/api/v1/platform/businesses").status_code == 403


def test_platform_business_lifecycle(api, admin):
    auth(api, admin)
    r = api.post(
        "/api/v1/platform/businesses",
        {"owner_email": "boss@shop.iq", "slug": "kebab", "name_ar": "كباب", "plan": "pro"},
        format="json",
    )
    assert r.status_code == 201, r.json()
    bid = r.json()["id"]
    assert r.json()["plan"] == "pro"

    r = api.post(f"/api/v1/platform/businesses/{bid}/suspend", {"reason": "unpaid"}, format="json")
    assert r.json()["status"] == "suspended"

    from apps.businesses.models import Business

    b = Business.objects.get(id=bid)
    c = make_customer(b)
    cart_svc.add_item(c, branch_of(b), make_product(b).id, [], 1)
    with pytest.raises(DomainError) as exc:
        place_order(
            c,
            branch_of(b),
            CheckoutInput(
                fulfilment="pickup",
                customer_name="Ali",
                customer_phone="07701234567",
                idempotency_key=uuid.uuid4(),
            ),
        )
    assert exc.value.code == "business_unavailable"

    api.post(f"/api/v1/platform/businesses/{bid}/activate")
    r = api.put(
        f"/api/v1/platform/businesses/{bid}/overrides",
        {"feature": "max_products", "value": 9999, "reason": "deal"},
        format="json",
    )
    assert r.status_code == 200
    usage = api.get(f"/api/v1/platform/businesses/{bid}/usage").json()
    assert usage["entitlements"]["max_products"] == 9999
    r = api.put(
        f"/api/v1/platform/businesses/{bid}/overrides",
        {"feature": "ai_assistant", "value": 5},
        format="json",
    )
    assert r.status_code == 400

    subs = api.post(
        f"/api/v1/platform/businesses/{bid}/subscriptions",
        {"plan": "basic", "months": 1},
        format="json",
    ).json()
    sub_id = subs[0]["id"]
    r = api.post(
        f"/api/v1/platform/subscriptions/{sub_id}/payments",
        {
            "amount": 25000,
            "currency": "IQD",
            "method": "zaincash",
            "months": 2,
            "paid_at": "2026-11-01T10:00:00Z",
        },
        format="json",
    )
    assert r.status_code == 201

    stats = api.get("/api/v1/platform/stats").json()
    assert stats["businesses_total"] >= 1
    assert api.get("/api/v1/platform/health").json()["components"]["database"] == "ok"
    log = api.get("/api/v1/platform/audit-log").json()
    assert {e["action"] for e in log} >= {"platform.business_suspend", "platform.payment_record"}


def test_plan_entitlements_editor(api, admin):
    auth(api, admin)
    plans = api.get("/api/v1/platform/plans").json()
    free = next(p for p in plans if p["code"] == "free")
    b = make_business(plan="free")
    r = api.put(
        f"/api/v1/platform/plans/{free['id']}/entitlements", {"max_products": 3}, format="json"
    )
    assert r.json()["entitlements"]["max_products"] == 3
    from apps.subscriptions.services import value

    assert value(b.id, "max_products") == 3
    r = api.put(f"/api/v1/platform/plans/{free['id']}/entitlements", {"nope": 1}, format="json")
    assert r.status_code == 400


def test_support_ticket_roundtrip(api, admin):
    b = make_business()
    auth(api, b.owner)
    t = api.post(
        f"/api/v1/b/{b.id}/support-tickets",
        {"subject": "مشكلة", "body": "البوت ما يرد"},
        format="json",
    ).json()
    auth(api, admin)
    r = api.post(
        f"/api/v1/platform/support-tickets/{t['id']}/messages",
        {"body": "نشتغل عليها"},
        format="json",
    )
    assert r.status_code == 201
    auth(api, b.owner)
    msgs = api.get(f"/api/v1/b/{b.id}/support-tickets/{t['id']}").json()["messages"]
    assert [m["is_from_platform"] for m in msgs] == [False, True]
