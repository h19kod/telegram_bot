from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from sopbot.context import Ctx
from sopbot.keyboards import main_menu
from sopbot.texts import t

router = Router(name="support")


class SupportState(StatesGroup):
    message = State()


async def ask_support(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await state.set_state(SupportState.message)
    await message.answer(t("support_prompt", ctx.lang))


@router.message(SupportState.message, F.text)
async def on_support(message: Message, ctx: Ctx, state: FSMContext) -> None:
    await state.clear()
    await ctx.api.support(ctx.bot_id, ctx.tg_id, ctx.business, message.text.strip()[:1000])
    await message.answer(t("support_sent", ctx.lang), reply_markup=main_menu(ctx.lang))
