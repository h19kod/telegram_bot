"""Business rules in accounts, customers, staff and notification services that the API tests
do not reach: owner protection, membership reactivation, 2FA replay, registration validation,
customer upsert, Telegram failure handling and support relay."""

import uuid

import pyotp
import pytest
import respx
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.password_validation import ValidationError as PasswordValidationError
from django.db import IntegrityError
from httpx import Response
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as accounts
from apps.accounts.models import TelegramAccount
from apps.customers.models import Customer
from apps.customers.services import upsert_from_telegram
from apps.notifications import services as notifications
from apps.notifications.models import NotificationOutbox
from apps.orders.models import OrderNotificationMessage
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.staff import services as staff
from apps.staff.models import Membership, Role
from core.crypto import decrypt
from core.errors import DomainError, NotFoundError
from tests.factories import (
    UserFactory,
    branch_of,
    make_business,
    make_customer,
    make_member,
    make_product,
    owner_membership,
)
from tests.helpers import BOT_TOKEN, attach_bot

pytestmark = pytest.mark.django_db
TG = "https://telegram.test"
STRONG = "Very-Strong-Pass-1"


# --- accounts --------------------------------------------------------------------------------


def test_register_validates_contact_and_duplicates():
    with pytest.raises(DomainError) as e:
        accounts.register(email="", phone="12", password=STRONG)
    assert e.value.code == "invalid_phone"
    with pytest.raises(DomainError) as e:
        accounts.register(email="", phone="", password=STRONG)
    assert e.value.details == {"email": ["email or phone required"]}

    user = accounts.register(email="", phone="07701234567", password=STRONG)
    assert user.phone == "+9647701234567"
    with pytest.raises(DomainError) as e:
        accounts.register(email="", phone="0770 123 4567", password=STRONG)
    assert e.value.details == {"email": ["already registered"]}
    with pytest.raises(PasswordValidationError):
        accounts.register(email="weak@x.com", password="1234567890")


def test_change_password_checks_old_and_revokes_sessions():
    user = UserFactory(password=STRONG)
    refresh = RefreshToken.for_user(user)
    with pytest.raises(DomainError):
        accounts.change_password(user, "wrong-password", "Another-Strong-Pass-2")
    accounts.change_password(user, STRONG, "Another-Strong-Pass-2")
    user.refresh_from_db()
    assert user.check_password("Another-Strong-Pass-2")
    assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()


def test_totp_lifecycle_and_replay_protection():
    user = UserFactory()
    assert accounts.verify_totp(user, "123456") is False  # no secret yet
    uri = accounts.totp_setup(user)
    assert uri.startswith("otpauth://totp/")
    secret = decrypt(user.totp_secret_encrypted)

    with pytest.raises(DomainError):
        accounts.totp_enable(user, "000000")
    code = pyotp.TOTP(secret).now()
    accounts.totp_enable(user, code)
    assert user.totp_enabled
    assert accounts.verify_totp(user, code) is False  # same code cannot be replayed

    with pytest.raises(DomainError):
        accounts.totp_disable(user, "000000")


def test_ws_ticket_is_single_use():
    user = UserFactory()
    ticket = accounts.issue_ws_ticket(user)
    assert accounts.consume_ws_ticket(ticket) == str(user.pk)
    assert accounts.consume_ws_ticket(ticket) is None
    assert accounts.consume_ws_ticket("unknown") is None


# --- customers -------------------------------------------------------------------------------


def test_upsert_updates_only_changed_fields_and_keeps_language():
    b = make_business()
    c1 = upsert_from_telegram(b.id, telegram_user_id=55, first_name="Ali", language_code="en")
    assert c1.language == "en"
    c2 = upsert_from_telegram(
        b.id, telegram_user_id=55, first_name="Ali Hassan", username="ali", language_code="ar"
    )
    assert c2.pk == c1.pk
    assert (c2.first_name, c2.telegram_username, c2.language) == ("Ali Hassan", "ali", "en")


def test_upsert_survives_concurrent_first_contact(monkeypatch):
    """Two first messages at once: the loser of the insert race reuses the winner's row."""
    b = make_business()
    winner = make_customer(b, telegram_user_id=77, first_name="Old")
    real_filter = Customer.objects.filter
    calls = {"n": 0}

    def racing_filter(*args, **kwargs):
        calls["n"] += 1
        return real_filter(pk=None) if calls["n"] == 1 else real_filter(*args, **kwargs)

    monkeypatch.setattr(Customer.objects, "filter", racing_filter)

    def lost_race(**kwargs):
        raise IntegrityError("duplicate key")

    monkeypatch.setattr(Customer.objects, "create", lost_race)
    got = upsert_from_telegram(b.id, telegram_user_id=77, first_name="New")
    assert got.pk == winner.pk
    assert got.first_name == "New"


# --- staff -----------------------------------------------------------------------------------


def test_get_membership_requires_authenticated_active_member():
    b = make_business()
    assert staff.get_membership(AnonymousUser(), b.id) is None
    m = make_member(b, "Cashier")
    assert staff.get_membership(m.user, b.id) == m
    m.is_active = False
    m.save()
    assert staff.get_membership(m.user, b.id) is None


def test_add_member_rejects_foreign_role_and_reactivates():
    a, b = make_business(), make_business()
    user = UserFactory()
    with pytest.raises(NotFoundError):
        staff.add_member(a, user, Role.objects.get(business=b, name="Cashier"), None)

    cashier = Role.objects.get(business=a, name="Cashier")
    kitchen = Role.objects.get(business=a, name="Kitchen")
    m = staff.add_member(a, user, cashier, None)
    assert staff.add_member(a, user, kitchen, None) == m  # already active: unchanged
    m.is_active = False
    m.save()
    again = staff.add_member(a, user, kitchen, None)
    assert again.pk == m.pk
    assert (again.is_active, again.role) == (True, kitchen)
    assert Membership.objects.filter(business=a, user=user).count() == 1


def test_owner_role_is_protected():
    b = make_business()
    owner = owner_membership(b)
    manager = make_member(b, "Manager")
    owner_role = Role.objects.get(business=b, is_owner=True)
    cashier = Role.objects.get(business=b, name="Cashier")

    with pytest.raises(DomainError) as e:
        staff.change_member_role(manager, owner_role, actor=manager)  # non-owner promotes
    assert e.value.code == "owner_role_protected"
    with pytest.raises(DomainError) as e:
        staff.change_member_role(owner, cashier, actor=owner)  # would leave no owner
    assert e.value.code == "last_owner"
    with pytest.raises(DomainError) as e:
        staff.deactivate_member(owner, actor=manager)
    assert e.value.code == "owner_role_protected"
    with pytest.raises(DomainError) as e:
        staff.deactivate_member(owner, actor=owner)
    assert e.value.code == "last_owner"

    second = make_member(b, "Manager")
    staff.change_member_role(second, owner_role, actor=owner)
    staff.deactivate_member(owner, actor=second)  # another owner remains: allowed
    owner.refresh_from_db()
    assert owner.is_active is False


def test_update_role_rules():
    b = make_business()
    with pytest.raises(DomainError):
        staff.update_role(Role.objects.get(business=b, is_owner=True), "Boss", None)
    role = Role.objects.get(business=b, name="Cashier")
    with pytest.raises(DomainError) as e:
        staff.update_role(role, None, ["orders.view", "not.a.permission"])
    assert e.value.details == {"permissions": ["not.a.permission"]}
    staff.update_role(role, "Front desk", ["orders.view"])
    role.refresh_from_db()
    assert role.name == "Front desk"
    assert list(role.permissions.values_list("codename", flat=True)) == ["orders.view"]


# --- notifications ---------------------------------------------------------------------------


def _order(b):
    p = make_product(b)
    c = make_customer(b)
    cart_svc.add_item(c, branch_of(b), p.id, [], 1)
    order, _ = place_order(
        c,
        branch_of(b),
        CheckoutInput(
            fulfilment="pickup",
            customer_name="Ali",
            customer_phone="07701234567",
            idempotency_key=uuid.uuid4(),
        ),
    )
    return order


def _staff_chat(b, role="Manager", tg_id=None):
    m = make_member(b, role)
    TelegramAccount.objects.create(user=m.user, telegram_user_id=tg_id or 600000 + m.pk % 1000)
    return m


def test_staff_chat_ids_dedupe_and_driver_scope():
    b = make_business()
    b.settings.notification_chat_ids = [111, 111]
    b.settings.save()
    manager = _staff_chat(b, "Manager", 222)
    order = _order(b)
    chats = notifications.staff_chat_ids(order)
    assert chats.count(111) == 1
    assert 222 in chats
    assert manager  # managers always hear about orders


@respx.mock
def test_blocked_chat_is_skipped_but_others_still_notified():
    b = make_business()
    attach_bot(b)
    b.settings.notification_chat_ids = [111, 222]
    b.settings.save()
    order = _order(b)
    blocked = {"ok": False, "error_code": 403, "description": "bot was blocked by the user"}
    sent = {"ok": True, "result": {"message_id": 9}}

    def reply(request):
        chat = __import__("json").loads(request.content)["chat_id"]
        return Response(403, json=blocked) if chat == 111 else Response(200, json=sent)

    route = respx.post(f"{TG}/bot{BOT_TOKEN}/sendMessage").mock(side_effect=reply)
    notifications.drain()
    chats = [__import__("json").loads(c.request.content)["chat_id"] for c in route.calls]
    assert {111, 222} <= set(chats)
    assert NotificationOutbox.objects.filter(status="sent").exists()
    assert OrderNotificationMessage.objects.filter(order=order, chat_id=222).exists()
    assert not OrderNotificationMessage.objects.filter(order=order, chat_id=111).exists()


@respx.mock
def test_status_change_edits_staff_messages_and_tolerates_not_modified():
    b = make_business()
    attach_bot(b)
    order = _order(b)
    bot = notifications.bot_for_business(b.id)
    OrderNotificationMessage.objects.create(
        business=b, order=order, bot=bot, chat_id=111, message_id=5, kind="staff"
    )
    respx.post(f"{TG}/bot{BOT_TOKEN}/editMessageText").mock(
        return_value=Response(
            400, json={"ok": False, "error_code": 400, "description": "message is not modified"}
        )
    )
    notifications.sync_staff_messages(order, notifications.BotAPI(BOT_TOKEN))  # no exception

    respx.post(f"{TG}/bot{BOT_TOKEN}/editMessageText").mock(
        return_value=Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests",
                "parameters": {"retry_after": 7},
            },
        )
    )
    with pytest.raises(notifications.RetryLater) as e:
        notifications.sync_staff_messages(order, notifications.BotAPI(BOT_TOKEN))
    assert e.value.seconds == 7


@respx.mock
def test_support_message_relayed_to_staff_with_escaped_text():
    b = make_business()
    attach_bot(b)
    _staff_chat(b, "Manager", 333)
    customer = make_customer(b, telegram_username="ali_<x>", phone="+9647701234567")
    route = respx.post(f"{TG}/bot{BOT_TOKEN}/sendMessage").mock(
        return_value=Response(200, json={"ok": True, "result": {"message_id": 1}})
    )
    event = NotificationOutbox(
        business_id=b.id,
        event_type="support.message",
        payload={"customer_id": str(customer.id), "text": "<script>hi</script>"},
    )
    notifications.handle(event)
    body = __import__("json").loads(route.calls.last.request.content)
    assert body["chat_id"] == 333
    assert "&lt;script&gt;hi&lt;/script&gt;" in body["text"]
    assert "@ali_&lt;x&gt;" in body["text"]
    assert "<script>" not in body["text"]

    # Unknown customer or business without a bot: silently dropped.
    event.payload = {"customer_id": str(uuid.uuid4()), "text": "x"}
    notifications.handle(event)
    assert route.call_count == 1


@respx.mock
def test_staff_test_message_counts_delivered_chats():
    b = make_business()
    with pytest.raises(DomainError):
        notifications.staff_test_message(b, None)  # no bot
    attach_bot(b)
    b.settings.notification_chat_ids = [111, 222]
    b.settings.save()

    def reply(request):
        chat = __import__("json").loads(request.content)["chat_id"]
        if chat == 111:
            return Response(403, json={"ok": False, "error_code": 403, "description": "blocked"})
        return Response(200, json={"ok": True, "result": {"message_id": 1}})

    respx.post(f"{TG}/bot{BOT_TOKEN}/sendMessage").mock(side_effect=reply)
    assert notifications.staff_test_message(b, None) == 1
