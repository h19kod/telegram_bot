import json
import uuid

import httpx
import pytest
import respx
from aiogram import Bot
from redis.asyncio import Redis

from harness import (
    FakeSession,
    StaticRegistry,
    cb_update,
    find_button,
    msg_update,
)
from sopbot.api import BackendClient
from sopbot.app import build_dispatcher
from sopbot.context import BotInfo
from sopbot.keyboards import h

B = "http://backend.test/internal/v1/bots/11111111-1111-1111-1111-111111111111"
BOT_ID = "11111111-1111-1111-1111-111111111111"
PID = str(uuid.uuid4())
OPT = str(uuid.uuid4())
ZONE = str(uuid.uuid4())
ORDER = str(uuid.uuid4())

BUSINESS = {"slug": "shop", "name": "مطعم الطيب", "currency": "IQD", "is_open": True,
            "is_active": True, "accepts_delivery": True, "accepts_pickup": True,
            "allow_order_notes": True, "welcome_message": "", "ai_enabled": False}
PRODUCT = {"id": PID, "category": str(uuid.uuid4()), "category_name": "برغر",
           "name": "برغر دبل", "description": "لحم", "price": 8000, "compare_at_price": None,
           "discount_percent": None, "is_available": True, "images": [],
           "option_groups": [{"id": str(uuid.uuid4()), "name": "الحجم", "selection_type": "single",
                              "min_select": 1, "max_select": 1,
                              "options": [{"id": OPT, "name": "كبير", "price_delta": 1500,
                                           "is_available": True, "is_default": False}]}]}
CART = {"lines": [{"id": str(uuid.uuid4()), "name": "برغر دبل", "options": [{"name": "كبير"}],
                   "quantity": 2, "line_total": 19000, "available": True}],
        "subtotal": 19000, "has_problems": False, "currency": "IQD", "item_count": 2}


@pytest.fixture
async def env():
    redis = Redis.from_url("redis://localhost:6379/14")
    await redis.flushdb()
    session = FakeSession()
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    info = BotInfo(id=BOT_ID, telegram_id=bot.id, username="shop_bot", is_shared=False,
                   webhook_secret="s")
    api = BackendClient("http://backend.test", httpx.AsyncClient())
    dp = build_dispatcher(redis, api, StaticRegistry(bot, info))
    yield dp, bot, session, redis
    await api.close()
    await redis.flushdb()
    await redis.aclose()


async def feed(dp, bot, redis, update):
    await redis.delete(*[k async for k in redis.scan_iter("sopbot:throttle:*")] or ["_"])
    await dp.feed_update(bot, update)


@respx.mock
async def test_full_order_conversation(env):
    dp, bot, session, redis = env
    respx.post(f"{B}/session").mock(return_value=httpx.Response(200, json={
        "business": BUSINESS, "customer": {"language": "ar", "full_name": "", "phone": ""},
        "is_staff": False, "mini_app_url": None}))
    respx.get(f"{B}/catalog/products/{PID}").mock(return_value=httpx.Response(200, json=PRODUCT))
    add = respx.post(f"{B}/customers/9001/cart/items").mock(
        return_value=httpx.Response(201, json=CART))
    respx.get(f"{B}/customers/9001/cart").mock(return_value=httpx.Response(200, json=CART))
    respx.get(f"{B}/zones").mock(return_value=httpx.Response(200, json=[
        {"id": ZONE, "name": "الكرادة", "fee": 2000}]))
    respx.post(f"{B}/customers/9001/checkout/quote").mock(return_value=httpx.Response(200, json={
        "subtotal": 19000, "delivery_fee": 2000, "discount_total": 0, "total": 21000,
        "currency": "IQD", "payment_method": "cash_on_delivery",
        "zone": {"id": ZONE, "name_ar": "الكرادة", "name_en": "Karrada"}}))
    checkout = respx.post(f"{B}/customers/9001/checkout").mock(
        return_value=httpx.Response(201, json={"id": ORDER, "number": 1042, "total": 21000,
                                               "currency": "IQD"}))

    await feed(dp, bot, redis, msg_update("/start"))
    assert "مطعم الطيب" in session.texts()[0]

    await feed(dp, bot, redis, cb_update(f"p:{h(PID)}"))
    # Adding without the required option is refused locally (and would be by the backend).
    await feed(dp, bot, redis, cb_update("pa"))
    assert any("لازم تختار" in a for a in session.alerts())
    assert not add.called
    await feed(dp, bot, redis, cb_update(f"po:{h(OPT)}"))
    await feed(dp, bot, redis, cb_update("pq:1"))
    assert "19,000" in json.dumps(session.last_markup().model_dump(), ensure_ascii=False)
    await feed(dp, bot, redis, cb_update("pa"))
    assert json.loads(add.calls[0].request.content) == {
        "product_id": PID, "option_ids": [OPT], "quantity": 2}

    await feed(dp, bot, redis, cb_update("n:checkout"))
    await feed(dp, bot, redis, msg_update("علي حسين"))
    await feed(dp, bot, redis, msg_update("07701234567"))
    await feed(dp, bot, redis, cb_update("f:delivery"))
    await feed(dp, bot, redis, cb_update(f"z:{h(ZONE)}"))
    await feed(dp, bot, redis, msg_update("الكرادة داخل، شارع 62"))
    await feed(dp, bot, redis, msg_update("قرب جامع الكرادة"))
    await feed(dp, bot, redis, msg_update("تخطي ⏭"))
    await feed(dp, bot, redis, cb_update("sk:notes"))
    summary = session.texts()[-1]
    assert "21,000" in summary
    assert "قرب جامع الكرادة" in summary
    assert not checkout.called  # nothing is submitted before explicit confirmation

    await feed(dp, bot, redis, cb_update("cf:1"))
    await feed(dp, bot, redis, cb_update("cf:1"))  # double tap
    assert checkout.call_count == 1
    req = checkout.calls[0].request
    uuid.UUID(req.headers["Idempotency-Key"])
    body = json.loads(req.content)
    assert body["zone_id"] == ZONE
    assert body["customer_phone"] == "07701234567"
    assert "price" not in json.dumps(body)
    assert "#1042" in session.texts()[-1]


@respx.mock
async def test_checkout_error_is_shown_not_success(env):
    dp, bot, session, redis = env
    respx.post(f"{B}/session").mock(return_value=httpx.Response(200, json={
        "business": BUSINESS, "customer": {"language": "ar", "full_name": "Ali",
                                           "phone": "+9647701234567"},
        "is_staff": False, "mini_app_url": None}))
    respx.get(f"{B}/customers/9001/cart").mock(return_value=httpx.Response(200, json=CART))
    respx.post(f"{B}/customers/9001/checkout/quote").mock(return_value=httpx.Response(200, json={
        "subtotal": 19000, "delivery_fee": 0, "discount_total": 0, "total": 19000,
        "currency": "IQD", "payment_method": "pay_at_pickup", "zone": None}))
    respx.post(f"{B}/customers/9001/checkout").mock(return_value=httpx.Response(422, json={
        "error": {"code": "outside_working_hours", "message": "المحل مسكّر هسه"}}))
    await feed(dp, bot, redis, msg_update("/start"))
    await feed(dp, bot, redis, cb_update("n:checkout"))
    await feed(dp, bot, redis, cb_update("us:name"))
    await feed(dp, bot, redis, cb_update("us:phone"))
    await feed(dp, bot, redis, cb_update("f:pickup"))
    await feed(dp, bot, redis, cb_update("sk:notes"))
    await feed(dp, bot, redis, cb_update("cf:1"))
    assert any("مسكّر" in a for a in session.alerts())
    assert not any("تم استلام طلبك" in x for x in session.texts())


@respx.mock
async def test_whatsapp_code_is_required_before_ordering(env):
    dp, bot, session, redis = env
    respx.post(f"{B}/session").mock(return_value=httpx.Response(200, json={
        "business": {**BUSINESS, "phone_verification_required": True},
        "customer": {"language": "ar", "full_name": "Ali", "phone": "", "phone_verified": False},
        "is_staff": False, "mini_app_url": None}))
    respx.get(f"{B}/customers/9001/cart").mock(return_value=httpx.Response(200, json=CART))
    code = respx.post(f"{B}/customers/9001/phone/code").mock(return_value=httpx.Response(
        202, json={"phone": "+9647701234567", "expires_in": 600, "resend_in": 60}))
    confirm = respx.post(f"{B}/customers/9001/phone/confirm").mock(side_effect=[
        httpx.Response(400, json={"error": {"code": "invalid_code", "message": "الرمز غير صحيح"}}),
        httpx.Response(200, json={"phone": "+9647701234567", "phone_verified": True}),
    ])
    await feed(dp, bot, redis, msg_update("/start"))
    await feed(dp, bot, redis, cb_update("n:checkout"))
    await feed(dp, bot, redis, cb_update("us:name"))
    await feed(dp, bot, redis, msg_update("07701234567"))
    assert json.loads(code.calls[0].request.content) == {"phone": "07701234567"}
    assert "واتساب" in session.texts()[-1]
    await feed(dp, bot, redis, msg_update("111111"))
    assert "غير صحيح" in session.texts()[-1]
    await feed(dp, bot, redis, msg_update("482913"))
    assert json.loads(confirm.calls[1].request.content) == {"code": "482913"}
    assert any("تم تأكيد" in x for x in session.texts())
    assert "توصيل" in session.texts()[-1]  # moved on to fulfilment


@respx.mock
async def test_own_telegram_contact_verifies_without_code(env):
    from aiogram.types import Contact

    dp, bot, session, redis = env
    respx.post(f"{B}/session").mock(return_value=httpx.Response(200, json={
        "business": {**BUSINESS, "phone_verification_required": True},
        "customer": {"language": "ar", "full_name": "Ali", "phone": "", "phone_verified": False},
        "is_staff": False, "mini_app_url": None}))
    respx.get(f"{B}/customers/9001/cart").mock(return_value=httpx.Response(200, json=CART))
    contact = respx.post(f"{B}/customers/9001/phone/contact").mock(return_value=httpx.Response(
        200, json={"phone": "+9647701234567", "phone_verified": True}))
    await feed(dp, bot, redis, msg_update("/start"))
    await feed(dp, bot, redis, cb_update("n:checkout"))
    await feed(dp, bot, redis, cb_update("us:name"))
    other = Contact(phone_number="9647700000000", first_name="X", user_id=1)
    await feed(dp, bot, redis, msg_update(contact=other))
    assert not contact.called
    own = Contact(phone_number="9647701234567", first_name="Ali", user_id=9001)
    await feed(dp, bot, redis, msg_update(contact=own))
    assert json.loads(contact.calls[0].request.content) == {
        "phone": "+9647701234567", "contact_user_id": 9001}
    assert "توصيل" in session.texts()[-1]


@respx.mock
async def test_rate_delivered_order_with_stars(env):
    dp, bot, session, redis = env
    respx.post(f"{B}/session").mock(return_value=httpx.Response(200, json={
        "business": BUSINESS, "customer": {"language": "ar", "full_name": "Ali", "phone": ""},
        "is_staff": False, "mini_app_url": None}))
    order = {"id": ORDER, "number": 7, "status": "delivered", "currency": "IQD", "items": [],
             "delivery_fee": 0, "total": 5000, "timeline": [], "can_cancel": False,
             "can_review": True, "review": None}
    respx.get(f"{B}/customers/9001/orders/{ORDER}").mock(
        return_value=httpx.Response(200, json=order))
    rate = respx.post(f"{B}/customers/9001/orders/{ORDER}/review").mock(
        return_value=httpx.Response(200, json={
            **order, "review": {"rating": 4, "comment": "", "reply": "نورتنا"}}))
    await feed(dp, bot, redis, msg_update("/start"))
    await feed(dp, bot, redis, cb_update(f"ov:{h(ORDER)}"))
    assert "قيّمنا" in session.texts()[-1]
    await feed(dp, bot, redis, cb_update(find_button(session.last_markup(), "rv:")[:-1] + "4"))
    assert json.loads(rate.calls[0].request.content) == {"rating": 4}
    assert any("شكراً" in a for a in session.alerts())
    assert "⭐⭐⭐⭐" in session.texts()[-1]
    assert "نورتنا" in session.texts()[-1]


@respx.mock
async def test_table_qr_orders_dine_in_without_phone(env):
    dp, bot, session, redis = env
    respx.post(f"{B}/session").mock(return_value=httpx.Response(200, json={
        "business": {**BUSINESS, "accepts_dine_in": True, "phone_verification_required": True},
        "customer": {"language": "ar", "full_name": "Ali", "phone": "", "phone_verified": False},
        "is_staff": False, "mini_app_url": "https://shop.example/?b=shop"}))
    respx.get(f"{B}/customers/9001/cart").mock(return_value=httpx.Response(200, json=CART))
    quote = respx.post(f"{B}/customers/9001/checkout/quote").mock(return_value=httpx.Response(
        200, json={"subtotal": 19000, "delivery_fee": 0, "discount_total": 0, "total": 19000,
                   "currency": "IQD", "payment_method": "pay_at_pickup", "zone": None}))
    checkout = respx.post(f"{B}/customers/9001/checkout").mock(return_value=httpx.Response(
        201, json={"id": ORDER, "number": 9, "total": 19000, "currency": "IQD"}))
    await feed(dp, bot, redis, msg_update("/start -t12"))
    assert "طاولة 12" in session.texts()[-1]
    web_app = [c for c in session.calls if getattr(c, "reply_markup", None) is not None
               and hasattr(c.reply_markup, "inline_keyboard")][-1]
    assert web_app.reply_markup.inline_keyboard[0][0].web_app.url.endswith("&table=12")
    await feed(dp, bot, redis, cb_update("n:checkout"))
    await feed(dp, bot, redis, cb_update("us:name"))  # straight to notes: no phone, no address
    await feed(dp, bot, redis, cb_update("sk:notes"))
    assert "على الطاولة 12" in session.texts()[-1]
    assert json.loads(quote.calls[0].request.content)["table_label"] == "12"
    await feed(dp, bot, redis, cb_update("cf:1"))
    body = json.loads(checkout.calls[0].request.content)
    assert body["fulfilment"] == "dine_in"
    assert "customer_phone" not in body

    # A plain /start afterwards leaves the table behind.
    await feed(dp, bot, redis, msg_update("/start"))
    await feed(dp, bot, redis, cb_update("n:checkout"))
    await feed(dp, bot, redis, cb_update("us:name"))
    assert "رقم موبايلك" in session.texts()[-1]


@respx.mock
async def test_bot_checkout_can_spend_points(env):
    dp, bot, session, redis = env
    respx.post(f"{B}/session").mock(return_value=httpx.Response(200, json={
        "business": {**BUSINESS, "accepts_delivery": False,
                     "loyalty": {"spend_per_point": 1000, "point_value": 25, "min_redeem": 100}},
        "customer": {"language": "ar", "full_name": "Ali", "phone": "+9647701234567",
                     "phone_verified": True, "points_balance": 300},
        "is_staff": False, "mini_app_url": None}))
    respx.get(f"{B}/customers/9001/cart").mock(return_value=httpx.Response(200, json=CART))

    def quote(request):
        used = json.loads(request.content).get("redeem_points", 0)
        return httpx.Response(200, json={
            "subtotal": 19000, "delivery_fee": 0, "discount_total": used * 25,
            "total": 19000 - used * 25, "currency": "IQD", "payment_method": "pay_at_pickup",
            "zone": None, "points_used": used, "points_discount": used * 25})

    respx.post(f"{B}/customers/9001/checkout/quote").mock(side_effect=quote)
    checkout = respx.post(f"{B}/customers/9001/checkout").mock(return_value=httpx.Response(
        201, json={"id": ORDER, "number": 3, "total": 11500, "currency": "IQD"}))
    await feed(dp, bot, redis, msg_update("/start"))
    await feed(dp, bot, redis, cb_update("n:checkout"))
    await feed(dp, bot, redis, cb_update("us:name"))
    await feed(dp, bot, redis, cb_update("us:phone"))
    await feed(dp, bot, redis, cb_update("sk:notes"))
    assert find_button(session.last_markup(), "us:points")
    await feed(dp, bot, redis, cb_update("us:points"))
    assert "7,500" in session.texts()[-1]
    assert "11,500" in session.texts()[-1]
    await feed(dp, bot, redis, cb_update("cf:1"))
    assert json.loads(checkout.calls[0].request.content)["redeem_points"] == 300


@respx.mock
async def test_staff_button_duplicate_and_unlinked(env):
    dp, bot, session, redis = env
    route = respx.post(f"{B}/staff/transition")
    route.side_effect = [
        httpx.Response(200, json={"applied": True, "status": "confirmed", "version": 2,
                                  "number": 1042}),
        httpx.Response(200, json={"applied": False, "status": "confirmed", "version": 2,
                                  "number": 1042}),
        httpx.Response(403, json={"error": {"code": "permission_denied", "message": "x"}}),
    ]
    data = f"o:{h(ORDER)}:cf:1"
    await feed(dp, bot, redis, cb_update(data))
    await feed(dp, bot, redis, cb_update(data))
    await feed(dp, bot, redis, cb_update(data))
    alerts = session.alerts()
    assert "✅" in alerts[0]
    assert "من قبل" in alerts[1]
    assert "مربوط" in alerts[2]
    sent = json.loads(route.calls[0].request.content)
    assert sent == {"order_id": ORDER, "to": "confirmed", "expected_version": 1,
                    "telegram_user_id": 9001, "reason": ""}


@respx.mock
async def test_reject_asks_for_reason(env):
    dp, bot, session, redis = env
    route = respx.post(f"{B}/staff/transition").mock(return_value=httpx.Response(200, json={
        "applied": True, "status": "rejected", "version": 2, "number": 7}))
    await feed(dp, bot, redis, cb_update(f"o:{h(ORDER)}:rj:1"))
    assert not route.called
    reason_cb = find_button(session.last_markup(), "rr:")
    await feed(dp, bot, redis, cb_update(reason_cb))
    assert json.loads(route.calls[0].request.content)["reason"]


async def test_throttling(env):
    dp, bot, session, redis = env
    await redis.flushdb()
    with respx.mock:
        respx.post(f"{B}/staff/transition").mock(return_value=httpx.Response(200, json={
            "applied": True, "status": "confirmed", "version": 2, "number": 1}))
        await dp.feed_update(bot, cb_update(f"o:{h(ORDER)}:cf:1"))
        await dp.feed_update(bot, cb_update(f"o:{h(ORDER)}:cf:1"))
        assert respx.calls.call_count == 1
