from __future__ import annotations

import contextlib
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from sopbot.context import Ctx
from sopbot.handlers.common import answer_cb
from sopbot.keyboards import (
    AddCart,
    Cat,
    Nav,
    Opt,
    Prod,
    Qty,
    categories_kb,
    product_kb,
    products_kb,
    u,
)
from sopbot.texts import money, t

router = Router(name="catalog")


class SearchState(StatesGroup):
    query = State()


async def show_categories(message: Message, ctx: Ctx, edit: bool = False) -> None:
    cats = await ctx.api.categories(ctx.bot_id, ctx.business, ctx.lang)
    text = t("categories_title", ctx.lang) if cats else t("no_categories", ctx.lang)
    kb = categories_kb(cats, ctx.lang)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


async def show_products(
    message: Message, ctx: Ctx, cat: str, page: int, edit: bool, search: str | None = None
) -> None:
    data = await ctx.api.products(
        ctx.bot_id,
        ctx.business,
        ctx.lang,
        category=u(cat) if cat != "-" else None,
        search=search,
        page=page,
    )
    if not data["results"]:
        await message.answer(t("no_products", ctx.lang))
        return
    if search:
        title = t("search_results", ctx.lang, q=escape(search))
    else:
        title = t(
            "products_title",
            ctx.lang,
            title=data["results"][0]["category_name"]
            if cat != "-"
            else t("all_products", ctx.lang),
            page=data["page"],
            pages=data["pages"],
        )
    kb = products_kb(data, cat, ctx.lang, ctx.currency)
    if edit:
        try:
            await message.edit_text(title, reply_markup=kb)
            return
        except Exception:
            pass
    await message.answer(title, reply_markup=kb)


@router.callback_query(Nav.filter(F.to == "cats"))
async def nav_cats(cb: CallbackQuery, ctx: Ctx) -> None:
    await answer_cb(cb)
    await show_categories(cb.message, ctx, edit=True)


@router.callback_query(Cat.filter())
async def on_category(cb: CallbackQuery, callback_data: Cat, ctx: Ctx) -> None:
    await answer_cb(cb)
    await show_products(cb.message, ctx, callback_data.id, callback_data.page, edit=True)


def product_caption(p: dict[str, Any], ctx: Ctx) -> str:
    lines = [f"<b>{escape(p['name'])}</b>"]
    if p.get("description"):
        lines.append(escape(p["description"])[:700])
    price = money(p["price"], ctx.currency, ctx.lang)
    if p.get("compare_at_price"):
        old = money(p["compare_at_price"], ctx.currency, ctx.lang)
        price = f"{price}  <s>{old}</s>  🔥 -{p['discount_percent']}%"
    lines.append(f"💰 {price}")
    if not p["is_available"]:
        lines.append(f"🚫 {t('unavailable', ctx.lang)}")
    return "\n\n".join(lines)


def _defaults(p: dict[str, Any]) -> list[str]:
    out = []
    for g in p["option_groups"]:
        defaults = [o["id"] for o in g["options"] if o["is_default"] and o["is_available"]]
        out.extend(defaults[: g["max_select"]])
    return out


@router.callback_query(Prod.filter())
async def on_product(cb: CallbackQuery, callback_data: Prod, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    p = await ctx.api.product(ctx.bot_id, ctx.business, ctx.lang, u(callback_data.id))
    selected = _defaults(p)
    await state.update_data(sel={"pid": p["id"], "opts": selected, "qty": 1})
    kb = product_kb(p, selected, 1, ctx.lang, ctx.currency)
    caption = product_caption(p, ctx)
    image = p["images"][0]["url"] if p["images"] else None
    if image and image.startswith("http"):
        await cb.message.answer_photo(image, caption=caption, reply_markup=kb)
    else:
        await cb.message.answer(caption, reply_markup=kb)


async def _selection(state: FSMContext) -> dict[str, Any] | None:
    return (await state.get_data()).get("sel")


async def _refresh(cb: CallbackQuery, ctx: Ctx, state: FSMContext, sel: dict[str, Any]) -> None:
    p = await ctx.api.product(ctx.bot_id, ctx.business, ctx.lang, sel["pid"])
    await state.update_data(sel=sel)
    with contextlib.suppress(Exception):
        await cb.message.edit_reply_markup(
            reply_markup=product_kb(p, sel["opts"], sel["qty"], ctx.lang, ctx.currency)
        )


@router.callback_query(Opt.filter())
async def on_option(cb: CallbackQuery, callback_data: Opt, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    sel = await _selection(state)
    if not sel:
        return
    p = await ctx.api.product(ctx.bot_id, ctx.business, ctx.lang, sel["pid"])
    oid = u(callback_data.id)
    group = next((g for g in p["option_groups"] if any(o["id"] == oid for o in g["options"])), None)
    if group is None:
        return
    group_ids = {o["id"] for o in group["options"]}
    current = [i for i in sel["opts"] if i in group_ids]
    others = [i for i in sel["opts"] if i not in group_ids]
    if group["selection_type"] == "single":
        current = [oid]
    elif oid in current:
        current.remove(oid)
    elif len(current) < group["max_select"]:
        current.append(oid)
    sel["opts"] = others + current
    await _refresh(cb, ctx, state, sel)


@router.callback_query(Qty.filter())
async def on_qty(cb: CallbackQuery, callback_data: Qty, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    sel = await _selection(state)
    if not sel:
        return
    sel["qty"] = max(1, min(99, sel["qty"] + callback_data.d))
    await _refresh(cb, ctx, state, sel)


@router.callback_query(AddCart.filter())
async def on_add(cb: CallbackQuery, ctx: Ctx, state: FSMContext) -> None:
    sel = await _selection(state)
    if not sel:
        await answer_cb(cb)
        return
    p = await ctx.api.product(ctx.bot_id, ctx.business, ctx.lang, sel["pid"])
    for g in p["option_groups"]:
        chosen = [o for o in g["options"] if o["id"] in sel["opts"]]
        if len(chosen) < g["min_select"]:
            await answer_cb(cb, t("choose_required", ctx.lang, group=g["name"]), alert=True)
            return
    await ctx.api.add_to_cart(
        ctx.bot_id, ctx.tg_id, ctx.business, sel["pid"], sel["opts"], sel["qty"]
    )
    await answer_cb(cb, t("added", ctx.lang))
    await state.update_data(sel=None)
    from sopbot.keyboards import single

    await cb.message.answer(
        t("added", ctx.lang), reply_markup=single(t("menu_cart", ctx.lang), Nav(to="cart"))
    )


@router.callback_query(Nav.filter(F.to == "search"))
async def nav_search(cb: CallbackQuery, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    await state.set_state(SearchState.query)
    await cb.message.answer(t("search_prompt", ctx.lang))


@router.message(SearchState.query, F.text)
async def on_search(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await state.set_state(None)
    q = message.text.strip()[:100]
    await show_products(message, ctx, "-", 1, edit=False, search=q)
