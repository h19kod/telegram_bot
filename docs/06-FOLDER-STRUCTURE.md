# 06 — Repository Structure

Monorepo: one repository, one version, one CI pipeline; services deploy independently.

```
.
├── backend/                         # Django project (API, Channels, Celery)
│   ├── pyproject.toml               # uv-managed deps, ruff, mypy, pytest config
│   ├── uv.lock
│   ├── manage.py
│   ├── config/
│   │   ├── settings/{base,dev,test,prod}.py
│   │   ├── urls.py  asgi.py  wsgi.py  celery.py
│   ├── core/                        # shared kernel (no business logic)
│   │   ├── models.py                # BaseModel (UUIDv7, timestamps), TenantModel, managers
│   │   ├── tenancy.py               # business resolution, TenantViewSet, TenantPKField, RLS hook
│   │   ├── money.py                 # Money value object, currency exponents, formatting
│   │   ├── phone.py                 # Iraqi phone normalisation
│   │   ├── arabic.py                # Arabic text normalisation for search
│   │   ├── crypto.py                # Fernet field encryption
│   │   ├── errors.py                # domain exceptions → API error format
│   │   ├── events.py                # on_commit domain event bus + outbox
│   │   ├── permissions.py           # HasBusinessPermission, IsPlatformAdmin
│   │   ├── throttles.py  pagination.py  logging.py  health.py
│   ├── apps/
│   │   ├── accounts/                # each app: models, services, selectors,
│   │   ├── businesses/              #   serializers, views, urls, permissions,
│   │   ├── staff/                   #   tasks, admin, migrations, tests/
│   │   ├── categories/
│   │   ├── products/
│   │   ├── customers/
│   │   ├── orders/                  # cart, checkout, state machine, numbering
│   │   ├── delivery/
│   │   ├── notifications/           # outbox, telegram sender, message templates
│   │   ├── subscriptions/           # plans, entitlements, usage
│   │   ├── analytics/
│   │   ├── chatbot/                 # AI providers, tools, proposal validation
│   │   ├── storefront/              # Mini App API (thin, reuses services)
│   │   ├── internal_api/            # bot service API (thin, reuses services)
│   │   └── platform_admin/          # SaaS console API, support, audit
│   ├── locale/{ar,en}/LC_MESSAGES/
│   └── tests/                       # cross-app: tenant isolation matrix, e2e API flows
│       ├── factories.py  conftest.py
│
├── bot/                             # aiogram 3 service (no DB access)
│   ├── pyproject.toml  uv.lock
│   ├── src/bot/
│   │   ├── main.py                  # polling or webhook (aiohttp) entrypoint
│   │   ├── config.py
│   │   ├── registry.py              # multi-bot: bot_id → Bot instance, secret verification
│   │   ├── api_client.py            # typed client for /internal/v1 (httpx, HMAC signing, retries)
│   │   ├── middlewares/             # tenant context, i18n, throttling, error handling, logging
│   │   ├── handlers/                # start, catalog, product, cart, checkout, orders,
│   │   │                            #   support, staff_actions, ai_chat, link
│   │   ├── keyboards/               # inline keyboard builders, callback data factories
│   │   ├── states.py                # FSM states (checkout, search, support)
│   │   ├── texts/{ar,en}.ftl        # Fluent translations (Iraqi Arabic tone)
│   │   └── formatting.py            # money/date/phone rendering
│   └── tests/
│
├── frontend/                        # pnpm workspace
│   ├── package.json  pnpm-workspace.yaml  tsconfig.base.json
│   ├── apps/
│   │   ├── miniapp/                 # customer Telegram Mini App
│   │   │   ├── src/{pages,components,features,telegram,hooks,routes}/
│   │   │   └── vite.config.ts
│   │   ├── dashboard/               # business dashboard + platform console (route-split)
│   │   │   └── src/{pages,features,components,layouts,routes}/
│   └── packages/
│       ├── api/                     # generated OpenAPI types + fetch client + TanStack Query hooks
│       ├── ui/                      # shared Tailwind components (RTL-aware)
│       ├── i18n/                    # ar/en resources, number/currency/phone formatting
│       └── config/                  # eslint, tailwind preset, tsconfig presets
│
├── infra/
│   ├── docker/{backend,bot,frontend}.Dockerfile
│   ├── nginx/{nginx.conf,sites/*.conf}
│   ├── postgres/{init.sql,backup/}
│   └── scripts/{backup.sh,restore.sh,entrypoint-*.sh}
├── compose.yaml                     # base services
├── compose.dev.yaml                 # dev overrides: bind mounts, MinIO, mailpit, polling bot
├── compose.prod.yaml                # prod overrides: replicas, certbot, restart policies
├── .env.example
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
├── Makefile                         # make up / test / lint / migrate / schema / seed
├── CLAUDE.md
└── docs/
```

Rules:
- Apps import each other only through `services`/`selectors`, never another app's views/serializers.
- `storefront`, `internal_api`, `platform_admin` contain **no business logic**: they adapt HTTP to services.
- The requested apps (`accounts, businesses, products, categories, orders, customers, delivery,
  notifications, subscriptions, analytics, staff, chatbot`) all exist; three adapter apps are added
  for the three API surfaces.
