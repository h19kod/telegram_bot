# 09 — Testing Strategy

## 1. Pyramid

| Level | Tooling | Scope | Share |
|-------|---------|-------|-------|
| Unit | pytest | Money, phone, Arabic normalisation, initData, state machine, entitlement resolution, pricing | ~50 % |
| Service / integration | pytest-django on real PostgreSQL (Docker), factory_boy | Services with DB, transactions, constraints, outbox | ~30 % |
| API | DRF `APIClient` | Every endpoint: auth, permissions, validation, tenant isolation, error format | ~15 % |
| E2E | Playwright (Mini App, dashboard); bot flows via aiogram test harness with mocked Bot API | Critical user journeys | ~5 % |
| Load | k6 or Locust | Checkout & catalog under NFR-4 load | Phase 8 |
| AI eval | Custom eval runner with fixed dataset | Intent accuracy, no hallucinated facts | Phase 6+ |

SQLite is **never** used for tests — PostgreSQL-specific features (constraints, `SELECT FOR UPDATE`,
arrays, tsvector, RLS) must be exercised for real.

## 2. Mandatory suites

1. **Tenant isolation matrix** — parametrised over every tenant endpoint and method: user of business A
   requesting B's object ids → `404`; list endpoints never include B's rows; create with B's FK ids → `400`.
   New endpoints fail CI if not registered in the matrix (introspection of the URL conf).
2. **Permission matrix** — each role × each protected action → expected allow/deny.
3. **Checkout correctness** — tampered prices ignored; unavailable product, missing required option,
   too many options, below minimum, outside hours, inactive zone, suspended business, blocked customer,
   plan order limit → correct error codes.
4. **Concurrency** — 10 parallel checkouts with the same idempotency key → exactly 1 order; 2 customers
   buying the last stock unit → 1 succeeds; parallel transitions with the same version → 1 applies;
   order numbers unique & gap-free under parallel load (`pytest-xdist` + threads with separate connections).
5. **State machine** — every allowed and forbidden transition; stock restored on cancel/reject.
6. **initData** — valid vector, tampered field, wrong bot token, expired `auth_date`, missing hash.
7. **Notifications** — outbox written in the same transaction; rollback → no notification; retries do
   not double-send; 429 from Telegram respected.
8. **Bot flows** — full ordering conversation, duplicate callback press, stale button after status change,
   unlinked user presses staff button → refused.
9. **Entitlements** — limits enforced, overrides precedence, monthly reset, unlimited (`null`).
10. **AI guardrails** — model proposes unknown product / wrong price / invented discount → validation rejects
    or corrects; timeout → fallback; quota exhausted → fallback.

## 3. Tooling and conventions

- `pytest`, `pytest-django`, `pytest-xdist`, `pytest-cov`, `factory_boy`, `freezegun`/`time-machine`, `respx` (httpx mocking), `hypothesis` for Money/phone/normalisation.
- Frontend: Vitest + Testing Library (components), MSW for API mocking in unit tests only; Playwright against the real backend in Compose for e2e.
- Test data via factories, never fixtures copied from production.
- Each requirement ID (e.g. `ORD-3`) appears in at least one test name/marker for traceability.

## 4. CI gates (GitHub Actions)

1. `ruff check` + `ruff format --check`, `mypy` (strict on `core` and services).
2. `pytest` with PostgreSQL & Redis service containers, coverage ≥ 85 % on `apps/*/services.py` and `core`.
3. OpenAPI schema generated and diffed; frontend type generation must be up to date.
4. Frontend: `tsc --noEmit`, ESLint, Vitest, build.
5. Security: `gitleaks`, `pip-audit`, `pnpm audit --prod`.
6. E2E (Playwright) on main branch and release tags.

## 5. Manual acceptance (each phase)

A short checklist in the phase report: what was clicked/sent in a real Telegram test bot, screenshots
of Mini App/dashboard, and results of the automated suites. "Success" is never claimed without it.
