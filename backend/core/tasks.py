import time

from celery import shared_task
from django.core.cache import cache


@shared_task(ignore_result=True)
def worker_heartbeat() -> None:
    cache.set("heartbeat:worker", int(time.time()), 120)
