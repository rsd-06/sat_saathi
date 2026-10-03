# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is, and what it is judged on

**SatSaathi — "Ask the Satellite, in Your Language."** Team MidDevz (Kumaraguru College of Technology, Coimbatore), Smart India Hackathon 2026.

- **Problem statement:** SIH26167 — *SatQuery AI: an interactive vision-language assistant for multimodal remote-sensing image analysis through text queries.* Theme: Space Technology. Category: Software. Ministry/organisation: ISRO.
- **The product:** a voice-first copilot for district officers. Ask about an area in your own language (English, Hindi, Tamil, Bangla); SatSaathi **computes** the answer from SAR and multispectral pixels, then a vision-language model **explains** it. Field officers today receive static maps and cannot ask follow-ups; SAR needs radar expertise; optical is blind under monsoon cloud; generic chatbots guess numbers and cannot read NIR/SWIR/SAR bands.
- **Tasks the PS requires, all of which the router must cover:** VQA and captioning · visual grounding (boxes/masks) · bitemporal change detection · optical–SAR fusion. Selecting the correct task and specialist model/tool is itself scored.
- **What is evaluated: the observable execution trace.** Not the UI, not the final prose. The trace is a first-class, persisted, versioned (`trace_version: 1`), exportable data product. Treat anything that makes the trace less truthful as a defect, however small.

The submission deck is `MidDevz_SIH26167_v1.pdf` (not in the repo). Its design commitments, which the code is built to honour:

| Commitment | Where it lives |
|---|---|
| **Compute, don't guess** — hectares and indices come from pixel maths; the LLM only explains verified numbers | `satsaathi_core.indices`, `verify.crosscheck` |
| NDVI, NDWI, LSWI from NIR/SWIR (the indices YES-TECH relies on); **bands are never substituted** — a missing band means "unavailable", not an approximation | `satsaathi_core.indices` raises `MissingBandError` |
| **Confidence gate:** an answer scoring below **0.75** goes to a human expert, never auto-released | `confidence_threshold` setting → `needs_review` job status → `/review` queue |
| Workflow-ready outputs: claim-report PDF, GeoJSON/KML that open in Bhuvan or any GIS | `/jobs/{id}/trace`, `/jobs/{id}/result.geojson`; PDF report is **not built yet** |
| Offline / low-bandwidth edge mode | `SATSAATHI_MODE=offline` |
| Regional language everywhere — Tamil, Hindi, Bangla, English | `packages/i18n` |

The intended query flow has **eight fixed steps**, and these keys are shared verbatim by backend, frontend, i18n catalogs and the exported trace — renaming one is a breaking change to all four:

`ask → imagery → understand → preprocess → compute → vision_language → verify → answer`

(Ask in any language · load SAR/optical/GeoTIFF/before-after · intent, AOI and dates · calibrate/co-register/cloud-mask · NDVI/NDWI/LSWI/SAR water/change/area in ha · VQA/caption/grounding · cross-check VLM claims against computed numbers · LLM explains verified numbers, translated.) Worked example from the deck: *"How much paddy flooded in this village last week?"* → before-image NDVI paddy mask, after-image SAR VV water mask, overlap = flooded paddy (illustrative: 142 ha, 32 % of paddy, confidence 0.86).

## Commands

JavaScript (pnpm 12.5.1 + Turborepo, Node 24):

```bash
pnpm install --frozen-lockfile
pnpm lint | pnpm typecheck | pnpm test          # all via turbo
pnpm --filter @satsaathi/i18n check              # locale parity gate (also a CI step)
pnpm --filter web exec vitest run lib/tiff.test.ts        # one web unit test file
pnpm --filter web exec playwright test -g "refuses"       # e2e; needs the full stack up
```

Python (3.12, uv workspace; `uv sync --all-packages --frozen`):

```bash
uv run ruff check .
uv run python -m pyright        # module form on purpose: the `pyright` .exe shim is blocked on Windows
uv run --package satsaathi-core  pytest python/core/tests
uv run --package satsaathi-tools pytest python/tools/tests/test_vlm_tools.py::test_name -q   # one test
uv run --package satsaathi-api   pytest apps/api/tests
uv run --package satsaathi-inference pytest python/inference/tests -m "not gpu"
make test | make lint | make typecheck          # the whole suite, both languages
```

API tests that need Postgres **skip silently when `DATABASE_URL` is unset** — a green run with many skips proves little. `apps/api/tests/conftest.py` refuses to run against a non-local database unless `SATSAATHI_ALLOW_REMOTE_TESTS=1`; point `DATABASE_URL` at the Docker Postgres.

Running it:

```bash
make dev                         # docker compose --profile core: web 3000, api 8000, tiler 8001, postgres 5432, redis 6379
bash scripts/stack.sh up         # the real demo on http://localhost:3100 (api 8010, cpu + gpu Celery workers, web)
bash scripts/stack.sh migrate|api|cpu|gpu|web   # one piece, foreground
uv sync --all-packages --extra gpu              # only on the GPU worker (torch, peft, bitsandbytes…)
make models-doctor               # what the inference runtime can and cannot see
```

Migrations (Alembic, run from `python/core`): `uv run alembic upgrade head`, `uv run alembic revision --autogenerate -m "…"`. Always round-trip (`upgrade` → `downgrade -1` → `upgrade`) before committing; autogenerate has produced destructive drops of PostGIS's own tables before (see `migrations/env.py`'s `_include_object`) and omits Postgres ENUM drops.

Regenerating the typed API client: with the API running, `curl localhost:8010/openapi.json -o packages/api-client/openapi.json && pnpm --filter @satsaathi/api-client generate`.

## Architecture (the parts that need several files to see)

**Monorepo, two toolchains.** `apps/web`, `packages/i18n`, `packages/api-client` are pnpm/Turbo. Python is a uv workspace: `python/core` (settings, models, raster/index maths, storage, events — everything else depends on it), `python/models` (declarative model catalog; stdlib only), `python/inference` (GPU runtime; **lazy torch**), `python/tools` (the tools, planner, pipeline, trace schema), `python/jobs` (running a job), and the thin shells `apps/api` (FastAPI) and `apps/worker` (Celery).

**One query, end to end.**
1. The browser calls same-origin `/api/v1/*`; `apps/web/app/api/v1/[...path]/route.ts` proxies it, turning the httpOnly session cookie into a bearer token. Next owns the cookie; the API never sets one.
2. `POST /jobs` seeds all eight pending steps, then **plans at creation** (`satsaathi_jobs.service.plan_job`): the rule-based planner (`registry.plan`, deliberately dumb — a table, not reasoning) maps (intent, input mode, available indices) to one tool per step. The task (vqa / caption / grounding / change / fusion) is an explicit recorded decision (`tools/tasks.py`), written into the step's permitted params.
3. `api/dispatch.py` sends the job to a Celery queue (`cpu` · `gpu` · `lang`, chosen from the scarcest queue any planned tool declares) or runs it inline (`JOB_DISPATCH=inline`, no broker). Two logged fallbacks keep a job from waiting forever: a `gpu` job drops to `cpu` when no GPU worker has heartbeated in the last 15 s (its model steps then take the fixture path and the trace says `model.not_loadable`), and an unreachable broker falls back to inline.
4. `satsaathi_jobs.runner.run_job` — the same code in both deployments — calls `satsaathi_tools.pipeline.run`, which is free of Celery/Redis/DB, persists each step, and publishes a **full snapshot** (never a delta) to the event bus (`core/events.py`: Redis pub/sub, in-process fallback).
5. `GET /jobs/{id}/events` streams snapshots over SSE. Pub/sub has no replay, so the stream re-reads the row whenever the broker is quiet — without that, a job finishing before the subscription existed hung the page forever.

**The honesty contract (the central invariant).** A step that returned fixture output must never look like one that ran a model. `is_stub`, `tool_version` (carries `+<model>@<revision>`), and `output_summary["source"]` must agree and describe the run that *actually happened*. A tool's `is_stub` is a *prediction*; `ToolResult.is_stub` / `.tool_version` override it, and `pipeline.run` prefers the result (`ModelBackedTool._tagged` sets all three from one branch). `verify.crosscheck` holds an answer unless something was really measured (`_has_measurement` — a dict of "unavailable" reasons is not a measurement). Confidence is a recorded product: `prior(model, task) × signal [× consistency] [× agreement]` (`tools/confidence.py`).

**Models.** `satsaathi_models.catalog` declares every adapter; availability is a `stat()`, so the API resolves it without importing torch. Adapters are LoRA on **one resident 4-bit Qwen3-VL-2B base**; an adapter trained on a different base is refused. `core/imaging.py` prepares inputs *exactly* as the adapters were trained (≤512 px longest side, bicubic, never enlarged; SAR 8-bit chips pass through, raw backscatter is dB-stretched) — do not resize elsewhere. The GPU worker uses the solo pool (CUDA does not survive fork), heartbeats, and unloads when idle. Weights live in `MODELS_DIR`, apart from user rasters in `STORAGE_DIR`.

**Data.** Postgres + PostGIS. Rasters live in storage (local or S3), never the database. Tables: `users`, `user_sessions` (token *hash* only), `auth_identities`, `assets`, `input_sets`, `jobs`, `job_steps`, `artifacts`, `review_items`, `analyses`. Work is owner-scoped. Settings (`core/settings.py`) read one gitignored `.env.local` at the repo root, shared by Python and Next (`next.config.ts` loads it); real env vars win. `effective_database_url`: **offline mode always uses the local Docker Postgres**; a remote host gets TLS; port 6543 (Supabase transaction pooler) disables the prepared-statement cache. The API warms its pool in the background because connecting to a hosted DB (~5 s) dwarfed the actual work (~0.4 s).

**Auth.** Opaque session tokens; Argon2id; wrong-password and unknown-email are indistinguishable in body *and* timing. Google sign-in uses state + PKCE; the API verifies the ID token (signature, issuer, audience, expiry). A Google identity links to an existing password account **only if Google says `email_verified`** — otherwise anyone able to register that address at Google owns the account. Identities match on `sub`, never email. Password-less accounts have `password_hash = NULL`.

**i18n.** `packages/i18n/messages/{en,hi,ta,bn}.json` are flat dotted keys, the single source of truth for web and Python. `check.mjs` (CI) enforces parity, matching ICU placeholders, and no key being a prefix of another. The API sends `{key, params}` and **never user-facing English** for chrome — that includes validation errors (`request.invalid`). Translations are machine-drafted and tracked in `*.review.json` under `entries` with `reviewed: false` until a native speaker signs off; new keys go *inside* `entries`.

**Web.** Next 16 App Router, locale-prefixed routes (`/en`, `/hi`, `/ta`, `/bn`), **`proxy.ts` not `middleware`**. Signed-in pages sit in `app/[locale]/(app)/`; `getSession()` (per-request cached) distinguishes signed-in / signed-out / invalid / unreachable — an API blip must not sign anyone out. Design language is a Survey-of-India toposheet ("Survey document"): paper/ink tokens, one indigo accent, semantic water/vegetation/relief colours that encode data, marginalia framing, motion that *draws* (`components/motion/`). Content must be visible without JS; reveals arm only after `data-motion="on"`.

**Upload rule.** The workspace accepts **GeoTIFF/TIFF only**, enforced three times: by extension, by the file's first four bytes (`satsaathi_core.raster.is_tiff`, mirrored in `apps/web/lib/tiff.ts`), and in the browser before any byte is sent. The server check is the one that counts. The "Image stack" panel (change/cross-modal) is browser-only canvas analysis of PNG/JPEG/WebP and never uploads.

## Conventions

- **Python:** 3.12, ruff (`E,F,I,UP`, line length 100), pyright basic, pydantic v2, async SQLAlchemy 2, `StrEnum`, timezone-aware UTC. Versions are pinned exactly; lockfiles (`uv.lock`, `pnpm-lock.yaml`) and Docker image tags are committed pinned.
- **TypeScript:** strict; Tailwind v4 CSS-first (`@theme` in `globals.css`); server-only code behind `import "server-only"` (pure helpers split out so vitest can import them).
- **Comments explain *why*,** usually by recording the failure that motivated the code. Keep that habit; do not narrate what the line does.
- **Copy:** sentence case, plain verbs, no ALL-CAPS labels, errors state what to do next. Same word for the same action everywhere.
- **Commits:** `type(scope): subject`, body says what went wrong and why. Tests are named for behaviour; regression tests carry the story.
- **Lean mode (user preference):** one smoke check per change, not suites; terse reports; stage only your own files.

## Hard-won gotchas

- **Never write backslash escapes through a shell heredoc** (`\n`, `\x00`, `\r`). They are resolved a layer early and corrupt source silently — raw NUL bytes ended up in `raster.py`. Build bytes with `bytes.fromhex(...)`, newlines with `chr(10)`, or write files with the editor tool. Check with a control-byte scan and `ast.parse`.
- **Test the way the user does.** Playwright's `setInputFiles` never opens a dialog, so it hid a picker that did not open. Click, wait for `filechooser`, count dialogs.
- **One event loop per process** for anything holding an asyncpg pool. `asyncio.run` per Celery task strands the pool on a dead loop (`'NoneType' object has no attribute 'send'` on the second job). The API disposes its engine in `lifespan` for the same reason.
- **Shared tree.** This worktree (`worktree-vlm-backend`) is the integration branch and other work lands here; the git stash is shared across worktrees (use `git stash push -u -m <tag>`, never bare `stash`/`pop`). Stage explicit paths, never `git add -A`.
- **Ports.** `:3100` is the real demo (api 8010, Qwen3-VL + adapters). `:3000`/`:8000` is the Docker fixture stack — every answer there is fixture text. Kill stale servers by port before restarting or you get `EADDRINUSE` and a half-working stack. Next's `Jest worker … child process exceptions` means the dev server died, usually from memory pressure; restart it.
- **Windows.** Smart App Control once blocked native DLLs (pyproj, psycopg), which is why the API once ran in Docker; it has since been turned off. Workers use `--pool=solo` (no fork). Secrets go only in `.env.local`; a database password containing `@` must be percent-encoded (`%40`) in URLs.
- **Honest numbers.** An image with no CRS has no pixel size (`None`, not `1.0`) and no area; the answer says so.

## Known gaps (see `TODO.md`)

Answer composer is a pass-through (`AnswerTemplate` is a stub) · `intent.keyword` is keyword lists, not a classifier · confidence is low (31–49 % on test images), so most answers are held for review — calibrate before trusting the 0.75 gate · change/cross-modal analyses in the browser are pixel heuristics, not models · new workspace panels are English-only · claim-report PDF, voice (ASR/TTS), IndicTrans2/Bhashini translation and Ollama explanation are planned, not built · all Hindi/Tamil/Bangla strings await native-speaker review.
