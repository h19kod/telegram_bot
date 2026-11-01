# Troubleshooting

Start with **Platform → System health** in the dashboard and `docker compose ps` / `logs`.
Every API response has an `X-Request-ID`; search logs for it.

## The bot does not answer

1. `docker compose logs bot --tail 100`.
2. Dashboard → Telegram: webhook status. `error` shows Telegram's message (e.g. wrong URL, TLS).
3. Telegram's view: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo` (run it on the
   server; never paste the token anywhere else). `last_error_message` explains failures.
4. `TELEGRAM_WEBHOOK_BASE_URL` must be the public HTTPS URL that reaches `web`; `/tg/webhook/` is
   proxied to `bot`.
5. After changing the base URL, reconnect the token in the dashboard (re-registers the webhook).

## Owners don't get order notifications

- Celery must run: `docker compose ps worker beat`; Health page shows the worker heartbeat.
- Health → "outbox pending" growing → worker down or Telegram rate-limiting (it retries).
- Staff must link Telegram (My account → Link Telegram → `/link CODE` to the bot), and their role
  needs *Receive new order notifications*. Group chats: add the bot to the group and put the group
  chat ID in Telegram settings; use *Send test notification*.

## Mini App shows "Open this store from Telegram"

The page was opened outside Telegram or without `?b=<slug>`. Configure the bot's Mini App URL as
`https://shop.example.iq/?b=<slug>`. In development use the browser dev mode (DEVELOPMENT.md §5).

## Mini App: "Invalid Telegram init data"

- The Mini App was opened from a different bot than the one connected to that business.
- Device clock far off, or initData older than `TELEGRAM_INIT_DATA_MAX_AGE_SECONDS`.

## Dashboard realtime shows "Offline"

- `/ws/` must be proxied with Upgrade headers (included in `snippets/common.conf`).
- The API must run under ASGI (Gunicorn with Uvicorn workers, or `uvicorn` in dev) — Django's
  `runserver` does not serve WebSockets.
- Redis channel layer reachable (`readyz` → cache ok).

## 401 loops / logged out immediately

- `REFRESH_COOKIE_SECURE=true` requires HTTPS. For plain-HTTP local tests set it to `false`.
- Dashboard and API must share an origin (Nginx serves both on `APP_DOMAIN`).

## 403 on Platform pages for a superuser

Platform admins must enable 2FA (My account → Two-factor authentication).

## "plan_limit_exceeded" / "feature_not_available"

Expected: the business reached its plan's limit. Platform → Businesses → open the business →
change plan, or add an override (e.g. `max_products`).

## Migrations / readiness

`docker compose exec api python manage.py showmigrations | grep '\[ \]'` lists pending ones; run
the release job. `readyz` returns 503 until migrations are applied.

## SELinux denials (Fedora)

`sudo ausearch -m avc -ts recent`. Relabel bind mounts with `:Z`; do not disable SELinux.

## Podman specifics

- Ports < 1024 rootless: see FEDORA_SETUP.md §2B.
- `podman-compose` uses `--env-file` only for variable interpolation; `ENV_FILE=…` selects the
  file containers receive.

## Lost `FIELD_ENCRYPTION_KEYS`

Stored bot tokens and 2FA secrets cannot be decrypted. Owners must reconnect their bots and users
must re-enroll 2FA. Restore the key from your backup if at all possible.
