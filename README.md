# SatSaathi

"Ask the Satellite, in Your Language" — Team MidDevz's SIH 2026 entry for
SatQuery AI (ISRO problem statement SIH26167): an interactive
vision-language assistant for multimodal remote-sensing image analysis
through text queries, with full English/Hindi/Tamil/Bangla UI support.

This repository is currently at **Phase 1: Skeleton** — the monorepo shape
boots end to end, with all model-backed logic stubbed or absent. See
`docs/superpowers/specs/2026-09-22-satsaathi-architecture-design.md` for the
full architecture and `docs/superpowers/plans/` for the phase-by-phase
implementation plans.

## Windows / WSL2 setup

Docker Desktop's bind mounts and Next.js's file-watcher are both slow (or
broken) when the repo lives on the **Windows** filesystem. This applies to
`/mnt/c/...` **and to any Windows-side path reached from WSL**, including
`C:\Users\<you>\OneDrive\...` — OneDrive additionally tries to sync
`node_modules`, which is both slow and a good way to fill your disk.

Clone the repo **inside** your WSL2 distro's own filesystem instead:

```bash
wsl
mkdir -p ~/code && cd ~/code
git clone https://github.com/rsd-06/sat_saathi.git
cd sat_saathi
```

Run every command below (`make dev`, `pnpm`, `uv`, `docker compose`) from
inside that WSL2 shell, in that path — not from a Windows-side terminal
against `\\wsl$`. Enable Docker Desktop's WSL2 integration for your distro
under Settings → Resources → WSL Integration. To edit in an IDE, use your
editor's native WSL/remote mode (e.g. VS Code's "Reopen in WSL") rather than
opening the `\\wsl.localhost\...` UNC path from a Windows-side editor window.

Docker needs real headroom on `C:` to build images — its WSL2 virtual disk
grows on demand, and a full drive surfaces as confusing `input/output error`
failures from containerd rather than a clear "disk full" message.

## Quickstart

```bash
cp .env.example .env
make dev
```

Then, in another terminal:

```bash
curl http://localhost:8000/api/v1/health
```

A healthy stack responds with `"status": "ok"` and all four dependency
checks passing:

```json
{
  "mode": "online",
  "status": "ok",
  "checks": {
    "database": { "status": "ok", "detail": null },
    "redis": { "status": "ok", "detail": null },
    "storage": { "status": "ok", "detail": null },
    "tiler": { "status": "ok", "detail": null }
  }
}
```

| Service | URL |
|---|---|
| web (Next.js) | http://localhost:3000 |
| api (FastAPI) | http://localhost:8000 — docs at `/docs` |
| tiler (TiTiler) | http://localhost:8001 |
| postgres+postgis | `localhost:5432` |
| redis | `localhost:6379` |

`make down` stops everything. `make test`, `make lint`, `make typecheck`
run the full test/lint/typecheck suite across both the JS and Python
workspaces. `make gen-client` is a no-op until Phase 3.

To run the offline profile (no external network calls), use
`.env.offline.example` as your `.env`.

## Layout

See `docs/superpowers/specs/2026-09-22-satsaathi-architecture-design.md`
§2 for the full monorepo layout and rationale.
