#!/usr/bin/env bash
# Start the full local Nautilius Prompting Workbench Podman stack (postgres + api + web).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v podman >/dev/null 2>&1; then
  echo "error: podman is not installed. On Fedora: sudo dnf install podman podman-compose" >&2
  exit 1
fi

mkdir -p \
  "${HOME}/Documents/Nautilius/exports" \
  "${HOME}/Documents/Nautilius/registry" \
  "${HOME}/Documents/Nautilius/audit" \
  data/model-cache \
  data/postgres \
  data/nltk_data \
  data/lexicon

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example (review before production use)."
  if [[ -t 0 ]] && [[ -x "${ROOT}/apps/api/.venv/bin/python" ]]; then
    echo ""
    read -r -p "Run model setup wizard now? [Y/n] " run_setup || run_setup=""
    if [[ "${run_setup}" != "n" && "${run_setup}" != "N" ]]; then
      "${ROOT}/scripts/setup.sh" || true
    fi
  fi
fi

if [[ -x "${ROOT}/apps/api/.venv/bin/python" ]]; then
  echo ""
  echo "Ensuring precision lexicon data (WordNet + embeddings)..."
  "${ROOT}/scripts/setup-lexicon.sh" --skip-index || true
  if [[ ! -f "${ROOT}/data/lexicon/precision_vectors.json" ]]; then
    echo "Tip: run 'make build-lexicon-index' on the host for semantic precision ranking."
  fi
fi

echo "Building and starting Nautilius Prompting Workbench containers..."
podman compose -f infra/podman-compose.yml up -d --build

"${ROOT}/scripts/init-db.sh"

cat <<EOF

Nautilius Prompting Workbench is running locally.

  Web UI:  http://127.0.0.1:5174
  API:     http://127.0.0.1:8010
  API docs http://127.0.0.1:8010/docs
  Postgres localhost:5432 (user/db from .env)

Exports:  ~/Documents/Nautilius/exports

Logs:  ./scripts/dev-logs.sh
Stop:  ./scripts/dev-down.sh
EOF
