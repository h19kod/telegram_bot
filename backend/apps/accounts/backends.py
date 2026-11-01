from __future__ import annotations

from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from apps.accounts.models import User
from core.phone import InvalidPhoneNumber, normalize_phone


class EmailOrPhoneBackend(ModelBackend):
    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        identifier = (username or kwargs.get("email") or kwargs.get("phone") or "").strip()
        if not identifier or not password:
            return None
        user: User | None
        if "@" in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
        else:
            try:
                user = User.objects.filter(phone=normalize_phone(identifier)).first()
            except InvalidPhoneNumber:
                user = None
        if user is None:
            User().set_password(password)  # equalise timing
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
