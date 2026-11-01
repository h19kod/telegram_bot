from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

import pyotp
from django.contrib.auth import password_validation
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts.models import TelegramAccount, TelegramLinkCode, User
from core.crypto import decrypt, encrypt
from core.errors import DomainError
from core.phone import InvalidPhoneNumber, normalize_phone

LINK_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
WS_TICKET_TTL = 30


def register(
    *,
    email: str | None = None,
    phone: str | None = None,
    password: str,
    full_name: str = "",
    language: str = "ar",
) -> User:
    if phone:
        try:
            phone = normalize_phone(phone)
        except InvalidPhoneNumber:
            raise DomainError("invalid_phone", status_code=400) from None
    if not email and not phone:
        raise DomainError("validation_error", {"email": ["email or phone required"]}, 400)
    candidate = User(email=email, phone=phone, full_name=full_name)
    password_validation.validate_password(password, candidate)
    try:
        return User.objects.create_user(
            email=email or None,
            phone=phone or None,
            password=password,
            full_name=full_name,
            language=language,
        )
    except IntegrityError:
        raise DomainError("validation_error", {"email": ["already registered"]}, 400) from None


def revoke_all_tokens(user: User) -> None:
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def change_password(user: User, old: str, new: str) -> None:
    if not user.check_password(old):
        raise DomainError("invalid_credentials", status_code=400)
    password_validation.validate_password(new, user)
    user.set_password(new)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_tokens(user)


# --- 2FA -----------------------------------------------------------------------------------


def totp_setup(user: User) -> str:
    secret = pyotp.random_base32()
    user.totp_secret_encrypted = encrypt(secret)
    user.totp_enabled = False
    user.save(update_fields=["totp_secret_encrypted", "totp_enabled", "updated_at"])
    return pyotp.TOTP(secret).provisioning_uri(name=str(user), issuer_name="Smart Ordering")


def verify_totp(user: User, code: str) -> bool:
    if not user.totp_secret_encrypted:
        return False
    secret = decrypt(user.totp_secret_encrypted)
    used_key = f"totp-used:{user.pk}:{code}"
    if cache.get(used_key):
        return False  # prevent replay within the validity window
    ok = pyotp.TOTP(secret).verify(str(code).strip(), valid_window=1)
    if ok:
        cache.set(used_key, 1, 90)
    return ok


def totp_enable(user: User, code: str) -> None:
    if not verify_totp(user, code):
        raise DomainError("invalid_otp", status_code=400)
    user.totp_enabled = True
    user.save(update_fields=["totp_enabled", "updated_at"])


def totp_disable(user: User, code: str) -> None:
    if not verify_totp(user, code):
        raise DomainError("invalid_otp", status_code=400)
    user.totp_enabled = False
    user.totp_secret_encrypted = None
    user.save(update_fields=["totp_enabled", "totp_secret_encrypted", "updated_at"])


# --- Telegram linking -----------------------------------------------------------------------


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def create_link_code(user: User) -> str:
    TelegramLinkCode.objects.filter(user=user, used_at__isnull=True).delete()
    code = "".join(secrets.choice(LINK_CODE_ALPHABET) for _ in range(8))
    TelegramLinkCode.objects.create(
        user=user, code_hash=_hash(code), expires_at=timezone.now() + timedelta(minutes=10)
    )
    return code


@transaction.atomic
def complete_link(
    code: str, telegram_user_id: int, username: str = "", first_name: str = ""
) -> User:
    link = (
        TelegramLinkCode.objects.select_for_update()
        .select_related("user")
        .filter(code_hash=_hash(code), used_at__isnull=True, expires_at__gt=timezone.now())
        .first()
    )
    if link is None:
        raise DomainError("invalid_link_code", status_code=400)
    link.used_at = timezone.now()
    link.save(update_fields=["used_at", "updated_at"])
    TelegramAccount.objects.filter(telegram_user_id=telegram_user_id).exclude(
        user=link.user
    ).delete()
    TelegramAccount.objects.update_or_create(
        user=link.user,
        defaults={
            "telegram_user_id": telegram_user_id,
            "username": username[:64],
            "first_name": first_name[:128],
        },
    )
    return link.user


def user_for_telegram(telegram_user_id: int) -> User | None:
    acc = (
        TelegramAccount.objects.select_related("user")
        .filter(telegram_user_id=telegram_user_id, user__is_active=True)
        .first()
    )
    return acc.user if acc else None


# --- WebSocket tickets --------------------------------------------------------------------


def issue_ws_ticket(user: User) -> str:
    ticket = secrets.token_urlsafe(24)
    cache.set(f"ws-ticket:{ticket}", str(user.pk), WS_TICKET_TTL)
    return ticket


def consume_ws_ticket(ticket: str) -> Any:
    key = f"ws-ticket:{ticket}"
    user_id = cache.get(key)
    if user_id:
        cache.delete(key)
    return user_id
