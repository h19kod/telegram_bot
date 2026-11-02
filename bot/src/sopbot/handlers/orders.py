from __future__ import annotations

import contextlib
from html import escape
from typing import Any

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from sopbot.api import ApiError
from sopbot.context import Ctx
from sopbot.handlers.common import answer_cb
from sopbot.keyboards import OrderCancel, OrderRate, OrderView, h, orders_kb, single, u
from sopbot.texts import money, status_label, t

router = Router(name="orders")


async def show_orders(message: Message, ctx: Ctx) -> None:
    orders = await ctx.api.orders(ctx.bot_id, ctx.tg_id, ctx.business)
    if not orders:
        await message.answer(t("no_orders", ctx.lang))
        return
    await message.answer(t("orders_title", ctx.lang), reply_markup=orders_kb(orders, ctx.lang))


def order_text(o: dict[str, Any], ctx: Ctx) -> str:
    cur = o["currency"]
    lines = [f"🧾 <b>#{o['number']}</b> — {status_label(o['status'], ctx.lang)}", ""]
    for i in o["items"]:
        opts = f" ({', '.join(escape(x) for x in i['options'])})" if i["options"] else ""
        lines.append(
            f"• {escape(i['name'])}{opts} × {i['quantity']} — "
            f"{money(i['line_total'], cur, ctx.lang)}"
        )
    lines.append("")
    if o["delivery_fee"]:
        lines.append(f"{t('delivery_fee', ctx.lang)}: {money(o['delivery_fee'], cur, ctx.lang)}")
    lines.append(f"<b>{t('total', ctx.lang)}: {money(o['total'], cur, ctx.lang)}</b>")
    if o["timeline"]:
        lines.append("")
        for ev in o["timeline"]:
            lines.append(f"▫️ {status_label(ev['status'], ctx.lang)} — {ev['at'][11:16]}")
    if o.get("cancel_reason") and o["status"] in ("cancelled", "rejected"):
        lines.append(f"\n{escape(o['cancel_reason'])}")
    if review := o.get("review"):
        lines.append(f"\n{t('your_rating', ctx.lang)}: {'⭐' * review['rating']}")
        if review.get("reply"):
            lines.append(f"💬 {t('shop_reply', ctx.lang)}: {escape(review['reply'])}")
    elif o.get("can_review"):
        lines.append(f"\n{t('rate_order', ctx.lang)}")
    return "\n".join(lines)


def order_kb(o: dict[str, Any], ctx: Ctx) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if o.get("can_review") and not o.get("review"):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{n}⭐", callback_data=OrderRate(id=h(o["id"]), stars=n).pack()
                )
                for n in range(1, 6)
            ]
        )
    if o["can_cancel"]:
        return single(t("cancel_order", ctx.lang), OrderCancel(id=h(o["id"])))
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@router.callback_query(OrderView.filter())
async def on_order(cb: CallbackQuery, callback_data: OrderView, ctx: Ctx) -> None:
    await answer_cb(cb)
    o = await ctx.api.order(ctx.bot_id, ctx.tg_id, ctx.business, u(callback_data.id))
    await cb.message.answer(order_text(o, ctx), reply_markup=order_kb(o, ctx))


@router.callback_query(OrderRate.filter())
async def on_rate(cb: CallbackQuery, callback_data: OrderRate, ctx: Ctx) -> None:
    try:
        o = await ctx.api.review_order(
            ctx.bot_id, ctx.tg_id, ctx.business, u(callback_data.id), callback_data.stars
        )
    except ApiError as e:
        await answer_cb(cb, e.message)
        return
    await answer_cb(cb, t("thanks_rating", ctx.lang))
    with contextlib.suppress(Exception):
        await cb.message.edit_text(order_text(o, ctx), reply_markup=order_kb(o, ctx))


@router.callback_query(OrderCancel.filter())
async def on_cancel(cb: CallbackQuery, callback_data: OrderCancel, ctx: Ctx) -> None:
    o = await ctx.api.cancel_order(ctx.bot_id, ctx.tg_id, ctx.business, u(callback_data.id))
    await answer_cb(cb, t("order_cancelled", ctx.lang, number=o["number"]))
    with contextlib.suppress(Exception):
        await cb.message.edit_text(order_text(o, ctx), reply_markup=None)
