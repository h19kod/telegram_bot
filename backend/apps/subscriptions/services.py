"""Entitlement resolution and enforcement. Limits are data — never hardcode them."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.subscriptions.models import (
    LIVE_SUBSCRIPTION_STATUSES,
    EntitlementOverride,
    Feature,
    Plan,
    PlanEntitlement,
    ResetPeriod,
    Subscription,
    SubscriptionStatus,
    UsageCounter,
)
from core.errors import DomainError

_CACHE_TTL = 300


def _cache_key(business_id: Any) -> str:
    return f"entitlements:{business_id}"


def invalidate(business_id: Any) -> None:
    cache.delete(_cache_key(business_id))


def live_subscription(business_id: Any) -> Subscription | None:
    return (
        Subscription.objects.select_related("plan")
        .filter(business_id=business_id, status__in=LIVE_SUBSCRIPTION_STATUSES)
        .first()
    )


def resolve_all(business_id: Any) -> dict[str, Any]:
    """Effective entitlement values: override → live plan → default plan → feature default."""
    cached = cache.get(_cache_key(business_id))
    if cached is not None:
        return cached
    values: dict[str, Any] = {f.key: f.default_value for f in Feature.objects.all()}
    sub = live_subscription(business_id)
    plan = sub.plan if sub else Plan.objects.filter(is_default=True).first()
    if plan is not None:
        for ent in PlanEntitlement.objects.filter(plan=plan).select_related("feature"):
            values[ent.feature_id] = ent.value
    now = timezone.now()
    for ov in EntitlementOverride.objects.filter(business_id=business_id):
        if ov.expires_at is None or ov.expires_at > now:
            values[ov.feature_id] = ov.value
    cache.set(_cache_key(business_id), values, _CACHE_TTL)
    return values


def value(business_id: Any, key: str) -> Any:
    return resolve_all(business_id).get(key)


def has_feature(business_id: Any, key: str) -> bool:
    return bool(value(business_id, key))


def require_feature(business_id: Any, key: str) -> None:
    if not has_feature(business_id, key):
        raise DomainError("feature_not_available", {"feature": key}, status_code=403)


def check_limit(business_id: Any, key: str, current: int, adding: int = 1) -> None:
    """For count-based limits (products, staff…). `None` means unlimited."""
    limit = value(business_id, key)
    if limit is None:
        return
    if current + adding > int(limit):
        raise DomainError(
            "plan_limit_exceeded", {"feature": key, "limit": limit, "current": current}
        )


def _period_start(feature: Feature, today: date | None = None) -> date:
    today = today or timezone.localdate()
    if feature.reset_period == ResetPeriod.MONTH:
        return today.replace(day=1)
    return date(2000, 1, 1)


def consume(business_id: Any, key: str, amount: int = 1) -> None:
    """Atomically consume a metered entitlement; raises when it would exceed the limit.

    Must be called inside the transaction of the action being metered so a rollback refunds it.
    """
    feature = Feature.objects.get(key=key)
    limit = value(business_id, key)
    period = _period_start(feature)
    counter_qs = UsageCounter.objects.filter(
        business_id=business_id, feature=feature, period_start=period
    )
    if not counter_qs.exists():
        try:
            with transaction.atomic():
                UsageCounter.objects.create(
                    business_id=business_id, feature=feature, period_start=period, used=0
                )
        except IntegrityError:
            pass
    qs = counter_qs
    if limit is not None:
        qs = qs.filter(used__lte=int(limit) - amount)
    if qs.update(used=F("used") + amount) == 0:
        raise DomainError("plan_limit_exceeded", {"feature": key, "limit": limit})


def usage(business_id: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for feature in Feature.objects.filter(is_metered=True):
        row = UsageCounter.objects.filter(
            business_id=business_id, feature=feature, period_start=_period_start(feature)
        ).first()
        out[feature.key] = row.used if row else 0
    return out


@transaction.atomic
def start_subscription(
    business_id: Any, plan: Plan, months: int | None = None, trial: bool = False
) -> Subscription:
    now = timezone.now()
    Subscription.objects.filter(
        business_id=business_id, status__in=LIVE_SUBSCRIPTION_STATUSES
    ).update(status=SubscriptionStatus.CANCELLED)
    if trial and plan.trial_days:
        status, end = SubscriptionStatus.TRIALING, now + timedelta(days=plan.trial_days)
    elif months:
        status, end = SubscriptionStatus.ACTIVE, now + timedelta(days=30 * months)
    else:
        status, end = SubscriptionStatus.ACTIVE, None  # open-ended (free plan)
    sub = Subscription.objects.create(
        business_id=business_id,
        plan=plan,
        status=status,
        current_period_start=now,
        current_period_end=end,
    )
    transaction.on_commit(lambda: invalidate(business_id))
    return sub


def extend_subscription(sub: Subscription, months: int) -> Subscription:
    now = timezone.now()
    base = (
        sub.current_period_end if sub.current_period_end and sub.current_period_end > now else now
    )
    sub.current_period_end = base + timedelta(days=30 * months)
    sub.status = SubscriptionStatus.ACTIVE
    sub.grace_until = None
    sub.save(update_fields=["current_period_end", "status", "grace_until", "updated_at"])
    invalidate(sub.business_id)
    return sub


GRACE_DAYS = 3


def expire_due_subscriptions(now: Any = None) -> int:
    """active/trialing past end → past_due (grace) → expired → business falls back to default plan."""
    now = now or timezone.now()
    changed = 0
    for sub in Subscription.objects.filter(
        status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
        current_period_end__lt=now,
    ):
        sub.status = SubscriptionStatus.PAST_DUE
        sub.grace_until = now + timedelta(days=GRACE_DAYS)
        sub.save(update_fields=["status", "grace_until", "updated_at"])
        invalidate(sub.business_id)
        changed += 1
    for sub in Subscription.objects.filter(status=SubscriptionStatus.PAST_DUE, grace_until__lt=now):
        sub.status = SubscriptionStatus.EXPIRED
        sub.save(update_fields=["status", "updated_at"])
        invalidate(sub.business_id)
        changed += 1
    return changed
