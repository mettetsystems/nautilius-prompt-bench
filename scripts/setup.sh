#!/usr/bin/env bash
# Interactive Nautilius Prompting Workbench setup wizard (model / CPU-only configuration).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example."
fi

API_DIR="${ROOT}/apps/api"
VENV="${API_DIR}/.venv"
PYTHON="${VENV}/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Backend venv not found. Run 'make install-api' first, then 'make setup'." >&2
  exit 1
fi

"${PYTHON}" -m prompt_piper.setup "$@"
setup_status=$?
for setup_arg in "$@"; do
  case "$setup_arg" in
    --hardware-scan|--clarification-only) exit "$setup_status" ;;
  esac
done

if [[ "${setup_status}" -ne 0 ]]; then
  exit "${setup_status}"
fi

preset="$(
  grep -E '^PROMPT_PIPER_LOCAL_MODEL_PRESET=' .env 2>/dev/null \
    | tail -n1 \
    | cut -d= -f2- \
    | tr -d '"' \
    | tr -d "'" \
    || true
)"
llm_enabled="$(
  grep -E '^PROMPT_PIPER_LLM_ENABLED=' .env 2>/dev/null \
    | tail -n1 \
    | cut -d= -f2- \
    | tr -d '"' \
    | tr -d "'" \
    | tr '[:upper:]' '[:lower:]' \
    || true
)"

if [[ "${preset}" != "cpu-only" && "${llm_enabled}" != "false" && -n "${preset}" && "${preset}" != "custom" ]]; then
  echo ""
  source_kind="$("${PYTHON}" -c 'from prompt_piper.setup.download_model import plan_model_download; print("local" if plan_model_download().source_path else "huggingface")')"
  if [[ "$source_kind" == "local" ]]; then
    echo "Importing the selected model from your local repository..."
    "${PYTHON}" -m prompt_piper.setup.download_model
  else
  echo "Local SLM selected (${preset}). Preparing GGUF download tooling..."
  "${VENV}/bin/pip" install -e "${API_DIR}[setup]" >/dev/null
  download_now="y"
  if [[ -t 0 ]]; then
    read -r -p "Download the configured GGUF into data/models/ now? [Y/n] " download_now || download_now="y"
  fi
  if [[ -z "${download_now}" || "${download_now}" == "y" || "${download_now}" == "Y" ]]; then
    "${ROOT}/scripts/download-model.sh" || {
      echo "GGUF download did not finish. Fix the error above, then run: make download-model" >&2
    }
  else
    echo "Skipped download. When ready: make download-model"
  fi
  echo ""
  "${PYTHON}" -c "from prompt_piper.setup.download_model import llama_server_status_message; print(llama_server_status_message())"
  fi
fi

echo ""
echo "Setting up precision lexicon (WordNet + embeddings)..."
if [[ -f "${ROOT}/data/lexicon/precision_vectors.json" ]]; then
  "${ROOT}/scripts/setup-lexicon.sh" --skip-index
else
  if [[ -t 0 ]]; then
    read -r -p "Build semantic vector index now (~20–60 min CPU)? [y/N] " build_index || build_index=""
    if [[ "${build_index}" == "y" || "${build_index}" == "Y" ]]; then
      "${ROOT}/scripts/setup-lexicon.sh"
    else
      "${ROOT}/scripts/setup-lexicon.sh" --skip-index
      echo "Run 'make build-lexicon-index' later for semantic vector ranking."
    fi
  else
    "${ROOT}/scripts/setup-lexicon.sh" --skip-index
    echo "Run 'make build-lexicon-index' for semantic vector ranking."
  fi
fi

echo ""
echo "Next: make download-model   # if you skipped the GGUF download"
echo "      make ensure-llm       # verify GPU + start llama-server"
echo "      make dev-api          # terminal 1"
echo "      make dev-web          # terminal 2"
