from __future__ import annotations

import contextlib
import re
import time

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from sopbot.context import Ctx
from sopbot.handlers.common import answer_cb, ensure_session, needs_business, send_welcome
from sopbot.keyboards import BranchPick, Nav, branch_kb, main_menu, u
from sopbot.texts import t

router = Router(name="start")
SLUG = re.compile(r"^[a-z0-9][a-z0-9_]{1,48}[a-z0-9]$")
TABLE = re.compile(r"^([a-z0-9_]*)-t([A-Za-z0-9]{1,10})$")  # "-t5" (own bot), "slug-t5" (shared)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, ctx: Ctx, state: FSMContext) -> None:
    await state.clear()
    payload = (command.args or "").strip()
    if payload.startswith("link_"):
        await _link(message, ctx, payload[5:])
        return
    table = ""
    if m := TABLE.match(payload):
        payload, table = m.group(1), m.group(2)
    business = payload if payload and SLUG.match(payload) else None
    if ctx.bot.is_shared and not business and not ctx.business:
        await message.answer(t("choose_business", ctx.lang))
        return
    data = await ensure_session(ctx, message.from_user, business)
    if table and data["business"].get("accepts_dine_in"):
        await ctx.prefs.update(ctx.bot_id, ctx.tg_id, table=table, table_at=int(time.time()))
        if url := data.get("mini_app_url"):
            data = {**data, "mini_app_url": f"{url}&table={table}"}
        await send_welcome(message, ctx, data)
        await message.answer(t("at_table", ctx.lang, n=table))
        return
    if payload or not table:  # a plain /start leaves the table (if any) behind
        await ctx.prefs.update(ctx.bot_id, ctx.tg_id, table="")
    await send_welcome(message, ctx, data)


@router.message(Command("link"))
async def link_cmd(message: Message, command: CommandObject, ctx: Ctx) -> None:
    await _link(message, ctx, (command.args or "").strip())


async def _link(message: Message, ctx: Ctx, code: str) -> None:
    if not code:
        await message.answer(t("link_usage", ctx.lang))
        return
    u = message.from_user
    res = await ctx.api.staff_link(
        ctx.bot_id,
        code,
        {"id": u.id, "first_name": u.first_name or "", "username": u.username or ""},
    )
    await message.answer(t("linked", ctx.lang, name=res["name"]))


@router.message(Command("menu"))
async def menu_cmd(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await state.clear()
    if needs_business(ctx):
        await message.answer(t("choose_business", ctx.lang))
        return
    await message.answer("👇", reply_markup=main_menu(ctx.lang))


async def toggle_language(message: Message, ctx: Ctx) -> None:
    new = "en" if ctx.lang == "ar" else "ar"
    await ctx.set_lang(new)
    if ctx.business or not ctx.bot.is_shared:
        await ctx.api.set_language(ctx.bot_id, ctx.tg_id, ctx.business, new)
    await message.answer(t("language_set", new), reply_markup=main_menu(new))


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await answer_cb(cb)


@router.callback_query(Nav.filter(F.to == "menu"))
async def nav_menu(cb: CallbackQuery, ctx: Ctx) -> None:
    await answer_cb(cb)
    await cb.message.answer("👇", reply_markup=main_menu(ctx.lang))


@router.callback_query(BranchPick.filter(F.id == ""))
async def branch_list(cb: CallbackQuery, ctx: Ctx) -> None:
    await answer_cb(cb)
    data = await ensure_session(ctx, cb.from_user)
    await cb.message.answer(
        t("choose_branch", ctx.lang), reply_markup=branch_kb(data["business"], ctx.lang)
    )


@router.callback_query(BranchPick.filter(F.id != ""))
async def branch_set(cb: CallbackQuery, callback_data: BranchPick, ctx: Ctx) -> None:
    await ctx.api.set_branch(ctx.bot_id, ctx.tg_id, ctx.business, u(callback_data.id))
    data = await ensure_session(ctx, cb.from_user)
    name = data["business"]["branch"]["name"]
    await answer_cb(cb, t("branch_changed", ctx.lang, name=name))
    with contextlib.suppress(Exception):
        await cb.message.edit_text(
            t("branch_changed", ctx.lang, name=name),
            reply_markup=branch_kb(data["business"], ctx.lang),
        )
