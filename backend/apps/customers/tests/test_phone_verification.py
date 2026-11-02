"""WhatsApp phone verification: codes, limits, checkout gate, bot paths and tenant isolation."""

import json
import uuid
from datetime import timedelta

import pytest
import respx
from django.core.cache import cache
from httpx import Response

from apps.customers import services, tasks
from apps.customers.models import Customer, PhoneVerification
from core import whatsapp
from core.errors import DomainError
from tests.factories import make_business, make_customer, make_product
from tests.helpers import attach_bot, init_data, internal

pytestmark = pytest.mark.django_db
PHONE = "07801112233"
E164 = "+9647801112233"


@pytest.fixture(autouse=True)
def memory_whatsapp(settings, monkeypatch):
    settings.WHATSAPP_PROVIDER = "memory"
    whatsapp.MemorySender.outbox.clear()
    cache.clear()
    monkeypatch.setattr(
        tasks.send_phone_code, "delay", lambda *a: tasks.send_phone_code.apply(args=a)
    )
    yield whatsapp.MemorySender.outbox
    whatsapp.MemorySender.outbox.clear()


def last_code() -> str:
    return whatsapp.MemorySender.outbox[-1].code


def send(customer, phone=PHONE, capture=None):
    if capture is None:
        return services.request_phone_code(customer, phone)
    with capture(execute=True):
        return services.request_phone_code(customer, phone)


def age_codes(customer, seconds: int) -> None:
    for v in PhoneVerification.objects.filter(customer=customer):
        PhoneVerification.objects.filter(pk=v.pk).update(
            created_at=v.created_at - timedelta(seconds=seconds)
        )


# --- services --------------------------------------------------------------------------------


def test_code_is_sent_over_whatsapp_and_only_its_hmac_is_stored(
    django_capture_on_commit_callbacks,
):
    c = make_customer(make_business(), language="en")
    sent = send(c, "0780 111 2233", django_capture_on_commit_callbacks)
    assert (sent.phone, sent.expires_in, sent.resend_in) == (E164, 600, 60)
    [msg] = whatsapp.MemorySender.outbox
    assert (msg.phone, msg.lang) == (E164, "en")
    assert len(msg.code) == 6
    assert msg.code.isdigit()
    v = PhoneVerification.objects.get(customer=c)
    assert msg.code not in v.code_hash
    assert len(v.code_hash) == 64

    services.confirm_phone_code(c, msg.code)
    c.refresh_from_db()
    assert c.phone == E164
    assert c.phone_verified
    assert services.is_phone_verified(c, E164)


def test_wrong_code_counts_attempts_then_locks(settings, django_capture_on_commit_callbacks):
    c = make_customer(make_business())
    send(c, capture=django_capture_on_commit_callbacks)
    good = last_code()
    wrong = "000000" if good != "000000" else "111111"
    for left in range(settings.PHONE_CODE_MAX_ATTEMPTS - 1, -1, -1):
        with pytest.raises(DomainError) as e:
            services.confirm_phone_code(c, wrong)
        assert (e.value.code, e.value.details["attempts_left"]) == ("invalid_code", left)
    with pytest.raises(DomainError) as e:
        services.confirm_phone_code(c, good)  # even the right code: locked
    assert e.value.code == "too_many_attempts"
    c.refresh_from_db()
    assert not c.phone_verified


def test_arabic_indic_digits_are_accepted(django_capture_on_commit_callbacks):
    c = make_customer(make_business())
    send(c, capture=django_capture_on_commit_callbacks)
    arabic = last_code().translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    assert services.confirm_phone_code(c, f" {arabic} ").phone_verified


def test_expired_code_and_new_code_replaces_old(django_capture_on_commit_callbacks):
    c = make_customer(make_business())
    send(c, capture=django_capture_on_commit_callbacks)
    first = last_code()
    PhoneVerification.objects.filter(customer=c).update(
        expires_at=PhoneVerification.objects.get(customer=c).created_at
    )
    with pytest.raises(DomainError) as e:
        services.confirm_phone_code(c, first)
    assert e.value.code == "code_expired"

    age_codes(c, 61)
    send(c, capture=django_capture_on_commit_callbacks)
    age_codes(c, 61)
    send(c, capture=django_capture_on_commit_callbacks)
    newest = last_code()
    old = whatsapp.MemorySender.outbox[-2].code
    if old != newest:
        with pytest.raises(DomainError):
            services.confirm_phone_code(c, old)  # superseded
    assert services.confirm_phone_code(c, newest).phone_verified


def test_resend_interval_and_hourly_caps(settings):
    c = make_customer(make_business())
    send(c)
    with pytest.raises(DomainError) as e:
        send(c)
    assert (e.value.code, e.value.status_code) == ("code_resend_too_soon", 429)
    assert 0 < e.value.details["retry_after"] <= 60

    for _ in range(settings.PHONE_CODES_PER_HOUR - 1):
        age_codes(c, 61)
        send(c)
    age_codes(c, 61)
    with pytest.raises(DomainError) as e:
        send(c)
    assert e.value.code == "too_many_codes"


def test_per_number_cap_spans_businesses(settings):
    for _ in range(settings.PHONE_CODES_PER_HOUR):
        send(make_customer(make_business()))
    with pytest.raises(DomainError) as e:
        send(make_customer(make_business()))
    assert e.value.code == "too_many_codes"


def test_rejects_bad_numbers_blocked_customers_and_disabled_provider(settings):
    b = make_business()
    with pytest.raises(DomainError) as e:
        send(make_customer(b), "12345")
    assert e.value.code == "invalid_phone"
    with pytest.raises(DomainError) as e:
        send(make_customer(b, is_blocked=True))
    assert e.value.code == "customer_blocked"
    settings.WHATSAPP_PROVIDER = "disabled"
    with pytest.raises(DomainError) as e:
        send(make_customer(b))
    assert e.value.code == "verification_unavailable"


def test_confirm_without_any_code():
    with pytest.raises(DomainError) as e:
        services.confirm_phone_code(make_customer(make_business()), "123456")
    assert e.value.code == "code_expired"


def test_typed_phone_change_drops_verification():
    c = make_customer(make_business(), phone=E164)
    services.verify_phone_by_telegram_contact(c, E164)
    services.set_unverified_phone(c, PHONE)  # same number, other format: kept
    assert c.phone_verified
    services.set_unverified_phone(c, "07701234567")
    c.refresh_from_db()
    assert (c.phone, c.phone_verified) == ("+9647701234567", False)


def test_verification_required_follows_setting_and_provider(settings):
    b = make_business()
    assert services.verification_required(b)
    b.settings.require_verified_phone = False
    assert not services.verification_required(b)
    b.settings.require_verified_phone = True
    settings.WHATSAPP_PROVIDER = "disabled"
    assert not services.verification_required(b)


# --- task / provider -------------------------------------------------------------------------


@respx.mock
def test_cloud_sender_posts_authentication_template(settings):
    settings.WHATSAPP_PROVIDER = "cloud"
    settings.WHATSAPP_TOKEN = "test-wa-token"
    settings.WHATSAPP_PHONE_NUMBER_ID = "123"
    route = respx.post(f"{settings.WHATSAPP_API_BASE}/123/messages").mock(
        return_value=Response(200, json={"messages": [{"id": "wamid.1"}]})
    )
    whatsapp.get_sender().send_code(E164, "482913", "ar")
    req = route.calls.last.request
    body = json.loads(req.content)
    assert req.headers["Authorization"] == "Bearer test-wa-token"
    assert body["to"] == "9647801112233"
    assert body["template"]["name"] == settings.WHATSAPP_OTP_TEMPLATE
    assert body["template"]["language"]["code"] == "ar"
    texts = [p["text"] for comp in body["template"]["components"] for p in comp["parameters"]]
    assert texts == ["482913", "482913"]

    route.mock(return_value=Response(400, json={"error": {"code": 132001, "message": "x"}}))
    with pytest.raises(whatsapp.WhatsAppError) as e:
        whatsapp.get_sender().send_code(E164, "482913", "en")
    assert not e.value.retryable
    route.mock(return_value=Response(503))
    with pytest.raises(whatsapp.WhatsAppError) as e:
        whatsapp.get_sender().send_code(E164, "482913", "en")
    assert e.value.retryable


def test_provider_configuration_guards(settings):
    from django.core.exceptions import ImproperlyConfigured

    settings.WHATSAPP_PROVIDER = "console"
    settings.DEBUG = False
    with pytest.raises(ImproperlyConfigured):
        whatsapp.get_sender()
    settings.WHATSAPP_PROVIDER = "cloud"
    settings.WHATSAPP_TOKEN = ""
    with pytest.raises(ImproperlyConfigured):
        whatsapp.get_sender()


def test_task_retries_transient_failures_and_skips_used_codes(monkeypatch):
    c = make_customer(make_business())
    send(c)  # not committed in this test: the task is invoked by hand below
    v = PhoneVerification.objects.get(customer=c)

    class Flaky:
        def send_code(self, *a):
            raise whatsapp.WhatsAppError("503", retryable=True)

    monkeypatch.setattr(whatsapp, "get_sender", lambda: Flaky())
    retried = []
    monkeypatch.setattr(
        tasks.send_phone_code, "retry", lambda **kw: retried.append(kw) or RuntimeError("retry")
    )
    with pytest.raises(RuntimeError):
        tasks.send_phone_code.run(str(v.id), "123456", "ar")
    assert retried

    PhoneVerification.objects.filter(pk=v.pk).update(verified_at=v.created_at)
    monkeypatch.setattr(whatsapp, "get_sender", lambda: pytest.fail("must not send"))
    tasks.send_phone_code.run(str(v.id), "123456", "ar")
    tasks.send_phone_code.run(str(uuid.uuid4()), "123456", "ar")


# --- Mini App API ----------------------------------------------------------------------------


def _store_session(api, b, user_id=777):
    r = api.post(
        f"/api/v1/store/{b.slug}/session", {"init_data": init_data(user_id=user_id)}, format="json"
    )
    assert r.status_code == 200, r.json()
    api.credentials(HTTP_AUTHORIZATION=f"Customer {r.json()['token']}")
    return r.json()


def test_mini_app_checkout_requires_whatsapp_verified_phone(
    api, django_capture_on_commit_callbacks
):
    b = make_business()
    attach_bot(b)
    data = _store_session(api, b)
    assert data["business"]["phone_verification_required"] is True
    assert data["customer"]["phone_verified"] is False
    base = f"/api/v1/store/{b.slug}"
    p = make_product(b, price=5000)
    api.post(f"{base}/cart/items", {"product_id": str(p.id), "quantity": 1}, format="json")
    body = {"fulfilment": "pickup", "customer_name": "زيد", "customer_phone": PHONE}

    r = api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "phone_not_verified"
    assert "customer_phone" in r.json()["error"]["details"]
    assert api.post(f"{base}/checkout/quote", body, format="json").status_code == 200

    with django_capture_on_commit_callbacks(execute=True):
        r = api.post(f"{base}/me/phone/code", {"phone": PHONE}, format="json")
    assert r.status_code == 202, r.json()
    assert r.json()["phone"] == E164
    assert api.post(f"{base}/me/phone/code", {"phone": PHONE}, format="json").status_code == 429

    r = api.post(f"{base}/me/phone/confirm", {"code": "abc"}, format="json")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_code"
    r = api.post(f"{base}/me/phone/confirm", {"code": last_code()}, format="json")
    assert r.status_code == 200
    assert (r.json()["phone"], r.json()["phone_verified"]) == (E164, True)

    r = api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 201, r.json()
    assert Customer.objects.get(telegram_user_id=777).phone_verified  # order kept it verified

    # A typed new number via PATCH /me is unverified again.
    r = api.patch(f"{base}/me", {"phone": "07701234567"}, format="json")
    assert (r.json()["phone"], r.json()["phone_verified"]) == ("+9647701234567", False)


def test_mini_app_orders_freely_when_business_opts_out(api):
    b = make_business()
    b.settings.require_verified_phone = False
    b.settings.save()
    attach_bot(b)
    data = _store_session(api, b)
    assert data["business"]["phone_verification_required"] is False
    base = f"/api/v1/store/{b.slug}"
    p = make_product(b, price=5000)
    api.post(f"{base}/cart/items", {"product_id": str(p.id), "quantity": 1}, format="json")
    body = {"fulfilment": "pickup", "customer_name": "زيد", "customer_phone": PHONE}
    r = api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 201


def test_phone_endpoints_are_tenant_isolated(api, django_capture_on_commit_callbacks):
    a, b = make_business(), make_business()
    attach_bot(a)
    attach_bot(b)
    _store_session(api, a)
    for path, body in (("code", {"phone": PHONE}), ("confirm", {"code": "123456"})):
        r = api.post(f"/api/v1/store/{b.slug}/me/phone/{path}", body, format="json")
        assert r.status_code == 404
    # The same Telegram user in business B has their own customer row and their own codes.
    with django_capture_on_commit_callbacks(execute=True):
        assert (
            api.post(
                f"/api/v1/store/{a.slug}/me/phone/code", {"phone": PHONE}, format="json"
            ).status_code
            == 202
        )
    code_a = last_code()
    api.credentials()
    _store_session(api, b)
    r = api.post(f"/api/v1/store/{b.slug}/me/phone/confirm", {"code": code_a}, format="json")
    assert r.json()["error"]["code"] == "code_expired"


def test_dashboard_settings_and_customer_list_expose_verification(api):
    from tests.helpers import auth

    b = make_business()
    c = make_customer(b)
    services.verify_phone_by_telegram_contact(c, PHONE)
    auth(api, b.memberships.get().user)
    r = api.get(f"/api/v1/b/{b.id}/settings")
    assert r.json()["require_verified_phone"] is True
    assert r.json()["phone_verification_available"] is True
    r = api.patch(f"/api/v1/b/{b.id}/settings", {"require_verified_phone": False}, format="json")
    assert r.status_code == 200
    assert r.json()["require_verified_phone"] is False
    rows = api.get(f"/api/v1/b/{b.id}/customers").json()["results"]
    assert rows[0]["phone_verified"] is True


# --- bot (internal API) ----------------------------------------------------------------------


def test_bot_code_and_contact_verification(api, django_capture_on_commit_callbacks):
    b = make_business()
    bot = attach_bot(b)
    tg = 4242
    r = internal(api, "POST", f"/internal/v1/bots/{bot.id}/session", {"user": {"id": tg}})
    assert r.json()["customer"]["phone_verified"] is False
    assert r.json()["business"]["phone_verification_required"] is True
    c = f"/internal/v1/bots/{bot.id}/customers/{tg}"

    with django_capture_on_commit_callbacks(execute=True):
        r = internal(api, "POST", f"{c}/phone/code", {"phone": PHONE})
    assert r.status_code == 202, r.json()
    r = internal(api, "POST", f"{c}/phone/confirm", {"code": last_code()})
    assert r.json() == {"phone": E164, "phone_verified": True}

    r = internal(
        api, "POST", f"{c}/phone/contact", {"phone": "+9647701234567", "contact_user_id": 1}
    )
    assert r.status_code == 400  # someone else's contact
    r = internal(
        api, "POST", f"{c}/phone/contact", {"phone": "+9647701234567", "contact_user_id": tg}
    )
    assert r.json() == {"phone": "+9647701234567", "phone_verified": True}

    p = make_product(b, price=5000)
    internal(api, "POST", f"{c}/cart/items", {"product_id": str(p.id), "quantity": 1})
    body = {"fulfilment": "pickup", "customer_name": "Ali", "customer_phone": PHONE}
    r = internal(
        api, "POST", f"{c}/checkout", body, headers={"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}
    )
    assert r.json()["error"]["code"] == "phone_not_verified"  # verified number is the contact one
    body["customer_phone"] = "07701234567"
    r = internal(
        api, "POST", f"{c}/checkout", body, headers={"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}
    )
    assert r.status_code == 201, r.json()
