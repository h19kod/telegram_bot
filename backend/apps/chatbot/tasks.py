from __future__ import annotations

import logging
from html import escape

from celery import shared_task

from core.telegram import TelegramAPIError

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True, max_retries=3)
def send_staff_reply(self, message_id: str) -> None:  # type: ignore[no-untyped-def]
    """Deliver a staff answer from the dashboard to the customer's Telegram chat."""
    from apps.businesses.services import bot_for_business
    from apps.chatbot.models import AIMessage
    from core.telegram import BotAPI

    msg = (
        AIMessage.objects.select_related("conversation__customer")
        .filter(id=message_id, provider="staff")
        .first()
    )
    if msg is None:
        return
    customer = msg.conversation.customer
    bot = bot_for_business(msg.business_id)
    if bot is None:
        AIMessage.objects.filter(pk=msg.pk).update(error="no bot")
        return
    try:
        BotAPI(bot.token).send_message(customer.telegram_user_id, f"💬 {escape(msg.content)}")
    except TelegramAPIError as exc:
        if exc.retry_after or exc.error_code >= 500 or exc.error_code == 0:
            raise self.retry(countdown=exc.retry_after or 5 * (self.request.retries + 1)) from None
        logger.warning("staff reply %s not delivered: %s", msg.id, exc.description)
        AIMessage.objects.filter(pk=msg.pk).update(error=f"not delivered: {exc.description}"[:300])
        return
