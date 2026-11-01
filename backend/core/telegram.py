"""Telegram helpers used by the backend: initData validation and a small Bot API client."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class InitDataError(ValueError):
    pass


@dataclass(frozen=True)
class WebAppUser:
    id: int
    first_name: str
    last_name: str
    username: str
    language_code: str


def validate_init_data(init_data: str, bot_token: str, max_age: int | None = None) -> WebAppUser:
    """Validate Telegram Mini App initData per the official algorithm.

    secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
    hash       = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))
    """
    if not init_data or not bot_token:
        raise InitDataError("missing")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise InitDataError("malformed") from exc
    data = dict(pairs)
    if len(data) != len(pairs):
        raise InitDataError("duplicate keys")
    received_hash = data.pop("hash", "")
    if not received_hash:
        raise InitDataError("missing hash")
    check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("bad hash")
    max_age = settings.TELEGRAM_INIT_DATA_MAX_AGE_SECONDS if max_age is None else max_age
    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("bad auth_date") from exc
    if auth_date <= 0 or time.time() - auth_date > max_age or auth_date - time.time() > 60:
        raise InitDataError("expired")
    try:
        user = json.loads(data["user"])
        return WebAppUser(
            id=int(user["id"]),
            first_name=str(user.get("first_name", ""))[:128],
            last_name=str(user.get("last_name", ""))[:128],
            username=str(user.get("username", ""))[:64],
            language_code=str(user.get("language_code", ""))[:8],
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise InitDataError("bad user") from exc


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Produce valid initData (used by tests and the documented browser dev mode)."""
    from urllib.parse import urlencode

    check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


class TelegramAPIError(Exception):
    def __init__(self, description: str, error_code: int = 0, retry_after: int | None = None):
        super().__init__(description)
        self.description = description
        self.error_code = error_code
        self.retry_after = retry_after


class BotAPI:
    """Synchronous Bot API client. The token lives in the URL, so httpx logging is silenced."""

    def __init__(self, token: str, timeout: float = 10.0):
        self._base = f"{settings.TELEGRAM_API_BASE}/bot{token}"
        self._timeout = timeout

    def call(self, method: str, **params: Any) -> Any:
        payload = {k: v for k, v in params.items() if v is not None}
        try:
            resp = httpx.post(f"{self._base}/{method}", json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise TelegramAPIError(f"network error: {type(exc).__name__}") from None
        try:
            body = resp.json()
        except ValueError:
            raise TelegramAPIError(f"bad response {resp.status_code}", resp.status_code) from None
        if not body.get("ok"):
            raise TelegramAPIError(
                body.get("description", "unknown error"),
                body.get("error_code", resp.status_code),
                (body.get("parameters") or {}).get("retry_after"),
            )
        return body.get("result")

    def get_me(self) -> dict[str, Any]:
        return self.call("getMe")

    def set_webhook(self, url: str, secret_token: str) -> None:
        self.call(
            "setWebhook",
            url=url,
            secret_token=secret_token,
            drop_pending_updates=False,
            allowed_updates=["message", "callback_query", "my_chat_member"],
            max_connections=40,
        )

    def delete_webhook(self) -> None:
        self.call("deleteWebhook")

    def send_message(self, chat_id: int, text: str, reply_markup: Any = None) -> dict[str, Any]:
        return self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            link_preview_options={"is_disabled": True},
        )

    def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: Any = None
    ) -> Any:
        return self.call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            link_preview_options={"is_disabled": True},
        )
