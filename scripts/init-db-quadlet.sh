#!/usr/bin/env bash
# Wait for PostgreSQL and create Nautilius Prompting Workbench tables (Quadlet / podman exec path).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-prompt_piper}"
POSTGRES_DB="${POSTGRES_DB:-prompt_piper}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-prompt-piper-postgres}"
API_CONTAINER="${API_CONTAINER:-prompt-piper-api}"

if ! podman container exists "${POSTGRES_CONTAINER}" 2>/dev/null; then
  echo "error: container ${POSTGRES_CONTAINER} is not running." >&2
  exit 1
fi

echo "Waiting for PostgreSQL in ${POSTGRES_CONTAINER}..."
ready=0
for _ in $(seq 1 60); do
  if podman exec "${POSTGRES_CONTAINER}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "${ready}" -ne 1 ]]; then
  echo "error: PostgreSQL did not become ready in time." >&2
  exit 1
fi

echo "Ensuring pgvector extension..."
podman exec "${POSTGRES_CONTAINER}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

if ! podman container exists "${API_CONTAINER}" 2>/dev/null; then
  echo "warning: ${API_CONTAINER} is not running; skipping init_db()." >&2
  exit 0
fi

echo "Creating application tables..."
podman exec "${API_CONTAINER}" python -c "from prompt_piper_api.db import init_db; init_db()"

echo "Database initialization complete."
