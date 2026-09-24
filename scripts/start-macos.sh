#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:$PATH"
PYTHON="$ROOT/apps/api/.venv/bin/python"
if [[ ! -x "$PYTHON" || ! -f .env || ! -d apps/web/dist ]]; then
  echo "Run bash scripts/install-macos.sh first." >&2
  exit 1
fi
set -a
source .env
set +a
# Reject occupied app ports before starting any managed processes.
"$PYTHON" - <<'PY'
import socket
for port in (8010, 5174):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))
PY
"$PYTHON" -m prompt_piper.setup.ensure_llm --strict
API_PID=""
WEB_PID=""
cleanup() {
  trap - EXIT INT TERM
  [[ -z "$API_PID" ]] || kill "$API_PID" 2>/dev/null || true
  [[ -z "$WEB_PID" ]] || kill "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$PYTHON" -m uvicorn prompt_piper_api.main:app --host 127.0.0.1 --port 8010 &
API_PID=$!
# Run the built UI with the same API proxy as development; local use only.
(cd apps/web && exec "$ROOT/node_modules/.bin/vite" preview --host 127.0.0.1 --port 5174 --strictPort) &
WEB_PID=$!
printf '\nOpen http://127.0.0.1:5174 — Ctrl+C stops the app.\n'
printf 'To release model memory afterward: make llama-down\n'
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done
exit 1
