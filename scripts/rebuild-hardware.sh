#!/usr/bin/env bash
# Rescan/reconfigure hardware and rebuild; never deletes saved data or downloads models.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${ROOT}/apps/api/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Backend environment missing. Run make install-api first." >&2
  exit 1
fi
exec "$PYTHON" -m prompt_piper.setup.rebuild "$@"
