# 11 — Architecture Decisions & Risk Register

## Architecture Decision Records

**ADR-001 — Monorepo.** Backend, bot, frontend, infra in one repository. One PR can change an API and
its clients together; the generated OpenAPI types keep them in sync.

**ADR-002 — Shared-schema multi-tenancy with `business_id` + RLS.** Schema-per-tenant (django-tenants)
makes migrations, analytics and platform-wide queries slow and complex at hundreds of tenants.
Shared schema with strict scoping, composite constraints, an isolation test matrix, and PostgreSQL RLS
as a safety net gives strong isolation with simple operations.

**ADR-003 — The bot service never touches the database.** It calls an internal API. All rules live in
the Django service layer, so the bot, Mini App, dashboard and AI cannot disagree on prices or permissions.
Cost: one internal HTTP hop (~ms on the Docker network) — acceptable.

**ADR-004 — Django 5.2 LTS on Python 3.13.** LTS supported until April 2028; 3.13 is well supported by
the whole dependency set. Upgrade to the next LTS in 2027.

**ADR-005 — TypeScript instead of JavaScript for frontends.** The brief mentioned both; TypeScript +
generated API types prevents a whole class of integration bugs in a large API surface.

**ADR-006 — Money as integer minor units.** Avoids float/rounding errors; IQD has no fractional
amounts in practice (exponent 0), USD exponent 2.

**ADR-007 — Optimistic concurrency + idempotency keys** for checkout and status transitions, instead of
relying on UI disabling. Telegram may deliver callbacks twice and users double-tap.

**ADR-008 — Transactional outbox for notifications.** Domain change and notification intent commit
atomically; Celery drains the outbox. No lost or ghost notifications.

**ADR-009 — Per-business bots + shared platform bot.** Own bot = branding (higher plans); shared bot
with deep links = zero-setup onboarding (Free/Basic). Both run in one multi-bot webhook service.

**ADR-010 — Variations and add-ons as option groups.** One flexible model (single/multiple selection,
min/max, price delta) covers sizes, flavours, extras, removals. Stock is tracked per product in v1;
per-variant stock (SKU variants) is a later extension if retail customers need it.

**ADR-011 — Entitlements as data.** Plans, features and limits live in tables with per-business
overrides; code only asks `entitlements.check(...)`. New plans need no deploy.

**ADR-012 — AI proposes, backend disposes.** The LLM gets read-only tools and outputs a structured
proposal; backend validation and the normal checkout service decide everything. Provider is pluggable;
Claude is the default.

**ADR-013 — Official `telegram-web-app.js` with a typed wrapper**, rather than a third-party SDK, to
follow Telegram's API directly and avoid dependency churn.

**ADR-014 — Django Channels for realtime** dashboard updates (WebSocket via Redis channel layer), served
with Gunicorn + Uvicorn workers (ASGI), matching the requested Gunicorn deployment.

**ADR-015 — Customer phones are verified before ordering (2026-11-02).** Fake numbers waste
delivery runs, so checkout requires a *verified* phone when the business keeps
`require_verified_phone` on (default). Proof is a 6-digit WhatsApp code sent with the Meta Cloud
API authentication template (Iraqi customers use WhatsApp far more than SMS, and Meta's
authentication messages are cheaper than SMS OTP), or — in the bot — the user's own Telegram
contact, which Telegram itself vouches for. Only an HMAC of each code is stored; codes expire in
10 min, allow 5 attempts, and are rate-limited per customer and per number across businesses
(anti SMS-pumping). One platform sender number serves all businesses. With no sender configured
(`WHATSAPP_PROVIDER=disabled`) verification is off rather than blocking every order.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|-----------|
| R1 | Cross-tenant data leak through a missed filter | Med | Critical | Tenant base classes, FK validation, isolation matrix in CI, RLS |
| R2 | Bot token leakage (logs, chats, repo) | Med | High | Encryption at rest, write-only API, log scrubbing, gitleaks, owner guidance |
| R3 | Telegram rate limits during peak (many staff messages) | Med | Med | Per-bot token bucket, edit-in-place instead of new messages, notification groups |
| R4 | Duplicate/ghost orders from retries & double taps | High | High | Idempotency keys, version checks, show success only after backend 201 |
| R5 | AI hallucinating items/prices | Med | High | Read-only tools, backend validation, prices from DB, eval set, fallback |
| R6 | AI cost overrun | Med | Med | Per-plan quotas, token limits, small model for intent, caching of catalog context |
| R7 | Iraqi Arabic variation hurts search/AI | High | Med | Arabic normalisation, trigram search, synonyms per business, eval dataset from real phrasing |
| R8 | Scope creep (very large brief) | High | High | Strict phases with exit criteria; backlog for extras |
| R9 | Local payment integration unavailable | High | Low (v1 cash) | Payment abstraction, manual subscription payments |
| R10 | Single-host outage | Low | High | Backups with PITR, documented restore drill, scaling path |
| R11 | Telegram Mini App platform changes | Low | Med | Thin wrapper over official script, feature detection |
| R12 | Unclear addresses → failed deliveries | High | Med | Landmark field, location sharing, zone areas, phone validation |
| R13 | Owner configures webhook/bot wrongly | Med | Med | Token validation via `getMe`, automatic `setWebhook`, status page with errors, test-notification button |

## Open questions (business facts only the owner can answer — not blocking Phase 2)

- Platform brand name and domain(s).
- Subscription prices in IQD per plan and which features each plan includes (defaults will be seeded and editable).
- Whether delivery staff are always the business's own staff, or third-party couriers later.
