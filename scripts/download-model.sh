#!/usr/bin/env bash
# Download the GGUF named in .env (after make setup chose a local SLM preset).
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

is_local="$("${PYTHON}" -c 'from prompt_piper.setup.download_model import plan_model_download; print("yes" if plan_model_download().source_path else "no")')"
if [[ "$is_local" != "yes" ]] && ! "${PYTHON}" -c "import huggingface_hub" >/dev/null 2>&1; then
  echo "Installing Hugging Face Hub CLI into the API venv..."
  "${VENV}/bin/pip" install -e "${API_DIR}[setup]"
fi

exec "${PYTHON}" -m prompt_piper.setup.download_model --check-llama "$@"
