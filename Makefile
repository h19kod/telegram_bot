# Common tasks. With Podman: make COMPOSE=podman-compose ...
COMPOSE ?= docker compose

.PHONY: test lint build up release down logs ps backup

test:
	cd backend && uv run pytest
	cd bot && uv run pytest
	cd frontend && npm run typecheck && npx vitest run --root packages/shared

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd bot && uv run ruff check src

build:
	$(COMPOSE) build

release:
	$(COMPOSE) --profile release run --rm release

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail 100

backup:
	$(COMPOSE) exec backup sh -c 'pg_dump -Fc -f /backups/db-manual-$$(date -u +%Y%m%dT%H%M%SZ).dump'
