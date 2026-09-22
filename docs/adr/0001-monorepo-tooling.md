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
  force a fat shared image. Verified in Phase 1: the api image is 350 MB
  and the worker image 310 MB, with no overlap in their app-level deps.
- Cross-language contract drift (frontend vs backend OpenAPI, or i18n key
  usage) is caught by CI running against one checkout, not by chasing
  version tags across repos.
- A single root `.dockerignore` governs every image's build context. Note
  that it uses Go `filepath.Match` semantics, not gitignore semantics, so
  nested paths need `**/` prefixes (`**/node_modules`, not
  `node_modules/`) — getting this wrong silently copies host-built,
  platform-specific `node_modules` into Linux images.
