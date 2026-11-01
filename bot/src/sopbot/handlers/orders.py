from __future__ import annotations

import contextlib
from html import escape
from typing import Any

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from sopbot.context import Ctx
from sopbot.handlers.common import answer_cb
from sopbot.keyboards import OrderCancel, OrderView, h, orders_kb, single, u
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
    return "\n".join(lines)


@router.callback_query(OrderView.filter())
async def on_order(cb: CallbackQuery, callback_data: OrderView, ctx: Ctx) -> None:
    await answer_cb(cb)
    o = await ctx.api.order(ctx.bot_id, ctx.tg_id, ctx.business, u(callback_data.id))
    kb: InlineKeyboardMarkup | None = None
    if o["can_cancel"]:
        kb = single(t("cancel_order", ctx.lang), OrderCancel(id=h(o["id"])))
    await cb.message.answer(order_text(o, ctx), reply_markup=kb)


@router.callback_query(OrderCancel.filter())
async def on_cancel(cb: CallbackQuery, callback_data: OrderCancel, ctx: Ctx) -> None:
    o = await ctx.api.cancel_order(ctx.bot_id, ctx.tg_id, ctx.business, u(callback_data.id))
    await answer_cb(cb, t("order_cancelled", ctx.lang, number=o["number"]))
    with contextlib.suppress(Exception):
        await cb.message.edit_text(order_text(o, ctx), reply_markup=None)
