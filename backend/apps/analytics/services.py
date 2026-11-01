"""Business analytics computed in the business timezone. Revenue counts delivered orders."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from apps.customers.models import Customer
from apps.orders.models import OPEN_STATUSES, Order, OrderItem, OrderStatus

DELIVERED = OrderStatus.DELIVERED


def _tz(business: Any) -> ZoneInfo:
    return ZoneInfo(business.timezone or "Asia/Baghdad")


def _day_start(business: Any, d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=_tz(business))


def overview(business: Any, start: date, end: date) -> dict[str, Any]:
    tz = _tz(business)
    today = timezone.now().astimezone(tz).date()
    orders = Order.objects.for_business(business)
    in_range = orders.filter(
        placed_at__gte=_day_start(business, start),
        placed_at__lt=_day_start(business, end + timedelta(days=1)),
    )
    agg = in_range.aggregate(
        total_orders=Count("id"),
        completed=Count("id", filter=Q(status=DELIVERED)),
        cancelled=Count("id", filter=Q(status__in=[OrderStatus.CANCELLED, OrderStatus.REJECTED])),
        sales=Sum("total", filter=Q(status=DELIVERED)),
        avg_order=Avg("total", filter=Q(status=DELIVERED)),
    )
    today_qs = orders.filter(
        placed_at__gte=_day_start(business, today),
        placed_at__lt=_day_start(business, today + timedelta(days=1)),
    )
    return {
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "currency": business.currency,
        "total_orders": agg["total_orders"],
        "completed_orders": agg["completed"],
        "cancelled_orders": agg["cancelled"],
        "total_sales": agg["sales"] or 0,
        "average_order_value": int(agg["avg_order"] or 0),
        "today_orders": today_qs.count(),
        "today_sales": today_qs.filter(status=DELIVERED).aggregate(s=Sum("total"))["s"] or 0,
        "pending_orders": orders.filter(status=OrderStatus.PENDING).count(),
        "open_orders": orders.filter(status__in=OPEN_STATUSES).count(),
        "new_customers": Customer.objects.for_business(business)
        .filter(
            first_order_at__gte=_day_start(business, start),
            first_order_at__lt=_day_start(business, end + timedelta(days=1)),
        )
        .count(),
    }


def sales_series(business: Any, start: date, end: date, interval: str = "day") -> list[dict]:
    trunc = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}[interval]
    tz = _tz(business)
    rows = (
        Order.objects.for_business(business)
        .filter(
            status=DELIVERED,
            placed_at__gte=_day_start(business, start),
            placed_at__lt=_day_start(business, end + timedelta(days=1)),
        )
        .annotate(bucket=trunc("placed_at", tzinfo=tz))
        .values("bucket")
        .annotate(orders=Count("id"), sales=Sum("total"))
        .order_by("bucket")
    )
    by_bucket = {r["bucket"].date(): r for r in rows}
    out = []
    if interval == "day":
        d = start
        while d <= end:
            r = by_bucket.get(d)
            out.append(
                {
                    "date": d.isoformat(),
                    "orders": r["orders"] if r else 0,
                    "sales": r["sales"] if r else 0,
                }
            )
            d += timedelta(days=1)
        return out
    return [
        {"date": k.isoformat(), "orders": v["orders"], "sales": v["sales"]}
        for k, v in by_bucket.items()
    ]


def top_products(business: Any, start: date, end: date, limit: int = 10) -> list[dict]:
    rows = (
        OrderItem.objects.for_business(business)
        .filter(
            order__status=DELIVERED,
            order__placed_at__gte=_day_start(business, start),
            order__placed_at__lt=_day_start(business, end + timedelta(days=1)),
        )
        .values("product_id", "product_name_ar", "product_name_en")
        .annotate(quantity=Sum("quantity"), revenue=Sum("line_total"))
        .order_by("-quantity")[:limit]
    )
    return [
        {
            "product_id": str(r["product_id"]) if r["product_id"] else None,
            "name_ar": r["product_name_ar"],
            "name_en": r["product_name_en"],
            "quantity": r["quantity"],
            "revenue": r["revenue"],
        }
        for r in rows
    ]


def recent_customers(business: Any, limit: int = 10) -> list[dict]:
    qs = (
        Customer.objects.for_business(business)
        .filter(last_order_at__isnull=False)
        .order_by("-last_order_at")[:limit]
    )
    return [
        {
            "id": str(c.id),
            "name": c.display_name,
            "orders_count": c.orders_count,
            "total_spent": c.total_spent,
            "last_order_at": c.last_order_at,
        }
        for c in qs
    ]


def status_breakdown(business: Any, start: date, end: date) -> dict[str, int]:
    rows = (
        Order.objects.for_business(business)
        .filter(
            placed_at__gte=_day_start(business, start),
            placed_at__lt=_day_start(business, end + timedelta(days=1)),
        )
        .values("status")
        .annotate(n=Count("id"))
    )
    return {r["status"]: r["n"] for r in rows}
