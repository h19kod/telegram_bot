from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import BaseModel, TenantModel


class Permission(models.Model):
    codename = models.CharField(max_length=64, primary_key=True)
    description = models.CharField(max_length=200)

    def __str__(self) -> str:
        return self.codename


class Role(TenantModel):
    name = models.CharField(max_length=64)
    is_owner = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "name"], name="role_unique_name"),
            models.UniqueConstraint(
                fields=["business"], condition=models.Q(is_owner=True), name="one_owner_role"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Membership(TenantModel):
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    branches = models.ManyToManyField("businesses.Branch", blank=True, related_name="+")
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "user"], name="membership_unique")
        ]

    def permission_set(self) -> frozenset[str]:
        cached = getattr(self, "_perm_cache", None)
        if cached is None:
            cached = frozenset(self.role.permissions.values_list("codename", flat=True))
            self._perm_cache = cached
        return cached

    def has_perm(self, codename: str) -> bool:
        return self.is_active and codename in self.permission_set()


class StaffInvitation(TenantModel):
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=16, blank=True)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="+")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )


__all__ = ["BaseModel", "Membership", "Permission", "Role", "StaffInvitation"]
