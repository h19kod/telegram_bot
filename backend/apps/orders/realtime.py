"""Thin WebSocket events to dashboard clients (they refetch details via the API)."""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def group_name(business_id: Any) -> str:
    return f"business.{business_id}.orders"


def broadcast(business_id: Any, event: dict[str, Any]) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            group_name(business_id), {"type": "order.event", "event": event}
        )
    except Exception:
        logger.warning("WebSocket broadcast failed", exc_info=True)
