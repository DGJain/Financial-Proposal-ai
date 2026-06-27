#!/usr/bin/env sh
# Full live end-to-end against a REAL PostgreSQL (the integration the unit tests
# fake with SQLite). Brings up Postgres via docker compose, migrates the schema,
# seeds demo data, starts the API, and runs the HTTP checks — then tears the API
# down. Run from the repo root.
#
#   PYTHON=backend/.venv/Scripts/python.exe sh infra/scripts/e2e/run_local_e2e.sh
set -eu

PYTHON="${PYTHON:-python}"
export POSTGRES_DSN="${POSTGRES_DSN:-postgresql+asyncpg://fpp:fpp@localhost:5432/fpp}"
export ENVIRONMENT="${ENVIRONMENT:-local}"
export AIR_GAPPED="${AIR_GAPPED:-true}"
export REDIS_DSN="${REDIS_DSN:-redis://localhost:6379/0}"
export BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "==> 1/5 starting PostgreSQL"
docker compose up -d postgres
# wait for readiness
for _ in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U fpp >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "==> 2/5 migrating schema"
( cd backend && "$PYTHON" -m alembic upgrade head )

echo "==> 3/5 seeding demo data"
"$PYTHON" infra/scripts/seed/seed_demo.py

echo "==> 4/5 starting API"
( cd backend && "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  if curl -fs "$BASE_URL/ready" >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "==> 5/5 running live E2E checks"
"$PYTHON" infra/scripts/e2e/live_e2e.py

echo "Live E2E complete."
