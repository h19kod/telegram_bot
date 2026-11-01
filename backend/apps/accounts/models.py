from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import BaseModel, Language


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str | None, phone: str | None, password: str | None, **extra: Any):
        if not email and not phone:
            raise ValueError("Email or phone is required")
        email = self.normalize_email(email).lower() if email else None
        user = self.model(email=email, phone=phone or None, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str | None = None,
        password: str | None = None,
        phone: str | None = None,
        **extra: Any,
    ) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, phone, password, **extra)

    def create_superuser(self, email: str, password: str, **extra: Any) -> User:
        extra.update(is_staff=True, is_superuser=True, is_platform_admin=True)
        return self._create(email, None, password, **extra)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=16, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=150, blank=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.AR)
    is_platform_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    totp_secret_encrypted = models.BinaryField(null=True, blank=True, editable=False)
    totp_enabled = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(email__isnull=False) | Q(phone__isnull=False),
                name="user_email_or_phone",
            )
        ]

    def __str__(self) -> str:
        return self.email or self.phone or str(self.id)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class TelegramAccount(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="telegram")
    telegram_user_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=64, blank=True)
    first_name = models.CharField(max_length=128, blank=True)


class TelegramLinkCode(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="telegram_link_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
