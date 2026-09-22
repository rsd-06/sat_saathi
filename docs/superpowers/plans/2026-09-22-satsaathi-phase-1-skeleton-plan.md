# SatSaathi Phase 1 — Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the full SatSaathi monorepo skeleton — pnpm+Turborepo workspace, uv Python workspace, four booting services (web, api, worker, tiler) behind Docker Compose, a real `/api/v1/health` endpoint, and green CI — with zero ML/model/orchestration code anywhere.

**Architecture:** pnpm workspace (`apps/web`, `packages/*`) + uv workspace (`python/core`, `python/tools`, `apps/api`, `apps/worker`) in one repo, wired together by Docker Compose's `core` profile. `apps/api` does real dependency-connectivity checks (Postgres, Redis, local storage, TiTiler) behind `/api/v1/health`; `apps/worker` boots a Celery app with three declared queues and no tasks yet; `apps/web` is a bare Next.js placeholder page; `apps/tiler` runs the official TiTiler image unmodified.

**Tech Stack:** Next.js 16.3.5, FastAPI 0.141.1, Celery 5.6.3, SQLAlchemy/GeoAlchemy2 (deferred to Phase 2), Postgres+PostGIS 16-3.5, Redis 8.10, TiTiler 2.4.0, pnpm 12.5.1 + Turborepo, uv 0.12.17, ruff, pyright, ESLint (flat config, `eslint-config-next`) + Prettier, pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-09-22-satsaathi-architecture-design.md`

## Global Constraints

- No ML model, training, or real orchestration/LLM logic anywhere in this phase — Phase 1 only proves the skeleton boots.
- Step-key enum, i18n message-key contract, and API error shape (`{"error": {"key": ..., "params": ...}}`) are NOT built in Phase 1 — they start in Phase 2/3. Don't invent them early.
- Python pinned to **3.12** via uv (`.python-version`), not the system Python.
- `redis` (redis-py) pinned to **exactly `6.4.0`** — Celery 5.6.3's `kombu[redis]==5.6.2` requires `redis<6.5,>=4.5.2,!=4.5.5,!=5.0.2`; current redis-py `8.1.0` breaks that. Never bump this without re-checking Kombu's ceiling.
- `lenis` npm package is named **`lenis`**, not `@studio-freight/lenis`. `motion` npm package is named **`motion`**, imported from `motion/react`, not `framer-motion`. (Not used until Phase 3/4, but don't let anyone typo the old names in.)
- Docker base images are pinned by tag, never `latest`: `python:3.12-slim-bookworm`, `node:24-slim`, `postgis/postgis:16-3.5`, `redis:8.10-alpine`, `ghcr.io/developmentseed/titiler:2.4.0`.
- ESLint (flat config + `eslint-config-next`) is the one JS lint tool — not Biome — because `eslint-plugin-react-hooks` and `eslint-config-next`'s Core Web Vitals rules have no Biome equivalent.
- pyright is the one Python type checker for CI — not mypy.
- `pnpm-lock.yaml` and `uv.lock` are committed. No dependency is installed without landing in a lockfile.
- Definition of done for this phase: `docker compose -f infra/compose/docker-compose.yml --profile core up --build` brings up postgres, redis, tiler, api, web; `curl http://localhost:8000/api/v1/health` returns HTTP 200 with `"status": "ok"` once all four dependency checks pass; CI is green.

---

### Task 1: Root monorepo scaffolding

**Files:**
- Create: `pnpm-workspace.yaml`
- Create: `package.json`
- Create: `turbo.json`
- Create: `pyproject.toml` (uv workspace root)
- Create: `.python-version`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `.env.offline.example`

**Interfaces:**
- Produces: pnpm workspace globs `apps/*`, `packages/*` (Task 6 and later `packages/*` work depend on this); uv workspace members `python/core`, `python/tools`, `apps/api`, `apps/worker` (Tasks 2, 3, 4, 5 depend on this existing before `uv sync` can resolve them).

- [ ] **Step 1: Create `pnpm-workspace.yaml`**

```yaml
packages:
  - "apps/*"
  - "packages/*"
```

- [ ] **Step 2: Create root `package.json`**

```json
{
  "name": "satsaathi",
  "private": true,
  "packageManager": "pnpm@12.5.1",
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "lint": "turbo run lint",
    "typecheck": "turbo run typecheck",
    "test": "turbo run test"
  },
  "devDependencies": {
    "turbo": "^2.3.0"
  }
}
```

- [ ] **Step 3: Create `turbo.json`**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": { "outputs": [".next/**", "!.next/cache/**"] },
    "dev": { "cache": false, "persistent": true },
    "lint": {},
    "typecheck": {},
    "test": {}
  }
}
```

- [ ] **Step 4: Create root `pyproject.toml` (virtual uv workspace root — no `[build-system]`, so it is never itself installed)**

```toml
[project]
name = "satsaathi-workspace"
version = "0.1.0"
requires-python = ">=3.12,<3.13"

[tool.uv.workspace]
members = ["python/core", "python/tools", "apps/api", "apps/worker"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pyright]
include = ["python/core/src", "python/tools/src", "apps/api/src", "apps/worker/src"]
pythonVersion = "3.12"
typeCheckingMode = "basic"
```

- [ ] **Step 5: Create `.python-version`**

```
3.12
```

- [ ] **Step 6: Create `.gitignore`**

```
node_modules/
.next/
.turbo/
dist/
build/
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
.data/
.env
```

- [ ] **Step 7: Create `.env.example`**

```
SATSAATHI_MODE=online
POSTGRES_USER=satsaathi
POSTGRES_PASSWORD=satsaathi_dev_password
POSTGRES_DB=satsaathi
DATABASE_URL=postgresql+asyncpg://satsaathi:satsaathi_dev_password@postgres:5432/satsaathi
REDIS_URL=redis://redis:6379/0
STORAGE_DIR=/data/storage
TILER_URL=http://tiler:8000
```

- [ ] **Step 8: Create `.env.offline.example`**

```
SATSAATHI_MODE=offline
POSTGRES_USER=satsaathi
POSTGRES_PASSWORD=satsaathi_dev_password
POSTGRES_DB=satsaathi
DATABASE_URL=postgresql+asyncpg://satsaathi:satsaathi_dev_password@postgres:5432/satsaathi
REDIS_URL=redis://redis:6379/0
STORAGE_DIR=/data/storage
TILER_URL=http://tiler:8000
```

- [ ] **Step 9: Verify toolchain sees the files**

Run: `pnpm -v && uv --version && cat .python-version`
Expected: prints `12.5.1`, the uv version string, and `3.12` — no errors.

- [ ] **Step 10: Commit**

```bash
git add pnpm-workspace.yaml package.json turbo.json pyproject.toml .python-version .gitignore .env.example .env.offline.example
git commit -m "chore: scaffold root monorepo workspace config"
```

---

### Task 2: `python/core` package with `Settings`

**Files:**
- Create: `python/core/pyproject.toml`
- Create: `python/core/src/satsaathi_core/__init__.py`
- Create: `python/core/src/satsaathi_core/settings.py`
- Test: `python/core/tests/test_settings.py`

**Interfaces:**
- Produces: `satsaathi_core.settings.Settings` with fields `mode: str`, `database_url: str`, `redis_url: str`, `storage_dir: Path`, `tiler_url: str`, and property `database_url_asyncpg_dsn -> str`; and `satsaathi_core.settings.get_settings() -> Settings` (lru-cached). Tasks 4 and 5 both import `get_settings` from here.

- [ ] **Step 1: Create `python/core/pyproject.toml`**

```toml
[project]
name = "satsaathi-core"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "pydantic==2.13.5",
    "pydantic-settings>=2.6,<3",
]

[dependency-groups]
dev = ["pytest>=8,<9"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/satsaathi_core"]
```

- [ ] **Step 2: Create empty package init**

`python/core/src/satsaathi_core/__init__.py`:

```python
```

- [ ] **Step 3: Write the failing test**

`python/core/tests/test_settings.py`:

```python
from satsaathi_core.settings import Settings, get_settings


def test_defaults_when_no_env(monkeypatch):
    for key in ("SATSAATHI_MODE", "DATABASE_URL", "REDIS_URL", "STORAGE_DIR", "TILER_URL"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings()

    assert settings.mode == "online"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.tiler_url == "http://localhost:8001"


def test_reads_from_env(monkeypatch):
    monkeypatch.setenv("SATSAATHI_MODE", "offline")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")

    settings = Settings()

    assert settings.mode == "offline"
    assert settings.database_url_asyncpg_dsn == "postgresql://u:p@db:5432/x"


def test_get_settings_is_cached(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SATSAATHI_MODE", "online")

    first = get_settings()
    second = get_settings()

    assert first is second
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run --package satsaathi-core pytest python/core/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'satsaathi_core.settings'`

- [ ] **Step 5: Write the implementation**

`python/core/src/satsaathi_core/settings.py`:

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    mode: str = Field(default="online", validation_alias="SATSAATHI_MODE")
    database_url: str = "postgresql+asyncpg://satsaathi:satsaathi@localhost:5432/satsaathi"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: Path = Path("./.data/storage")
    tiler_url: str = "http://localhost:8001"

    @property
    def database_url_asyncpg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv sync --package satsaathi-core && uv run --package satsaathi-core pytest python/core/tests -v`
Expected: PASS — 3 passed

- [ ] **Step 7: Commit**

```bash
git add python/core uv.lock
git commit -m "feat(core): add Settings with env-driven config"
```

---

### Task 3: `python/tools` placeholder package

**Files:**
- Create: `python/tools/pyproject.toml`
- Create: `python/tools/src/satsaathi_tools/__init__.py`
- Test: `python/tools/tests/test_placeholder.py`

**Interfaces:**
- Produces: an importable `satsaathi_tools` package with `__version__ = "0.1.0"`. No `Tool` protocol yet — that is explicitly Phase 2 scope (see spec §2). This task only proves the uv workspace member wiring works end to end.

- [ ] **Step 1: Create `python/tools/pyproject.toml`**

```toml
[project]
name = "satsaathi-tools"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = []

[dependency-groups]
dev = ["pytest>=8,<9"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/satsaathi_tools"]
```

- [ ] **Step 2: Write the failing test**

`python/tools/tests/test_placeholder.py`:

```python
import satsaathi_tools


def test_package_exposes_version():
    assert satsaathi_tools.__version__ == "0.1.0"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run --package satsaathi-tools pytest python/tools/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'satsaathi_tools'`

- [ ] **Step 4: Write the implementation**

`python/tools/src/satsaathi_tools/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv sync --package satsaathi-tools && uv run --package satsaathi-tools pytest python/tools/tests -v`
Expected: PASS — 1 passed

- [ ] **Step 6: Commit**

```bash
git add python/tools uv.lock
git commit -m "feat(tools): scaffold satsaathi_tools placeholder package"
```

---

### Task 4: `apps/api` FastAPI skeleton with real `/api/v1/health`

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/satsaathi_api/__init__.py`
- Create: `apps/api/src/satsaathi_api/main.py`
- Create: `apps/api/src/satsaathi_api/routers/__init__.py`
- Create: `apps/api/src/satsaathi_api/routers/health.py`
- Test: `apps/api/tests/test_health.py`

**Interfaces:**
- Consumes: `satsaathi_core.settings.get_settings` (Task 2).
- Produces: FastAPI app at `satsaathi_api.main.app`; router module `satsaathi_api.routers.health` exposing `router`, `CheckResult`, `HealthResponse`, and the four coroutine functions `check_database(settings)`, `check_redis(settings)`, `check_storage(settings)`, `check_tiler(settings)` — each returning `CheckResult(status="ok"|"error", detail=str|None)`. `GET /api/v1/health` returns `HealthResponse(mode, status, checks)`.

- [ ] **Step 1: Create `apps/api/pyproject.toml`**

```toml
[project]
name = "satsaathi-api"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi==0.141.1",
    "sse-starlette==3.4.11",
    "uvicorn[standard]>=0.34,<1",
    "pydantic==2.13.5",
    "pydantic-settings>=2.6,<3",
    "asyncpg>=0.30,<1",
    "redis==6.4.0",
    "httpx>=0.28,<1",
    "satsaathi-core",
]

[dependency-groups]
dev = ["pytest>=8,<9"]

[tool.uv.sources]
satsaathi-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/satsaathi_api"]
```

- [ ] **Step 2: Create empty package inits**

`apps/api/src/satsaathi_api/__init__.py`:

```python
```

`apps/api/src/satsaathi_api/routers/__init__.py`:

```python
```

- [ ] **Step 3: Write the failing test**

`apps/api/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from satsaathi_api.main import app
from satsaathi_api.routers import health as health_router


def test_health_ok_when_all_checks_pass(monkeypatch):
    async def ok(_settings):
        return health_router.CheckResult(status="ok")

    monkeypatch.setattr(health_router, "check_database", ok)
    monkeypatch.setattr(health_router, "check_redis", ok)
    monkeypatch.setattr(health_router, "check_storage", ok)
    monkeypatch.setattr(health_router, "check_tiler", ok)

    client = TestClient(app)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["checks"]["storage"]["status"] == "ok"
    assert body["checks"]["tiler"]["status"] == "ok"


def test_health_degraded_when_one_check_fails(monkeypatch):
    async def ok(_settings):
        return health_router.CheckResult(status="ok")

    async def failing(_settings):
        return health_router.CheckResult(status="error", detail="boom")

    monkeypatch.setattr(health_router, "check_database", failing)
    monkeypatch.setattr(health_router, "check_redis", ok)
    monkeypatch.setattr(health_router, "check_storage", ok)
    monkeypatch.setattr(health_router, "check_tiler", ok)

    client = TestClient(app)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"]["status"] == "error"
    assert body["checks"]["database"]["detail"] == "boom"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run --package satsaathi-api pytest apps/api/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'satsaathi_api'`

- [ ] **Step 5: Write the implementation**

`apps/api/src/satsaathi_api/routers/health.py`:

```python
from __future__ import annotations

import asyncio
from typing import Literal

import asyncpg
import httpx
import redis.asyncio as redis_asyncio
from fastapi import APIRouter
from pydantic import BaseModel

from satsaathi_core.settings import Settings, get_settings

router = APIRouter()


class CheckResult(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    mode: str
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckResult]


async def check_database(settings: Settings) -> CheckResult:
    try:
        conn = await asyncpg.connect(dsn=settings.database_url_asyncpg_dsn, timeout=2)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return CheckResult(status="ok")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))


async def check_redis(settings: Settings) -> CheckResult:
    client = redis_asyncio.from_url(settings.redis_url, socket_connect_timeout=2)
    try:
        await client.ping()
        return CheckResult(status="ok")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))
    finally:
        await client.aclose()


async def check_storage(settings: Settings) -> CheckResult:
    try:
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.storage_dir / ".health-probe"
        probe.write_text("ok")
        probe.unlink()
        return CheckResult(status="ok")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))


async def check_tiler(settings: Settings) -> CheckResult:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(settings.tiler_url)
        if response.status_code < 500:
            return CheckResult(status="ok")
        return CheckResult(status="error", detail=f"HTTP {response.status_code}")
    except Exception as exc:
        return CheckResult(status="error", detail=str(exc))


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    names = ("database", "redis", "storage", "tiler")
    checkers = (check_database, check_redis, check_storage, check_tiler)
    results = await asyncio.gather(*(checker(settings) for checker in checkers))
    checks = dict(zip(names, results))
    overall: Literal["ok", "degraded"] = (
        "ok" if all(c.status == "ok" for c in checks.values()) else "degraded"
    )
    return HealthResponse(mode=settings.mode, status=overall, checks=checks)
```

`apps/api/src/satsaathi_api/main.py`:

```python
from fastapi import FastAPI

from satsaathi_api.routers.health import router as health_router

app = FastAPI(title="SatSaathi API")
app.include_router(health_router, prefix="/api/v1", tags=["health"])
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv sync --package satsaathi-api && uv run --package satsaathi-api pytest apps/api/tests -v`
Expected: PASS — 2 passed

- [ ] **Step 7: Commit**

```bash
git add apps/api uv.lock
git commit -m "feat(api): add FastAPI skeleton with real dependency health checks"
```

---

### Task 5: `apps/worker` Celery app skeleton

**Files:**
- Create: `apps/worker/pyproject.toml`
- Create: `apps/worker/src/satsaathi_worker/__init__.py`
- Create: `apps/worker/src/satsaathi_worker/celery_app.py`
- Test: `apps/worker/tests/test_celery_app.py`

**Interfaces:**
- Consumes: `satsaathi_core.settings.get_settings` (Task 2).
- Produces: `satsaathi_worker.celery_app.create_celery_app() -> Celery` and module-level `satsaathi_worker.celery_app.celery_app`, broker/backend both set to `settings.redis_url`, with `task_queues` containing exactly `cpu`, `gpu`, `lang` and `task_default_queue == "cpu"`. Phase 2 registers real tasks against these queues; none exist yet.

- [ ] **Step 1: Create `apps/worker/pyproject.toml`**

```toml
[project]
name = "satsaathi-worker"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "celery==5.6.3",
    "redis==6.4.0",
    "satsaathi-core",
]

[dependency-groups]
dev = ["pytest>=8,<9"]

[tool.uv.sources]
satsaathi-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/satsaathi_worker"]
```

- [ ] **Step 2: Create empty package init**

`apps/worker/src/satsaathi_worker/__init__.py`:

```python
```

- [ ] **Step 3: Write the failing test**

`apps/worker/tests/test_celery_app.py`:

```python
from satsaathi_core.settings import get_settings
from satsaathi_worker.celery_app import create_celery_app


def test_broker_and_backend_come_from_settings(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/2")

    app = create_celery_app()

    assert app.conf.broker_url == "redis://example:6379/2"
    assert app.conf.result_backend == "redis://example:6379/2"


def test_declares_cpu_gpu_lang_queues(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/2")

    app = create_celery_app()

    queue_names = {queue.name for queue in app.conf.task_queues}
    assert queue_names == {"cpu", "gpu", "lang"}
    assert app.conf.task_default_queue == "cpu"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run --package satsaathi-worker pytest apps/worker/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'satsaathi_worker'`

- [ ] **Step 5: Write the implementation**

`apps/worker/src/satsaathi_worker/celery_app.py`:

```python
from __future__ import annotations

from celery import Celery
from kombu import Queue

from satsaathi_core.settings import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("satsaathi", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.task_queues = (Queue("cpu"), Queue("gpu"), Queue("lang"))
    app.conf.task_default_queue = "cpu"
    return app


celery_app = create_celery_app()
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv sync --package satsaathi-worker && uv run --package satsaathi-worker pytest apps/worker/tests -v`
Expected: PASS — 2 passed

- [ ] **Step 7: Commit**

```bash
git add apps/worker uv.lock
git commit -m "feat(worker): add Celery app with cpu/gpu/lang queues, no tasks yet"
```

---

### Task 6: `apps/web` bare Next.js placeholder

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/next.config.ts`
- Create: `apps/web/eslint.config.mjs`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/page.tsx`
- Test: `apps/web/app/page.test.tsx`

**Interfaces:**
- Produces: a Next.js App Router app that builds, lints, and serves one placeholder page at `/`. No Tailwind, no shadcn/ui, no i18n routing yet — those are Phase 3.

- [ ] **Step 1: Create `apps/web/package.json`**

```json
{
  "name": "web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "next": "16.3.5",
    "react": "^19.2.0",
    "react-dom": "^19.2.0"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "@types/node": "^24.0.0",
    "@types/react": "^19.2.0",
    "@types/react-dom": "^19.2.0",
    "eslint": "^9.0.0",
    "eslint-config-next": "16.3.5",
    "prettier": "^3.4.0",
    "vitest": "^3.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "@testing-library/react": "^16.0.0",
    "jsdom": "^25.0.0"
  }
}
```

- [ ] **Step 2: Create `apps/web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Create `apps/web/next.config.ts`**

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
```

- [ ] **Step 4: Create `apps/web/eslint.config.mjs`**

```js
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// eslint-config-next ships flat-config arrays natively as of the ESLint 9 /
// flat-config-only release line — FlatCompat is for legacy .eslintrc-shaped
// shareable configs and corrupts these (circular plugin references) when
// forced through it.
const config = [...nextCoreWebVitals, ...nextTypescript];

export default config;
```

> **Correction found during Phase 1 execution (2026-09-22):** the original
> plan text used `FlatCompat.extends("next/core-web-vitals", "next/typescript")`,
> which crashes with `TypeError: Converting circular structure to JSON`
> against `eslint-config-next@16.3.5` — that package now exports ready-made
> flat-config arrays directly, so `FlatCompat` (built for legacy `.eslintrc`
> shareable configs) double-wraps an already-flat plugin object. Fixed above;
> `@eslint/eslintrc` is correspondingly dropped from devDependencies in Step 1.

- [ ] **Step 5: Create `apps/web/vitest.config.ts`**

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
  },
});
```

- [ ] **Step 6: Write the failing test**

`apps/web/app/page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  it("renders the SatSaathi heading", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: "SatSaathi" })).toBeDefined();
  });
});
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `pnpm --filter web install && pnpm --filter web test`
Expected: FAIL — cannot resolve `./page` (module does not exist yet)

- [ ] **Step 8: Write the implementation**

`apps/web/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "SatSaathi",
  description: "Ask the Satellite, in Your Language",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

`apps/web/app/page.tsx`:

```tsx
export default function HomePage() {
  return (
    <main>
      <h1>SatSaathi</h1>
      <p>Skeleton is booting. The real workspace lands in later phases.</p>
    </main>
  );
}
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `pnpm --filter web test`
Expected: PASS — 1 passed

- [ ] **Step 10: Verify build and lint also work**

Run: `pnpm --filter web build && pnpm --filter web lint && pnpm --filter web typecheck`
Expected: all three exit 0

- [ ] **Step 11: Commit**

```bash
git add apps/web pnpm-lock.yaml
git commit -m "feat(web): scaffold bare Next.js App Router placeholder"
```

---

### Task 7: Generate and verify workspace-wide lockfiles

**Files:**
- Create: `pnpm-lock.yaml` (if not already produced by Task 6)
- Create: `uv.lock`

**Interfaces:** none — this task only proves every package.json/pyproject.toml written so far resolves together into one coherent, committed lockfile pair.

- [ ] **Step 1: Resolve and install the whole JS workspace**

Run: `pnpm install`
Expected: exits 0, `pnpm-lock.yaml` is written/updated at the repo root

- [ ] **Step 2: Resolve and install the whole Python workspace**

Run: `uv sync --all-packages`
Expected: exits 0, `uv.lock` is written at the repo root, listing `satsaathi-core`, `satsaathi-tools`, `satsaathi-api`, `satsaathi-worker` and pinning `redis==6.4.0`, `celery==5.6.3`, `fastapi==0.141.1`, `pydantic==2.13.5`

- [ ] **Step 3: Confirm the redis pin actually resolved to 6.4.0, not something newer**

Run: `uv run --package satsaathi-api python -c "import redis; print(redis.__version__)"`
Expected: prints `6.4.0`

- [ ] **Step 4: Re-run every test suite from the whole workspace to confirm nothing drifted**

Run:
```bash
pnpm test
uv run --package satsaathi-core pytest python/core/tests
uv run --package satsaathi-tools pytest python/tools/tests
uv run --package satsaathi-api pytest apps/api/tests
uv run --package satsaathi-worker pytest apps/worker/tests
```
Expected: all green

- [ ] **Step 5: Commit**

```bash
git add pnpm-lock.yaml uv.lock
git commit -m "chore: commit workspace lockfiles"
```

---

### Task 8: Dockerfiles for api, worker, web

**Files:**
- Create: `infra/docker/api.Dockerfile`
- Create: `infra/docker/worker.Dockerfile`
- Create: `infra/docker/web.Dockerfile`
- Create: `.dockerignore` (repo root)

**Interfaces:** each image's `CMD` is what Task 9's compose file invokes — api listens on `0.0.0.0:8000`, web on `0.0.0.0:3000` (via `next start` default), worker has no listening port.

> **Correction found during Phase 1 execution (2026-09-22):** the original
> plan omitted a root `.dockerignore`. Without one, `web.Dockerfile`'s
> `COPY apps/web apps/web` copies the host's locally-installed
> `apps/web/node_modules` (built for the host OS/arch, with pnpm's
> Windows-style junctions) over the image's own correctly-installed Linux
> `node_modules` from the preceding `pnpm install --frozen-lockfile` layer —
> breaking `next`'s binary resolution (`Cannot find module
> .../next/dist/bin/next`). Add a root `.dockerignore` as part of this task,
> before building any image.
>
> **Critically**, `.dockerignore` uses Go `filepath.Match` semantics, *not*
> gitignore semantics: a bare `node_modules/` pattern matches only a
> **top-level** `node_modules` and silently fails to exclude
> `apps/web/node_modules`. Patterns must be written `**/node_modules`,
> `**/.next`, `**/.venv`, etc. Copying `.gitignore`'s contents verbatim into
> `.dockerignore` reproduces the exact failure above.

- [ ] **Step 1: Create `infra/docker/api.Dockerfile`**

```dockerfile
FROM python:3.12-slim-bookworm

RUN pip install --no-cache-dir uv==0.12.17

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY python/core/pyproject.toml python/core/pyproject.toml
COPY python/tools/pyproject.toml python/tools/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml

RUN uv sync --frozen --package satsaathi-api --no-install-project

COPY python/core python/core
COPY python/tools python/tools
COPY apps/api apps/api

RUN uv sync --frozen --package satsaathi-api

EXPOSE 8000
CMD ["uv", "run", "--package", "satsaathi-api", "uvicorn", "satsaathi_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `infra/docker/worker.Dockerfile`**

```dockerfile
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
```

- [ ] **Step 3: Create `infra/docker/web.Dockerfile`**

```dockerfile
FROM node:24-slim

WORKDIR /workspace

RUN corepack enable

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml turbo.json ./
COPY apps/web/package.json apps/web/package.json

RUN pnpm install --frozen-lockfile

COPY apps/web apps/web

WORKDIR /workspace/apps/web
RUN pnpm build

EXPOSE 3000
CMD ["pnpm", "start"]
```

- [ ] **Step 4: Build each image and verify it succeeds**

Run:
```bash
docker build -f infra/docker/api.Dockerfile -t satsaathi-api:dev .
docker build -f infra/docker/worker.Dockerfile -t satsaathi-worker:dev .
docker build -f infra/docker/web.Dockerfile -t satsaathi-web:dev .
```
Expected: all three builds exit 0. If a `COPY` path or `uv sync --frozen` step fails because a workspace member's `pyproject.toml` changed since `uv.lock` was generated, re-run `uv sync --all-packages` (Task 7, Step 2) and retry.

- [ ] **Step 5: Commit**

```bash
git add infra/docker
git commit -m "feat(infra): add Dockerfiles for api, worker, web"
```

---

### Task 9: Docker Compose (core/offline profiles) + Makefile

**Files:**
- Create: `infra/compose/docker-compose.yml`
- Create: `Makefile`

**Interfaces:** compose service names `postgres`, `redis`, `tiler`, `api`, `worker`, `web` — these exact names are what Phase 2's `docker compose logs <service>` and any future override files will target.

> **Correction found during Phase 1 execution (2026-09-22):** the official
> `ghcr.io/developmentseed/titiler` image runs gunicorn on **port 80**
> inside the container, not 8000. The original plan mapped `8001:8000` and
> set `TILER_URL=http://tiler:8000`, which made the `/api/v1/health` tiler
> check fail with "All connection attempts failed" while every other check
> passed. Correct values: port mapping `8001:80`, and `TILER_URL`
> `http://tiler:80` (in `docker-compose.yml`, `.env.example`, and
> `.env.offline.example`). The image tag `2.4.0` itself is valid and pulls
> successfully.

- [ ] **Step 1: Create `infra/compose/docker-compose.yml`**

```yaml
name: satsaathi

services:
  postgres:
    image: postgis/postgis:16-3.5
    profiles: ["core", "offline"]
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-satsaathi}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-satsaathi_dev_password}
      POSTGRES_DB: ${POSTGRES_DB:-satsaathi}
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-satsaathi}"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:8.10-alpine
    profiles: ["core", "offline"]
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  tiler:
    image: ghcr.io/developmentseed/titiler:2.4.0
    profiles: ["core", "offline"]
    ports:
      - "8001:8000"

  api:
    build:
      context: ../..
      dockerfile: infra/docker/api.Dockerfile
    profiles: ["core", "offline"]
    env_file: ../../.env
    environment:
      TILER_URL: http://tiler:8000
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build:
      context: ../..
      dockerfile: infra/docker/worker.Dockerfile
    profiles: ["core", "offline"]
    env_file: ../../.env
    depends_on:
      redis:
        condition: service_healthy

  web:
    build:
      context: ../..
      dockerfile: infra/docker/web.Dockerfile
    profiles: ["core", "offline"]
    ports:
      - "3000:3000"
    depends_on:
      - api

# gpu profile placeholder — the real VLM worker lands after Phase 5.
# services:
#   worker-gpu:
#     build:
#       context: ../..
#       dockerfile: infra/docker/worker-gpu.Dockerfile
#     profiles: ["gpu"]
#     deploy:
#       resources:
#         reservations:
#           devices:
#             - driver: nvidia
#               count: 1
#               capabilities: [gpu]

volumes:
  postgres-data:
```

- [ ] **Step 2: Create `Makefile`**

```makefile
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
	uv run pyright

gen-client:
	@echo "gen-client wires up in Phase 3 once apps/api's OpenAPI schema and packages/api-client exist"
```

- [ ] **Step 3: Verify the compose file is valid**

Run: `docker compose -f infra/compose/docker-compose.yml --profile core config`
Expected: exits 0, prints the resolved service graph with no errors

- [ ] **Step 4: Bring the whole core profile up and hit health**

Run:
```bash
cp .env.example .env
make dev &
sleep 5
for i in $(seq 1 30); do curl -sf http://localhost:8000/api/v1/health && break; sleep 2; done
curl -s http://localhost:8000/api/v1/health
```
Expected: JSON body with `"status": "ok"` and all four checks `"status": "ok"`. If `tiler` or `database`/`redis` show `"error"`, check `docker compose -f infra/compose/docker-compose.yml logs <service>` — most likely cause is the service not being ready yet within the health check's own retry loop, or the pinned `ghcr.io/developmentseed/titiler:2.4.0` tag needing verification against the live registry (§0 of the spec flags this as unverified).

- [ ] **Step 5: Tear down**

Run: `make down`
Expected: exits 0

- [ ] **Step 6: Commit**

```bash
git add infra/compose/docker-compose.yml Makefile
git commit -m "feat(infra): add docker-compose core/offline profiles and Makefile"
```

---

### Task 10: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:** none — this encodes the Phase 1 Definition of Done as an automated gate.

> **Corrections found during Phase 1 execution (2026-09-22):**
> 1. **`ruff` and `pyright` were never declared as dependencies.** The root
>    `pyproject.toml` configured `[tool.ruff]`/`[tool.pyright]` but nothing
>    installed them, so `uv run ruff check .` and `uv run pyright` both
>    failed with `program not found` — CI's python job and `make lint` /
>    `make typecheck` would all have been red. Added a root
>    `[dependency-groups] dev = ["ruff==0.16.8", "pyright>=1.1.400,<2"]`.
> 2. **Ruff's isort treated our own packages as third-party.** Added
>    `[tool.ruff.lint.isort] known-first-party = ["satsaathi_core",
>    "satsaathi_tools", "satsaathi_api", "satsaathi_worker"]`.
> 3. **Invoke pyright as `uv run python -m pyright`, not `uv run pyright`.**
>    The generated `pyright.exe` shim is unsigned and is blocked outright by
>    Windows Application Control policies (`os error 4551`); the module form
>    works identically on Windows and Linux.
> 4. **Pyright caught a real type error** in `health.py`: `dict` is invariant
>    in its key type, so `dict(zip(names, results))` infers
>    `dict[Literal[...], CheckResult]`, which is not assignable to
>    `dict[str, CheckResult]`. Annotate the binding:
>    `checks: dict[str, CheckResult] = dict(zip(names, results))`.
> 5. **The compose-health CI step must assert on the response body.**
>    `/api/v1/health` returns HTTP 200 even when `degraded`, so a bare
>    `curl -sf` would pass with a broken dependency; grep for
>    `"status":"ok"` instead.

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  js:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 12.5.1
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck
      - run: pnpm test

  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          version: "0.12.17"
      - run: uv python install 3.12
      - run: uv sync --all-packages --frozen
      - run: uv run ruff check .
      - run: uv run pyright
      - run: uv run --package satsaathi-core pytest python/core/tests
      - run: uv run --package satsaathi-tools pytest python/tools/tests
      - run: uv run --package satsaathi-api pytest apps/api/tests
      - run: uv run --package satsaathi-worker pytest apps/worker/tests

  compose-health:
    runs-on: ubuntu-latest
    needs: [js, python]
    steps:
      - uses: actions/checkout@v4
      - run: cp .env.example .env
      - run: docker compose -f infra/compose/docker-compose.yml --profile core up --build -d
      - run: |
          for i in $(seq 1 30); do
            if curl -sf http://localhost:8000/api/v1/health; then exit 0; fi
            sleep 2
          done
          echo "API health check never became reachable" >&2
          exit 1
      - if: failure()
        run: docker compose -f infra/compose/docker-compose.yml --profile core logs
      - if: always()
        run: docker compose -f infra/compose/docker-compose.yml --profile core down -v
```

- [ ] **Step 2: Validate the YAML parses**

Run: `python -c "import yaml, sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: prints `ok`. (Full behavioral verification happens on push, once this is committed and pushed per Task 11.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint/typecheck/test/compose-health workflow"
```

---

### Task 11: ADR, architecture placeholder, README, final end-to-end verification

**Files:**
- Create: `docs/adr/0001-monorepo-tooling.md`
- Create: `docs/architecture.md`
- Create: `README.md`

**Interfaces:** none — documentation plus the final proof that the whole phase's Definition of Done holds together.

- [ ] **Step 1: Create `docs/adr/0001-monorepo-tooling.md`**

```markdown
# ADR 0001: pnpm + Turborepo + uv workspaces, one repo

## Status

Accepted — 2026-09-22

## Context

SatSaathi has a TypeScript frontend (Next.js), a TypeScript API client
generated from the Python backend's OpenAPI schema, and a Python
backend/worker pair. Two artifacts must stay tightly coupled across
languages: `packages/i18n/messages/*.json` (read by both the Next.js app
and the Python API/worker for PDF templates), and `packages/api-client`
(generated from `apps/api`'s live OpenAPI schema). A polyrepo split would
turn every backend API change into a cross-repo version-bump dance during
a hackathon timeline, which is the failure mode this decision avoids.

## Decision

One repo. JS/TS side uses pnpm workspaces for dependency management and
Turborepo for task orchestration/caching. Python side uses a uv workspace
(`[tool.uv.workspace]`) so `python/core`, `python/tools`, `apps/api`, and
`apps/worker` share one resolved dependency graph and one `uv.lock`.

## Consequences

- One CI pipeline, one pair of lockfiles (`pnpm-lock.yaml`, `uv.lock`),
  one source of truth for i18n strings.
- Docker images still build narrow per-service dependency sets (via
  `uv sync --package <name>`), so the API image never pulls in Celery and
  the worker image never pulls in FastAPI — the uv workspace does not
  force a fat shared image.
- Cross-language contract drift (frontend vs backend OpenAPI, or i18n key
  usage) is caught by CI running against one checkout, not by chasing
  version tags across repos.
```

- [ ] **Step 2: Create `docs/architecture.md`**

```markdown
# SatSaathi Architecture

This file is a placeholder. The full request-lifecycle diagram (upload →
compatibility check → job creation → 8-step pipeline over SSE → answer)
gets written once Phase 3 (frontend foundation) and Phase 4 (workspace UI)
exist to diagram against — writing it against Phase 1's skeleton alone
would describe boxes that don't do anything yet.

Until then, the authoritative description of the target architecture is
`docs/superpowers/specs/2026-09-22-satsaathi-architecture-design.md`.
```

- [ ] **Step 3: Create `README.md`**

```markdown
# SatSaathi

"Ask the Satellite, in Your Language" — Team MidDevz's SIH 2026 entry for
SatQuery AI (ISRO problem statement SIH26167): an interactive
vision-language assistant for multimodal remote-sensing image analysis
through text queries, with full English/Hindi/Tamil/Bangla UI support.

This repository is currently at **Phase 1: Skeleton** — the monorepo
shape boots end to end, with all model-backed logic stubbed. See
`docs/superpowers/specs/2026-09-22-satsaathi-architecture-design.md` for
the full architecture and `docs/superpowers/plans/` for the phase-by-phase
implementation plans.

## Windows / WSL2 setup

Docker Desktop's bind mounts and Next.js's file-watcher are both slow (or
broken) when the repo lives under `/mnt/c/...`. Clone the repo **inside**
your WSL2 distro's own filesystem instead:

```
wsl
mkdir -p ~/code && cd ~/code
git clone https://github.com/rsd-06/sat_saathi.git
cd sat_saathi
```

Run every command below (`make dev`, `pnpm`, `uv`, `docker compose`) from
inside that WSL2 shell, in that path — not from a Windows-side terminal
against `\\wsl$`. Enable Docker Desktop's WSL2 integration for your distro
under Settings → Resources → WSL Integration. To edit in an IDE, use your
editor's native WSL/remote mode (e.g. VS Code's "Reopen in WSL") rather
than opening the `\\wsl.localhost\...` UNC path from a Windows-side editor
window.

## Quickstart

```bash
cp .env.example .env
make dev
```

Then, in another terminal:

```bash
curl http://localhost:8000/api/v1/health
```

`make down` stops everything. `make test`, `make lint`, `make typecheck`
run the full test/lint/typecheck suite across both the JS and Python
workspaces. `make gen-client` is a no-op until Phase 3.

## Layout

See `docs/superpowers/specs/2026-09-22-satsaathi-architecture-design.md`
§2 for the full monorepo layout and rationale.
```

- [ ] **Step 4: Final end-to-end verification of the whole phase**

Run:
```bash
make lint
make typecheck
make test
cp .env.example .env
make dev &
for i in $(seq 1 30); do curl -sf http://localhost:8000/api/v1/health && break; sleep 2; done
curl -s http://localhost:8000/api/v1/health
make down
```
Expected: lint/typecheck/test all exit 0; the health JSON shows
`"status": "ok"` with all four checks `"ok"`.

- [ ] **Step 5: Commit and push**

```bash
git add docs/adr/0001-monorepo-tooling.md docs/architecture.md README.md
git commit -m "docs: add ADR 0001, architecture placeholder, README with WSL2 setup"
git push -u origin main
```
