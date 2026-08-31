#!/usr/bin/env bash
# Permanently delete local finalized-prompt registry files (and optional session JSON).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

YES=0
WIPE_SESSIONS=0
WIPE_SIMILARITY=0

usage() {
  cat <<'EOF'
Wipe the local prompt registry so it can be rebuilt from scratch.

Usage:
  ./scripts/wipe-registry.sh
  ./scripts/wipe-registry.sh --yes
  ./scripts/wipe-registry.sh --yes --sessions
  ./scripts/wipe-registry.sh --yes --similarity

Options:
  --yes          Do not prompt for confirmation
  --sessions     Also delete saved session JSON (in-progress and completed)
  --similarity   Also delete the JSON similarity index if one is configured
  -h, --help     Show this help

Prompts live as files on this machine only. Older installs may still have a
leftover registry .git directory; wiping removes that too. Restart the API
after wiping.

Stale Dashboard "recent session" rows live in the browser
(localStorage key nautilius.recent-sessions) and are not removed here.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --sessions) WIPE_SESSIONS=1 ;;
    --similarity) WIPE_SIMILARITY=1 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

expand_path() {
  local raw="$1"
  if [[ -z "$raw" ]]; then
    echo ""
    return
  fi
  raw="${raw/#\~/${HOME}}"
  if [[ "$raw" != /* ]]; then
    raw="${ROOT}/${raw#./}"
  fi
  realpath -m "$raw"
}

load_env_file() {
  if [[ -f "${ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${ROOT}/.env"
    set +a
  fi
}

resolve_paths_python() {
  local py="${ROOT}/apps/api/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    return 1
  fi
  PYTHONPATH="${ROOT}/apps/api" "$py" - <<'PY'
from prompt_piper_api.config import get_settings

settings = get_settings()
print(settings.registry_path)
print(settings.sessions_path)
print(settings.similarity_index_path or "")
PY
}

REGISTRY_PATH=""
SESSIONS_PATH=""
SIMILARITY_INDEX_PATH=""

if paths="$(resolve_paths_python 2>/dev/null)"; then
  REGISTRY_PATH="$(echo "$paths" | sed -n '1p')"
  SESSIONS_PATH="$(echo "$paths" | sed -n '2p')"
  SIMILARITY_INDEX_PATH="$(echo "$paths" | sed -n '3p')"
else
  load_env_file
  REGISTRY_PATH="$(expand_path "${REGISTRY_PATH:-./data/registry}")"
  SESSIONS_PATH="$(expand_path "${SESSIONS_PATH:-./data/sessions}")"
  if [[ -n "${SIMILARITY_INDEX_PATH:-}" ]]; then
    SIMILARITY_INDEX_PATH="$(expand_path "$SIMILARITY_INDEX_PATH")"
  fi
fi

REGISTRY_PATH="$(expand_path "$REGISTRY_PATH")"
SESSIONS_PATH="$(expand_path "$SESSIONS_PATH")"
if [[ -n "$SIMILARITY_INDEX_PATH" ]]; then
  SIMILARITY_INDEX_PATH="$(expand_path "$SIMILARITY_INDEX_PATH")"
fi

assert_safe() {
  local path="$1"
  local kind="$2"
  if [[ -z "$path" || "$path" == "/" || "$path" == "$HOME" ]]; then
    echo "Refusing to delete ${kind} path: ${path:-empty}" >&2
    exit 1
  fi
  case "$path" in
    "${ROOT}/data/"*|"${HOME}/Documents/Nautilius/"*)
      return 0
      ;;
  esac
  case "$path" in
    */registry|*/sessions|*similarity_index.json)
      return 0
      ;;
  esac
  echo "Refusing to delete unexpected ${kind} path: ${path}" >&2
  exit 1
}

assert_safe "$REGISTRY_PATH" "registry"
if [[ "$WIPE_SESSIONS" -eq 1 ]]; then
  assert_safe "$SESSIONS_PATH" "sessions"
fi
if [[ "$WIPE_SIMILARITY" -eq 1 && -n "$SIMILARITY_INDEX_PATH" ]]; then
  assert_safe "$SIMILARITY_INDEX_PATH" "similarity index"
fi

describe_target() {
  local path="$1"
  if [[ -e "$path" ]]; then
    local size
    size="$(du -sh "$path" | awk '{print $1}')"
    echo "  ${path}  (${size})"
  else
    echo "  ${path}  (missing)"
  fi
}

echo "The following will be deleted permanently:"
describe_target "$REGISTRY_PATH"
if [[ "$WIPE_SESSIONS" -eq 1 ]]; then
  describe_target "$SESSIONS_PATH"
fi
if [[ "$WIPE_SIMILARITY" -eq 1 ]]; then
  if [[ -n "$SIMILARITY_INDEX_PATH" ]]; then
    describe_target "$SIMILARITY_INDEX_PATH"
  else
    echo "  (no JSON similarity index configured; database embeddings are left alone)"
  fi
fi

if [[ "$YES" -ne 1 ]]; then
  if [[ ! -t 0 ]]; then
    echo "Refusing to wipe without --yes in a non-interactive shell." >&2
    exit 1
  fi
  read -r -p "Type wipe to continue: " confirm
  if [[ "$confirm" != "wipe" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

wipe_directory() {
  local dir="$1"
  mkdir -p "$dir"
  find "$dir" -mindepth 1 -maxdepth 1 \
    ! -name 'README.md' \
    ! -name '.gitkeep' \
    -exec rm -rf {} +
}

wipe_directory "$REGISTRY_PATH"
touch "${REGISTRY_PATH}/.gitkeep"

if [[ "$WIPE_SESSIONS" -eq 1 ]]; then
  wipe_directory "$SESSIONS_PATH"
  touch "${SESSIONS_PATH}/.gitkeep"
fi

if [[ "$WIPE_SIMILARITY" -eq 1 && -n "$SIMILARITY_INDEX_PATH" && -e "$SIMILARITY_INDEX_PATH" ]]; then
  rm -f "$SIMILARITY_INDEX_PATH"
fi

echo "Registry wiped. Restart the API (make dev-api) before opening the app."
echo "If Dashboard still lists old rows, they are browser recents — they are not on disk."
