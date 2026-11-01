from __future__ import annotations

import json
import time
import uuid

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.businesses.models import TelegramBot
from apps.internal_api.auth import make_header
from core.crypto import encrypt
from core.telegram import sign_init_data

BOT_TOKEN = "7000000001:AAtestTOKENabcdefghijklmnopqrstuvwxyz"


def auth(api, user):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return api


def attach_bot(business, token: str = BOT_TOKEN, tg_id: int | None = None) -> TelegramBot:
    return TelegramBot.objects.create(
        business=business,
        bot_telegram_id=tg_id or int(token.split(":")[0]) + hash(business.slug) % 1000,
        username=f"{business.slug}_bot",
        token_encrypted=encrypt(token),
        webhook_secret="s" * 40,
    )


def init_data(user_id: int = 4242, token: str = BOT_TOKEN, **user) -> str:
    u = {"id": user_id, "first_name": "Ali", "language_code": "ar", **user}
    return sign_init_data(
        {"auth_date": str(int(time.time())), "query_id": "q1", "user": json.dumps(u)}, token
    )


def internal(api, method: str, path: str, data=None, headers=None):
    body = json.dumps(data).encode() if data is not None else b""
    hdr = make_header(settings.INTERNAL_API_SECRET, method, path, body, uuid.uuid4().hex)
    fn = getattr(api, method.lower())
    extra = {"HTTP_X_SERVICE_AUTH": hdr, **(headers or {})}
    if data is not None:
        return fn(path, data=body, content_type="application/json", **extra)
    return fn(path, **extra)
