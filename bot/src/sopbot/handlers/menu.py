"""Reply-keyboard menu buttons and free text. Must be registered after stateful routers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from sopbot.context import Ctx
from sopbot.handlers import ai
from sopbot.handlers.cart import show_cart
from sopbot.handlers.catalog import SearchState, show_categories, show_products
from sopbot.handlers.common import needs_business
from sopbot.handlers.orders import show_orders
from sopbot.handlers.start import toggle_language
from sopbot.handlers.support import ask_support
from sopbot.keyboards import menu_text_to_key
from sopbot.texts import t

router = Router(name="menu")


@router.message(F.text)
async def on_text(message: Message, ctx: Ctx, state: FSMContext) -> None:
    key = menu_text_to_key(message.text)
    if key == "menu_language":
        await toggle_language(message, ctx)
        return
    if needs_business(ctx):
        await message.answer(t("choose_business", ctx.lang))
        return
    if key:
        await state.set_state(None)
    match key:
        case "menu_browse":
            await show_products(message, ctx, "-", 1, edit=False)
        case "menu_categories":
            await show_categories(message, ctx)
        case "menu_search":
            await state.set_state(SearchState.query)
            await message.answer(t("search_prompt", ctx.lang))
        case "menu_cart":
            await show_cart(message, ctx)
        case "menu_orders":
            await show_orders(message, ctx)
        case "menu_support":
            await ask_support(message, ctx, state)
        case _:
            await ai.handle_free_text(message, ctx, state)
