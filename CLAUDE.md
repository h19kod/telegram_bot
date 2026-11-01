# Smart Ordering Platform

Multi-tenant Telegram ordering SaaS for Iraqi restaurants/shops. Design docs live in `docs/` —
read `docs/README.md` and `docs/08-ROADMAP.md` (current phase) before starting work.

## Non-negotiable rules
- All business logic lives in `backend/apps/*/services.py`; bot, Mini App, dashboard, AI and Celery only call it.
- The bot service never accesses the database — only `/internal/v1`.
- Every tenant model has `business_id`; querysets go through `for_business()`; foreign ids from clients are validated against the same business. Foreign-tenant ids return 404.
- Never trust client prices or identities. Re-price on the server; validate Telegram initData server-side.
- Money = integer minor units (`core.money`). Phones = E.164 via `core.phone` (Iraq). Arabic text search via `core.arabic` normalisation.
- Checkout and transitions use idempotency keys + optimistic `version`.
- Side effects only via `transaction.on_commit` / the notification outbox.
- No secrets in code or git; bot tokens are encrypted and write-only.
- Tests run on PostgreSQL, never SQLite. Every new tenant endpoint must be covered by the isolation matrix.
- Do not claim a phase is done without running its tests and exit criteria.

## Stack
Python 3.13, Django 5.2 LTS, DRF, Channels, Celery, aiogram 3, PostgreSQL 17, Redis 7,
React 19 + TypeScript + Vite + Tailwind 4, uv, pnpm, Docker Compose. Dev machine: Fedora (SELinux enforcing → use `:Z` on bind mounts).
