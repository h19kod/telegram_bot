# Development

## 1. Services (PostgreSQL + Redis)

```bash
podman run -d --name sop-postgres -e POSTGRES_USER=sop -e POSTGRES_PASSWORD=sop_dev_password \
  -e POSTGRES_DB=sop -p 127.0.0.1:5432:5432 -v sop-pgdata:/var/lib/postgresql/data \
  docker.io/library/postgres:17-alpine
podman run -d --name sop-redis -p 127.0.0.1:6379:6379 docker.io/library/redis:7-alpine
```

(`docker run …` works identically.) Next time just `podman start sop-postgres sop-redis`.

## 2. Configuration

```bash
cp .env.example .env
```

Fill at least `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEYS`, `INTERNAL_API_SECRET` (commands to
generate them are in the file), and set
`DATABASE_URL=postgres://sop:sop_dev_password@localhost:5432/sop`. Every variable is described in
[ENVIRONMENT.md](ENVIRONMENT.md).

## 3. Backend (Django)

```bash
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo --owner-password 'Choose-A-Dev-Password-1'
uv run uvicorn config.asgi:application --reload --port 8000
```

`seed_demo` (DEBUG only) creates the demo restaurant `demo_shop` with a menu, three Baghdad delivery
zones and the owner account `owner@demo.local` with the password you pass. Use uvicorn (ASGI), not
`runserver`, so WebSockets work. API docs: http://localhost:8000/api/docs/ (DEBUG only).

Celery (notifications, timers) in two more terminals:

```bash
uv run celery -A config worker -l INFO -Q telegram,default,media,ai,reports,celery
uv run celery -A config beat -l INFO
```

## 4. Telegram bot (polling mode, no public URL needed)

1. Create a test bot with [@BotFather](https://t.me/BotFather) (`/newbot`). Keep the token private.
2. Attach it to the demo shop: `uv run python manage.py seed_demo --bot-token '<token>'`
   (or connect it from the dashboard → Telegram; requires a plan with `custom_bot`).
3. Run the bot service:

```bash
cd bot
uv sync
uv run python -m sopbot.main   # BOT_MODE=polling is the default
```

Open your bot in Telegram and send `/start`. To receive staff notifications, open the dashboard →
My account → *Link your Telegram*, then send `/link CODE` to the bot.

## 5. Frontends

```bash
cd frontend
npm install
npm run dev:dashboard     # http://localhost:5174 (proxies /api and /ws to :8000)
npm run dev:miniapp       # http://localhost:5173
```

### Mini App browser dev mode

Outside Telegram the Mini App needs signed test `initData`. Generate it (DEBUG only) and put it in
`frontend/apps/miniapp/.env.development.local` (gitignored):

```bash
cd backend
echo "VITE_DEV_BUSINESS=demo_shop" > ../frontend/apps/miniapp/.env.development.local
echo "VITE_DEV_INIT_DATA=$(uv run python manage.py dev_init_data --slug demo_shop)" \
  >> ../frontend/apps/miniapp/.env.development.local
```

Signed data is valid for 24 h (`TELEGRAM_INIT_DATA_MAX_AGE_SECONDS`); regenerate when it expires.
To test inside real Telegram, expose the dev server over HTTPS (e.g. a tunnel) and set the Mini
App URL in BotFather and `MINI_APP_BASE_URL`.

## 6. Tests and checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd bot && uv run pytest && uv run ruff check src
cd frontend && npm run typecheck && npx vitest run --root packages/shared && npm run build
```

Backend tests need the PostgreSQL and Redis containers running (they never use SQLite).

## 7. AI assistant locally

Set `AI_API_KEY` (Anthropic) in `.env`, enable the assistant in the dashboard → Business settings
(needs a plan with `ai_assistant`), then chat with the bot in free text. Without a key the bot
falls back to normal search. Tests use a scripted provider (`AI_PROVIDER=scripted`) and never call
the network.
