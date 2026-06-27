#!/usr/bin/env sh
# Apply database migrations to head. Used by the K8s migration Job (which runs the
# backend image with `alembic upgrade head`) and for local/CI runs. Idempotent.
#
#   POSTGRES_DSN=postgresql+asyncpg://fpp:fpp@localhost:5432/fpp \
#     sh infra/scripts/migrate/run-migrations.sh
set -eu

: "${POSTGRES_DSN:?POSTGRES_DSN must be set}"
export AIR_GAPPED="${AIR_GAPPED:-true}"

# Resolve the backend directory relative to this script so it runs from anywhere.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BACKEND_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../../../backend" && pwd)

cd "$BACKEND_DIR"
echo "Running 'alembic upgrade head' against $POSTGRES_DSN"
alembic upgrade head
echo "Migrations complete."
