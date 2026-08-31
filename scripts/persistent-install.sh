#!/usr/bin/env bash
# Persistent Quadlet install: build, test, enable systemd units, open the UI.
#
# Usage:
#   ./scripts/persistent-install.sh cpu
#   ./scripts/persistent-install.sh ai
#   ./scripts/persistent-install.sh ai --preset qwen3-4b
#
# Env overrides:
#   AI_PRESET / PROMPT_PIPER_PERSISTENT_AI_PRESET  default SLM preset (ai mode)
#   SKIP_TESTS=1     skip make test / test-web
#   SKIP_BROWSER=1   do not open the default browser
#   SKIP_BUILD=1     skip image rebuild (use existing images)
#   HEALTH_TIMEOUT   seconds to wait for /health (default 180)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

MODE=""
AI_PRESET="${PROMPT_PIPER_PERSISTENT_AI_PRESET:-${AI_PRESET:-qwen3-1.7b}}"
SKIP_TESTS="${SKIP_TESTS:-0}"
SKIP_BROWSER="${SKIP_BROWSER:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
WEB_URL="http://127.0.0.1:5173"
API_HEALTH_URL="http://127.0.0.1:8000/health"

usage() {
  cat <<EOF
Usage: $(basename "$0") <cpu|ai> [--preset PRESET]

Install a boot-persistent Nautilius Prompting Workbench stack via Podman Quadlets + systemd.

  cpu   CPU-only (no local SLM / llama profile)
  ai    Local SLM via compose llama profile (default preset: ${AI_PRESET})

Options:
  --preset PRESET   AI mode model preset id (e.g. qwen3-1.7b, gemma3-1b)
  -h, --help        Show this help

Environment:
  SKIP_TESTS=1      Skip backend/frontend tests
  SKIP_BROWSER=1    Do not open the default browser
  SKIP_BUILD=1      Skip container image rebuild
  HEALTH_TIMEOUT=N  Seconds to wait for API health (default 180)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    cpu | ai)
      MODE="$1"
      shift
      ;;
    --preset)
      AI_PRESET="${2:-}"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${MODE}" ]]; then
  usage
  exit 1
fi

if [[ -z "${AI_PRESET}" ]]; then
  echo "error: --preset / AI_PRESET must not be empty" >&2
  exit 1
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    echo "  On Fedora: sudo dnf install $2" >&2
    exit 1
  fi
}

require_cmd podman "podman podman-compose"
require_cmd systemctl "systemd"
require_cmd make "make"
require_cmd curl "curl"

echo "==> Persistent install (${MODE})"
echo "    Repo: ${ROOT}"

# Avoid port conflicts with an ephemeral compose stack.
if [[ -x "${ROOT}/scripts/dev-down.sh" ]]; then
  echo "==> Stopping any ephemeral Podman compose stack..."
  "${ROOT}/scripts/dev-down.sh" >/dev/null 2>&1 || true
fi
systemctl --user stop prompt-piper.service >/dev/null 2>&1 || true

echo "==> Installing host dependencies (API, web, lexicon)..."
make install

if [[ ! -f "${ROOT}/.env" ]]; then
  cp "${ROOT}/.env.example" "${ROOT}/.env"
  echo "Created .env from .env.example"
fi

if [[ "${MODE}" == "cpu" ]]; then
  echo "==> Configuring CPU-only runtime..."
  # Non-interactive; lexicon index prompt is skipped when stdin is not a TTY.
  "${ROOT}/scripts/setup.sh" --non-interactive cpu-only
  COMPOSE_PROFILES=""
else
  echo "==> Configuring local SLM (podman:${AI_PRESET})..."
  "${ROOT}/scripts/setup.sh" --non-interactive "podman:${AI_PRESET}"
  echo "==> Downloading GGUF into data/models/..."
  "${ROOT}/scripts/download-model.sh" || {
    echo "error: GGUF download failed. For Gemma presets run: hf auth login" >&2
    echo "       Then: make download-model" >&2
    exit 1
  }

  model_path="$(
    grep -E '^PROMPT_PIPER_LOCAL_MODEL_PATH=' "${ROOT}/.env" 2>/dev/null \
      | tail -n1 \
      | cut -d= -f2- \
      | tr -d '"' \
      | tr -d "'" \
      || true
  )"
  if [[ -z "${model_path}" ]]; then
    echo "error: PROMPT_PIPER_LOCAL_MODEL_PATH missing from .env after setup" >&2
    exit 1
  fi
  if [[ "${model_path}" != /* ]]; then
    model_path="${ROOT}/${model_path#./}"
  fi
  if [[ ! -f "${model_path}" ]]; then
    echo "error: expected GGUF not found at ${model_path}" >&2
    exit 1
  fi
  mkdir -p "${ROOT}/data/models"
  # Relative symlink so the llama container mount (data/models:/models) resolves.
  model_basename="$(basename "${model_path}")"
  if [[ ! -f "${ROOT}/data/models/${model_basename}" ]]; then
    echo "error: GGUF must live under data/models/ for the llama profile (missing ${model_basename})" >&2
    exit 1
  fi
  ln -sfn "${model_basename}" "${ROOT}/data/models/model.gguf"
  echo "    Linked data/models/${model_basename} -> data/models/model.gguf (llama compose profile)"
  COMPOSE_PROFILES="llama"
fi

if [[ "${SKIP_TESTS}" != "1" ]]; then
  echo "==> Running backend tests..."
  make test
  echo "==> Running frontend tests..."
  make test-web
else
  echo "==> Skipping tests (SKIP_TESTS=1)"
fi

if [[ "${SKIP_BUILD}" != "1" ]]; then
  echo "==> Building container images..."
  if [[ -n "${COMPOSE_PROFILES}" ]]; then
    profile_args=()
    IFS=',' read -ra _profiles <<<"${COMPOSE_PROFILES}"
    for p in "${_profiles[@]}"; do
      profile_args+=(--profile "${p}")
    done
    podman compose -f infra/podman-compose.yml "${profile_args[@]}" build
    # Ensure llama.cpp server image is present for the AI profile.
    podman pull docker.io/ggerganov/llama.cpp:server
  else
    podman compose -f infra/podman-compose.yml build
  fi
  # Stable tags used by individual-container Quadlets and offline export.
  api_image="$(podman images --format '{{.Repository}}:{{.Tag}}' | grep -E 'prompt-piper[_-]api' | head -n1 || true)"
  web_image="$(podman images --format '{{.Repository}}:{{.Tag}}' | grep -E 'prompt-piper[_-]web' | head -n1 || true)"
  if [[ -n "${api_image}" ]]; then
    podman tag "${api_image}" localhost/prompt-piper-api:latest
  fi
  if [[ -n "${web_image}" ]]; then
    podman tag "${web_image}" localhost/prompt-piper-web:latest
  fi
  podman pull docker.io/pgvector/pgvector:pg16
else
  echo "==> Skipping image build (SKIP_BUILD=1)"
fi

echo "==> Installing Quadlet units and starting systemd user services..."
install_args=(--method compose --start --quiet)
if [[ -n "${COMPOSE_PROFILES}" ]]; then
  install_args+=(--profiles "${COMPOSE_PROFILES}")
fi
"${ROOT}/scripts/install-quadlets.sh" "${install_args[@]}"

echo "==> Waiting for API health (${HEALTH_TIMEOUT}s)..."
deadline=$((SECONDS + HEALTH_TIMEOUT))
until curl -fsS "${API_HEALTH_URL}" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "error: API did not become healthy at ${API_HEALTH_URL}" >&2
    echo "  Check: systemctl --user status prompt-piper.service" >&2
    echo "         journalctl --user -u prompt-piper.service -n 80 --no-pager" >&2
    exit 1
  fi
  sleep 2
done
echo "    API healthy: ${API_HEALTH_URL}"

open_browser() {
  local url="$1"
  if [[ "${SKIP_BROWSER}" == "1" ]]; then
    echo "==> Skipping browser open (SKIP_BROWSER=1). Open: ${url}"
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    echo "==> Opening default browser: ${url}"
    xdg-open "${url}" >/dev/null 2>&1 || true
  elif command -v gio >/dev/null 2>&1; then
    echo "==> Opening default browser: ${url}"
    gio open "${url}" >/dev/null 2>&1 || true
  else
    echo "==> Open the UI in your browser: ${url}"
  fi
}

open_browser "${WEB_URL}"

cat <<EOF

Persistent install complete (${MODE}).

  Web UI:  ${WEB_URL}
  API:     http://127.0.0.1:8000
  Status:  systemctl --user status prompt-piper.service
  Logs:    journalctl --user -u prompt-piper.service -f

The stack restarts on boot (user linger). To stop running processes without disabling boot start:
  make shutdown
To disable boot start:
  systemctl --user disable --now prompt-piper.service

Guide: ${ROOT}/infra/quadlets/README.md
EOF
