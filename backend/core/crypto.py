"""Symmetric encryption for secrets at rest (bot tokens, TOTP secrets)."""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    keys = [k.strip() for k in settings.FIELD_ENCRYPTION_KEYS if k.strip()]
    if not keys:
        raise RuntimeError("FIELD_ENCRYPTION_KEYS is not configured")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(token: bytes | memoryview) -> str:
    try:
        return _fernet().decrypt(bytes(token)).decode()
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt value") from exc


def rotate(token: bytes | memoryview) -> bytes:
    return _fernet().rotate(bytes(token))
