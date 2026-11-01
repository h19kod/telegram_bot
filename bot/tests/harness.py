"""Drive the real dispatcher with fake Telegram transport and a mocked backend."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from sopbot.context import BotInfo

_ids = itertools.count(1)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None
                           ) -> Any:
        self.calls.append(method)
        name = type(method).__name__
        if name in ("SendMessage", "SendPhoto", "EditMessageText"):
            return Message(message_id=next(_ids), date=datetime.now(UTC),
                           chat=Chat(id=getattr(method, "chat_id", 1) or 1, type="private"),
                           text=getattr(method, "text", None) or "x")
        return True

    async def close(self) -> None:
        pass

    async def stream_content(self, *a: Any, **k: Any):  # pragma: no cover
        yield b""

    def texts(self) -> list[str]:
        return [getattr(c, "text", None) or getattr(c, "caption", None) or ""
                for c in self.calls if type(c).__name__ in ("SendMessage", "SendPhoto",
                                                            "EditMessageText")]

    def alerts(self) -> list[str]:
        return [c.text or "" for c in self.calls if type(c).__name__ == "AnswerCallbackQuery"]

    def last_markup(self) -> Any:
        for c in reversed(self.calls):
            markup = getattr(c, "reply_markup", None)
            if markup is not None and hasattr(markup, "inline_keyboard"):
                return markup
        return None


class StaticRegistry:
    def __init__(self, bot: Bot, info: BotInfo):
        self.bot, self.info = bot, info

    def info_for(self, telegram_bot_id: int) -> BotInfo | None:
        return self.info if telegram_bot_id == self.bot.id else None


USER = User(id=9001, is_bot=False, first_name="Ali", language_code="ar")
CHAT = Chat(id=9001, type="private")
_upd = itertools.count(1)


def msg_update(text: str | None = None, **extra: Any) -> Update:
    m = Message(message_id=next(_ids), date=datetime.now(UTC), chat=CHAT, from_user=USER,
                text=text, **extra)
    return Update(update_id=next(_upd), message=m)


def cb_update(data: str, user: User = USER) -> Update:
    m = Message(message_id=next(_ids), date=datetime.now(UTC), chat=CHAT, text="x")
    cq = CallbackQuery(id=str(next(_ids)), from_user=user, chat_instance="ci", data=data,
                       message=m)
    return Update(update_id=next(_upd), callback_query=cq)


def find_button(markup: Any, prefix: str) -> str:
    for row in markup.inline_keyboard:
        for b in row:
            if b.callback_data and b.callback_data.startswith(prefix):
                return b.callback_data
    raise AssertionError(f"no button {prefix!r} in {markup}")
