# 12 — QA & Security Report

Date: 2026-11-01 · Scope: backend, bot service, Mini App, dashboard, deployment config.

## 1. Automated test results

| Suite | Result | Notes |
|---|---|---|
| Backend (pytest, real PostgreSQL 17 + Redis) | **151 passed, 0 failed** (2026-11-02) | 83 % line coverage overall; checkout 94 %, transitions 94 %, entitlements 97 %, AI 89 % |
| Bot (pytest + real dispatcher, mocked Telegram/backend) | **5 passed** | Full ordering conversation, duplicate/stale staff buttons, reject reasons, throttling |
| End-to-end (Playwright, real backend + both apps) | **3 passed** | Mini App order → dashboard accept → customer sees status (`make e2e`) |
| Frontend shared (Vitest) | **13 passed** | Money formatting, Iraqi phone hints, Arabic-Indic digits |
| TypeScript (`tsc --noEmit`, strict) | Mini App ✓, Dashboard ✓ | Production builds succeed (110 KB / 125 KB gzipped JS) |
| Ruff lint/format | ✓ backend, ✓ bot | |
| `manage.py check --deploy` (prod settings) | ✓ | Only `security.W021` (HSTS preload) — deliberately deferred until the domain is stable |
| `pip-audit` (runtime deps) | No known vulnerabilities | |
| `npm audit --omit=dev` | 0 vulnerabilities | |

### Workflows covered (requirement → tests)

| Workflow | Where |
|---|---|
| Business registration / onboarding, cap per owner | `test_api_dashboard::test_onboarding_creates_business`, `test_security::test_business_creation_is_capped` |
| Authentication (JWT, rotating refresh cookie + CSRF, reuse detection, phone login, 2FA) | `tests/test_api_auth.py` |
| Tenant isolation (every route, introspected; FK injection; `business` injection) | `tests/test_tenant_isolation.py` |
| OpenAPI contract (schema clean, real responses match it, committed schema current) | `tests/test_openapi.py` |
| Row-level security (policy coverage, unscoped reads/writes blocked, role reset, view without `for_business()` still 404) | `tests/test_rls.py` |
| Product create/update, price permission, images (WebP re-encode, fake image rejected) | `test_api_dashboard.py` |
| Cart management (merge, required/single options, foreign options) | `apps/orders/tests/test_checkout.py` |
| Order creation (re-pricing, snapshots, fees, minimums, hours across midnight, blocked/suspended) | `test_checkout.py` |
| Duplicate order prevention (sequential + 8 parallel identical requests) | `test_checkout::test_idempotent_checkout`, `tests/test_concurrency.py` |
| Stock under contention, gap-free order numbers under load | `tests/test_concurrency.py` |
| Telegram notifications (outbox, 429 retry, give-up, no double send, HTML escaping) | `tests/test_services_extra.py`, `test_api_internal.py` |
| Order status updates (state machine, permissions, idempotent/stale buttons, auto-reject) | `apps/orders/tests/test_transitions.py`, `test_api_internal.py` |
| Customer tracking & cancel window; customers can't see others' orders | `test_api_storefront.py`, `test_transitions.py` |
| Staff permissions (role matrix, delivery staff scope, owner protection) | `test_transitions.py`, `test_api_dashboard.py` |
| Subscription restrictions (limits, overrides, metered quota + rollback refund, expiry/grace) | `apps/subscriptions/tests/test_entitlements.py`, `test_api_platform.py` |
| AI assistant validation (invented products, wrong prices, cross-tenant ids, quota, refusal, timeouts, round limit, PII) | `apps/chatbot/tests/test_assistant.py` |

### Manual end-to-end checks performed

- Live cross-service: bot client → Django (HMAC with Arabic query strings) → session, search,
  cart, order #1001, localized error.
- Mini App in a browser (dev mode): browse → product with required size + extra (price updated to
  10,000) → cart → checkout validation errors → Arabic-Indic phone → zone fee from server (12,000)
  → order placed → tracking timeline. Verified in the database: phone normalised to
  `+9647701234567`, snapshots and outbox entry.
- Dashboard: login, overview, orders list; orders placed via the bot appeared live over WebSocket
  (pending badge updated); accepted an order — history shows the actor and source.
- Full container stack (Podman, production images, HTTP mode): all 8 services healthy; Nginx
  routing, CSP per app, `/internal` blocked (404), SPA fallbacks, admin static via WhiteNoise;
  bot → API signed internal call; register → create business → cookie refresh (200; 401 without
  CSRF header); nightly backup produced; restore drill rolled data back correctly; API container
  moved to a new IP and Nginx kept routing without restart.

Issues found and fixed during deployment verification: host `.venv` leaking into images
(`.dockerignore`), OCI images dropping `HEALTHCHECK` (declared in compose), SELinux bind-mount
labels (`:Z`), duplicate Nginx proxy directives, BusyBox `wget` health check, stale upstream IPs
after container recreation (runtime DNS re-resolution), `Secure` cookie flag now configurable.

## 2. Security audit

| Area | Status | Evidence / control |
|---|---|---|
| Authentication | ✓ | Argon2, ≥10-char validators, generic errors, login throttling, TOTP (replay-protected), refresh rotation + blacklist, password change revokes sessions |
| Authorization | ✓ | Permission catalog enforced in views **and** services; owner-role protections; delivery scope |
| IDOR / tenant leakage | ✓ | 404 for foreign ids on every tenant route (introspected test), tenant-scoped FK fields, server-injected `business` |
| SQL injection | ✓ | ORM only; no raw SQL |
| XSS | ✓ | React escaping, no `dangerouslySetInnerHTML`; Telegram HTML fully escaped (test); CSP per app in Nginx |
| CSRF | ✓ | API uses bearer tokens; cookie-auth refresh needs double-submit header + SameSite=Strict |
| Rate limiting | ✓ | Nginx zones (api/auth/webhooks), DRF throttles (login, store, checkout), bot throttle (Redis) |
| Secret exposure | ✓ | No secrets in git (`.env*` ignored, CI gitleaks); bot tokens Fernet-encrypted, write-only, scrubbed from logs |
| Telegram initData | ✓ | Official HMAC algorithm, max age, bound to the business's bot; tampered/expired/wrong-bot tests |
| Webhook spoofing | ✓ | Per-bot secret token (constant-time compare), opaque bot id in URL |
| Internal API | ✓ | HMAC + timestamp + nonce replay cache; not routed by Nginx; **new:** refuses proxied requests |
| File uploads | ✓ | Pillow decode/verify, size and pixel limits, EXIF stripped, WebP re-encode, random names |
| Export injection | ✓ | CSV/XLSX formula neutralisation (test) |
| AI prompt injection | ✓ | Read-only tools, backend validation, server-rendered totals, explicit system rules |
| Dependencies | ✓ | pip-audit / npm audit clean; lockfiles committed |

Fixes made during the audit: proxied-request guard for `/internal/`, per-owner business creation
cap, redis-py 8 socket-timeout incompatibility in the WebSocket layer (found by live testing),
quote endpoint no longer requires contact data.

## 3. Remaining risks and open items

| # | Item | Impact | Plan |
|---|---|---|---|
| 1 | RLS enabled on all 36 tenant tables (07-SECURITY §6); `businesses` table and Celery tasks rely on application isolation only | Low | Bind per-business Celery tasks to the tenant role when touched next |
| 2 | Not tested against real Telegram servers (no bot token available in this environment) | Medium | First staging step: connect a BotFather test bot and run the manual checklist (DEVELOPMENT.md §4) |
| 3 | AI assistant not evaluated with real model output on an Iraqi-Arabic dataset (needs API key) | Medium | Build the ≥150-message eval set before enabling for customers |
| 4 | Load test only on a dev machine, not staging hardware | Low | Re-run `loadtest_storefront` on staging before launch (see §4) |
| 5 | Multi-branch UI, Lighthouse audit (coupons and the Playwright E2E order flow are done) | Feature gaps | Backlog (08-ROADMAP) |
| 6 | OpenAPI complete (0 errors / 0 warnings, contract-tested, TS types generated); Mini App and dashboard use the generated types | Low | —; vitest upgraded to 4.1.12 (tinypool/@vitest/mocker advisories gone). Accepted: `minimatch` ReDoS (GHSA-g3hv-75wg-m249) inside openapi-typescript → @redocly, build-time only on our own schema file; fixed only in minimatch 11, which @redocly 1.x cannot use |
| 7 | PITR in place (§5); off-site RPO depends on the host rclone schedule | Low | Use the 5-minute off-site sync from BACKUP_RESTORE.md; add backup-age alerting |
| 8 | HSTS preload not enabled | Low | Enable after the domain is stable |

## 4. Load test (2026-11-02)

`manage.py loadtest_storefront` (DEBUG only) simulates Mini App customers end to end: signed
initData session → shop info → product list → product detail → add to cart → quote → checkout
(with idempotency key). Server: gunicorn + 3 UvicornWorkers (production command), psycopg pool
(max 15 per worker), PostgreSQL 17 + Redis in containers, **all on one 4-core dev laptop together
with the load generator**, DEBUG on.

| Run | Requests | Throughput | Orders/s | Errors | p95 checkout |
|---|---|---|---|---|---|
| 30 customers, concurrency 1 | 210 | 23 req/s | — | 0 | 127 ms (p50 94 ms; reads p50 19–25 ms) |
| 200 customers, concurrency 20 | 1400 | 43 req/s | 6.1 | 0 | 1.95 s |
| 150 customers, concurrency 40 | 1050 | 37 req/s | 5.3 | 0 | 4.5 s |

- NFR-4 (50k orders/day ≈ 0.6 orders/s average, ~6/s at a 10× peak) is met on this machine; latency
  under load is CPU queueing (throughput flat from concurrency 20 → 40), not locking or errors.
- At concurrency 40 PostgreSQL held 42 connections — bounded by the pool (3 × 15), no pool timeouts.
  Before the pool, ASGI's per-thread persistent connections (`CONN_MAX_AGE=60`) could grow without
  bound and exhaust `max_connections`.
- No duplicate orders, no 5xx, no stock/number anomalies.

## 5. Point-in-time recovery drill (2026-11-02)

Backup service: `pg_receivewal` through a WAL-reserving replication slot (`--synchronous`) +
daily `pg_basebackup`; restore with `infra/scripts/restore-pitr.sh`. Drill on an isolated
Podman stack (`-p sopdrill`, production images and compose file):

| Scenario | Result |
|---|---|
| Create data → note time T → `DROP TABLE` + new table 2 s later → restore to T | ✓ dropped table back with its row, later table absent; new timeline; whole restore 28 s |
| Restore to latest (no target) from a base backup taken on the new timeline | ✓ commit made 2 s before the restore present (local RPO ≈ 0) |
| Slot health after restore and after fast-checkpoint base backups | ✓ `reserved`, never invalidated |
| Slot invalidated on purpose (pre-fix state) | ✓ detected within a minute, archive set aside as `wal-gap-*`, slot recreated, new base backup taken |

Found and fixed during the drill: `pg_receivewal --create-slot` does not reserve WAL, so the
checkpoint of the following base backup could recycle the stream's start segment and invalidate
the slot (silent loss of WAL protection). The slot is now created with
`pg_create_physical_replication_slot(name, true)` and its health is checked every minute.
