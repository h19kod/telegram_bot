"""Transactional outbox: record intent inside the domain transaction, deliver after commit."""

from __future__ import annotations

import contextlib
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.models import NotificationOutbox


def enqueue(event_type: str, business_id: Any, payload: dict[str, Any], dedup_key: str) -> None:
    try:
        with transaction.atomic():
            NotificationOutbox.objects.create(
                business_id=business_id,
                event_type=event_type,
                payload=payload,
                dedup_key=dedup_key,
                next_attempt_at=timezone.now(),
            )
    except IntegrityError:
        return  # already enqueued: idempotent

    def _kick() -> None:
        from apps.notifications.tasks import drain_outbox

        with contextlib.suppress(Exception):
            drain_outbox.delay()

    transaction.on_commit(_kick)
