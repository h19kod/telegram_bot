from celery import shared_task

from apps.subscriptions.services import expire_due_subscriptions


@shared_task
def expire_subscriptions() -> int:
    return expire_due_subscriptions()
