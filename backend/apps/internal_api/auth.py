"""HMAC service authentication for the bot → backend internal API.

Header: X-Service-Auth: v1:<unix_ts>:<nonce>:<hex hmac>
Signed message: METHOD\\nPATH?QUERY\\nTS\\nNONCE\\nSHA256(BODY)
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from core.errors import DomainError


def sign(secret: str, method: str, path: str, ts: str, nonce: str, body: bytes) -> str:
    msg = "\n".join([method.upper(), path, ts, nonce, hashlib.sha256(body).hexdigest()])
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def make_header(
    secret: str, method: str, path: str, body: bytes, nonce: str, ts: int | None = None
) -> str:
    t = str(ts or int(time.time()))
    return f"v1:{t}:{nonce}:{sign(secret, method, path, t, nonce, body)}"


@dataclass
class ServicePrincipal:
    name: str = "bot-service"
    is_authenticated: bool = True
    is_active: bool = True
    is_platform_admin: bool = False
    pk: str = "service:bot"


class ServiceAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[ServicePrincipal, None] | None:
        header = request.headers.get("X-Service-Auth", "")
        parts = header.split(":")
        if len(parts) != 4 or parts[0] != "v1":
            raise DomainError("not_authenticated", status_code=401)
        _, ts, nonce, signature = parts
        try:
            age = abs(time.time() - int(ts))
        except ValueError:
            raise DomainError("not_authenticated", status_code=401) from None
        if age > settings.INTERNAL_API_CLOCK_SKEW_SECONDS or not 8 <= len(nonce) <= 64:
            raise DomainError("not_authenticated", status_code=401)
        path = request.get_full_path()
        expected = sign(settings.INTERNAL_API_SECRET, request.method, path, ts, nonce, request.body)
        if not hmac.compare_digest(expected, signature):
            raise DomainError("not_authenticated", status_code=401)
        if not cache.add(f"svc-nonce:{nonce}", 1, settings.INTERNAL_API_CLOCK_SKEW_SECONDS * 2):
            raise DomainError("not_authenticated", status_code=401)  # replay
        return ServicePrincipal(), None


class IsService(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        return isinstance(request.user, ServicePrincipal)
