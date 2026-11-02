# 08 — Development Roadmap

Strategy (from the product brief): **first a real order end-to-end** — a bot that takes an order,
saves it, and notifies the owner — then Mini App and dashboard, AI last. Subscriptions are modelled
early (so limits have a home) but the SaaS console comes later.

Each phase ends only when its exit criteria pass. "Done" means tested, linted, documented.

| Phase | Scope | Exit criteria |
|-------|-------|---------------|
| **1. Architecture & docs** ✅ | docs/01–11 | Docs reviewed by owner |
| **0. Foundation** (start of Phase 2) | Repo, git, Docker Compose (Postgres, Redis, MinIO, Mailpit), Django skeleton with settings split, `core` kernel (BaseModel, TenantModel, Money, phone, Arabic normalisation, errors, logging, health), CI (ruff, mypy, pytest), pre-commit, Makefile | `make up` starts all services; `/readyz` green; CI green |
| **2. Backend core** | accounts, businesses, branches, hours, staff/roles/permissions, categories, products/options/images, customers, delivery zones, cart, checkout & order service, state machine, outbox, subscriptions/entitlements (data + enforcement), storefront & internal APIs, OpenAPI | All ORD/CAT/CRT/BUS/STF tests pass; tenant isolation matrix 100 %; concurrency tests for checkout & transitions; coverage ≥ 85 % on services |
| **3. Telegram bot** | aiogram multi-bot service, polling (dev) + webhook (prod), full customer flow, staff notifications with action buttons, message syncing, customer status notifications, support relay, `/link`, i18n ar/en, throttling | Real order placed from Telegram on a test bot reaches the owner and moves through every status; duplicate-callback and stale-button tests pass |
| **4. Mini App** | React+TS app: all 11 pages, Telegram integration (theme, MainButton, BackButton, haptics), initData session, shared cart with bot, RTL/LTR, dark/light, browser dev mode with signed test initData | Playwright e2e: browse → cart → checkout → track; Lighthouse mobile ≥ 90; no dead buttons |
| **5. Dashboard** | Overview, orders (realtime WS + sound), products/categories/images/options, customers, staff & roles, delivery, discounts (coupons), reports & export, settings, telegram settings, subscription page | Playwright e2e per section; permission-aware UI (hidden ≠ secured: API tests already enforce); a11y checks |
| **6. AI assistant** | Provider interface + Claude provider, tools, proposal validation, confirmation flow, handover, quotas, logging, fallback; Arabic/Iraqi evaluation set | Eval set (≥ 150 messages ar-IQ/MSA/en) ≥ 90 % correct intent; 0 invented products/prices; timeout → fallback verified |
| **7. SaaS management** | Platform console: businesses, suspend/activate, plans/features/entitlements editor, subscriptions & manual payments, overrides, platform stats, support tickets, health page | Plan limits enforced end-to-end; suspension blocks ordering in bot & Mini App |
| **8. QA & security** | Full audit against 07 §13, load test (k6/Locust), RLS enabled, penetration-style tests, fix all findings | Final report: passed/failed tests, remaining risks |
| **9. Deployment** | Production Dockerfiles, compose.prod, Nginx + Let's Encrypt, backups (WAL + daily), Sentry, monitoring, docs FEDORA_SETUP, DEVELOPMENT, DEPLOYMENT, ENVIRONMENT, BACKUP_RESTORE, TROUBLESHOOTING | Fresh server deploy from docs; all health checks green; restore drill succeeds |

## Future (post-v1 backlog)

Done after v1 (2026-11-02): WhatsApp phone verification · ratings & reviews · QR code per
business/table · dine-in/table ordering · loyalty points · multi-branch (customer branch choice,
branch management, per-branch staff) · AI assistant dashboard page (status, knowledge base, staff
take-over and replies, private playground) · 80 mm receipt printing (thermal
printers / PDF) · Excel export (in v1).

Open: silent auto-printing (ESC/POS print agent) · voice alert for new orders
(dashboard already has sound; Telegram voice optional) · local payment
gateways (ZainCash, FastPay, Qi Card) when APIs/merchant accounts are available ·
WhatsApp ordering channel.

## Prerequisites on the Fedora machine (before Phase 2)

- Docker Engine + Compose plugin (not installed as of 2026-11-01) — exact commands in FEDORA_SETUP.md (Phase 9 doc; a short version will be added in Phase 0).
- `uv` (Python), Node 22 LTS (installed) + `pnpm` via corepack.
- A **test** Telegram bot from BotFather; its token goes only into `.env` (never into chats or code).
