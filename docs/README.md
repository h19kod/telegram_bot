# Smart Ordering Platform — Documentation

A multi-tenant SaaS that lets restaurants and shops in Iraq take orders through Telegram
(Bot + Mini App), manage them from a web dashboard, and optionally let an AI assistant
take orders in Iraqi Arabic — so the owner no longer answers every customer by hand.

> Status: **Phase 1 — Architecture & Planning.** No application code yet.
> Each phase must pass its exit criteria (see [08-ROADMAP.md](08-ROADMAP.md)) before the next begins.

## Documents

| # | Document | Contents |
|---|----------|----------|
| 01 | [SRS](01-SRS.md) | Actors, functional & non-functional requirements, Iraq-specific rules |
| 02 | [Architecture](02-ARCHITECTURE.md) | Services, data flows, multi-tenancy, multi-bot design, events |
| 03 | [ERD](03-ERD.md) | Entity-relationship diagrams (Mermaid) |
| 04 | [Data Models](04-DATA-MODELS.md) | Every table: fields, types, constraints, indexes |
| 05 | [API](05-API.md) | REST endpoints, auth per surface, error format, conventions |
| 06 | [Folder Structure](06-FOLDER-STRUCTURE.md) | Repository layout for backend, bot, frontend, infra |
| 07 | [Security](07-SECURITY.md) | Threat model, tenant isolation, initData, secrets, OWASP checklist |
| 08 | [Roadmap](08-ROADMAP.md) | Phases, deliverables, exit criteria |
| 09 | [Testing](09-TESTING.md) | Test pyramid, tooling, mandatory test suites, CI gates |
| 10 | [Deployment](10-DEPLOYMENT.md) | Production topology, Docker Compose, Nginx, backups, monitoring |
| 11 | [Decisions & Risks](11-DECISIONS-AND-RISKS.md) | Architecture Decision Records and risk register |

## Final stack (decided — see ADRs in doc 11)

| Layer | Choice |
|-------|--------|
| Backend | Python 3.13, Django 5.2 LTS, Django REST Framework, drf-spectacular (OpenAPI 3) |
| Realtime | Django Channels (WebSocket) over Redis channel layer, served by Gunicorn + Uvicorn workers |
| Bot | aiogram 3, separate service, multi-bot webhook mode (long polling in development) |
| DB | PostgreSQL 17 |
| Async jobs | Celery + Celery Beat, Redis broker |
| Cache / FSM / rate limit | Redis 7 |
| Frontend | **React 19 + TypeScript** (strict), Vite, Tailwind CSS 4, TanStack Query, React Router, react-hook-form + zod, i18next |
| API client | Generated from the OpenAPI schema (`openapi-typescript`) → frontend and backend can never drift |
| Telegram Mini App | Official `telegram-web-app.js` behind a small typed wrapper |
| Storage | S3-compatible (MinIO in dev, any S3 in prod) via django-storages |
| AI | Provider-agnostic interface; Claude as default provider; non-AI fallback always available |
| Infra | Docker + Docker Compose, Nginx, Let's Encrypt, Sentry, structured JSON logs |
| Quality | Pytest, pytest-django, factory_boy, Vitest, Playwright, Ruff, mypy (django-stubs), ESLint, pre-commit |
| Python deps | `uv` (lockfile, fast, reproducible) |

TypeScript was chosen over plain JavaScript (the plan mentioned both): the frontend consumes a large
API, and generated types turn every backend contract change into a compile error instead of a runtime bug.
