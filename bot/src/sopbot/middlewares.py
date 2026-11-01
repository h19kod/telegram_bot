from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

from sopbot.api import ApiError, BackendClient
from sopbot.context import Ctx, UserPrefs
from sopbot.texts import t

logger = logging.getLogger(__name__)
Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


def _user(event: TelegramObject) -> Any:
    return getattr(event, "from_user", None)


class ThrottleMiddleware(BaseMiddleware):
    """At most one action per `interval` per user per bot (Redis-backed, multi-instance safe)."""

    def __init__(self, redis: Redis, interval: float):
        self.redis = redis
        self.interval_ms = int(interval * 1000)

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = _user(event)
        bot = data.get("bot")
        if user is None or bot is None:
            return await handler(event, data)
        key = f"sopbot:throttle:{bot.id}:{user.id}"
        if not await self.redis.set(key, 1, px=self.interval_ms, nx=True):
            if isinstance(event, CallbackQuery):
                ctx: Ctx | None = data.get("ctx")
                await event.answer(t("too_fast", ctx.lang if ctx else "ar"))
            return None
        return await handler(event, data)


class ContextMiddleware(BaseMiddleware):
    def __init__(self, registry: Any, api: BackendClient, prefs: UserPrefs):
        self.registry = registry
        self.api = api
        self.prefs = prefs

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        bot = data["bot"]
        info = self.registry.info_for(bot.id)
        user = _user(event)
        if info is None or user is None:
            return await handler(event, data)
        prefs = await self.prefs.get(info.id, user.id)
        lang = prefs.get("lang") or ("en" if (user.language_code or "").startswith("en") else "ar")
        data["ctx"] = Ctx(
            bot=info,
            api=self.api,
            prefs=self.prefs,
            tg_id=user.id,
            lang=lang,
            business=prefs.get("business"),
            currency=prefs.get("currency", "IQD"),
        )
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    """Turn backend business errors into friendly replies; never leak internals."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        started = time.monotonic()
        try:
            return await handler(event, data)
        except ApiError as exc:
            ctx: Ctx | None = data.get("ctx")
            lang = ctx.lang if ctx else "ar"
            text = exc.message if exc.status < 500 and exc.message else t("error_generic", lang)
            if exc.status >= 500:
                logger.warning("Backend error %s %s", exc.status, exc.code)
            await _reply(event, text)
        except Exception:
            logger.exception("Unhandled bot error")
            ctx = data.get("ctx")
            await _reply(event, t("error_generic", ctx.lang if ctx else "ar"))
        finally:
            elapsed = (time.monotonic() - started) * 1000
            if elapsed > 1500:
                logger.info("Slow update handled in %.0f ms", elapsed)
        return None


async def _reply(event: TelegramObject, text: str) -> None:
    try:
        if isinstance(event, CallbackQuery):
            await event.answer(text[:190], show_alert=True)
        elif isinstance(event, Message):
            await event.answer(text)
    except Exception:
        logger.debug("Could not deliver error reply", exc_info=True)
