"""Telegram message rendering for orders. All dynamic text is HTML-escaped."""

from __future__ import annotations

from html import escape
from typing import Any

from apps.orders.models import Fulfilment, Order, OrderStatus
from apps.orders.services.transitions import allowed_targets
from core.money import format_amount

STATUS_CODES: dict[str, str] = {
    OrderStatus.CONFIRMED: "cf",
    OrderStatus.REJECTED: "rj",
    OrderStatus.PREPARING: "pr",
    OrderStatus.READY: "rd",
    OrderStatus.OUT_FOR_DELIVERY: "od",
    OrderStatus.DELIVERED: "dl",
    OrderStatus.CANCELLED: "cn",
}
CODE_STATUS = {v: k for k, v in STATUS_CODES.items()}

STATUS_LABELS: dict[str, tuple[str, str]] = {
    OrderStatus.PENDING: ("⏳ بانتظار القبول", "⏳ Pending"),
    OrderStatus.CONFIRMED: ("✅ مقبول", "✅ Confirmed"),
    OrderStatus.PREPARING: ("👨‍🍳 قيد التحضير", "👨‍🍳 Preparing"),
    OrderStatus.READY: ("📦 جاهز", "📦 Ready"),
    OrderStatus.OUT_FOR_DELIVERY: ("🛵 بالطريق", "🛵 Out for delivery"),
    OrderStatus.DELIVERED: ("🎉 تم التسليم", "🎉 Delivered"),
    OrderStatus.CANCELLED: ("❌ ملغي", "❌ Cancelled"),
    OrderStatus.REJECTED: ("🚫 مرفوض", "🚫 Rejected"),
}

ACTION_LABELS: dict[str, tuple[str, str]] = {
    OrderStatus.CONFIRMED: ("✅ قبول", "✅ Accept"),
    OrderStatus.REJECTED: ("🚫 رفض", "🚫 Reject"),
    OrderStatus.PREPARING: ("👨‍🍳 بدء التحضير", "👨‍🍳 Start preparing"),
    OrderStatus.READY: ("📦 جاهز", "📦 Ready"),
    OrderStatus.OUT_FOR_DELIVERY: ("🛵 خرج للتوصيل", "🛵 Out for delivery"),
    OrderStatus.DELIVERED: ("🎉 تم التسليم", "🎉 Delivered"),
    OrderStatus.CANCELLED: ("❌ إلغاء", "❌ Cancel"),
}

CUSTOMER_STATUS_TEXT: dict[str, tuple[str, str]] = {
    OrderStatus.PENDING: (
        "استلمنا طلبك #{n} ✅\nراح نبلغك أول ما المحل يأكده.",
        "We received your order #{n} ✅\nWe'll notify you once it's confirmed.",
    ),
    OrderStatus.CONFIRMED: (
        "تم تأكيد طلبك #{n} ✅ هسه نبدي بيه.",
        "Your order #{n} is confirmed ✅",
    ),
    OrderStatus.PREPARING: (
        "طلبك #{n} قيد التحضير 👨‍🍳",
        "Your order #{n} is being prepared 👨‍🍳",
    ),
    OrderStatus.READY: ("طلبك #{n} جاهز 📦", "Your order #{n} is ready 📦"),
    OrderStatus.OUT_FOR_DELIVERY: (
        "طلبك #{n} طلع بالطريق إلك 🛵",
        "Your order #{n} is on its way 🛵",
    ),
    OrderStatus.DELIVERED: (
        "تم تسليم طلبك #{n} 🎉 بالعافية!",
        "Your order #{n} was delivered 🎉 Enjoy!",
    ),
    OrderStatus.CANCELLED: ("تم إلغاء طلبك #{n} ❌", "Your order #{n} was cancelled ❌"),
    OrderStatus.REJECTED: (
        "نعتذر، المحل ما كدر يقبل طلبك #{n} 🙏",
        "Sorry, your order #{n} was rejected 🙏",
    ),
}

PAYMENT_LABELS = {
    "cash_on_delivery": ("الدفع عند الاستلام", "Cash on delivery"),
    "pay_at_pickup": ("الدفع بالمحل", "Pay at pickup"),
}


def _l(pair: tuple[str, str], lang: str) -> str:
    return pair[1] if lang == "en" else pair[0]


def callback_data(order: Order, to: str) -> str:
    return f"o:{order.id.hex}:{STATUS_CODES[to]}:{order.version}"


def parse_callback(data: str) -> tuple[str, str, int] | None:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "o" or parts[2] not in CODE_STATUS:
        return None
    try:
        return parts[1], CODE_STATUS[parts[2]], int(parts[3])
    except ValueError:
        return None


def staff_keyboard(order: Order, lang: str = "ar") -> dict[str, Any] | None:
    targets = allowed_targets(order)
    if not targets:
        return None
    buttons = [
        {"text": _l(ACTION_LABELS[t], lang), "callback_data": callback_data(order, t)}
        for t in targets
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return {"inline_keyboard": rows}


def staff_order_text(order: Order, lang: str = "ar") -> str:
    cur = order.currency
    en = lang == "en"
    lines = [
        f"🧾 <b>{'Order' if en else 'طلب'} #{order.number}</b> — {_l(STATUS_LABELS[order.status], lang)}",
        "",
        f"👤 {escape(order.customer_name)}",
    ]
    if order.customer_phone:
        lines.append(f"📞 <code>{escape(order.customer_phone)}</code>")
    if order.fulfilment == Fulfilment.DINE_IN:
        lines.append(f"🍽 <b>{'Table' if en else 'طاولة'} {escape(order.table_label)}</b>")
    if order.fulfilment == Fulfilment.DELIVERY:
        addr = " - ".join(
            escape(p)
            for p in (
                order.zone_name_snapshot,
                order.address_area,
                order.address_street,
                order.address_building,
            )
            if p
        )
        lines.append(f"📍 {addr}")
        if order.address_landmark:
            lines.append(
                f"🏁 {'Landmark' if en else 'أقرب نقطة دالة'}: {escape(order.address_landmark)}"
            )
        if order.latitude is not None and order.longitude is not None:
            lines.append(
                f'🗺 <a href="https://maps.google.com/?q={order.latitude},{order.longitude}">'
                f"{'Map' if en else 'الموقع'}</a>"
            )
    else:
        lines.append(f"🏪 {'Pickup' if en else 'استلام من المحل'}")
    lines.append("")
    for item in order.items.prefetch_related("options"):
        name = escape(item.product_name_en if en and item.product_name_en else item.product_name_ar)
        lines.append(f"• {name} × {item.quantity} — {format_amount(item.line_total, cur, lang)}")
        for opt in item.options.all():
            oname = opt.option_name_en if en and opt.option_name_en else opt.option_name_ar
            lines.append(f"   ◦ {escape(oname)}")
        if item.note:
            lines.append(f"   📝 {escape(item.note)}")
    lines.append("")
    lines.append(f"{'Subtotal' if en else 'المجموع'}: {format_amount(order.subtotal, cur, lang)}")
    if order.fulfilment == Fulfilment.DELIVERY:
        lines.append(
            f"{'Delivery' if en else 'التوصيل'}: {format_amount(order.delivery_fee, cur, lang)}"
        )
    if order.discount_total:
        lines.append(
            f"{'Discount' if en else 'الخصم'}: -{format_amount(order.discount_total, cur, lang)}"
        )
    lines.append(f"<b>{'Total' if en else 'الإجمالي'}: {format_amount(order.total, cur, lang)}</b>")
    lines.append(
        f"💳 {_l(PAYMENT_LABELS.get(order.payment_method, (order.payment_method,) * 2), lang)}"
    )
    if order.notes:
        lines.append(f"🗒 {escape(order.notes)}")
    if order.cancel_reason and order.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
        lines.append(f"{'Reason' if en else 'السبب'}: {escape(order.cancel_reason)}")
    return "\n".join(lines)


def customer_status_text(order: Order) -> str:
    lang = order.language
    text = _l(CUSTOMER_STATUS_TEXT[order.status], lang).format(n=order.number)
    if order.status == OrderStatus.PENDING:
        text += f"\n{'Total' if lang == 'en' else 'الإجمالي'}: {format_amount(order.total, order.currency, lang)}"
    if (
        order.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED)
        and order.cancel_reason
        and order.cancel_reason != "auto_rejected_timeout"
    ):
        text += f"\n{'Reason' if lang == 'en' else 'السبب'}: {escape(order.cancel_reason)}"
    return text
