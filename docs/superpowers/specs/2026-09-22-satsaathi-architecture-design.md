# SatSaathi — Architecture & Foundation Spec

Status: draft — awaiting user review. Phase 1 design direction (§12 item 1)
was verbally approved in chat on 2026-09-22; this document itself has not
yet been reviewed by the user.
Scope: architecture, UI and backend plumbing only. No ML model, no training,
no real orchestration/LLM logic anywhere in this spec or in Phase 1–5. Every
model-backed step is a stub tool returning deterministic fixture output.

Team MidDevz — SIH 2026, problem statement SIH26167 (ISRO): SatQuery AI, an
interactive vision-language assistant for multimodal remote-sensing image
analysis through text queries. Product name: SatSaathi — "Ask the Satellite,
in Your Language." USP built now: full en/hi/ta/bn UI localisation.

---

## 0. Open Questions — Version Verification Pass (2026-09-22)

Before pinning versions, every library in the original stack list was
checked against its current PyPI/npm/registry state as of today. Findings
that change or contradict the original plan are called out explicitly, per
"tell me instead of silently working around it."

### Real conflicts found (changed the plan)

| # | Issue | Resolution |
|---|-------|------------|
| 1 | **Celery 5.6.3's dependency `kombu[redis]==5.6.2` pins `redis!=4.5.5,!=5.0.2,<6.5,>=4.5.2`.** Current `redis-py` stable is **8.1.0** — that's above the `<6.5` ceiling. `pip install "celery[redis]"` together with an unpinned/latest `redis-py` will not resolve, or will silently install an old cached redis-py. | Explicitly pin **`redis-py==6.4.0`** (highest release under the `<6.5` ceiling, and `>=5.3.0` to dodge a known `celery==5.6.3` regression where `_reconnect_pubsub` breaks on `redis-py<5.3.0`). Revisit this pin whenever Celery/Kombu bumps their redis ceiling. |
| 2 | **`openapi-fetch` (the TS client runtime the spec calls for) has moved into maintenance mode** upstream, per current release notes. Not abandoned, but not actively growing. | Proceed with `openapi-typescript` (codegen) + `openapi-fetch` (runtime) as planned — the API surface needed here (typed fetch wrapper) is small and stable — but flag it in `packages/api-client/README.md` as a "watch" dependency, with `@hey-api/openapi-ts` noted as the fallback if it stalls entirely. |
| 3 | **Lenis is no longer published as `@studio-freight/lenis`.** Studio Freight rebranded to Darkroom Engineering; the package is now plain **`lenis`** on npm (`@studio-freight/lenis` is deprecated). | Spec below uses package name `lenis`, current `1.3.26`. |
| 4 | **Framer Motion was renamed to `motion`.** `framer-motion` still exists as a legacy alias but new code should import from `motion/react`. | Spec below uses package `motion` (`13.4.0`), imports from `motion/react`. |
| 5 | **Zod v4 has open type-compatibility issues with `@hookform/resolvers` `zodResolver`** (ZodObject vs `Zod3Type` mismatches reported against recent `zod@4.x` + `@hookform/resolvers@5.x` combos). | Pin **`zod@^3.25`** (not v4) with `@hookform/resolvers@^5` (which peer-accepts `^3.25 || ^4`) for now. Re-evaluate zod v4 once the resolver issue is closed upstream — tracked as a footnote, not a blocker. |
| 6 | **ESLint vs Biome**, as requested — decided, not left open. | See §3a. |

### Confirmed / corrected, not blocking

- **Python 3.12 pin**: the original justification ("rasterio has no 3.13/3.14 wheels yet") is **no longer accurate** — `rasterio 1.5.1` (current) ships `cp312`, `cp313`, and `cp314` wheels. The 3.12 pin is kept anyway, but for a different, still-valid reason: the wider geospatial stack this project will eventually need (pyproj, shapely, fiona-adjacent GDAL bindings, and later ONNX Runtime for edge inference) is generally a release cycle or two behind on very new CPython versions, and 3.14 is only ~11 months old as of this writing. 3.12 is the safe intersection. This is a judgment call, not a hard requirement — flagged so it's not silently stale.
- **WeasyPrint dropped Cairo/GDK-Pixbuf** (as of v53, current is 70.0) in favor of a pure-Python PDF backend (`pydyf`). It **still requires Pango ≥1.44 and HarfBuzz** for text shaping — confirmed directly from WeasyPrint's own install docs — so the Indic-conjunct-shaping rationale for choosing WeasyPrint over ReportLab still holds. Net effect: the Docker image needs a **smaller** apt package list than originally assumed (no `libcairo2`, no `gdk-pixbuf`), just `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0` (Debian) — a nice simplification, not a problem.
- **rasterio wheels bundle GDAL** — no system `libgdal-dev` needed in the API/worker images for the pure-Python raster I/O this project does.
- **GeoAlchemy2 + async SQLAlchemy**: works in practice (asyncpg engine + `AsyncSession`, community-confirmed pattern), but GeoAlchemy2's own docs don't have a dedicated async section — treat as "supported, undocumented." Alembic autogenerate for `geometry` columns needs GeoAlchemy2's `alembic_helpers` render hook; this is a Phase 2 implementation detail, not a Phase 1 concern.
- **TiTiler now ships one unified Docker image** (`ghcr.io/developmentseed/titiler`) instead of the old split `titiler` / `titiler-uvicorn` images — simpler than the original plan assumed.
- **shadcn/ui + Tailwind v4 + Next.js + React 19**: current shadcn/ui has full Tailwind v4 and React 19 support (no `forwardRef`, `data-slot` attributes) — no conflict.
- **Windows/WSL2 guidance confirmed current**: Docker Desktop's own docs (checked today) still say bind-mounting from `/mnt/c` uses a Plan9 file-share path with materially worse I/O than the WSL2 ext4 filesystem, and measured Sep-2026 benchmarks show the same gap (e.g. `npm ci` 65-100s on `/mnt/c` vs 12-20s natively). See §7.

### Left as-is, no conflict found

FastAPI `0.141.1` / pydantic `2.13.5` (FastAPI requires `pydantic>=2.9.0` — satisfied), SQLAlchemy `2.0.54`, Alembic `1.20.0`, sse-starlette `3.4.11` (requires `starlette>=0.49.1`, satisfied transitively via FastAPI), ruff `0.16.8`, uv `0.12.17`, Next.js `16.3.5`, next-intl `4.14.6`, react-map-gl `8.1.3` (maplibre-gl `>=4` peer).

---

## 1. The Ask → Answer Workflow

Every query is a **Job**. A Job always passes through 8 steps, in order. The
step keys are a fixed enum shared by backend, frontend, i18n and the
exported trace — never renamed:

| # | Step key | Final behaviour | Phase-appropriate stub behaviour |
|---|----------|------------------|-----------------------------------|
| 1 | `ask` | Receive text/voice query + languages | Accept text; voice endpoint returns 501 `voice.not_available` |
| 2 | `imagery` | Register input set, read metadata | **Real** — `rasterio` header read (§6) |
| 3 | `understand` | STT, translate to English, classify intent, extract AOI/dates | Stub: keyword intent classifier + passthrough translation |
| 4 | `preprocess` | Calibrate, de-speckle, co-register, cloud-mask | Stub: "skipped — already co-registered" + params |
| 5 | `compute` | Spectral indices, SAR water mask, change maps, area (ha) | **Real** for indices under the size cap (§6); change/SAR mask stubbed |
| 6 | `vision_language` | Fine-tuned RS VLM: VQA, captioning, grounding | Stub: fixture caption + fixture boxes |
| 7 | `verify` | Cross-check claims vs numbers, confidence, review queue | Stub confidence; real threshold + queue logic |
| 8 | `answer` | LLM phrasing, translation, TTS, layers, PDF, GeoJSON | Stub templated text; real PDF + GeoJSON + trace export |

Each step record persists: `status` (`pending|running|succeeded|skipped|failed|needs_review`),
`started_at`, `finished_at`, `duration_ms`, `tool_name`, `tool_version`,
`params` (permitted-only), `output_summary`, `artifacts`, `error` (key +
params). This trace is the ISRO-evaluated artifact — first-class, persisted,
exportable, not a UI animation.

---

## 2. Monorepo Layout

pnpm workspaces + Turborepo (JS) and a uv workspace (Python) in one repo:

```
satsaathi/
├── apps/
│   ├── web/                  # Next.js App Router + Tailwind v4 + Lenis
│   ├── api/                  # FastAPI — HTTP API, validation, jobs, SSE
│   ├── worker/                # Celery — runs the 8-step pipeline
│   └── tiler/                # TiTiler — serves GeoTIFFs/COGs as tiles
├── packages/
│   ├── i18n/                 # messages/{en,hi,ta,bn}.json + glossary.json
│   ├── api-client/           # TS client generated from FastAPI's OpenAPI
│   ├── ui/                   # Shared React components (shadcn/ui-based)
│   └── config/               # Shared tsconfig, eslint, tailwind preset
├── python/
│   ├── core/                  # satsaathi_core: schemas, step enum, settings, storage, geo utils
│   └── tools/                 # satsaathi_tools: Tool protocol, registry, stub tools
├── infra/
│   ├── docker/                # Dockerfile per app
│   ├── compose/                # docker-compose.yml, profiles: core / offline / gpu
│   └── fixtures/               # sample GeoTIFFs + fixture outputs
├── docs/
│   ├── adr/                   # one ADR per major decision
│   └── architecture.md
├── .github/workflows/          # CI: lint, typecheck, tests, i18n check, OpenAPI drift
├── turbo.json · pnpm-workspace.yaml · pyproject.toml (uv workspace root) · Makefile · .env.example
```

Rules (unchanged from the brief):
- `packages/i18n/messages/*.json` is read by both Next.js and the Python
  API/worker (for PDF templates). Flat-namespaced keys
  (`steps.compute.title`, `upload.errors.crs_mismatch`, …).
- The API never sends user-facing English chrome strings — it sends
  `{"key": "...", "params": {...}}`; the frontend localises. Only free-text
  model output (the answer) goes through the translation service.
- `packages/api-client` is generated from `apps/api`'s OpenAPI schema via
  `openapi-typescript` + `openapi-fetch`. CI fails on drift.

---

## 3. Tech Stack (pinned)

### Frontend (`apps/web`)

| Package | Pinned version | Notes |
|---|---|---|
| next | 16.3.5 | App Router, TS strict, React 19.2.x (resolved by Next) |
| react / react-dom | resolved by Next 16.3.5 (^19.2) | do not hand-pin a mismatched version |
| tailwindcss | ^4.1 (current v4 line) | CSS-first `@theme` config |
| shadcn/ui | latest CLI, generated components | Radix primitives, React-19-safe (no forwardRef) |
| lucide-react | latest | icons |
| motion | 13.4.0 | **not** `framer-motion`; import from `motion/react` |
| lenis | 1.3.26 | **not** `@studio-freight/lenis` |
| next-intl | 4.14.6 | locale-prefixed routes |
| react-map-gl | 8.1.3 | import from `react-map-gl/maplibre` |
| maplibre-gl | latest v5/v6 at lockfile time | react-map-gl 8.1 supports maplibre v4–v6 |
| @tanstack/react-query | latest | server state |
| zustand | latest | workspace UI state |
| react-hook-form | latest | forms |
| zod | ^3.25 (not v4 — see §0) | schema validation |
| @hookform/resolvers | ^5 | zodResolver |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 | codegen + runtime (watch: maintenance mode, §0) |

Fonts: Noto Sans + Noto Sans Devanagari/Tamil/Bengali, self-hosted via
`next/font` — no runtime font CDN (offline mode must work). `<html lang>`
per locale.

### 3a. ESLint vs Biome — decided: **ESLint**

Biome covers roughly 80% of common ESLint rules but has **no equivalent**
for `eslint-config-next` (Core Web Vitals rules, `next/image`, `next/link`
checks) or `eslint-plugin-react-hooks` (`exhaustive-deps`, rules-of-hooks).
`apps/web` is a hooks-heavy, Next-App-Router-heavy surface — losing those
checks is a real regression, not a style preference. So: **ESLint (flat
config) + `eslint-config-next` across the whole JS side**, for one
consistent tool per your instruction to pick one. Formatting is Prettier
(the standard ESLint pairing) — that's a formatter decision, not a second
lint tool, so it doesn't reopen the "pick one" question.

### Backend

| Package | Pinned version | Notes |
|---|---|---|
| Python | 3.12 (uv-managed, `.python-version` pinned) | see §0 footnote |
| fastapi | 0.141.1 | requires `pydantic>=2.9.0` |
| pydantic | 2.13.5 | |
| sse-starlette | 3.4.11 | SSE for job events |
| celery | 5.6.3 | |
| redis (redis-py) | **6.4.0 — pinned, not latest** | kombu 5.6.2 requires `redis<6.5` (§0 #1) |
| sqlalchemy | 2.0.54 | async engine, asyncpg driver |
| geoalchemy2 | 0.20.0 | requires `SQLAlchemy>=1.4`; async works, undocumented (§0) |
| alembic | 1.20.0 | async migrations via `run_sync` |
| rasterio | 1.5.1 | GDAL bundled in wheel; cp312/313/314 all shipped |
| weasyprint | 70.0 | pydyf backend now; still needs Pango+HarfBuzz (§0) |
| titiler.application | 2.4.0 | served via official unified Docker image |
| ruff | 0.16.8 | lint + format |
| pyright | latest | **chosen over mypy** — faster, higher spec conformance, native pydantic-v2 support; mypy not run in CI (can be added later as a slower secondary gate if wanted) |
| uv | 0.12.17 | workspace + Python pinning |

### Deploy

Docker Compose profiles: `core` (web, api, worker-cpu, tiler, postgres,
redis), `offline` (`SATSAATHI_MODE=offline`, no external calls), `gpu`
(placeholder, disabled).

| Base image | Pinned tag |
|---|---|
| Python services | `python:3.12-slim-bookworm` (Trixie exists but is still new; Bookworm has the more field-tested apt/wheel matrix for GDAL/Pango-adjacent packages) |
| Node/web | `node:24-slim` (Node 24 is the current LTS line) |
| Postgres+PostGIS | `postgis/postgis:16-3.5` |
| Redis | `redis:8.10-alpine` |
| TiTiler | `ghcr.io/developmentseed/titiler:2.4.0` (verify exact tag exists at implementation time; fall back to closest matching release tag) |

All lockfiles (`pnpm-lock.yaml`, `uv.lock`) are committed. No image uses
`:latest`.

---

## 4–11. UI, API, real logic, tool registry, data model, config, i18n, quality bar

Unchanged from the original brief in full — routes (`/[locale]`,
`/[locale]/workspace`, `/[locale]/jobs/[id]`, `/[locale]/history`,
`/[locale]/review`, `/[locale]/settings`), the 3-column workspace layout,
Lenis-prevent rule on map/panels, the `/api/v1/*` surface, the
metadata-inspection / pair-compatibility / spectral-index real logic in
§6, the `Tool` protocol + registry + rule-based planner, the Postgres+PostGIS
schema, the pydantic `Settings`, and the 4-locale i18n rules all carry
forward as specified in the original brief. Re-stated in full in
`docs/architecture.md` once Phase 3 exists to point at; not duplicated here
to avoid drift between two copies of the same truth.

---

## 7. Windows / WSL2 Development Setup

This machine is Windows with Docker Desktop. Per current Docker Desktop
guidance (re-verified today, §0): **the repo must live inside the WSL2
filesystem, not under `/mnt/c/...`.** `/mnt/c` is exposed to WSL2 through a
Plan9 protocol file share; bind mounts and file-watchers (Next.js hot
reload, `--watch` mode) through it are measurably slower — reported
Sep-2026 benchmarks show `npm ci` at 65–100s on `/mnt/c` vs 12–20s on native
WSL2 ext4.

`README.md` gets a short section:

```
## Windows / WSL2 setup

Clone the repo INSIDE your WSL2 distro's filesystem, not under /mnt/c:

    wsl
    mkdir -p ~/code && cd ~/code
    git clone https://github.com/rsd-06/sat_saathi.git
    cd sat_saathi

Run every command (make dev, pnpm, uv, docker compose) from inside the WSL2
shell, in this path. Docker Desktop's WSL2 integration must be enabled for
your distro (Settings → Resources → WSL Integration). Opening the folder in
an editor: use \\wsl.localhost\<distro>\home\<user>\code\sat_saathi or the
VS Code "Reopen in WSL" command — do not edit via the \\wsl$ UNC path from a
Windows-side terminal for day-to-day work, only for one-off file browsing.
```

`Makefile` targets are plain POSIX (`sh`-compatible), so they work
identically once invoked from the WSL2 shell — no Windows-specific branches
needed in the Makefile itself, only in the README's setup instructions.

---

## 12. Phases

Unchanged from the brief — five phases, stop-and-report after each:

1. **Skeleton** — repo layout, workspaces, tooling, docker compose `core`
   profile (empty services all booting), `/health` works, CI runs.
2. **Backend plumbing** — settings, storage, DB models + migrations, asset
   upload + metadata inspection, compatibility checks, tool registry +
   stub tools + planner, Celery pipeline, SSE, trace/GeoJSON export, real
   index computation. Tests.
3. **Frontend foundation** — Next.js app, design tokens, fonts, shadcn/ui,
   next-intl (4 locales), header + switcher, landing page + Lenis,
   generated API client.
4. **Workspace** — mode selector, uploads, compatibility cards, band
   mapping, map + TiTiler + swipe compare, query box, live trace, answer
   card, all UI states.
5. **Remaining pages + polish** — job view, history, review queue,
   settings, PDF report (all 4 languages), offline profile verified,
   Playwright e2e in all locales, README + architecture diagram.

Phase 1 is detailed in the companion implementation plan:
`docs/superpowers/plans/2026-09-22-satsaathi-phase-1-skeleton-plan.md`.
