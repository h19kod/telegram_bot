import uuid

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _reference_data(request):
    if "django_db_setup" not in request.fixturenames and not request.node.get_closest_marker(
        "django_db"
    ):
        return
    request.getfixturevalue("django_db_blocker")
    from apps.subscriptions.models import Plan
    from core.seed import ensure_reference_data

    if not Plan.objects.exists():
        ensure_reference_data()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _no_celery(monkeypatch):
    """Outbox kicks are best-effort; tests drain the outbox explicitly."""
    from apps.notifications import tasks

    monkeypatch.setattr(tasks.drain_outbox, "delay", lambda *a, **k: None)


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def idem():
    return lambda: str(uuid.uuid4())
