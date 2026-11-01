"""Free-text messages: AI assistant when enabled for the business, else product search."""

from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sopbot.api import ApiError
from sopbot.context import Ctx
from sopbot.handlers.catalog import show_products
from sopbot.handlers.common import answer_cb
from sopbot.keyboards import AIConfirm, Nav, h, single, u
from sopbot.texts import t

router = Router(name="ai")


async def handle_free_text(message: Message, ctx: Ctx, state: FSMContext) -> None:
    text = message.text.strip()[:1000]
    prefs = await ctx.prefs.get(ctx.bot_id, ctx.tg_id)
    if not prefs.get("ai"):
        await show_products(message, ctx, "-", 1, edit=False, search=text[:100])
        return
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
        res = await ctx.api.ai_message(ctx.bot_id, ctx.tg_id, ctx.business, text)
    except ApiError as exc:
        if exc.code in ("ai_unavailable", "feature_not_available", "plan_limit_exceeded"):
            await show_products(message, ctx, "-", 1, edit=False, search=text[:100])
            return
        raise
    kb = None
    if res.get("proposal_id"):
        kb = single(t("ai_confirm", ctx.lang), AIConfirm(id=h(res["proposal_id"])))
    elif res.get("handed_over"):
        res["reply"] = res.get("reply") or t("ai_handover", ctx.lang)
    await message.answer(res.get("reply") or t("error_generic", ctx.lang), reply_markup=kb)


@router.callback_query(AIConfirm.filter())
async def on_ai_confirm(cb: CallbackQuery, callback_data: AIConfirm, ctx: Ctx) -> None:
    await ctx.api.ai_confirm(ctx.bot_id, ctx.tg_id, ctx.business, u(callback_data.id))
    await answer_cb(cb, "✅")
    with contextlib.suppress(Exception):
        await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        t("ai_added", ctx.lang), reply_markup=single(t("menu_cart", ctx.lang), Nav(to="cart"))
    )
