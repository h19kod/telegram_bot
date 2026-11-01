from celery import shared_task

from apps.notifications.services import drain


@shared_task(ignore_result=True)
def drain_outbox() -> int:
    return drain()
