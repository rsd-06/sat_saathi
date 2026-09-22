# SatSaathi Architecture

This file is a placeholder. The full request-lifecycle diagram (upload →
compatibility check → job creation → 8-step pipeline over SSE → answer)
gets written once Phase 3 (frontend foundation) and Phase 4 (workspace UI)
exist to diagram against — writing it against Phase 1's skeleton alone
would describe boxes that don't do anything yet.

Until then, the authoritative description of the target architecture is
`docs/superpowers/specs/2026-09-22-satsaathi-architecture-design.md`.

## What exists as of Phase 1

```
web (Next.js :3000)  ──>  api (FastAPI :8000)  ──>  postgres+postgis :5432
                                │                    redis :6379
                                │                    tiler (TiTiler :8001 -> :80)
                          worker (Celery)  ──>  redis  (queues: cpu, gpu, lang)
```

`GET /api/v1/health` performs live connectivity checks against all four
dependencies (database, redis, storage, tiler) and reports `ok` only when
every one passes. No pipeline steps, no tools, and no models exist yet —
those land in Phase 2 onward.
