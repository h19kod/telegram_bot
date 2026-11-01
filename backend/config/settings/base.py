"""Base settings shared by every environment. All secrets come from the environment."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR.parent / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "channels",
    "core",
    "apps.accounts",
    "apps.businesses",
    "apps.staff",
    "apps.categories",
    "apps.products",
    "apps.customers",
    "apps.delivery",
    "apps.orders",
    "apps.notifications",
    "apps.subscriptions",
    "apps.analytics",
    "apps.chatbot",
    "apps.storefront",
    "apps.internal_api",
    "apps.platform_admin",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.RequestIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "sop",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        # redis-py 8 defaults socket_timeout=5s, equal to channels-redis' 5s blocking pop;
        # a larger timeout prevents idle consumers from crashing with TimeoutError.
        "CONFIG": {
            "hosts": [
                {"address": env("CHANNELS_REDIS_URL", default=REDIS_URL), "socket_timeout": 30}
            ]
        },
    }
}

AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailOrPhoneBackend"]

LANGUAGE_CODE = "ar"
LANGUAGES = [("ar", "العربية"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Baghdad"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = env("MEDIA_URL", default="/media/")
MEDIA_ROOT = BASE_DIR / "media"

USE_S3 = env.bool("USE_S3", default=False)
if USE_S3:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("S3_BUCKET"),
                "endpoint_url": env("S3_ENDPOINT_URL", default=None),
                "access_key": env("S3_ACCESS_KEY"),
                "secret_key": env("S3_SECRET_KEY"),
                "region_name": env("S3_REGION", default="us-east-1"),
                "custom_domain": env("S3_CUSTOM_DOMAIN", default=None),
                "querystring_auth": False,
                "file_overwrite": False,
                "default_acl": None,
            },
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

# --- REST framework -------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.errors.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "600/min",
        "login": "10/min",
        "checkout": "5/min",
        "store": "240/min",
        "link_code": "5/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=10)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=14)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
}
REFRESH_COOKIE_NAME = "sop_refresh"
REFRESH_COOKIE_SECURE = env.bool("REFRESH_COOKIE_SECURE", default=True)

SPECTACULAR_SETTINGS = {
    "TITLE": "Smart Ordering Platform API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-language",
    "authorization",
    "content-type",
    "idempotency-key",
    "x-csrf-token",
    "x-request-id",
]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- Celery ---------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 120
CELERY_TASK_SOFT_TIME_LIMIT = 100
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ROUTES = {
    "apps.notifications.tasks.*": {"queue": "telegram"},
    "apps.products.tasks.*": {"queue": "media"},
    "apps.chatbot.tasks.*": {"queue": "ai"},
    "apps.analytics.tasks.*": {"queue": "reports"},
}
CELERY_BEAT_SCHEDULE = {
    "worker-heartbeat": {"task": "core.tasks.worker_heartbeat", "schedule": 30.0},
    "drain-notification-outbox": {
        "task": "apps.notifications.tasks.drain_outbox",
        "schedule": 15.0,
    },
    "auto-reject-stale-orders": {
        "task": "apps.orders.tasks.auto_reject_stale_orders",
        "schedule": 60.0,
    },
    "expire-carts": {"task": "apps.orders.tasks.expire_carts", "schedule": 3600.0},
    "expire-subscriptions": {
        "task": "apps.subscriptions.tasks.expire_subscriptions",
        "schedule": 3600.0,
    },
}

# --- Platform-specific ----------------------------------------------------
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS")
INTERNAL_API_SECRET = env("INTERNAL_API_SECRET")
INTERNAL_API_CLOCK_SKEW_SECONDS = 60
TELEGRAM_API_BASE = env("TELEGRAM_API_BASE", default="https://api.telegram.org")
TELEGRAM_WEBHOOK_BASE_URL = env("TELEGRAM_WEBHOOK_BASE_URL", default="")
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = env.int("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS", default=86400)
MINI_APP_BASE_URL = env("MINI_APP_BASE_URL", default="")
SHARED_BOT_TOKEN = env("SHARED_BOT_TOKEN", default="")
CUSTOMER_TOKEN_LIFETIME = timedelta(hours=1)
CART_TTL_DAYS = 7
MAX_OPEN_ORDERS_PER_CUSTOMER = 3

# AI assistant
AI_PROVIDER = env("AI_PROVIDER", default="anthropic")
AI_MODEL = env("AI_MODEL", default="claude-opus-5-5")
AI_EFFORT = env("AI_EFFORT", default="low")  # chat workload: low effort keeps latency and cost down
AI_API_KEY = env("AI_API_KEY", default="")
AI_TIMEOUT_SECONDS = env.float("AI_TIMEOUT_SECONDS", default=45.0)
AI_MAX_OUTPUT_TOKENS = env.int("AI_MAX_OUTPUT_TOKENS", default=16000)
AI_HISTORY_MESSAGES = 12
AI_MAX_TOOL_ROUNDS = 4

# --- Logging --------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "core.logging.RequestContextFilter"},
        "scrub": {"()": "core.logging.SecretScrubFilter"},
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(business_id)s",
        },
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": env("LOG_FORMAT", default="json"),
            "filters": ["request_id", "scrub"],
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.05),
        send_default_pii=False,
    )

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@localhost")
DASHBOARD_BASE_URL = env("DASHBOARD_BASE_URL", default="http://localhost:5174")
PLATFORM_ADMIN_REQUIRE_2FA = env.bool("PLATFORM_ADMIN_REQUIRE_2FA", default=True)
