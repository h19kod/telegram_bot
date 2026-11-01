# Deployment (single server, Docker Compose)

Target: one Fedora server (4 vCPU / 8 GB is enough for v1 — see SRS NFR-4) with a public IP and
two DNS names, e.g. `app.example.iq` (dashboard, API, Telegram webhooks) and `shop.example.iq`
(Mini App). Commands use `docker compose`; with Podman use `podman-compose`.

## 1. Prepare the server

Follow [FEDORA_SETUP.md](FEDORA_SETUP.md) §1–3 (Docker, firewall). Point both DNS A records to
the server.

```bash
sudo mkdir -p /srv/sop && sudo chown "$USER" /srv/sop
git clone <your repository URL> /srv/sop
cd /srv/sop
```

## 2. Configure

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` (all variables: [ENVIRONMENT.md](ENVIRONMENT.md)). Production essentials:

| Variable | Value |
|---|---|
| `DJANGO_SECRET_KEY`, `INTERNAL_API_SECRET` | `python3 -c "import secrets;print(secrets.token_urlsafe(50))"` |
| `FIELD_ENCRYPTION_KEYS` | Fernet key (command in `.env.example`) — **back it up separately**; without it bot tokens cannot be decrypted |
| `POSTGRES_USER/PASSWORD/DB`, `REDIS_PASSWORD` | strong random values |
| `APP_DOMAIN`, `SHOP_DOMAIN` | your two domains |
| `DJANGO_ALLOWED_HOSTS` | `app.example.iq,shop.example.iq,api` (`api` lets the bot reach the API internally) |
| `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` | `https://app.example.iq,https://shop.example.iq` |
| `TELEGRAM_WEBHOOK_BASE_URL` | `https://app.example.iq` |
| `MINI_APP_BASE_URL` | `https://shop.example.iq` |
| `DASHBOARD_BASE_URL` | `https://app.example.iq` |
| `BOT_MODE` | `webhook` |
| `EMAIL_*`, `SENTRY_DSN`, `AI_API_KEY` | as available |

## 3. Build and first start (HTTP, to obtain certificates)

```bash
docker compose build
docker compose up -d postgres redis
docker compose --profile release run --rm release
docker compose up -d
```

Obtain the certificate (one certificate for both names). Port 80 must be free, so stop `web`
briefly and let certbot answer the challenge itself:

```bash
docker compose stop web
docker compose -f compose.yaml -f compose.prod.yaml run --rm -p 80:80 --entrypoint certbot certbot \
  certonly --standalone -d app.example.iq -d shop.example.iq \
  --email you@example.iq --agree-tos --no-eff-email
```

Renewals afterwards use the webroot served by the TLS configuration (no downtime).

## 4. Switch to TLS

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

Certbot renews automatically every 12 h check; reload Nginx after renewals with
`docker compose exec web nginx -s reload` (add it to a weekly cron/systemd timer).

## 5. Create the platform administrator

```bash
docker compose exec api python manage.py createsuperuser
```

Log in at `https://app.example.iq`, go to **My account → Two-factor authentication** and enable
TOTP — platform endpoints refuse admins without 2FA. Then use **Platform** to create businesses,
or let owners self-register.

Optional shared platform bot (businesses on plans without `custom_bot` use it via deep links):

```bash
docker compose exec api python manage.py shell -c "
from apps.businesses.models import TelegramBot
from apps.businesses.services import register_webhook
from core.crypto import encrypt
import secrets
token = input('Shared bot token: ').strip()
bot = TelegramBot.objects.create(is_shared_platform_bot=True, bot_telegram_id=int(token.split(':')[0]),
  username=input('Bot username (no @): ').strip(), token_encrypted=encrypt(token),
  webhook_secret=secrets.token_urlsafe(32))
register_webhook(bot, token); print(bot.webhook_status, bot.last_error)"
```

In BotFather set each bot's Mini App / menu button URL to `https://shop.example.iq/?b=<slug>`.

## 6. Verify (every release)

Nginx re-resolves `api`/`bot` at runtime, so recreating those containers needs no Nginx restart.


```bash
docker compose ps                                  # all services "healthy"/"running"
curl -fsS https://app.example.iq/healthz           # {"status": "ok"}
docker compose exec api curl -fsS http://127.0.0.1:8000/readyz   # database, migrations, cache ok
```

Then in the dashboard: **Platform → System health** (bot service and Celery heartbeats, outbox,
webhook status per bot), and place a test order on a staging business.

## 7. Releasing a new version

```bash
git pull
docker compose build
docker compose --profile release run --rm release   # migrations are backward compatible (expand/contract)
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

Rollback: check out the previous tag, rebuild, `up -d`. Never roll back past a migration that
dropped columns; the project follows expand → deploy → contract.

## 8. What runs where

| Service | Role |
|---|---|
| `web` | Nginx: TLS, rate limits, CSP, SPAs, proxies `/api`, `/ws`, `/tg/webhook`; blocks `/internal` |
| `api` | Django (Gunicorn + Uvicorn workers, ASGI: REST + WebSocket) |
| `worker` / `beat` | Celery: Telegram notifications (outbox), timers, expiries, heartbeat |
| `bot` | aiogram multi-bot webhook server (talks to `api` over the private network) |
| `postgres`, `redis` | data, broker, cache, FSM, channel layer (never published) |
| `backup` | daily `pg_dump` + media archive with retention → `./backups` |
| `certbot` | certificate renewal (TLS overlay) |
