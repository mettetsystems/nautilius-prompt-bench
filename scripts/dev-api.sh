#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/apps/api/.venv/bin"
PYTHON="${VENV}/python"

if [[ ! -x "${VENV}/uvicorn" ]]; then
  echo "API venv missing. Run: make install-api" >&2
  exit 1
fi

API_PKG="$("${PYTHON}" -c "import prompt_piper_api, pathlib; print(pathlib.Path(prompt_piper_api.__file__).resolve())")"
case "${API_PKG}" in
  "${ROOT}"/*) ;;
  *)
    echo "error: this venv is loading ${API_PKG}" >&2
    echo "Recreate it from this repo so the 16-question agent card is used:" >&2
    echo "  make install-api" >&2
    echo "then restart: make dev-api" >&2
    exit 1
    ;;
esac

cd "${ROOT}"
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi
eval "$("${PYTHON}" -m prompt_piper.setup.ensure_llm --shell)"
# Watch API source only — not data/, logs, or models (reload would wipe in-memory sessions).
exec "${VENV}/uvicorn" prompt_piper_api.main:app --reload \
  --reload-dir "${ROOT}/apps/api/prompt_piper_api" \
  --reload-dir "${ROOT}/apps/api/prompt_piper" \
  --host "${API_HOST:-127.0.0.1}" \
  --port "${API_PORT:-8010}"
