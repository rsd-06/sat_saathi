# The GPU worker: one process, one resident 4-bit base, every adapter attached.
# Linux torch wheels from PyPI bundle CUDA; the host needs the NVIDIA container
# toolkit and a driver, nothing else. Weights are mounted at /models, never
# baked into the image.
FROM python:3.12-slim-bookworm

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

RUN uv sync --frozen --package satsaathi-worker --extra gpu --no-install-project

COPY python/core python/core
COPY python/tools python/tools
COPY python/models python/models
COPY python/inference python/inference
COPY python/jobs python/jobs
COPY apps/worker apps/worker
COPY infra/fixtures/golden infra/fixtures/golden

RUN uv sync --frozen --package satsaathi-worker --extra gpu

ENV MODELS_DIR=/models
# solo pool: CUDA does not survive fork, and one process holds the model.
CMD ["uv", "run", "--package", "satsaathi-worker", "celery", "-A", "satsaathi_worker.celery_app.celery_app", "worker", "--loglevel=INFO", "-Q", "gpu", "--pool=solo", "--concurrency=1", "-n", "gpu@%h"]
