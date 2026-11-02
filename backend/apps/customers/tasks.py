from __future__ import annotations

import logging

from celery import shared_task

from core import whatsapp

logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True, max_retries=3)
def send_phone_code(self, verification_id: str, code: str, lang: str) -> None:  # type: ignore[no-untyped-def]
    """The code travels only through the broker; the database keeps its HMAC."""
    from apps.customers.models import PhoneVerification

    v = PhoneVerification.objects.filter(id=verification_id).first()
    if v is None or v.verified_at is not None:
        return
    try:
        whatsapp.get_sender().send_code(v.phone, code, lang)
    except whatsapp.WhatsAppError as exc:
        logger.warning("whatsapp code to %s failed: %s", v.id, exc)
        if exc.retryable:
            raise self.retry(countdown=5 * (self.request.retries + 1)) from None
