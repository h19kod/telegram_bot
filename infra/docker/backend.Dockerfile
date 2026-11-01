# syntax=docker/dockerfile:1.7
FROM docker.io/library/python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY backend/ ./

FROM docker.io/library/python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home /app app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.prod
RUN DJANGO_SECRET_KEY=build FIELD_ENCRYPTION_KEYS=6HGhQxIVW-VoiF-qGdziTZSnnjUOm1LStkrEZQwxqmQ= \
    INTERNAL_API_SECRET=build DATABASE_URL=sqlite:////tmp/x.db \
    python manage.py collectstatic --noinput -v0
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
CMD ["gunicorn", "config.asgi:application", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--forwarded-allow-ips", "*"]
