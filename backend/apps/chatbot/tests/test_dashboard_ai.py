"""Dashboard side of the AI assistant: status, playground, staff replies, isolation."""

import json

import pytest
import respx
from httpx import Response

from apps.chatbot import tasks
from apps.chatbot.models import AIConversation, AIMessage
from apps.chatbot.providers import ScriptedProvider
from apps.chatbot.services import handle_message
from apps.customers.models import Customer
from apps.notifications.models import NotificationOutbox
from tests.factories import make_business, make_customer, make_member
from tests.helpers import BOT_TOKEN, attach_bot, auth

pytestmark = pytest.mark.django_db
TG = "https://telegram.test"


@pytest.fixture
def shop(settings, monkeypatch):
    settings.AI_PROVIDER = "scripted"
    ScriptedProvider.script = [{"reply": "هلا بيك! شنو تحب تطلب؟"}]
    monkeypatch.setattr(
        tasks.send_staff_reply, "delay", lambda *a: tasks.send_staff_reply.apply(args=a)
    )
    b = make_business(plan="pro")
    attach_bot(b)
    return b


def url(b, tail):
    return f"/api/v1/b/{b.id}/{tail}"


def test_status_reports_key_plan_switch_and_usage(api, shop, settings):
    auth(api, shop.owner)
    s = api.get(url(shop, "ai/status")).json()
    assert s["configured"] is True  # scripted provider needs no key
    assert (s["entitled"], s["enabled"], s["messages_used"], s["handed_over"]) == (
        True,
        False,
        0,
        0,
    )
    assert s["messages_limit"] == 3000
    settings.AI_PROVIDER = "anthropic"
    settings.AI_API_KEY = ""
    assert api.get(url(shop, "ai/status")).json()["configured"] is False


def test_playground_works_before_switching_on_and_stays_private(
    api, shop, django_capture_on_commit_callbacks
):
    assert shop.settings.ai_enabled is False
    auth(api, shop.owner)
    with django_capture_on_commit_callbacks(execute=True):
        r = api.post(url(shop, "ai/playground"), {"text": "هلو"}, format="json")
    assert r.status_code == 200, r.json()
    assert r.json()["reply"] == "هلا بيك! شنو تحب تطلب؟"
    sandbox = Customer.objects.get(business=shop, is_sandbox=True)
    assert sandbox.telegram_user_id < 0

    # Asking for a human in the playground pages nobody and does not stick.
    with django_capture_on_commit_callbacks(execute=True):
        r = api.post(url(shop, "ai/playground"), {"text": "اريد موظف"}, format="json")
    assert r.json()["handed_over"] is True
    assert not NotificationOutbox.objects.filter(business=shop).exists()
    assert not AIConversation.objects.filter(customer=sandbox).exclude(status="closed").exists()

    # Sandbox never shows up for staff as a customer or a conversation.
    assert api.get(url(shop, "customers")).json()["count"] == 0
    assert api.get(url(shop, "ai/conversations")).json()["count"] == 0

    r = api.post(url(shop, "ai/playground"), {"text": "", "reset": True}, format="json")
    assert r.json()["reply"] == ""


def test_playground_explains_missing_plan(api, settings):
    settings.AI_PROVIDER = "scripted"
    free = make_business(plan="free")
    auth(api, free.owner)
    r = api.post(url(free, "ai/playground"), {"text": "hi"}, format="json")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "feature_not_available"


@respx.mock
def test_staff_reply_hands_over_and_reaches_the_customer(
    api, shop, django_capture_on_commit_callbacks
):
    sent = respx.post(f"{TG}/bot{BOT_TOKEN}/sendMessage").mock(
        return_value=Response(200, json={"ok": True, "result": {"message_id": 1}})
    )
    shop.settings.ai_enabled = True
    shop.settings.save()
    c = make_customer(shop, telegram_user_id=777)
    handle_message(shop, c, "عندكم برغر؟")
    conv = AIConversation.objects.get(customer=c)
    auth(api, shop.owner)

    with django_capture_on_commit_callbacks(execute=True):
        r = api.post(
            url(shop, f"ai/conversations/{conv.id}/reply"),
            {"text": "هلا <b>عيني</b>"},
            format="json",
        )
    assert r.status_code == 200, r.json()
    assert r.json()["status"] == "handed_over"
    assert r.json()["messages"][-1]["from_staff"] is True
    body = json.loads(sent.calls.last.request.content)
    assert body["chat_id"] == 777
    assert "&lt;b&gt;" in body["text"]  # staff text is escaped, not rendered as HTML

    # While handed over, the customer's next message skips the AI.
    assert handle_message(shop, c, "تمام")["handed_over"] is True
    r = api.post(url(shop, f"ai/conversations/{conv.id}/close"))
    assert r.json()["status"] == "closed"
    r = api.post(url(shop, f"ai/conversations/{conv.id}/reply"), {"text": "x"}, format="json")
    assert r.status_code == 422


@respx.mock
def test_undeliverable_reply_is_recorded(api, shop):
    respx.post(f"{TG}/bot{BOT_TOKEN}/sendMessage").mock(
        return_value=Response(
            403, json={"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked"}
        )
    )
    c = make_customer(shop)
    conv = AIConversation.objects.create(business=shop, customer=c)
    msg = AIMessage.objects.create(
        business=shop, conversation=conv, role="assistant", content="hi", provider="staff"
    )
    tasks.send_staff_reply.run(str(msg.id))
    msg.refresh_from_db()
    assert msg.error.startswith("not delivered")


def test_new_actions_need_permission_and_are_tenant_isolated(api, shop):
    conv = AIConversation.objects.create(business=shop, customer=make_customer(shop))
    other = make_business(plan="pro")
    auth(api, other.owner)
    for tail in ("reply", "close"):
        r = api.post(url(other, f"ai/conversations/{conv.id}/{tail}"), {"text": "x"}, format="json")
        assert r.status_code == 404
    auth(api, make_member(shop, "Cashier").user)
    assert api.get(url(shop, "ai/status")).status_code == 403
    assert api.post(url(shop, "ai/playground"), {"text": "x"}, format="json").status_code == 403
    r = api.post(url(shop, f"ai/conversations/{conv.id}/reply"), {"text": "x"}, format="json")
    assert r.status_code == 403
