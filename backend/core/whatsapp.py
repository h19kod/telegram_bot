"""WhatsApp delivery of one-time phone verification codes. Swap providers via WHATSAPP_PROVIDER.

- ``cloud``    Meta WhatsApp Cloud API, an approved *authentication* template (body + copy-code
               button, both carrying the code). Production.
- ``console``  Logs the code (DEBUG only, refused otherwise). Local development without Meta.
- ``memory``   Keeps sent codes in ``outbox`` (tests).
- ``disabled`` No sender: phone verification is switched off platform-wide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class WhatsAppError(Exception):
    def __init__(self, description: str, retryable: bool = False):
        super().__init__(description)
        self.retryable = retryable


class Sender(Protocol):
    def send_code(self, phone: str, code: str, lang: str) -> None: ...


@dataclass
class SentCode:
    phone: str
    code: str
    lang: str


class MemorySender:
    outbox: list[SentCode] = []

    def send_code(self, phone: str, code: str, lang: str) -> None:
        self.outbox.append(SentCode(phone, code, lang))


class ConsoleSender:
    def send_code(self, phone: str, code: str, lang: str) -> None:
        logger.warning("DEV WhatsApp code for %s: %s", phone, code)


class CloudSender:
    """POST /{phone-number-id}/messages with the authentication template (Graph API)."""

    def __init__(self) -> None:
        if not (settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID):
            raise ImproperlyConfigured("WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID are required")
        self._url = f"{settings.WHATSAPP_API_BASE}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    def send_code(self, phone: str, code: str, lang: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": phone.lstrip("+"),
            "type": "template",
            "template": {
                "name": settings.WHATSAPP_OTP_TEMPLATE,
                "language": {"code": "en" if lang == "en" else settings.WHATSAPP_TEMPLATE_LANG},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": code}]},
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": "0",
                        "parameters": [{"type": "text", "text": code}],
                    },
                ],
            },
        }
        try:
            resp = httpx.post(
                self._url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise WhatsAppError(f"network error: {type(exc).__name__}", retryable=True) from None
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
            except ValueError:
                err = {}
            raise WhatsAppError(
                f"{resp.status_code} {err.get('code', '')} {err.get('message', '')}".strip(),
                retryable=resp.status_code == 429 or resp.status_code >= 500,
            )


def is_enabled() -> bool:
    return settings.WHATSAPP_PROVIDER != "disabled"


def get_sender() -> Sender:
    match settings.WHATSAPP_PROVIDER:
        case "cloud":
            return CloudSender()
        case "console":
            if not settings.DEBUG:
                raise ImproperlyConfigured("WHATSAPP_PROVIDER=console is only allowed with DEBUG")
            return ConsoleSender()
        case "memory":
            return MemorySender()
        case other:
            raise ImproperlyConfigured(f"WhatsApp provider unavailable: {other}")
