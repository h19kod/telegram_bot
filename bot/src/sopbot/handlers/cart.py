from __future__ import annotations

from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from sopbot.context import Ctx
from sopbot.handlers.common import answer_cb
from sopbot.keyboards import CartQty, Nav, cart_kb, u
from sopbot.texts import money, t

router = Router(name="cart")


def cart_text(cart: dict[str, Any], ctx: Ctx) -> str:
    cur = cart.get("currency") or ctx.currency
    lines = [t("cart_title", ctx.lang), ""]
    for line in cart["lines"]:
        opts = (
            f" ({', '.join(escape(o['name']) for o in line['options'])})" if line["options"] else ""
        )
        mark = "" if line["available"] else "🚫 "
        lines.append(
            f"{mark}• {escape(line['name'])}{opts} × {line['quantity']} — "
            f"{money(line['line_total'], cur, ctx.lang)}"
        )
    lines += ["", t("cart_subtotal", ctx.lang, amount=money(cart["subtotal"], cur, ctx.lang))]
    if cart["has_problems"]:
        lines += ["", t("cart_problem", ctx.lang)]
    return "\n".join(lines)


async def show_cart(message: Message, ctx: Ctx, edit: bool = False) -> None:
    cart = await ctx.api.cart(ctx.bot_id, ctx.tg_id, ctx.business)
    if not cart["lines"]:
        text, kb = t("cart_empty", ctx.lang), None
    else:
        text, kb = cart_text(cart, ctx), cart_kb(cart, ctx.lang)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


@router.callback_query(Nav.filter(F.to == "cart"))
async def nav_cart(cb: CallbackQuery, ctx: Ctx) -> None:
    await answer_cb(cb)
    await show_cart(cb.message, ctx)


@router.callback_query(CartQty.filter())
async def on_cart_qty(cb: CallbackQuery, callback_data: CartQty, ctx: Ctx) -> None:
    await answer_cb(cb)
    await ctx.api.set_quantity(
        ctx.bot_id, ctx.tg_id, ctx.business, u(callback_data.item), max(0, min(99, callback_data.q))
    )
    await show_cart(cb.message, ctx, edit=True)


@router.callback_query(Nav.filter(F.to == "clear"))
async def on_clear(cb: CallbackQuery, ctx: Ctx) -> None:
    await answer_cb(cb)
    await ctx.api.clear_cart(ctx.bot_id, ctx.tg_id, ctx.business)
    await show_cart(cb.message, ctx, edit=True)
