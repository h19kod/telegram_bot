from __future__ import annotations

import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder

from apps.platform_admin.models import AuditLog


def _ip(request: Any) -> str | None:
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def audit(
    request: Any,
    action: str,
    business: Any = None,
    target: Any = None,
    changes: dict[str, Any] | None = None,
) -> AuditLog:
    safe = json.loads(json.dumps(changes or {}, cls=DjangoJSONEncoder, default=str))
    for secret_key in ("bot_token", "password", "token"):
        safe.pop(secret_key, None)
    user = getattr(request, "user", None)
    return AuditLog.objects.create(
        actor=user if getattr(user, "is_authenticated", False) else None,
        business=business,
        action=action,
        target_type=type(target).__name__ if target is not None else "",
        target_id=str(getattr(target, "pk", "")) if target is not None else "",
        changes=safe,
        ip=_ip(request),
    )
