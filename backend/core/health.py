from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, JsonResponse


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def check_components() -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        result["database"] = "ok"
        result["migrations"] = "ok" if not pending else f"{len(pending)} pending"
    except Exception as exc:
        result["database"] = f"error: {type(exc).__name__}"
    try:
        cache.set("health:ping", "1", 5)
        result["cache"] = "ok" if cache.get("health:ping") == "1" else "error"
    except Exception as exc:
        result["cache"] = f"error: {type(exc).__name__}"
    return result


def readyz(request: HttpRequest) -> JsonResponse:
    components = check_components()
    ok = all(v == "ok" for v in components.values())
    return JsonResponse(
        {"status": "ok" if ok else "degraded", "components": components}, status=200 if ok else 503
    )
