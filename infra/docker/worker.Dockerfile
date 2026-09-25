FROM python:3.12-slim-bookworm

# rasterio's bundled GDAL links against expat, which slim images leave out.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.12.17

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY python/core/pyproject.toml python/core/pyproject.toml
COPY python/tools/pyproject.toml python/tools/pyproject.toml
COPY python/models/pyproject.toml python/models/pyproject.toml
COPY python/inference/pyproject.toml python/inference/pyproject.toml
COPY python/jobs/pyproject.toml python/jobs/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

RUN uv sync --frozen --package satsaathi-worker --no-install-project

COPY python/core python/core
COPY python/tools python/tools
COPY python/models python/models
COPY python/inference python/inference
COPY python/jobs python/jobs
COPY apps/worker apps/worker

RUN uv sync --frozen --package satsaathi-worker

CMD ["uv", "run", "--package", "satsaathi-worker", "celery", "-A", "satsaathi_worker.celery_app.celery_app", "worker", "--loglevel=INFO", "-Q", "cpu,lang"]
