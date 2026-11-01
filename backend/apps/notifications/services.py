"""Delivers outbox events to Telegram. Every step is idempotent so retries are safe."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import TelegramAccount
from apps.businesses.models import TelegramBot
from apps.businesses.services import bot_for_business
from apps.notifications.models import NotificationOutbox, OutboxStatus
from apps.notifications.render import customer_status_text, staff_keyboard, staff_order_text
from apps.orders.models import (
    Channel,
    NotificationKind,
    Order,
    OrderNotificationMessage,
    OrderStatus,
)
from apps.staff.services import members_with_permission
from core.telegram import BotAPI, TelegramAPIError

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8


class RetryLater(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds


def staff_chat_ids(order: Order) -> list[int]:
    chats: list[int] = list(order.business.settings.notification_chat_ids or [])
    for m in members_with_permission(order.business_id, "orders.receive_notifications"):
        if m.has_perm("orders.view_assigned_only") and order.assigned_driver_id != m.id:
            continue
        tg = TelegramAccount.objects.filter(user_id=m.user_id).first()
        if tg:
            chats.append(tg.telegram_user_id)
    return list(dict.fromkeys(chats))


def _send(api: BotAPI, chat_id: int, text: str, markup: Any) -> int | None:
    try:
        return int(api.send_message(chat_id, text, markup)["message_id"])
    except TelegramAPIError as exc:
        if exc.retry_after:
            raise RetryLater(exc.retry_after) from None
        if exc.error_code in (400, 403):  # chat not found / bot blocked: skip this recipient
            logger.info("Telegram rejected message to chat: %s", exc.description)
            return None
        raise


def _record(
    order: Order, bot: TelegramBot, chat_id: int, message_id: int, kind: str, event_key: str = ""
) -> None:
    try:
        with transaction.atomic():
            OrderNotificationMessage.objects.create(
                business_id=order.business_id,
                order=order,
                bot=bot,
                chat_id=chat_id,
                message_id=message_id,
                kind=kind,
                event_key=event_key,
            )
    except IntegrityError:
        pass


def notify_staff_new_order(order: Order, bot: TelegramBot, api: BotAPI) -> None:
    text = staff_order_text(order, order.business.default_language)
    markup = staff_keyboard(order, order.business.default_language)
    already = set(
        OrderNotificationMessage.objects.filter(
            order=order, kind=NotificationKind.STAFF
        ).values_list("chat_id", flat=True)
    )
    for chat_id in staff_chat_ids(order):
        if chat_id in already:
            continue
        mid = _send(api, chat_id, text, markup)
        if mid:
            _record(order, bot, chat_id, mid, NotificationKind.STAFF)


def sync_staff_messages(order: Order, api: BotAPI) -> None:
    text = staff_order_text(order, order.business.default_language)
    markup = staff_keyboard(order, order.business.default_language) or {"inline_keyboard": []}
    for msg in OrderNotificationMessage.objects.filter(order=order, kind=NotificationKind.STAFF):
        try:
            api.edit_message_text(msg.chat_id, msg.message_id, text, markup)
        except TelegramAPIError as exc:
            if exc.retry_after:
                raise RetryLater(exc.retry_after) from None
            if "message is not modified" not in exc.description:
                logger.info("Could not edit staff message: %s", exc.description)


def notify_customer(order: Order, bot: TelegramBot, api: BotAPI, event_key: str) -> None:
    chat_id = order.customer.telegram_user_id
    if OrderNotificationMessage.objects.filter(
        order=order, chat_id=chat_id, kind=NotificationKind.CUSTOMER, event_key=event_key
    ).exists():
        return
    mid = _send(api, chat_id, customer_status_text(order), None)
    _record(order, bot, chat_id, mid or 0, NotificationKind.CUSTOMER, event_key)


def handle(event: NotificationOutbox) -> None:
    order_id = event.payload.get("order_id")
    order = (
        Order.objects.select_related("business__settings", "customer").filter(id=order_id).first()
    )
    if order is None:
        return
    bot = bot_for_business(order.business_id)
    if bot is None:
        logger.info("No bot configured for business %s; skipping", order.business_id)
        return
    api = BotAPI(bot.token)
    if event.event_type == "order.placed":
        notify_staff_new_order(order, bot, api)
        if order.channel != Channel.BOT:
            notify_customer(order, bot, api, "placed")
    elif event.event_type == "order.status_changed":
        # Staff messages always reflect the latest state; customers hear about the
        # change only if it is still current (avoids sending stale statuses after bursts).
        sync_staff_messages(order, api)
        to = event.payload.get("to")
        if event.payload.get("version") == order.version:
            notify_customer(order, bot, api, f"v{order.version}")
        if to == OrderStatus.OUT_FOR_DELIVERY and order.assigned_driver_id:
            notify_staff_new_order(order, bot, api)


def drain(batch: int = 50) -> int:
    now = timezone.now()
    processed = 0
    with transaction.atomic():
        events = list(
            NotificationOutbox.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxStatus.PENDING, next_attempt_at__lte=now)
            .order_by("created_at")[:batch]
        )
        for event in events:
            event.attempts += 1
            try:
                handle(event)
                event.status, event.processed_at, event.last_error = (
                    OutboxStatus.SENT,
                    timezone.now(),
                    "",
                )
            except RetryLater as exc:
                event.next_attempt_at = timezone.now() + timedelta(seconds=exc.seconds + 1)
            except Exception as exc:
                logger.warning("Outbox delivery failed", exc_info=True)
                event.last_error = f"{type(exc).__name__}: {exc}"[:500]
                if event.attempts >= MAX_ATTEMPTS:
                    event.status = OutboxStatus.FAILED
                else:
                    event.next_attempt_at = timezone.now() + timedelta(
                        seconds=min(2**event.attempts * 5, 3600)
                    )
            event.save()
            processed += 1
    return processed
