"""Per-update context: which backend bot, which business (shared bot), user language."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from sopbot.api import BackendClient


@dataclass
class BotInfo:
    id: str
    telegram_id: int
    username: str
    is_shared: bool
    webhook_secret: str


@dataclass
class Ctx:
    bot: BotInfo
    api: BackendClient
    prefs: UserPrefs
    tg_id: int
    lang: str
    business: str | None  # slug; only meaningful for the shared bot
    currency: str

    @property
    def bot_id(self) -> str:
        return self.bot.id

    async def set_lang(self, lang: str) -> None:
        self.lang = lang
        await self.prefs.update(self.bot.id, self.tg_id, lang=lang)


class UserPrefs:
    """Small per-chat preferences that survive FSM state resets."""

    def __init__(self, redis: Redis):
        self.redis = redis

    def _key(self, bot_id: str, tg_id: int) -> str:
        return f"sopbot:prefs:{bot_id}:{tg_id}"

    async def get(self, bot_id: str, tg_id: int) -> dict[str, Any]:
        raw = await self.redis.get(self._key(bot_id, tg_id))
        return json.loads(raw) if raw else {}

    async def update(self, bot_id: str, tg_id: int, **values: Any) -> dict[str, Any]:
        data = await self.get(bot_id, tg_id)
        data.update({k: v for k, v in values.items() if v is not None})
        await self.redis.set(self._key(bot_id, tg_id), json.dumps(data), ex=60 * 60 * 24 * 90)
        return data
