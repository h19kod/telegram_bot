"""Bot copy. Arabic uses a friendly Iraqi tone; English is plain and clear."""

from __future__ import annotations

from typing import Any

T: dict[str, dict[str, str]] = {
    "welcome": {
        "ar": "هلا بيك بـ <b>{name}</b> 👋\nشتحب تطلب اليوم؟ اختار من القائمة 👇",
        "en": "Welcome to <b>{name}</b> 👋\nWhat would you like today? Pick from the menu 👇",
    },
    "closed_now": {
        "ar": "⏰ المحل مسكّر هسه، تكدر تتصفح المنيو.",
        "en": "⏰ We're closed right now — you can still browse the menu.",
    },
    "business_inactive": {
        "ar": "🙏 المحل غير متاح حالياً.",
        "en": "🙏 This business is currently unavailable.",
    },
    "choose_business": {
        "ar": "افتح رابط المحل حتى تبدي الطلب.",
        "en": "Open the shop's link to start ordering.",
    },
    "menu_browse": {"ar": "🍽 المنيو", "en": "🍽 Menu"},
    "menu_categories": {"ar": "📂 الأقسام", "en": "📂 Categories"},
    "menu_search": {"ar": "🔎 بحث", "en": "🔎 Search"},
    "menu_cart": {"ar": "🛒 السلة", "en": "🛒 Cart"},
    "menu_orders": {"ar": "📦 طلباتي", "en": "📦 My orders"},
    "menu_support": {"ar": "💬 الدعم", "en": "💬 Support"},
    "menu_language": {"ar": "🌐 English", "en": "🌐 العربية"},
    "open_store": {"ar": "🛍 افتح المتجر", "en": "🛍 Open store"},
    "categories_title": {"ar": "📂 اختار القسم:", "en": "📂 Choose a category:"},
    "no_categories": {"ar": "ماكو أقسام هسه.", "en": "No categories yet."},
    "products_title": {
        "ar": "🍽 {title} — صفحة {page}/{pages}",
        "en": "🍽 {title} — page {page}/{pages}",
    },
    "all_products": {"ar": "كل المنتجات", "en": "All products"},
    "no_products": {"ar": "ماكو منتجات هنا.", "en": "No products here."},
    "unavailable": {"ar": "غير متوفر", "en": "Unavailable"},
    "back": {"ar": "⬅️ رجوع", "en": "⬅️ Back"},
    "prev": {"ar": "◀️", "en": "◀️"},
    "next": {"ar": "▶️", "en": "▶️"},
    "add_to_cart": {"ar": "➕ أضف للسلة — {price}", "en": "➕ Add to cart — {price}"},
    "added": {"ar": "✅ انضاف للسلة", "en": "✅ Added to cart"},
    "choose_required": {"ar": "لازم تختار: {group}", "en": "Please choose: {group}"},
    "qty": {"ar": "الكمية: {n}", "en": "Qty: {n}"},
    "search_prompt": {"ar": "🔎 اكتب اسم الأكلة أو المنتج:", "en": "🔎 Type a product name:"},
    "search_results": {"ar": "نتائج البحث عن «{q}»:", "en": "Results for “{q}”:"},
    "cart_empty": {"ar": "🛒 سلتك فارغة.", "en": "🛒 Your cart is empty."},
    "cart_title": {"ar": "🛒 <b>سلتك</b>", "en": "🛒 <b>Your cart</b>"},
    "cart_subtotal": {"ar": "المجموع: <b>{amount}</b>", "en": "Subtotal: <b>{amount}</b>"},
    "cart_problem": {
        "ar": "⚠️ بعض المنتجات صارت غير متوفرة، شيلها قبل الطلب.",
        "en": "⚠️ Some items are no longer available — remove them first.",
    },
    "checkout": {"ar": "✅ إتمام الطلب", "en": "✅ Checkout"},
    "clear_cart": {"ar": "🧹 تفريغ السلة", "en": "🧹 Clear cart"},
    "ask_name": {"ar": "👤 شنو اسمك الكريم؟", "en": "👤 What's your name?"},
    "use_value": {"ar": "استخدم: {v}", "en": "Use: {v}"},
    "ask_phone": {
        "ar": "📞 دز رقم موبايلك (مثال 07701234567) أو اضغط الزر:",
        "en": "📞 Send your mobile number (e.g. 07701234567) or tap the button:",
    },
    "share_phone": {"ar": "📱 مشاركة رقمي", "en": "📱 Share my number"},
    "bad_phone": {
        "ar": "❌ الرقم مو صحيح، جرب مرة ثانية (مثال 07701234567).",
        "en": "❌ Invalid number, try again (e.g. 07701234567).",
    },
    "ask_fulfilment": {"ar": "🚚 توصيل لو استلام من المحل؟", "en": "🚚 Delivery or pickup?"},
    "delivery": {"ar": "🛵 توصيل", "en": "🛵 Delivery"},
    "pickup": {"ar": "🏪 استلام من المحل", "en": "🏪 Pickup"},
    "ask_zone": {"ar": "📍 اختار منطقتك:", "en": "📍 Choose your area:"},
    "no_zones": {
        "ar": "ماكو مناطق توصيل مفعّلة، تكدر تستلم من المحل.",
        "en": "No delivery zones available — pickup only.",
    },
    "zone_line": {"ar": "{name} — توصيل {fee}", "en": "{name} — delivery {fee}"},
    "ask_area": {
        "ar": "🏘 اكتب اسم المنطقة/الحي والشارع:",
        "en": "🏘 Type your neighbourhood and street:",
    },
    "ask_landmark": {
        "ar": "🏁 شنو أقرب نقطة دالة؟ (جامع، مدرسة، محل معروف...)",
        "en": "🏁 Nearest landmark? (mosque, school, known shop...)",
    },
    "ask_location": {
        "ar": "🗺 تكدر تدز موقعك (اختياري):",
        "en": "🗺 You can share your location (optional):",
    },
    "share_location": {"ar": "📍 إرسال موقعي", "en": "📍 Send my location"},
    "skip": {"ar": "تخطي ⏭", "en": "Skip ⏭"},
    "ask_notes": {
        "ar": "🗒 عندك ملاحظة على الطلب؟ اكتبها أو اضغط تخطي.",
        "en": "🗒 Any notes for the order? Type them or tap Skip.",
    },
    "summary_title": {"ar": "🧾 <b>ملخص طلبك</b>", "en": "🧾 <b>Order summary</b>"},
    "summary_fulfilment_delivery": {
        "ar": "🛵 توصيل إلى: {zone} — {area}",
        "en": "🛵 Delivery to: {zone} — {area}",
    },
    "summary_fulfilment_pickup": {"ar": "🏪 استلام من المحل", "en": "🏪 Pickup"},
    "summary_landmark": {"ar": "🏁 {v}", "en": "🏁 {v}"},
    "subtotal": {"ar": "المجموع", "en": "Subtotal"},
    "delivery_fee": {"ar": "التوصيل", "en": "Delivery"},
    "total": {"ar": "الإجمالي", "en": "Total"},
    "payment_cod": {"ar": "💵 الدفع عند الاستلام", "en": "💵 Cash on delivery"},
    "payment_pickup": {"ar": "💵 الدفع بالمحل", "en": "💵 Pay at pickup"},
    "confirm_order": {"ar": "✅ تأكيد الطلب", "en": "✅ Confirm order"},
    "cancel": {"ar": "❌ إلغاء", "en": "❌ Cancel"},
    "checkout_cancelled": {
        "ar": "تم الإلغاء. سلتك بعدها محفوظة 👍",
        "en": "Cancelled. Your cart is kept 👍",
    },
    "order_placed": {
        "ar": "🎉 تم استلام طلبك <b>#{number}</b>\nالإجمالي: <b>{total}</b>\nراح نبلغك بكل تحديث على حالة الطلب.",
        "en": "🎉 Order <b>#{number}</b> received\nTotal: <b>{total}</b>\nWe'll notify you of every status update.",
    },
    "orders_title": {"ar": "📦 <b>طلباتك الأخيرة</b>", "en": "📦 <b>Your recent orders</b>"},
    "no_orders": {"ar": "ما عندك طلبات بعد.", "en": "You have no orders yet."},
    "cancel_order": {"ar": "❌ إلغاء الطلب", "en": "❌ Cancel order"},
    "order_cancelled": {"ar": "تم إلغاء الطلب #{number}.", "en": "Order #{number} cancelled."},
    "support_prompt": {
        "ar": "💬 اكتب رسالتك وراح توصل للمحل:",
        "en": "💬 Type your message and we'll pass it to the shop:",
    },
    "support_sent": {
        "ar": "✅ وصلت رسالتك، راح يتواصلون وياك.",
        "en": "✅ Message sent — they'll get back to you.",
    },
    "language_set": {"ar": "✅ صارت اللغة عربي.", "en": "✅ Language set to English."},
    "error_generic": {
        "ar": "صار خطأ بسيط 🙏 جرب مرة ثانية.",
        "en": "Something went wrong 🙏 please try again.",
    },
    "too_fast": {"ar": "على كيفك شوية 🙂", "en": "Slow down a little 🙂"},
    "link_usage": {"ar": "استخدم: /link CODE", "en": "Usage: /link CODE"},
    "linked": {
        "ar": "✅ تم ربط حسابك ({name}). راح توصلك إشعارات الطلبات هنا.",
        "en": "✅ Account linked ({name}). Order notifications will arrive here.",
    },
    "staff_applied": {
        "ar": "✅ تم: طلب #{number} ← {status}",
        "en": "✅ Done: order #{number} → {status}",
    },
    "staff_already": {
        "ar": "ℹ️ الطلب #{number} صار {status} من قبل.",
        "en": "ℹ️ Order #{number} is already {status}.",
    },
    "staff_stale": {
        "ar": "⚠️ الطلب تحدث من شخص ثاني، هسه حالته: {status}",
        "en": "⚠️ Someone already updated this order. Current status: {status}",
    },
    "staff_not_linked": {
        "ar": "🔒 حسابك مو مربوط أو ما عندك صلاحية. اربط حسابك من لوحة التحكم.",
        "en": "🔒 Your account isn't linked or lacks permission. Link it from the dashboard.",
    },
    "reject_reason": {"ar": "اختار سبب الرفض:", "en": "Choose a rejection reason:"},
    "ai_thinking": {"ar": "لحظة أشوفلك… 🤔", "en": "One moment… 🤔"},
    "ai_confirm": {"ar": "✅ أكّد وأضف للسلة", "en": "✅ Confirm & add to cart"},
    "ai_added": {
        "ar": "✅ ضفت الطلب للسلة. تكدر تكمل الدفع من «إتمام الطلب».",
        "en": "✅ Added to your cart. Continue with Checkout.",
    },
    "ai_handover": {
        "ar": "👤 حولتك على موظف من المحل، راح يرد عليك قريباً.",
        "en": "👤 I've passed you to a staff member — they'll reply soon.",
    },
}

STATUS = {
    "pending": {"ar": "⏳ بانتظار القبول", "en": "⏳ Pending"},
    "confirmed": {"ar": "✅ مقبول", "en": "✅ Confirmed"},
    "preparing": {"ar": "👨‍🍳 قيد التحضير", "en": "👨‍🍳 Preparing"},
    "ready": {"ar": "📦 جاهز", "en": "📦 Ready"},
    "out_for_delivery": {"ar": "🛵 بالطريق", "en": "🛵 Out for delivery"},
    "delivered": {"ar": "🎉 تم التسليم", "en": "🎉 Delivered"},
    "cancelled": {"ar": "❌ ملغي", "en": "❌ Cancelled"},
    "rejected": {"ar": "🚫 مرفوض", "en": "🚫 Rejected"},
}

REJECT_REASONS = [
    {"ar": "المحل مسكّر/مزدحم", "en": "Closed / too busy"},
    {"ar": "منتج غير متوفر", "en": "Item unavailable"},
    {"ar": "خارج منطقة التوصيل", "en": "Outside delivery area"},
    {"ar": "معلومات الزبون غير صحيحة", "en": "Invalid customer details"},
]

CURRENCY = {"IQD": {"ar": "د.ع", "en": "IQD"}, "USD": {"ar": "$", "en": "$"}}
EXPONENT = {"IQD": 0, "USD": 2}


def t(key: str, lang: str, **kw: Any) -> str:
    entry = T.get(key, {})
    text = entry.get(lang) or entry.get("ar") or key
    return text.format(**kw) if kw else text


def status_label(status: str, lang: str) -> str:
    return STATUS.get(status, {}).get(lang, status)


def money(amount: int, currency: str, lang: str) -> str:
    exp = EXPONENT.get(currency, 0)
    if exp:
        major, minor = divmod(abs(amount), 10**exp)
        num = f"{major:,}.{minor:0{exp}d}"
    else:
        num = f"{abs(amount):,}"
    sign = "-" if amount < 0 else ""
    sym = CURRENCY.get(currency, {}).get(lang, currency)
    if currency == "USD":
        return f"{sign}{sym}{num}"
    return f"{sign}{num} {sym}" if lang == "ar" else f"{sign}{sym} {num}"
