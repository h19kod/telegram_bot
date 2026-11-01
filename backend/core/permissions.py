from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_platform_admin):
            return False
        # Platform admins must have 2FA enabled (can be relaxed only in development).
        return bool(user.totp_enabled or not settings.PLATFORM_ADMIN_REQUIRE_2FA)
