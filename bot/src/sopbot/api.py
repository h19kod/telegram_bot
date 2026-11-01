"""Typed client for the backend internal API (HMAC-signed, replay-protected)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from typing import Any

import httpx

from sopbot.config import settings

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def _sign(method: str, path: str, body: bytes) -> str:
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    msg = "\n".join([method.upper(), path, ts, nonce, hashlib.sha256(body).hexdigest()])
    sig = hmac.new(settings.internal_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"v1:{ts}:{nonce}:{sig}"


class BackendClient:
    def __init__(self, base_url: str | None = None, client: httpx.AsyncClient | None = None):
        self.base_url = (base_url or settings.backend_url).rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        data: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        lang: str | None = None,
    ) -> Any:
        query = httpx.QueryParams({k: v for k, v in (params or {}).items() if v is not None})
        full_path = f"/internal/v1/{path.lstrip('/')}" + (f"?{query}" if query else "")
        body = json.dumps(data).encode() if data is not None else b""
        hdrs = {
            "X-Service-Auth": _sign(method, full_path, body),
            "Content-Type": "application/json",
            **(headers or {}),
        }
        if lang:
            hdrs["Accept-Language"] = lang
        for attempt in range(3):
            try:
                resp = await self._client.request(
                    method, self.base_url + full_path, content=body, headers=hdrs
                )
                break
            except httpx.TransportError:
                if attempt == 2:
                    raise ApiError(503, "backend_unavailable", "") from None
                hdrs["X-Service-Auth"] = _sign(method, full_path, body)
        if resp.status_code >= 400:
            try:
                err = resp.json()["error"]
            except (ValueError, KeyError, TypeError):
                err = {"code": "error", "message": ""}
            raise ApiError(
                resp.status_code,
                err.get("code", "error"),
                err.get("message", ""),
                err.get("details"),
            )
        return resp.json() if resp.content else None

    # --- bots ---
    async def bots(self) -> list[dict[str, Any]]:
        return await self.request("GET", "bots")

    async def credentials(self, bot_id: str) -> dict[str, Any]:
        return await self.request("GET", f"bots/{bot_id}/credentials")

    # --- session & catalog ---
    async def session(self, bot_id: str, user: dict[str, Any], business: str | None) -> dict:
        return await self.request(
            "POST", f"bots/{bot_id}/session", {"user": user, "business": business}
        )

    async def categories(self, bot_id: str, business: str | None, lang: str) -> list[dict]:
        return await self.request(
            "GET", f"bots/{bot_id}/catalog/categories", params={"business": business, "lang": lang}
        )

    async def products(
        self,
        bot_id: str,
        business: str | None,
        lang: str,
        *,
        category: str | None = None,
        search: str | None = None,
        page: int = 1,
    ) -> dict:
        return await self.request(
            "GET",
            f"bots/{bot_id}/catalog/products",
            params={
                "business": business,
                "lang": lang,
                "category": category,
                "search": search,
                "page": page,
            },
        )

    async def product(self, bot_id: str, business: str | None, lang: str, product_id: str) -> dict:
        return await self.request(
            "GET",
            f"bots/{bot_id}/catalog/products/{product_id}",
            params={"business": business, "lang": lang},
        )

    async def zones(self, bot_id: str, business: str | None, lang: str) -> list[dict]:
        return await self.request(
            "GET", f"bots/{bot_id}/zones", params={"business": business, "lang": lang}
        )

    # --- customer scoped ---
    def _c(self, bot_id: str, tg_id: int, tail: str) -> str:
        return f"bots/{bot_id}/customers/{tg_id}/{tail}"

    async def cart(self, bot_id: str, tg_id: int, business: str | None) -> dict:
        return await self.request(
            "GET", self._c(bot_id, tg_id, "cart"), params={"business": business}
        )

    async def clear_cart(self, bot_id: str, tg_id: int, business: str | None) -> dict:
        return await self.request(
            "DELETE", self._c(bot_id, tg_id, "cart"), params={"business": business}
        )

    async def add_to_cart(
        self,
        bot_id: str,
        tg_id: int,
        business: str | None,
        product_id: str,
        option_ids: list[str],
        quantity: int,
    ) -> dict:
        return await self.request(
            "POST",
            self._c(bot_id, tg_id, "cart/items"),
            {"product_id": product_id, "option_ids": option_ids, "quantity": quantity},
            params={"business": business},
        )

    async def set_quantity(
        self, bot_id: str, tg_id: int, business: str | None, item_id: str, quantity: int
    ) -> dict:
        return await self.request(
            "PATCH",
            self._c(bot_id, tg_id, f"cart/items/{item_id}"),
            {"quantity": quantity},
            params={"business": business},
        )

    async def quote(self, bot_id: str, tg_id: int, business: str | None, data: dict) -> dict:
        return await self.request(
            "POST", self._c(bot_id, tg_id, "checkout/quote"), data, params={"business": business}
        )

    async def checkout(
        self, bot_id: str, tg_id: int, business: str | None, data: dict, idempotency_key: str
    ) -> dict:
        uuid.UUID(idempotency_key)
        return await self.request(
            "POST",
            self._c(bot_id, tg_id, "checkout"),
            data,
            params={"business": business},
            headers={"Idempotency-Key": idempotency_key},
        )

    async def orders(self, bot_id: str, tg_id: int, business: str | None) -> list[dict]:
        return await self.request(
            "GET", self._c(bot_id, tg_id, "orders"), params={"business": business}
        )

    async def order(self, bot_id: str, tg_id: int, business: str | None, order_id: str) -> dict:
        return await self.request(
            "GET", self._c(bot_id, tg_id, f"orders/{order_id}"), params={"business": business}
        )

    async def cancel_order(
        self, bot_id: str, tg_id: int, business: str | None, order_id: str
    ) -> dict:
        return await self.request(
            "POST",
            self._c(bot_id, tg_id, f"orders/{order_id}/cancel"),
            {},
            params={"business": business},
        )

    async def set_language(self, bot_id: str, tg_id: int, business: str | None, lang: str) -> dict:
        return await self.request(
            "PATCH", self._c(bot_id, tg_id, "me"), {"language": lang}, params={"business": business}
        )

    async def support(self, bot_id: str, tg_id: int, business: str | None, message: str) -> dict:
        return await self.request(
            "POST",
            self._c(bot_id, tg_id, "support"),
            {"message": message},
            params={"business": business},
        )

    # --- staff ---
    async def staff_transition(
        self,
        bot_id: str,
        order_id: str,
        to: str,
        version: int,
        telegram_user_id: int,
        reason: str = "",
    ) -> dict:
        return await self.request(
            "POST",
            f"bots/{bot_id}/staff/transition",
            {
                "order_id": order_id,
                "to": to,
                "expected_version": version,
                "telegram_user_id": telegram_user_id,
                "reason": reason,
            },
        )

    async def staff_link(self, bot_id: str, code: str, user: dict[str, Any]) -> dict:
        return await self.request("POST", f"bots/{bot_id}/staff/link", {"code": code, "user": user})

    # --- AI ---
    async def ai_message(self, bot_id: str, tg_id: int, business: str | None, text: str) -> dict:
        return await self.request(
            "POST",
            self._c(bot_id, tg_id, "ai/message"),
            {"text": text},
            params={"business": business},
        )

    async def ai_confirm(
        self, bot_id: str, tg_id: int, business: str | None, proposal_id: str
    ) -> dict:
        return await self.request(
            "POST",
            self._c(bot_id, tg_id, f"ai/proposals/{proposal_id}/confirm"),
            {},
            params={"business": business},
        )
