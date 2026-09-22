.PHONY: dev down test lint typecheck gen-client

dev:
	docker compose -f infra/compose/docker-compose.yml --profile core up --build

down:
	docker compose -f infra/compose/docker-compose.yml --profile core down

test:
	pnpm test
	uv run --package satsaathi-core pytest python/core/tests
	uv run --package satsaathi-tools pytest python/tools/tests
	uv run --package satsaathi-api pytest apps/api/tests
	uv run --package satsaathi-worker pytest apps/worker/tests

lint:
	pnpm lint
	uv run ruff check .

typecheck:
	pnpm typecheck
	uv run python -m pyright

gen-client:
	@echo "gen-client wires up in Phase 3 once apps/api's OpenAPI schema and packages/api-client exist"
