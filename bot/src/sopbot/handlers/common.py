from __future__ import annotations

import contextlib
from typing import Any

from aiogram.types import CallbackQuery, Message

from sopbot.context import Ctx
from sopbot.keyboards import BranchPick, main_menu, single, store_button
from sopbot.texts import t


async def ensure_session(ctx: Ctx, user: Any, business: str | None = None) -> dict[str, Any]:
    """Register/refresh the customer and return business info (cached in prefs)."""
    slug = business or ctx.business
    data = await ctx.api.session(
        ctx.bot_id,
        {
            "id": user.id,
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "username": user.username or "",
            "language_code": user.language_code or "",
        },
        slug if ctx.bot.is_shared else None,
    )
    info = data["business"]
    prefs = await ctx.prefs.get(ctx.bot_id, ctx.tg_id)
    lang = prefs.get("lang") or data["customer"]["language"]
    ctx.lang = lang
    ctx.business = info["slug"]
    ctx.currency = info["currency"]
    await ctx.prefs.update(
        ctx.bot_id,
        ctx.tg_id,
        business=info["slug"],
        lang=lang,
        currency=info["currency"],
        ai=info.get("ai_enabled", False),
        mini_app=data.get("mini_app_url"),
    )
    data["lang"] = lang
    return data


def needs_business(ctx: Ctx) -> bool:
    return ctx.bot.is_shared and not ctx.business


async def send_welcome(message: Message, ctx: Ctx, data: dict[str, Any]) -> None:
    info = data["business"]
    lang = ctx.lang
    text = info.get("welcome_message") or t("welcome", lang, name=info["name"])
    if not info["is_active"]:
        text += "\n\n" + t("business_inactive", lang)
    elif not info["is_open"]:
        text += "\n\n" + t("closed_now", lang)
    await message.answer(text, reply_markup=main_menu(lang))
    if len(info.get("branches") or []) > 1:
        await message.answer(
            t("your_branch", lang, name=info["branch"]["name"]),
            reply_markup=single(t("change_branch", lang), BranchPick(id="")),
        )
    kb = store_button(lang, data.get("mini_app_url"))
    if kb:
        await message.answer("👇", reply_markup=kb)


async def answer_cb(cb: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    with contextlib.suppress(Exception):
        await cb.answer(text, show_alert=alert)
