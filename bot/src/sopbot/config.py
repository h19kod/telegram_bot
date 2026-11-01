from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parents[3] / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    backend_url: str = field(
        default_factory=lambda: os.environ.get("BACKEND_INTERNAL_URL", "http://localhost:8000")
    )
    internal_secret: str = field(default_factory=lambda: os.environ["INTERNAL_API_SECRET"])
    redis_url: str = field(
        default_factory=lambda: os.environ.get(
            "BOT_REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/1")
        )
    )
    cache_redis_url: str = field(
        default_factory=lambda: os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )
    mode: str = field(default_factory=lambda: os.environ.get("BOT_MODE", "polling"))
    webhook_host: str = field(default_factory=lambda: os.environ.get("BOT_WEBHOOK_HOST", "0.0.0.0"))  # noqa: S104
    webhook_port: int = field(
        default_factory=lambda: int(os.environ.get("BOT_WEBHOOK_PORT", "8081"))
    )
    bots_refresh_seconds: int = 30
    throttle_seconds: float = 0.5
    sentry_dsn: str = field(default_factory=lambda: os.environ.get("SENTRY_DSN", ""))


settings = Settings()
