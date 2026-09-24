.PHONY: dev down test lint typecheck gen-client gpu-worker cpu-worker models-doctor models-load-test

dev:
	docker compose -f infra/compose/docker-compose.yml --profile core up --build

down:
	docker compose -f infra/compose/docker-compose.yml --profile core down

# The model worker, natively (e.g. on the Windows dev box with the GPU).
# solo pool: CUDA does not survive fork. Needs `uv sync --all-packages --extra gpu`.
gpu-worker:
	uv run --package satsaathi-worker celery -A satsaathi_worker.celery_app.celery_app worker --loglevel=INFO -Q gpu --pool=solo --concurrency=1 -n gpu@%h

cpu-worker:
	uv run --package satsaathi-worker celery -A satsaathi_worker.celery_app.celery_app worker --loglevel=INFO -Q cpu,lang -n cpu@%h

models-doctor:
	uv run --package satsaathi-inference satsaathi-models doctor

models-load-test:
	uv run --package satsaathi-inference satsaathi-models load-test --adapters all --n 5

test:
	pnpm test
	uv run --package satsaathi-core pytest python/core/tests
	uv run --package satsaathi-models pytest python/models/tests
	uv run --package satsaathi-inference pytest python/inference/tests -m "not gpu"
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
