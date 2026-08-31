#!/usr/bin/env bash
# WordNet + embedding deps + optional precision vector index (CPU embed).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_DIR="${ROOT}/apps/api"
VENV="${API_DIR}/.venv"
PYTHON="${VENV}/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Backend venv not found. Run 'make install-api' first." >&2
  exit 1
fi

# NLTK 3.10+ blocks imports whose path is under CWD. Our venv lives under the
# repo root, so site-packages (e.g. regex) are false-positive blocked.
export NLTK_DISABLE_IMPORT_SECURITY="${NLTK_DISABLE_IMPORT_SECURITY:-1}"

exec "${PYTHON}" -m prompt_piper.setup.lexicon_setup "$@"
