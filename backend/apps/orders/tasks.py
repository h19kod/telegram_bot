from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.orders.models import Cart, CartStatus
from apps.orders.services.transitions import auto_reject_stale


@shared_task
def auto_reject_stale_orders() -> int:
    return auto_reject_stale()


@shared_task
def expire_carts() -> int:
    now = timezone.now()
    n = Cart.objects.filter(status=CartStatus.ACTIVE, expires_at__lt=now).update(
        status=CartStatus.ABANDONED
    )
    Cart.objects.filter(
        status=CartStatus.ABANDONED, updated_at__lt=now - timedelta(days=30)
    ).delete()
    return n
