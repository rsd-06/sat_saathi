FROM python:3.12-slim-bookworm

RUN pip install --no-cache-dir uv==0.12.17

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY python/core/pyproject.toml python/core/pyproject.toml
COPY python/tools/pyproject.toml python/tools/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

RUN uv sync --frozen --package satsaathi-worker --no-install-project

COPY python/core python/core
COPY python/tools python/tools
COPY apps/worker apps/worker

RUN uv sync --frozen --package satsaathi-worker

CMD ["uv", "run", "--package", "satsaathi-worker", "celery", "-A", "satsaathi_worker.celery_app.celery_app", "worker", "--loglevel=INFO", "-Q", "cpu,gpu,lang"]
