import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production-0123456789")
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", "6HGhQxIVW-VoiF-qGdziTZSnnjUOm1LStkrEZQwxqmQ=")
os.environ.setdefault("INTERNAL_API_SECRET", "test-internal-secret")
os.environ.setdefault("DATABASE_URL", "postgres://sop:sop_dev_password@localhost:5432/sop")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from .base import *  # noqa: F403
from .base import LOGGING

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = False
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
REST_FRAMEWORK = {**REST_FRAMEWORK}  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
TELEGRAM_API_BASE = "https://telegram.test"
WHATSAPP_PROVIDER = "disabled"  # verification tests switch to "memory"
MEDIA_ROOT = "/tmp/sop-test-media"  # noqa: S108
LOGGING["handlers"]["console"]["formatter"] = "plain"
LOGGING["root"]["level"] = "WARNING"
# Tests open connections from many threads (concurrency tests); keep them unpooled.
DATABASES["default"]["OPTIONS"].pop("pool", None)  # noqa: F405
