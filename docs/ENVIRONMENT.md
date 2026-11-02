# Environment variables

All configuration is read from the environment (`.env`, never committed; `.env.example` is the
template). **Never** put real tokens, keys or passwords in code, issues, chats or commits.

## Required

| Variable | Used by | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | api | Django signing key (sessions, customer tokens, password reset). ≥ 50 random chars |
| `DATABASE_URL` | api | `postgres://user:pass@host:5432/db` (compose builds it from `POSTGRES_*`) |
| `DB_POOL_MIN` / `DB_POOL_MAX` / `DB_POOL_TIMEOUT` | api | psycopg connection pool per worker process (defaults 2 / 15 / 20 s). Keep `workers × DB_POOL_MAX` + Celery below PostgreSQL `max_connections` |
| `FIELD_ENCRYPTION_KEYS` | api | Comma-separated Fernet keys; first encrypts, all decrypt. Rotate by prepending a new key |
| `INTERNAL_API_SECRET` | api, bot | HMAC secret for the bot → API internal channel. Same value in both |
| `REDIS_URL` | api, bot | Cache, channel layer and bot data |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `REDIS_PASSWORD` | compose | Database/Redis credentials |
| `BACKUP_KEEP_DAYS` | backup | Retention of base backups, dumps and WAL (default 14) |
| `PG_MAX_SLOT_WAL_KEEP` | postgres | Max WAL kept for a stalled backup stream before its slot is dropped (default `8GB`; the backup service then recovers with a new base backup) |

## Django / HTTP

| Variable | Default | Description |
|---|---|---|
| `DJANGO_DEBUG` | `false` | Never true in production |
| `DJANGO_ALLOWED_HOSTS` | — | Comma list; include your domains and `api` |
| `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` | — | `https://` origins of dashboard and Mini App |
| `SECURE_SSL_REDIRECT` | `true` | Disable only behind a proxy that already redirects |
| `SECURE_HSTS_SECONDS` | `31536000` | HSTS max-age |
| `REFRESH_COOKIE_SECURE` | `true` | Refresh cookie `Secure` flag |
| `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS` | `10`, `14` | Token lifetimes |
| `PLATFORM_ADMIN_REQUIRE_2FA` | `true` | Platform admins need TOTP |
| `MAX_BUSINESSES_PER_OWNER` | `3` | Self-service business cap |
| `LOG_LEVEL`, `LOG_FORMAT` | `INFO`, `json` | `plain` for local reading |
| `DASHBOARD_BASE_URL` | — | Used in password-reset and invitation links |

## Telegram

| Variable | Description |
|---|---|
| `TELEGRAM_WEBHOOK_BASE_URL` | Public HTTPS base for webhooks, e.g. `https://app.example.iq`. Empty → bots run in polling mode |
| `MINI_APP_BASE_URL` | Public HTTPS URL of the Mini App, e.g. `https://shop.example.iq` |
| `TELEGRAM_INIT_DATA_MAX_AGE_SECONDS` | Max age of Mini App initData (default 86400) |
| `BOT_MODE` | `polling` (dev) or `webhook` (prod) |
| `BACKEND_INTERNAL_URL` | Bot → API URL (`http://api:8000` in compose) |
| `BOT_REDIS_URL` | Redis DB for bot FSM/throttling |

Bot tokens are **not** environment variables: owners enter them in the dashboard; they are stored
encrypted with `FIELD_ENCRYPTION_KEYS` and never returned by any API.

## Storage

| Variable | Description |
|---|---|
| `USE_S3` | `true` to store media in S3/MinIO instead of the local `media` volume |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `S3_CUSTOM_DOMAIN` | S3 settings |

## Email

`EMAIL_BACKEND` (console by default), `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`.

## AI assistant (optional)

| Variable | Default | Description |
|---|---|---|
| `AI_PROVIDER` | `anthropic` | `anthropic` or `scripted` (tests) |
| `AI_API_KEY` | — | Anthropic API key. Empty → the assistant is unavailable and bots fall back to search |
| `AI_MODEL` | `claude-opus-5-5` | Any Claude model ID; a smaller model lowers cost and latency |
| `AI_EFFORT` | `low` | `low`/`medium`/`high` — chat rarely benefits from more |
| `AI_TIMEOUT_SECONDS` | `45` | Per request; on timeout the bot falls back to menu search |
| `AI_MAX_OUTPUT_TOKENS` | `16000` | Per response cap |

## WhatsApp phone verification (optional)

Customers confirm their phone with a 6-digit code sent over WhatsApp before ordering (when the
business keeps *Require verified phone* on). In the bot, sharing the Telegram contact also counts
as verified. With `WHATSAPP_PROVIDER=disabled` verification is off everywhere.

| Variable | Default | Description |
|---|---|---|
| `WHATSAPP_PROVIDER` | `disabled` | `cloud` (Meta WhatsApp Cloud API), `console` (log codes, DEBUG only), `memory` (tests), `disabled` |
| `WHATSAPP_TOKEN` | — | Permanent system-user access token with `whatsapp_business_messaging` |
| `WHATSAPP_PHONE_NUMBER_ID` | — | Sender phone number ID from WhatsApp Manager |
| `WHATSAPP_OTP_TEMPLATE` | `phone_verification` | Approved template of category *Authentication* with a copy-code button |
| `WHATSAPP_TEMPLATE_LANG` | `ar` | Language of the template (an `en` translation is used for English customers) |
| `WHATSAPP_API_BASE` | `https://graph.facebook.com/v22.0` | Graph API base URL (version) |

Codes expire after 10 minutes, allow 5 attempts, can be resent after 60 s, and are capped at 5 per
hour per customer and per phone number. Only an HMAC of each code is stored.

## Monitoring

`SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` (backend); `SENTRY_DSN` (bot).
PII is never sent (`send_default_pii=False`).
