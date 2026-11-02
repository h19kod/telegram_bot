"""Order ratings: a customer rates their own delivered order; staff may reply."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.customers.models import Customer
from apps.orders.models import Order, OrderReview, OrderStatus
from core.errors import DomainError, NotFoundError

REVIEW_WINDOW = timedelta(days=7)


def can_review(order: Order) -> bool:
    return bool(
        order.status == OrderStatus.DELIVERED
        and order.delivered_at
        and timezone.now() - order.delivered_at <= REVIEW_WINDOW
    )


def submit_review(customer: Customer, order_id: Any, rating: int, comment: str = "") -> OrderReview:
    """Create or (within the window) update the customer's rating of their order."""
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        raise DomainError("validation_error", {"rating": ["1-5"]}, 400)
    comment = (comment or "").strip()[:500]
    with transaction.atomic():
        order = (
            Order.objects.for_business(customer.business_id)
            .select_for_update()
            .filter(id=order_id, customer=customer)
            .first()
        )
        if order is None:
            raise NotFoundError()
        if not can_review(order):
            raise DomainError("review_not_allowed")
        review, created = OrderReview.objects.get_or_create(
            order=order,
            defaults={
                "business_id": order.business_id,
                "customer": customer,
                "rating": rating,
                "comment": comment,
            },
        )
        if not created:
            review.rating, review.comment = rating, comment
            review.save(update_fields=["rating", "comment", "updated_at"])
    return review


def reply_to_review(business: Any, review_id: Any, user: Any, text: str) -> OrderReview:
    text = (text or "").strip()[:500]
    review = OrderReview.objects.for_business(business).filter(id=review_id).first()
    if review is None:
        raise NotFoundError()
    review.reply = text
    review.replied_at = timezone.now() if text else None
    review.replied_by = user if text else None
    review.save(update_fields=["reply", "replied_at", "replied_by", "updated_at"])
    return review


def rating_summary(business: Any) -> dict[str, Any]:
    agg = OrderReview.objects.for_business(business).aggregate(avg=Avg("rating"), n=Count("id"))
    return {"rating_avg": round(agg["avg"], 1) if agg["avg"] else None, "rating_count": agg["n"]}
