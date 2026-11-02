from __future__ import annotations

import uuid
from typing import Any

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sopbot.texts import REJECT_REASONS, money, t


def h(value: str) -> str:
    """UUID → 32-char hex for compact callback data."""
    return uuid.UUID(str(value)).hex


def u(value: str) -> str:
    """32-char hex → canonical UUID string for the API."""
    return str(uuid.UUID(value))


class Nav(CallbackData, prefix="n"):
    to: str


class Cat(CallbackData, prefix="c"):
    id: str  # "-" = all products
    page: int = 1


class Prod(CallbackData, prefix="p"):
    id: str


class Opt(CallbackData, prefix="po"):
    id: str


class Qty(CallbackData, prefix="pq"):
    d: int


class AddCart(CallbackData, prefix="pa"):
    pass


class CartQty(CallbackData, prefix="cq"):
    item: str
    q: int


class Ful(CallbackData, prefix="f"):
    v: str


class Zone(CallbackData, prefix="z"):
    id: str


class Skip(CallbackData, prefix="sk"):
    step: str


class Use(CallbackData, prefix="us"):
    step: str


class Confirm(CallbackData, prefix="cf"):
    ok: int


class OrderView(CallbackData, prefix="ov"):
    id: str


class OrderCancel(CallbackData, prefix="oc"):
    id: str


class OrderRate(CallbackData, prefix="rv"):
    id: str
    stars: int


class StaffAction(CallbackData, prefix="o"):
    """Format produced by the backend: o:<order hex>:<status code>:<version>."""

    order: str
    code: str
    version: int


class RejectReason(CallbackData, prefix="rr"):
    order: str
    code: str
    idx: int
    version: int


class AIConfirm(CallbackData, prefix="ai"):
    id: str


MENU_KEYS = [
    "menu_browse",
    "menu_categories",
    "menu_search",
    "menu_cart",
    "menu_orders",
    "menu_support",
    "menu_language",
]


def main_menu(lang: str) -> ReplyKeyboardMarkup:
    rows = [
        ["menu_browse", "menu_categories"],
        ["menu_cart", "menu_orders"],
        ["menu_search", "menu_support"],
        ["menu_language"],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(k, lang)) for k in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
    )


def menu_text_to_key(text: str) -> str | None:
    for key in MENU_KEYS:
        if text in (t(key, "ar"), t(key, "en")):
            return key
    return None


def store_button(lang: str, url: str | None) -> InlineKeyboardMarkup | None:
    if not url or not url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("open_store", lang), web_app=WebAppInfo(url=url))]
        ]
    )


def categories_kb(categories: list[dict[str, Any]], lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t("all_products", lang), callback_data=Cat(id="-", page=1))
    for c in categories:
        b.button(text=c["name"], callback_data=Cat(id=h(c["id"]), page=1))
    b.adjust(2)
    return b.as_markup()


def products_kb(data: dict[str, Any], cat: str, lang: str, currency: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in data["results"]:
        label = f"{p['name']} — {money(p['price'], currency, lang)}"
        if not p["is_available"]:
            label = f"🚫 {p['name']} ({t('unavailable', lang)})"
        b.row(InlineKeyboardButton(text=label, callback_data=Prod(id=h(p["id"])).pack()))
    nav = []
    if data["page"] > 1:
        nav.append(
            InlineKeyboardButton(
                text=t("prev", lang), callback_data=Cat(id=cat, page=data["page"] - 1).pack()
            )
        )
    if data["page"] < data["pages"]:
        nav.append(
            InlineKeyboardButton(
                text=t("next", lang), callback_data=Cat(id=cat, page=data["page"] + 1).pack()
            )
        )
    if nav:
        b.row(*nav)
    b.row(
        InlineKeyboardButton(text=t("back", lang), callback_data=Nav(to="cats").pack()),
        InlineKeyboardButton(text=t("menu_cart", lang), callback_data=Nav(to="cart").pack()),
    )
    return b.as_markup()


def selection_total(product: dict[str, Any], selected: list[str], qty: int) -> int:
    deltas = {o["id"]: o["price_delta"] for g in product["option_groups"] for o in g["options"]}
    return (product["price"] + sum(deltas.get(i, 0) for i in selected)) * qty


def product_kb(
    product: dict[str, Any], selected: list[str], qty: int, lang: str, currency: str
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in product["option_groups"]:
        req = " *" if g["min_select"] else ""
        b.row(InlineKeyboardButton(text=f"— {g['name']}{req} —", callback_data="noop"))
        row = []
        for o in g["options"]:
            if not o["is_available"]:
                continue
            mark = "✅ " if o["id"] in selected else ""
            extra = f" +{money(o['price_delta'], currency, lang)}" if o["price_delta"] else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{mark}{o['name']}{extra}", callback_data=Opt(id=h(o["id"])).pack()
                )
            )
        for i in range(0, len(row), 2):
            b.row(*row[i : i + 2])
    if product["is_available"]:
        b.row(
            InlineKeyboardButton(text="➖", callback_data=Qty(d=-1).pack()),
            InlineKeyboardButton(text=t("qty", lang, n=qty), callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=Qty(d=1).pack()),
        )
        total = money(selection_total(product, selected, qty), currency, lang)
        b.row(
            InlineKeyboardButton(
                text=t("add_to_cart", lang, price=total), callback_data=AddCart().pack()
            )
        )
    b.row(
        InlineKeyboardButton(
            text=t("back", lang), callback_data=Cat(id=h(product["category"]), page=1).pack()
        )
    )
    return b.as_markup()


def cart_kb(cart: dict[str, Any], lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for line in cart["lines"]:
        b.row(
            InlineKeyboardButton(
                text="➖", callback_data=CartQty(item=h(line["id"]), q=line["quantity"] - 1).pack()
            ),
            InlineKeyboardButton(
                text=f"{line['name'][:20]} ×{line['quantity']}", callback_data="noop"
            ),
            InlineKeyboardButton(
                text="➕", callback_data=CartQty(item=h(line["id"]), q=line["quantity"] + 1).pack()
            ),
            InlineKeyboardButton(text="🗑", callback_data=CartQty(item=h(line["id"]), q=0).pack()),
        )
    if not cart["has_problems"]:
        b.row(
            InlineKeyboardButton(text=t("checkout", lang), callback_data=Nav(to="checkout").pack())
        )
    b.row(
        InlineKeyboardButton(text=t("clear_cart", lang), callback_data=Nav(to="clear").pack()),
        InlineKeyboardButton(text=t("menu_browse", lang), callback_data=Nav(to="cats").pack()),
    )
    return b.as_markup()


def single(text: str, data: CallbackData | str) -> InlineKeyboardMarkup:
    cb = data if isinstance(data, str) else data.pack()
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=cb)]]
    )


def phone_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("share_phone", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def location_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("share_location", lang), request_location=True)],
            [KeyboardButton(text=t("skip", lang))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def fulfilment_kb(info: dict[str, Any], lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if info.get("accepts_delivery"):
        b.button(text=t("delivery", lang), callback_data=Ful(v="delivery"))
    if info.get("accepts_pickup"):
        b.button(text=t("pickup", lang), callback_data=Ful(v="pickup"))
    b.button(text=t("cancel", lang), callback_data=Confirm(ok=0))
    b.adjust(2, 1)
    return b.as_markup()


def zones_kb(zones: list[dict[str, Any]], lang: str, currency: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for z in zones:
        b.button(
            text=t("zone_line", lang, name=z["name"], fee=money(z["fee"], currency, lang)),
            callback_data=Zone(id=h(z["id"])),
        )
    b.button(text=t("cancel", lang), callback_data=Confirm(ok=0))
    b.adjust(1)
    return b.as_markup()


def confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("confirm_order", lang), callback_data=Confirm(ok=1).pack()
                ),
                InlineKeyboardButton(text=t("cancel", lang), callback_data=Confirm(ok=0).pack()),
            ]
        ]
    )


def orders_kb(orders: list[dict[str, Any]], lang: str) -> InlineKeyboardMarkup:
    from sopbot.texts import status_label

    b = InlineKeyboardBuilder()
    for o in orders:
        b.button(
            text=f"#{o['number']} — {status_label(o['status'], lang)}",
            callback_data=OrderView(id=h(o["id"])),
        )
    b.adjust(1)
    return b.as_markup()


def reject_reasons_kb(order_hex: str, code: str, version: int, lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, r in enumerate(REJECT_REASONS):
        b.button(
            text=r[lang],
            callback_data=RejectReason(order=order_hex, code=code, idx=i, version=version),
        )
    b.adjust(1)
    return b.as_markup()


REMOVE = ReplyKeyboardRemove()
