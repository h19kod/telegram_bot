from __future__ import annotations

import contextlib
import secrets
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.businesses.models import (
    Branch,
    Business,
    BusinessSettings,
    BusinessStatus,
    Closure,
    TelegramBot,
    WebhookStatus,
    WorkingHours,
)
from apps.orders.models import OrderCounter
from apps.staff.models import Membership
from apps.staff.services import create_default_roles
from apps.subscriptions import services as entitlements
from apps.subscriptions.models import Plan
from core.crypto import encrypt
from core.errors import DomainError
from core.telegram import BotAPI, TelegramAPIError


@transaction.atomic
def create_business(
    owner: User, *, slug: str, name_ar: str, plan_code: str | None = None, **fields: Any
) -> Business:
    business = Business.objects.create(owner=owner, slug=slug, name_ar=name_ar, **fields)
    Branch.objects.create(
        business=business, name_ar=name_ar, name_en=fields.get("name_en", ""), is_default=True
    )
    BusinessSettings.objects.create(business=business)
    OrderCounter.objects.create(business=business)
    roles = create_default_roles(business)
    Membership.objects.create(business=business, user=owner, role=roles["Owner"])
    plan = (
        Plan.objects.get(code=plan_code)
        if plan_code
        else Plan.objects.filter(is_default=True).first()
    )
    if plan is not None:
        entitlements.start_subscription(business.id, plan, trial=plan.trial_days > 0)
    return business


def default_branch(business: Business | Any) -> Branch:
    business_id = getattr(business, "pk", business)
    branch = Branch.objects.filter(business_id=business_id, is_default=True).first()
    if branch is None:
        branch = Branch.objects.filter(business_id=business_id, is_active=True).first()
    if branch is None:
        raise DomainError("business_unavailable")
    return branch


def _interval_contains(opens: time, closes: time, t: time) -> bool:
    if closes > opens:
        return opens <= t < closes
    return t >= opens or t < closes  # crosses midnight (or 24h when equal)


def is_open(branch: Branch, at: datetime | None = None) -> bool:
    """Open if not manually closed, not in a closure and inside a working-hours interval.

    A branch with no working hours configured is treated as always open.
    """
    if branch.is_temporarily_closed or not branch.is_active:
        return False
    at = at or timezone.now()
    if Closure.objects.filter(branch=branch, starts_at__lte=at, ends_at__gt=at).exists():
        return False
    hours = list(WorkingHours.objects.filter(branch=branch))
    if not hours:
        return True
    tz = ZoneInfo(branch.business.timezone if hasattr(branch, "business") else "Asia/Baghdad")
    local = at.astimezone(tz)
    today, now_t = local.weekday(), local.time()
    yesterday = (today - 1) % 7
    for h in hours:
        crosses = h.closes_at <= h.opens_at
        # Today's interval; the after-midnight tail of a crossing interval belongs to yesterday.
        in_today = h.weekday == today and _interval_contains(h.opens_at, h.closes_at, now_t)
        if in_today and (not crosses or now_t >= h.opens_at):
            return True
        if crosses and h.weekday == yesterday and now_t < h.closes_at:
            return True
    return False


def ensure_can_take_orders(business: Business) -> None:
    if business.status != BusinessStatus.ACTIVE:
        raise DomainError("business_unavailable")


@transaction.atomic
def set_working_hours(branch: Branch, intervals: list[dict[str, Any]]) -> list[WorkingHours]:
    WorkingHours.objects.filter(branch=branch).delete()
    return [
        WorkingHours.objects.create(business_id=branch.business_id, branch=branch, **iv)
        for iv in intervals
    ]


def webhook_url(bot: TelegramBot) -> str:
    base = settings.TELEGRAM_WEBHOOK_BASE_URL.rstrip("/")
    return f"{base}/tg/webhook/{bot.id}"


def connect_bot(business: Business, token: str) -> TelegramBot:
    """Validate the token with getMe, store it encrypted, and register the webhook."""
    entitlements.require_feature(business.id, "custom_bot")
    token = token.strip()
    api = BotAPI(token)
    try:
        me = api.get_me()
    except TelegramAPIError:
        raise DomainError("invalid_bot_token", status_code=400) from None
    if not me.get("is_bot"):
        raise DomainError("invalid_bot_token", status_code=400)
    with transaction.atomic():
        TelegramBot.objects.filter(business=business).delete()
        try:
            bot = TelegramBot.objects.create(
                business=business,
                bot_telegram_id=me["id"],
                username=me.get("username", ""),
                token_encrypted=encrypt(token),
                webhook_secret=secrets.token_urlsafe(32),
            )
        except IntegrityError:
            raise DomainError(
                "invalid_bot_token", {"reason": "bot already connected"}, 409
            ) from None
    register_webhook(bot, token)
    return bot


def register_webhook(bot: TelegramBot, token: str | None = None) -> TelegramBot:
    if not settings.TELEGRAM_WEBHOOK_BASE_URL:
        bot.webhook_status = WebhookStatus.POLLING
        bot.last_error = ""
    else:
        try:
            BotAPI(token or bot.token).set_webhook(webhook_url(bot), bot.webhook_secret)
            bot.webhook_status, bot.last_error = WebhookStatus.ACTIVE, ""
        except TelegramAPIError as exc:
            bot.webhook_status, bot.last_error = WebhookStatus.ERROR, exc.description[:500]
    bot.save(update_fields=["webhook_status", "last_error", "updated_at"])
    return bot


def disconnect_bot(business: Business) -> None:
    bot = TelegramBot.objects.filter(business=business).first()
    if bot is None:
        return
    with contextlib.suppress(TelegramAPIError):
        BotAPI(bot.token).delete_webhook()
    bot.delete()


def bot_for_business(business_id: Any) -> TelegramBot | None:
    """The bot that serves this business: its own bot, else the shared platform bot."""
    bot = TelegramBot.objects.filter(business_id=business_id, is_active=True).first()
    return bot or TelegramBot.objects.filter(is_shared_platform_bot=True, is_active=True).first()


def customer_branch(customer: Any) -> Branch:
    """The branch a customer orders from: their choice while it is active, else the default."""
    if customer.preferred_branch_id:
        branch = Branch.objects.filter(
            id=customer.preferred_branch_id, business_id=customer.business_id, is_active=True
        ).first()
        if branch:
            return branch
    return default_branch(customer.business_id)


def choose_branch(customer: Any, branch_id: Any) -> Branch:
    """Set the customer's branch. A foreign or inactive branch id is simply not found."""
    from core.errors import NotFoundError

    branch = Branch.objects.filter(
        id=branch_id, business_id=customer.business_id, is_active=True
    ).first()
    if branch is None:
        raise NotFoundError()
    customer.preferred_branch = branch
    customer.save(update_fields=["preferred_branch", "updated_at"])
    return branch


def store_link(business: Business, table: str = "") -> str | None:
    """The t.me link customers open: the shop's own bot, else the shared bot with its slug.

    A table QR adds `-t<table>` to the start payload (`?start=-t5`, shared: `?start=slug-t5`);
    the bot then takes dine-in orders for that table.
    """
    suffix = f"-t{table}" if table else ""
    own = TelegramBot.objects.filter(business=business).first()
    if own:
        return f"https://t.me/{own.username}" + (f"?start={suffix}" if suffix else "")
    shared = TelegramBot.objects.filter(is_shared_platform_bot=True, is_active=True).first()
    return f"https://t.me/{shared.username}?start={business.slug}{suffix}" if shared else None


def qr_code(data: str, kind: str = "svg", scale: int = 10) -> tuple[bytes, str]:
    """A printable QR code (error correction H survives a logo sticker or a scratched print)."""
    import io

    import segno

    qr = segno.make(data, error="h", micro=False)
    buf = io.BytesIO()
    if kind == "png":
        qr.save(buf, kind="png", scale=scale, border=2)
        return buf.getvalue(), "image/png"
    qr.save(buf, kind="svg", scale=scale, border=2, xmldecl=False, svgns=True)
    return buf.getvalue(), "image/svg+xml"


def suspend(business: Business, reason: str) -> Business:
    business.status, business.suspended_reason = BusinessStatus.SUSPENDED, reason
    business.save(update_fields=["status", "suspended_reason", "updated_at"])
    return business


def activate(business: Business) -> Business:
    business.status, business.suspended_reason = BusinessStatus.ACTIVE, ""
    business.save(update_fields=["status", "suspended_reason", "updated_at"])
    return business
