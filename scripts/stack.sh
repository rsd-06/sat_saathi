#!/usr/bin/env bash
# The whole product on one port: open http://localhost:3100.
#
# The web app (3100) proxies /api/v1 to the API (8010, loopback only), which
# hands jobs to Celery: a CPU worker and a GPU worker holding the vision model.
# Postgres, Redis and the tiler come from docker compose.
#
#   bash scripts/stack.sh up        # everything, logs in .data/stack-*.log
#   bash scripts/stack.sh migrate|api|cpu|gpu|web   # one piece, foreground
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${SATSAATHI_DATA:-D:/Projects/sat_saathi/.data}"
export UV_LINK_MODE=copy PYTHONUNBUFFERED=1
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://satsaathi:satsaathi_dev_password@localhost:5432/satsaathi_demo}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export STORAGE_DIR="$DATA/storage" MODELS_DIR="$DATA/models"
export TILER_URL="http://localhost:8001" JOB_DISPATCH=celery
export SATSAATHI_MODEL_IDLE_UNLOAD_MIN=20
export API_URL="http://localhost:8010" NEXT_PUBLIC_API_URL="http://localhost:8010"
CELERY="uv run --no-sync celery -A satsaathi_worker.celery_app.celery_app worker --loglevel=INFO"

case "${1:-}" in
  migrate) cd "$ROOT/python/core" && uv run --no-sync alembic upgrade head ;;
  api) cd "$ROOT" && uv run --no-sync uvicorn satsaathi_api.main:app --host 127.0.0.1 --port 8010 ;;
  # Windows has no fork: both workers use the solo pool.
  cpu) cd "$ROOT" && $CELERY -Q cpu,lang --pool=solo -n cpu@%h ;;
  gpu) cd "$ROOT" && $CELERY -Q gpu --pool=solo --concurrency=1 -n gpu@%h ;;
  web) cd "$ROOT/apps/web" && pnpm exec next dev --port 3100 ;;
  up)
    docker start satsaathi-postgres-1 satsaathi-redis-1 satsaathi-tiler-1 >/dev/null
    bash "$0" migrate
    for part in api cpu gpu web; do
      nohup bash "$0" "$part" >"$DATA/stack-$part.log" 2>&1 &
    done
    echo "starting; open http://localhost:3100 (first question loads the model, ~3 min)"
    ;;
  *) echo "usage: stack.sh up|migrate|api|cpu|gpu|web"; exit 2 ;;
esac
