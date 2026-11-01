import uuid

import pytest
import respx
from httpx import Response

from apps.accounts.services import create_link_code
from apps.notifications.services import drain
from apps.orders.models import OrderNotificationMessage
from tests.factories import make_business, make_member, make_product, owner_membership
from tests.helpers import BOT_TOKEN, attach_bot, internal

pytestmark = pytest.mark.django_db
TG = "https://telegram.test"


def test_rejects_unsigned_and_replayed_requests(api):
    assert api.get("/internal/v1/bots").status_code == 401
    import json

    from django.conf import settings

    from apps.internal_api.auth import make_header

    hdr = make_header(settings.INTERNAL_API_SECRET, "GET", "/internal/v1/bots", b"", "nonce1234")
    assert api.get("/internal/v1/bots", HTTP_X_SERVICE_AUTH=hdr).status_code == 200
    assert api.get("/internal/v1/bots", HTTP_X_SERVICE_AUTH=hdr).status_code == 401  # replay
    bad = make_header("wrong", "GET", "/internal/v1/bots", b"", "nonce5678")
    assert api.get("/internal/v1/bots", HTTP_X_SERVICE_AUTH=bad).status_code == 401
    _ = json


@respx.mock
def test_bot_order_flow_with_staff_buttons(api):
    sent = []

    def capture(request):
        import json

        sent.append(json.loads(request.content))
        return Response(200, json={"ok": True, "result": {"message_id": len(sent) + 100}})

    respx.post(f"{TG}/bot{BOT_TOKEN}/sendMessage").mock(side_effect=capture)
    respx.post(f"{TG}/bot{BOT_TOKEN}/editMessageText").mock(
        return_value=Response(200, json={"ok": True, "result": True})
    )

    b = make_business()
    bot = attach_bot(b)
    owner = owner_membership(b)
    code = create_link_code(owner.user)
    r = internal(
        api,
        "POST",
        f"/internal/v1/bots/{bot.id}/staff/link",
        {"code": code, "user": {"id": 555, "first_name": "Owner"}},
    )
    assert r.status_code == 200, r.json()

    p = make_product(b, price=5000)
    tg = 9001
    r = internal(
        api,
        "POST",
        f"/internal/v1/bots/{bot.id}/session",
        {"user": {"id": tg, "first_name": "Customer"}},
    )
    assert r.status_code == 200
    c = f"/internal/v1/bots/{bot.id}/customers/{tg}"
    assert (
        internal(
            api, "POST", f"{c}/cart/items", {"product_id": str(p.id), "quantity": 2}
        ).status_code
        == 201
    )
    r = internal(
        api,
        "POST",
        f"{c}/checkout",
        {"fulfilment": "pickup", "customer_name": "Ali", "customer_phone": "07701234567"},
        headers={"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.json()
    order = r.json()
    assert order["total"] == 10000

    drain()
    staff_msgs = [m for m in sent if m["chat_id"] == 555]
    assert len(staff_msgs) == 1
    assert "#1001" in staff_msgs[0]["text"]
    buttons = [
        btn["callback_data"]
        for row in staff_msgs[0]["reply_markup"]["inline_keyboard"]
        for btn in row
    ]
    assert any(":cf:1" in cb for cb in buttons)
    assert OrderNotificationMessage.objects.filter(kind="staff").count() == 1

    # Staff presses Accept twice (duplicate callback) → applied once.
    payload = {
        "order_id": order["id"],
        "to": "confirmed",
        "expected_version": 1,
        "telegram_user_id": 555,
    }
    r1 = internal(api, "POST", f"/internal/v1/bots/{bot.id}/staff/transition", payload)
    r2 = internal(api, "POST", f"/internal/v1/bots/{bot.id}/staff/transition", payload)
    assert r1.json()["applied"] is True
    assert r2.json()["applied"] is False

    drain()
    customer_msgs = [m for m in sent if m["chat_id"] == tg]
    assert len(customer_msgs) == 1
    assert "تأكيد" in customer_msgs[0]["text"]

    # Unlinked Telegram user cannot act.
    payload.update(to="preparing", expected_version=2, telegram_user_id=123)
    r = internal(api, "POST", f"/internal/v1/bots/{bot.id}/staff/transition", payload)
    assert r.status_code == 403


def test_staff_of_other_business_cannot_use_buttons(api):
    a, b = make_business(), make_business()
    bot_a = attach_bot(a)
    stranger = make_member(b, "Manager")
    code = create_link_code(stranger.user)
    internal(
        api, "POST", f"/internal/v1/bots/{bot_a.id}/staff/link", {"code": code, "user": {"id": 777}}
    )
    p = make_product(a)
    internal(api, "POST", f"/internal/v1/bots/{bot_a.id}/session", {"user": {"id": 1}})
    c = f"/internal/v1/bots/{bot_a.id}/customers/1"
    internal(api, "POST", f"{c}/cart/items", {"product_id": str(p.id)})
    order = internal(
        api,
        "POST",
        f"{c}/checkout",
        {"fulfilment": "pickup", "customer_name": "Ali", "customer_phone": "07701234567"},
        headers={"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())},
    ).json()
    r = internal(
        api,
        "POST",
        f"/internal/v1/bots/{bot_a.id}/staff/transition",
        {
            "order_id": order["id"],
            "to": "confirmed",
            "expected_version": 1,
            "telegram_user_id": 777,
        },
    )
    assert r.status_code == 403


def test_credentials_endpoint_and_token_never_in_public_api(api):
    from tests.helpers import auth

    b = make_business()
    bot = attach_bot(b)
    r = internal(api, "GET", f"/internal/v1/bots/{bot.id}/credentials")
    assert r.json()["token"] == BOT_TOKEN
    api.credentials()
    auth(api, b.owner)
    body = api.get(f"/api/v1/b/{b.id}/telegram").content.decode()
    assert BOT_TOKEN not in body
    assert BOT_TOKEN.split(":")[1] not in body
