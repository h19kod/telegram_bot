from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.customers.models import Customer, PhoneVerification
from core import whatsapp
from core.errors import DomainError
from core.phone import InvalidPhoneNumber, normalize_phone
from core.text import to_latin_digits


def upsert_from_telegram(
    business_id: Any,
    *,
    telegram_user_id: int,
    first_name: str = "",
    last_name: str = "",
    username: str = "",
    language_code: str = "",
) -> Customer:
    defaults = {
        "first_name": first_name[:128],
        "last_name": last_name[:128],
        "telegram_username": username[:64],
        "last_seen_at": timezone.now(),
    }
    customer = Customer.objects.filter(
        business_id=business_id, telegram_user_id=telegram_user_id
    ).first()
    if customer is None:
        lang = "en" if language_code.startswith("en") else "ar"
        try:
            with transaction.atomic():
                return Customer.objects.create(
                    business_id=business_id,
                    telegram_user_id=telegram_user_id,
                    language=lang,
                    **defaults,
                )
        except IntegrityError:
            customer = Customer.objects.get(
                business_id=business_id, telegram_user_id=telegram_user_id
            )
    changed = [k for k, v in defaults.items() if v and getattr(customer, k) != v]
    for k in changed:
        setattr(customer, k, defaults[k])
    if changed:
        customer.save(update_fields=[*changed, "updated_at"])
    return customer


# --- Phone verification ----------------------------------------------------------------------


@dataclass(frozen=True)
class CodeSent:
    phone: str
    expires_in: int
    resend_in: int


def verification_required(business: Any) -> bool:
    """Checkout needs a verified phone: the business wants it and a code sender exists."""
    return bool(business.settings.require_verified_phone and whatsapp.is_enabled())


def is_phone_verified(customer: Customer, phone: str) -> bool:
    return customer.phone_verified and customer.phone == phone


def _code_hash(verification_id: Any, code: str) -> str:
    msg = f"{verification_id}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def _hit_phone_quota(phone: str) -> bool:
    """Per-number hourly cap across all businesses (stops code-pumping one victim's number)."""
    key = f"phone-code:{phone}"
    cache.add(key, 0, timeout=3600)
    try:
        return cache.incr(key) > settings.PHONE_CODES_PER_HOUR
    except ValueError:  # expired between add and incr
        cache.set(key, 1, timeout=3600)
        return False


def request_phone_code(customer: Customer, raw_phone: str) -> CodeSent:
    """Send a 6-digit WhatsApp code proving the customer owns `raw_phone`."""
    if not whatsapp.is_enabled():
        raise DomainError("verification_unavailable")
    if customer.is_blocked:
        raise DomainError("customer_blocked", status_code=403)
    try:
        phone = normalize_phone(raw_phone)
    except InvalidPhoneNumber:
        raise DomainError("invalid_phone", status_code=400) from None

    now = timezone.now()
    ttl = settings.PHONE_CODE_TTL_SECONDS
    with transaction.atomic():
        Customer.objects.select_for_update().filter(pk=customer.pk).first()  # serialise sends
        recent = PhoneVerification.objects.for_business(customer.business_id).filter(
            customer=customer, created_at__gte=now - timedelta(hours=1)
        )
        last = recent.order_by("-created_at").first()
        if last and (now - last.created_at).total_seconds() < settings.PHONE_CODE_RESEND_SECONDS:
            wait = settings.PHONE_CODE_RESEND_SECONDS - int((now - last.created_at).total_seconds())
            raise DomainError("code_resend_too_soon", {"retry_after": wait}, 429)
        if recent.count() >= settings.PHONE_CODES_PER_HOUR or _hit_phone_quota(phone):
            raise DomainError("too_many_codes", status_code=429)
        recent.filter(verified_at__isnull=True, expires_at__gt=now).update(expires_at=now)

        code = f"{secrets.randbelow(10**6):06d}"
        v = PhoneVerification(
            business_id=customer.business_id,
            customer=customer,
            phone=phone,
            expires_at=now + timedelta(seconds=ttl),
        )
        v.code_hash = _code_hash(v.id, code)
        v.save()

        def _send() -> None:
            from apps.customers.tasks import send_phone_code

            send_phone_code.delay(str(v.id), code, customer.language)

        transaction.on_commit(_send)
    return CodeSent(phone, ttl, settings.PHONE_CODE_RESEND_SECONDS)


def confirm_phone_code(customer: Customer, code: str) -> Customer:
    """Check the latest code; on success the number becomes the customer's verified phone."""
    now = timezone.now()
    code = to_latin_digits(code or "").strip()
    with transaction.atomic():
        v = (
            PhoneVerification.objects.for_business(customer.business_id)
            .select_for_update()
            .filter(customer=customer, verified_at__isnull=True, expires_at__gt=now)
            .order_by("-created_at")
            .first()
        )
        if v is None:
            raise DomainError("code_expired")
        if v.attempts >= settings.PHONE_CODE_MAX_ATTEMPTS:
            raise DomainError("too_many_attempts", status_code=429)
        v.attempts += 1
        ok = hmac.compare_digest(v.code_hash, _code_hash(v.id, code))
        if ok:
            v.verified_at = now
        v.save(update_fields=["attempts", "verified_at", "updated_at"])
        if ok:
            _set_verified_phone(customer, v.phone, now)
    if not ok:  # outside the atomic block: the attempt counter must stick
        left = settings.PHONE_CODE_MAX_ATTEMPTS - v.attempts
        raise DomainError("invalid_code", {"attempts_left": left}, 400)
    return customer


def verify_phone_by_telegram_contact(customer: Customer, raw_phone: str) -> Customer:
    """The bot saw the user share *their own* Telegram contact: Telegram vouches for it."""
    try:
        phone = normalize_phone(raw_phone)
    except InvalidPhoneNumber:
        raise DomainError("invalid_phone", status_code=400) from None
    _set_verified_phone(customer, phone, timezone.now())
    return customer


def set_unverified_phone(customer: Customer, raw_phone: str) -> None:
    """A phone typed by the customer: kept for contact, verification dropped if it changed."""
    phone = normalize_phone(raw_phone) if raw_phone else ""
    if phone == customer.phone:
        return
    customer.phone, customer.phone_verified_at = phone, None
    customer.save(update_fields=["phone", "phone_verified_at", "updated_at"])


def _set_verified_phone(customer: Customer, phone: str, at: Any) -> None:
    customer.phone, customer.phone_verified_at = phone, at
    customer.save(update_fields=["phone", "phone_verified_at", "updated_at"])
