from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.businesses.models import Business
from apps.staff.models import Membership, Permission, Role, StaffInvitation
from apps.staff.permissions_catalog import DEFAULT_ROLES, PERMISSIONS
from apps.subscriptions import services as entitlements
from core.errors import DomainError, NotFoundError


def sync_permission_catalog() -> None:
    for codename, description in PERMISSIONS.items():
        Permission.objects.update_or_create(
            codename=codename, defaults={"description": description}
        )


def create_default_roles(business: Business) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for name, cfg in DEFAULT_ROLES.items():
        role = Role.objects.create(
            business=business, name=name, is_owner=bool(cfg["is_owner"]), is_system=True
        )
        role.permissions.set(Permission.objects.filter(codename__in=cfg["permissions"]))
        roles[name] = role
    return roles


def get_membership(user: Any, business_id: Any) -> Membership | None:
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        Membership.objects.select_related("role", "business")
        .filter(user=user, business_id=business_id, is_active=True)
        .first()
    )


def active_staff_count(business: Business) -> int:
    return Membership.objects.filter(business=business, is_active=True).count()


def _validate_role(business: Business, role: Role) -> None:
    if role.business_id != business.id:
        raise NotFoundError({"role": str(role.id)})


@transaction.atomic
def add_member(business: Business, user: User, role: Role, invited_by: User | None) -> Membership:
    _validate_role(business, role)
    existing = Membership.objects.filter(business=business, user=user).first()
    if existing and existing.is_active:
        return existing
    entitlements.check_limit(business.id, "max_staff", active_staff_count(business))
    if existing:
        existing.is_active, existing.role = True, role
        existing.save(update_fields=["is_active", "role", "updated_at"])
        return existing
    return Membership.objects.create(business=business, user=user, role=role, invited_by=invited_by)


def _owner_count(business: Business, exclude: Membership | None = None) -> int:
    qs = Membership.objects.filter(business=business, is_active=True, role__is_owner=True)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.count()


@transaction.atomic
def change_member_role(membership: Membership, role: Role, actor: Membership) -> Membership:
    _validate_role(membership.business, role)
    if (membership.role.is_owner or role.is_owner) and not actor.role.is_owner:
        raise DomainError("owner_role_protected", status_code=403)
    if (
        membership.role.is_owner
        and not role.is_owner
        and _owner_count(membership.business, exclude=membership) == 0
    ):
        raise DomainError("last_owner")
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    return membership


@transaction.atomic
def deactivate_member(membership: Membership, actor: Membership) -> None:
    if membership.role.is_owner:
        if not actor.role.is_owner:
            raise DomainError("owner_role_protected", status_code=403)
        if _owner_count(membership.business, exclude=membership) == 0:
            raise DomainError("last_owner")
    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])


def update_role(role: Role, name: str | None, permissions: list[str] | None) -> Role:
    if role.is_owner:
        raise DomainError("owner_role_protected", status_code=403)
    if name is not None:
        role.name = name
        role.save(update_fields=["name", "updated_at"])
    if permissions is not None:
        unknown = set(permissions) - set(PERMISSIONS)
        if unknown:
            raise DomainError("validation_error", {"permissions": sorted(unknown)}, 400)
        role.permissions.set(Permission.objects.filter(codename__in=permissions))
    return role


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invitation(
    business: Business, role: Role, invited_by: User, email: str = "", phone: str = ""
) -> tuple[StaffInvitation, str]:
    _validate_role(business, role)
    if role.is_owner:
        raise DomainError("owner_role_protected", status_code=403)
    entitlements.check_limit(business.id, "max_staff", active_staff_count(business))
    token = secrets.token_urlsafe(32)
    inv = StaffInvitation.objects.create(
        business=business,
        role=role,
        email=email,
        phone=phone,
        invited_by=invited_by,
        token_hash=_hash(token),
        expires_at=timezone.now() + timedelta(days=7),
    )
    return inv, token


@transaction.atomic
def accept_invitation(token: str, user: User) -> Membership:
    inv = (
        StaffInvitation.objects.select_for_update()
        .select_related("business", "role")
        .filter(token_hash=_hash(token), accepted_at__isnull=True, expires_at__gt=timezone.now())
        .first()
    )
    if inv is None:
        raise NotFoundError()
    membership = add_member(inv.business, user, inv.role, inv.invited_by)
    inv.accepted_at = timezone.now()
    inv.save(update_fields=["accepted_at", "updated_at"])
    return membership


def members_with_permission(business_id: Any, codename: str) -> list[Membership]:
    return list(
        Membership.objects.select_related("user", "user__telegram")
        .filter(business_id=business_id, is_active=True, role__permissions__codename=codename)
        .distinct()
    )
