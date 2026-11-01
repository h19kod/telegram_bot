import uuid
from datetime import timedelta

import pytest
import respx
from django.utils import timezone
from httpx import Response

from apps.accounts.services import complete_link, create_link_code
from apps.businesses.models import TelegramBot, WebhookStatus
from apps.businesses.services import connect_bot, disconnect_bot
from apps.notifications.models import NotificationOutbox, OutboxStatus
from apps.notifications.services import drain
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.staff.models import Role
from apps.staff.services import accept_invitation, create_invitation
from core.errors import DomainError
from tests.factories import UserFactory, branch_of, make_business, make_customer, make_product
from tests.helpers import BOT_TOKEN, attach_bot

pytestmark = pytest.mark.django_db
TG = "https://telegram.test"


@respx.mock
def test_connect_bot_validates_and_registers_webhook(settings):
    settings.TELEGRAM_WEBHOOK_BASE_URL = "https://api.example.iq"
    respx.post(f"{TG}/bot{BOT_TOKEN}/getMe").mock(
        return_value=Response(
            200,
            json={"ok": True, "result": {"id": 7000000001, "is_bot": True, "username": "shop_bot"}},
        )
    )
    hook = respx.post(f"{TG}/bot{BOT_TOKEN}/setWebhook").mock(
        return_value=Response(200, json={"ok": True, "result": True})
    )
    b = make_business(plan="basic")
    bot = connect_bot(b, BOT_TOKEN)
    assert bot.webhook_status == WebhookStatus.ACTIVE
    assert bot.token == BOT_TOKEN
    assert BOT_TOKEN.encode() not in bytes(bot.token_encrypted)
    sent = hook.calls[0].request.content.decode()
    assert f"/tg/webhook/{bot.id}" in sent
    assert bot.webhook_secret in sent

    respx.post(f"{TG}/bot{BOT_TOKEN}/deleteWebhook").mock(
        return_value=Response(200, json={"ok": True, "result": True})
    )
    disconnect_bot(b)
    assert not TelegramBot.objects.filter(business=b).exists()


@respx.mock
def test_connect_bot_rejects_bad_token():
    respx.post(f"{TG}/botbad:token/getMe").mock(
        return_value=Response(
            401, json={"ok": False, "error_code": 401, "description": "Unauthorized"}
        )
    )
    b = make_business(plan="basic")
    with pytest.raises(DomainError) as exc:
        connect_bot(b, "bad:token")
    assert exc.value.code == "invalid_bot_token"


def test_custom_bot_requires_plan():
    b = make_business(plan="free")
    with pytest.raises(DomainError) as exc:
        connect_bot(b, BOT_TOKEN)
    assert exc.value.code == "feature_not_available"


def test_invitation_accept_once():
    b = make_business()
    role = Role.objects.get(business=b, name="Cashier")
    _, token = create_invitation(b, role, b.owner, email="c@x.com")
    user = UserFactory()
    m = accept_invitation(token, user)
    assert m.role == role
    with pytest.raises(DomainError):
        accept_invitation(token, UserFactory())


def test_owner_role_cannot_be_invited():
    b = make_business()
    with pytest.raises(DomainError):
        create_invitation(b, Role.objects.get(business=b, is_owner=True), b.owner)


def test_link_code_single_use_and_expiry():
    user = UserFactory()
    code = create_link_code(user)
    assert complete_link(code.lower(), 42).telegram.telegram_user_id == 42
    with pytest.raises(DomainError):
        complete_link(code, 42)
    code2 = create_link_code(user)
    from apps.accounts.models import TelegramLinkCode

    TelegramLinkCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(DomainError):
        complete_link(code2, 42)


def _order(b):
    c = make_customer(b)
    cart_svc.add_item(c, branch_of(b), make_product(b).id, [], 1)
    o, _ = place_order(
        c,
        branch_of(b),
        CheckoutInput(
            fulfilment="pickup",
            customer_name="Ali <b>",
            customer_phone="07701234567",
            idempotency_key=uuid.uuid4(),
            channel="mini_app",
            notes="<script>x</script>",
        ),
    )
    return o


@respx.mock
def test_outbox_retries_on_429_and_escapes_html():
    b = make_business()
    attach_bot(b)
    b.settings.notification_chat_ids = [-100123]
    b.settings.save()
    route = respx.post(f"{TG}/bot{BOT_TOKEN}/sendMessage")
    route.mock(
        return_value=Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests",
                "parameters": {"retry_after": 3},
            },
        )
    )
    _order(b)
    drain()
    ev = NotificationOutbox.objects.get(event_type="order.placed")
    assert ev.status == OutboxStatus.PENDING
    assert ev.next_attempt_at > timezone.now()

    route.mock(return_value=Response(200, json={"ok": True, "result": {"message_id": 5}}))
    NotificationOutbox.objects.update(next_attempt_at=timezone.now())
    drain()
    ev.refresh_from_db()
    assert ev.status == OutboxStatus.SENT
    texts = [c.request.content.decode() for c in route.calls]
    assert any("&lt;script&gt;" in t for t in texts)
    assert not any("<script>" in t for t in texts)
    # Re-draining never re-sends.
    n = len(route.calls)
    NotificationOutbox.objects.update(status=OutboxStatus.PENDING, next_attempt_at=timezone.now())
    drain()
    assert len(route.calls) == n


@respx.mock
def test_outbox_gives_up_after_max_attempts():
    from apps.notifications import services

    b = make_business()
    attach_bot(b)
    b.settings.notification_chat_ids = [-1]
    b.settings.save()
    respx.post(f"{TG}/bot{BOT_TOKEN}/sendMessage").mock(
        return_value=Response(500, json={"ok": False, "error_code": 500, "description": "boom"})
    )
    _order(b)
    for _ in range(services.MAX_ATTEMPTS):
        NotificationOutbox.objects.filter(status="pending").update(next_attempt_at=timezone.now())
        drain()
    assert NotificationOutbox.objects.get(event_type="order.placed").status == OutboxStatus.FAILED
