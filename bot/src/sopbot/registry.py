"""Multi-bot registry: backend bot id ↔ aiogram Bot instance, loaded lazily from the backend."""

from __future__ import annotations

import asyncio
import hmac
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from sopbot.api import ApiError, BackendClient
from sopbot.context import BotInfo

logger = logging.getLogger(__name__)


class BotRegistry:
    def __init__(self, api: BackendClient):
        self.api = api
        self._by_backend_id: dict[str, tuple[Bot, BotInfo]] = {}
        self._by_telegram_id: dict[int, BotInfo] = {}
        self._lock = asyncio.Lock()

    async def get(self, bot_id: str) -> tuple[Bot, BotInfo] | None:
        if bot_id in self._by_backend_id:
            return self._by_backend_id[bot_id]
        async with self._lock:
            if bot_id in self._by_backend_id:
                return self._by_backend_id[bot_id]
            try:
                creds = await self.api.credentials(bot_id)
            except ApiError as exc:
                if exc.status == 404:
                    return None
                raise
            bot = Bot(
                creds["token"],
                default=DefaultBotProperties(
                    parse_mode=ParseMode.HTML, link_preview_is_disabled=True
                ),
            )
            info = BotInfo(
                id=creds["id"],
                telegram_id=bot.id,
                username=creds["username"],
                is_shared=creds["is_shared"],
                webhook_secret=creds["webhook_secret"],
            )
            self._by_backend_id[bot_id] = (bot, info)
            self._by_telegram_id[bot.id] = info
            return bot, info

    def info_for(self, telegram_bot_id: int) -> BotInfo | None:
        return self._by_telegram_id.get(telegram_bot_id)

    def verify_secret(self, info: BotInfo, header: str | None) -> bool:
        return bool(header) and hmac.compare_digest(info.webhook_secret, header or "")

    async def remove(self, bot_id: str) -> None:
        entry = self._by_backend_id.pop(bot_id, None)
        if entry:
            self._by_telegram_id.pop(entry[1].telegram_id, None)
            await entry[0].session.close()

    def loaded_ids(self) -> set[str]:
        return set(self._by_backend_id)

    async def close(self) -> None:
        for bot, _ in self._by_backend_id.values():
            await bot.session.close()
