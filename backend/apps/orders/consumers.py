"""Dashboard realtime: ws/b/<business_id>/?ticket=<single-use ticket>."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts.services import consume_ws_ticket
from apps.orders.realtime import group_name
from apps.staff.models import Membership


@database_sync_to_async
def _authorize(ticket: str, business_id: str) -> bool:
    user_id = consume_ws_ticket(ticket)
    if not user_id:
        return False
    m = (
        Membership.objects.select_related("role")
        .filter(user_id=user_id, business_id=business_id, is_active=True, user__is_active=True)
        .first()
    )
    return bool(m and m.has_perm("orders.view") and not m.has_perm("orders.view_assigned_only"))


class OrdersConsumer(AsyncJsonWebsocketConsumer):
    group: str | None = None

    async def connect(self) -> None:
        business_id = self.scope["url_route"]["kwargs"]["business_id"]
        qs = parse_qs(self.scope.get("query_string", b"").decode())
        ticket = (qs.get("ticket") or [""])[0]
        if not ticket or not await _authorize(ticket, business_id):
            await self.close(code=4401)
            return
        self.group = group_name(business_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        if content == {"type": "ping"}:
            await self.send_json({"type": "pong"})

    async def order_event(self, message: dict[str, Any]) -> None:
        await self.send_json(message["event"])
