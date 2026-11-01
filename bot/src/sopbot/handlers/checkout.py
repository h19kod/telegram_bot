"""Checkout conversation. The order is confirmed to the customer only after the backend
returns it — never before."""

from __future__ import annotations

import contextlib
import uuid
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from sopbot.api import ApiError
from sopbot.context import Ctx
from sopbot.handlers.common import answer_cb, ensure_session
from sopbot.keyboards import (
    REMOVE,
    Confirm,
    Ful,
    Nav,
    Skip,
    Use,
    Zone,
    confirm_kb,
    fulfilment_kb,
    location_kb,
    main_menu,
    phone_kb,
    single,
    u,
    zones_kb,
)
from sopbot.texts import money, t

router = Router(name="checkout")


class Checkout(StatesGroup):
    name = State()
    phone = State()
    fulfilment = State()
    zone = State()
    area = State()
    landmark = State()
    location = State()
    notes = State()
    confirm = State()


async def _co(state: FSMContext) -> dict[str, Any]:
    return (await state.get_data()).get("co", {})


async def _save(state: FSMContext, **kw: Any) -> dict[str, Any]:
    co = await _co(state)
    co.update(kw)
    await state.update_data(co=co)
    return co


@router.callback_query(Nav.filter(F.to == "checkout"))
async def begin(cb: CallbackQuery, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    cart = await ctx.api.cart(ctx.bot_id, ctx.tg_id, ctx.business)
    if not cart["lines"]:
        await cb.message.answer(t("cart_empty", ctx.lang))
        return
    if cart["has_problems"]:
        await cb.message.answer(t("cart_problem", ctx.lang))
        return
    session = await ensure_session(ctx, cb.from_user)
    customer, info = session["customer"], session["business"]
    await state.set_state(Checkout.name)
    await state.update_data(
        co={
            "known_name": customer.get("full_name") or "",
            "known_phone": customer.get("phone") or "",
            "info": {
                "accepts_delivery": info["accepts_delivery"],
                "accepts_pickup": info["accepts_pickup"],
                "allow_notes": info["allow_order_notes"],
            },
        }
    )
    known = customer.get("full_name") or cb.from_user.full_name
    kb = single(t("use_value", ctx.lang, v=known), Use(step="name")) if known else None
    await state.update_data(co={**(await _co(state)), "suggest_name": known})
    await cb.message.answer(t("ask_name", ctx.lang), reply_markup=kb)


@router.callback_query(Checkout.name, Use.filter(F.step == "name"))
async def name_use(cb: CallbackQuery, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    co = await _co(state)
    await _after_name(cb.message, ctx, state, co.get("suggest_name", ""))


@router.message(Checkout.name, F.text)
async def name_text(message: Message, ctx: Ctx, state: FSMContext) -> None:
    name = message.text.strip()
    if not 2 <= len(name) <= 150:
        await message.answer(t("ask_name", ctx.lang))
        return
    await _after_name(message, ctx, state, name)


async def _after_name(message: Message, ctx: Ctx, state: FSMContext, name: str) -> None:
    co = await _save(state, customer_name=name)
    await state.set_state(Checkout.phone)
    await message.answer(t("ask_phone", ctx.lang), reply_markup=phone_kb(ctx.lang))
    if co.get("known_phone"):
        await message.answer(
            "☝️",
            reply_markup=single(t("use_value", ctx.lang, v=co["known_phone"]), Use(step="phone")),
        )


@router.callback_query(Checkout.phone, Use.filter(F.step == "phone"))
async def phone_use(cb: CallbackQuery, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    co = await _co(state)
    await _after_phone(cb.message, ctx, state, co["known_phone"])


@router.message(Checkout.phone, F.contact)
async def phone_contact(message: Message, ctx: Ctx, state: FSMContext) -> None:
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer(t("bad_phone", ctx.lang))
        return
    await _after_phone(message, ctx, state, message.contact.phone_number)


@router.message(Checkout.phone, F.text)
async def phone_text(message: Message, ctx: Ctx, state: FSMContext) -> None:
    digits = "".join(ch for ch in message.text if ch.isdigit() or ch == "+")
    if len(digits) < 10:
        await message.answer(t("bad_phone", ctx.lang))
        return
    await _after_phone(message, ctx, state, message.text.strip())


async def _after_phone(message: Message, ctx: Ctx, state: FSMContext, phone: str) -> None:
    co = await _save(state, customer_phone=phone)
    info = co["info"]
    if info["accepts_delivery"] and info["accepts_pickup"]:
        await state.set_state(Checkout.fulfilment)
        await message.answer("✔️", reply_markup=REMOVE)
        await message.answer(
            t("ask_fulfilment", ctx.lang), reply_markup=fulfilment_kb(info, ctx.lang)
        )
    elif info["accepts_delivery"]:
        await message.answer("✔️", reply_markup=REMOVE)
        await _ask_zone(message, ctx, state)
    else:
        await _save(state, fulfilment="pickup")
        await message.answer("✔️", reply_markup=REMOVE)
        await _ask_notes_or_summary(message, ctx, state)


@router.callback_query(Checkout.fulfilment, Ful.filter())
async def on_fulfilment(cb: CallbackQuery, callback_data: Ful, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    if callback_data.v == "pickup":
        await _save(state, fulfilment="pickup")
        await _ask_notes_or_summary(cb.message, ctx, state)
    else:
        await _ask_zone(cb.message, ctx, state)


async def _ask_zone(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await _save(state, fulfilment="delivery")
    zones = await ctx.api.zones(ctx.bot_id, ctx.business, ctx.lang)
    if not zones:
        await message.answer(t("no_zones", ctx.lang))
        co = await _co(state)
        if co["info"]["accepts_pickup"]:
            await _save(state, fulfilment="pickup")
            await _ask_notes_or_summary(message, ctx, state)
        else:
            await state.clear()
        return
    await state.set_state(Checkout.zone)
    await message.answer(
        t("ask_zone", ctx.lang), reply_markup=zones_kb(zones, ctx.lang, ctx.currency)
    )


@router.callback_query(Checkout.zone, Zone.filter())
async def on_zone(cb: CallbackQuery, callback_data: Zone, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    await _save(state, zone_id=u(callback_data.id))
    await state.set_state(Checkout.area)
    await cb.message.answer(t("ask_area", ctx.lang))


@router.message(Checkout.area, F.text)
async def on_area(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await _save(state, address_area=message.text.strip()[:120])
    await state.set_state(Checkout.landmark)
    await message.answer(t("ask_landmark", ctx.lang))


@router.message(Checkout.landmark, F.text)
async def on_landmark(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await _save(state, address_landmark=message.text.strip()[:200])
    await state.set_state(Checkout.location)
    await message.answer(t("ask_location", ctx.lang), reply_markup=location_kb(ctx.lang))


@router.message(Checkout.location, F.location)
async def on_location(message: Message, ctx: Ctx, state: FSMContext) -> None:
    loc = message.location
    await _save(state, latitude=f"{loc.latitude:.6f}", longitude=f"{loc.longitude:.6f}")
    await message.answer("📍✔️", reply_markup=REMOVE)
    await _ask_notes_or_summary(message, ctx, state)


@router.message(Checkout.location, F.text)
async def on_location_skip(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await message.answer("✔️", reply_markup=REMOVE)
    await _ask_notes_or_summary(message, ctx, state)


async def _ask_notes_or_summary(message: Message, ctx: Ctx, state: FSMContext) -> None:
    co = await _co(state)
    if co["info"].get("allow_notes"):
        await state.set_state(Checkout.notes)
        await message.answer(
            t("ask_notes", ctx.lang), reply_markup=single(t("skip", ctx.lang), Skip(step="notes"))
        )
        return
    await _summary(message, ctx, state)


@router.callback_query(Checkout.notes, Skip.filter(F.step == "notes"))
async def notes_skip(cb: CallbackQuery, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    await _summary(cb.message, ctx, state)


@router.message(Checkout.notes, F.text)
async def notes_text(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await _save(state, notes=message.text.strip()[:500])
    await _summary(message, ctx, state)


def payload(co: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "fulfilment",
        "customer_name",
        "customer_phone",
        "zone_id",
        "address_area",
        "address_landmark",
        "latitude",
        "longitude",
        "notes",
    ]
    return {k: co[k] for k in keys if co.get(k) not in (None, "")}


async def _summary(message: Message, ctx: Ctx, state: FSMContext) -> None:
    co = await _co(state)
    try:
        q = await ctx.api.quote(ctx.bot_id, ctx.tg_id, ctx.business, payload(co))
    except ApiError as exc:
        await state.clear()
        await message.answer(
            exc.message or t("error_generic", ctx.lang), reply_markup=main_menu(ctx.lang)
        )
        return
    cart = await ctx.api.cart(ctx.bot_id, ctx.tg_id, ctx.business)
    cur = q["currency"]
    lines = [t("summary_title", ctx.lang), ""]
    for line in cart["lines"]:
        lines.append(
            f"• {escape(line['name'])} × {line['quantity']} — "
            f"{money(line['line_total'], cur, ctx.lang)}"
        )
    lines.append("")
    lines.append(f"👤 {escape(co['customer_name'])}  📞 {escape(co['customer_phone'])}")
    if co["fulfilment"] == "delivery":
        zone = q["zone"]["name_en" if ctx.lang == "en" and q["zone"]["name_en"] else "name_ar"]
        lines.append(
            t(
                "summary_fulfilment_delivery",
                ctx.lang,
                zone=escape(zone),
                area=escape(co.get("address_area", "")),
            )
        )
        if co.get("address_landmark"):
            lines.append(t("summary_landmark", ctx.lang, v=escape(co["address_landmark"])))
        lines.append(f"{t('delivery_fee', ctx.lang)}: {money(q['delivery_fee'], cur, ctx.lang)}")
    else:
        lines.append(t("summary_fulfilment_pickup", ctx.lang))
    if co.get("notes"):
        lines.append(f"🗒 {escape(co['notes'])}")
    lines.append(f"{t('subtotal', ctx.lang)}: {money(q['subtotal'], cur, ctx.lang)}")
    lines.append(f"<b>{t('total', ctx.lang)}: {money(q['total'], cur, ctx.lang)}</b>")
    lines.append(t("payment_cod" if co["fulfilment"] == "delivery" else "payment_pickup", ctx.lang))
    # One idempotency key per summary: double-tapping Confirm can never create two orders.
    await _save(state, key=str(uuid.uuid4()))
    await state.set_state(Checkout.confirm)
    await message.answer("\n".join(lines), reply_markup=confirm_kb(ctx.lang))


@router.callback_query(Checkout.confirm, Confirm.filter(F.ok == 1))
async def confirm(cb: CallbackQuery, ctx: Ctx, state: FSMContext) -> None:
    co = await _co(state)
    if not co.get("key"):
        await answer_cb(cb)
        return
    await answer_cb(cb, "⏳")
    order = await ctx.api.checkout(ctx.bot_id, ctx.tg_id, ctx.business, payload(co), co["key"])
    await state.clear()
    with contextlib.suppress(Exception):
        await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        t(
            "order_placed",
            ctx.lang,
            number=order["number"],
            total=money(order["total"], order["currency"], ctx.lang),
        ),
        reply_markup=main_menu(ctx.lang),
    )


@router.callback_query(Confirm.filter(F.ok == 0))
async def cancel(cb: CallbackQuery, ctx: Ctx, state: FSMContext) -> None:
    await answer_cb(cb)
    await state.clear()
    await cb.message.answer(t("checkout_cancelled", ctx.lang), reply_markup=main_menu(ctx.lang))
