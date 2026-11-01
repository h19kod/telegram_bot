"""Staff order buttons. Identity comes from the linked Telegram account on the backend; the
backend checks permissions and versions, so duplicate or stale presses are harmless."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from sopbot.api import ApiError
from sopbot.context import Ctx
from sopbot.handlers.common import answer_cb
from sopbot.keyboards import RejectReason, StaffAction, reject_reasons_kb, u
from sopbot.texts import REJECT_REASONS, status_label, t

router = Router(name="staff")
CODES = {
    "cf": "confirmed",
    "rj": "rejected",
    "pr": "preparing",
    "rd": "ready",
    "od": "out_for_delivery",
    "dl": "delivered",
    "cn": "cancelled",
}


@router.callback_query(StaffAction.filter())
async def on_staff_action(cb: CallbackQuery, callback_data: StaffAction, ctx: Ctx) -> None:
    to = CODES.get(callback_data.code)
    if to is None:
        await answer_cb(cb)
        return
    if to in ("rejected", "cancelled"):
        await answer_cb(cb)
        await cb.message.edit_reply_markup(
            reply_markup=reject_reasons_kb(
                callback_data.order, callback_data.code, callback_data.version, ctx.lang
            )
        )
        return
    await _apply(cb, ctx, callback_data.order, to, callback_data.version, "")


@router.callback_query(RejectReason.filter())
async def on_reason(cb: CallbackQuery, callback_data: RejectReason, ctx: Ctx) -> None:
    to = CODES.get(callback_data.code)
    if to not in ("rejected", "cancelled") or not 0 <= callback_data.idx < len(REJECT_REASONS):
        await answer_cb(cb)
        return
    reason = REJECT_REASONS[callback_data.idx]["ar"]
    await _apply(cb, ctx, callback_data.order, to, callback_data.version, reason)


async def _apply(
    cb: CallbackQuery, ctx: Ctx, order_hex: str, to: str, version: int, reason: str
) -> None:
    try:
        res = await ctx.api.staff_transition(
            ctx.bot_id, u(order_hex), to, version, cb.from_user.id, reason
        )
    except ApiError as exc:
        if exc.status == 403:
            await answer_cb(cb, t("staff_not_linked", ctx.lang), alert=True)
        elif exc.code == "stale_order_version":
            status = status_label(exc.details.get("status", ""), ctx.lang)
            await answer_cb(cb, t("staff_stale", ctx.lang, status=status), alert=True)
        else:
            await answer_cb(cb, exc.message or t("error_generic", ctx.lang), alert=True)
        return
    key = "staff_applied" if res["applied"] else "staff_already"
    await answer_cb(
        cb, t(key, ctx.lang, number=res["number"], status=status_label(res["status"], ctx.lang))
    )
    # The backend edits every staff copy of this order message via the outbox.
