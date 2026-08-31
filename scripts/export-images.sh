#!/usr/bin/env bash
# Build Nautilius Prompting Workbench container images and export them for disconnected hosts.
#
# Usage:
#   ./scripts/export-images.sh
#   ./scripts/export-images.sh --with-ai
#   make export
#
# Load on the target machine:
#   podman load -i dist/prompt-piper-images-*.tar
#   # or: ./scripts/export-images.sh --import PATH
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

WITH_AI=0
DO_IMPORT=""
OUT_DIR="${EXPORT_OUT_DIR:-${ROOT}/dist}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE=""

API_TAG="localhost/prompt-piper-api:latest"
WEB_TAG="localhost/prompt-piper-web:latest"
POSTGRES_IMAGE="docker.io/pgvector/pgvector:pg16"
LLAMA_IMAGE="docker.io/ggerganov/llama.cpp:server"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--with-ai] [--output PATH] [--import ARCHIVE]

Build and save Nautilius Prompting Workbench images as a single Podman archive for offline use.

Options:
  --with-ai         Also pull/save the llama.cpp server image
  --output PATH     Destination .tar path (default: dist/prompt-piper-images-<stamp>.tar)
  --import ARCHIVE  Load a previously exported archive into local Podman (no build)
  -h, --help        Show this help

Environment:
  EXPORT_OUT_DIR    Directory for default output files (default: <repo>/dist)

After export, copy the .tar to the disconnected host and run:
  podman load -i prompt-piper-images-....tar
  # then install Quadlets / make persistent-install-* with SKIP_BUILD=1
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-ai)
      WITH_AI=1
      shift
      ;;
    --output)
      OUT_FILE="${2:-}"
      shift 2
      ;;
    --import)
      DO_IMPORT="${2:-}"
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

if ! command -v podman >/dev/null 2>&1; then
  echo "error: podman is not installed. On Fedora: sudo dnf install podman podman-compose" >&2
  exit 1
fi

if [[ -n "${DO_IMPORT}" ]]; then
  if [[ ! -f "${DO_IMPORT}" ]]; then
    echo "error: archive not found: ${DO_IMPORT}" >&2
    exit 1
  fi
  echo "==> Loading images from ${DO_IMPORT}"
  podman load -i "${DO_IMPORT}"
  echo "Done. Images available to podman."
  exit 0
fi

mkdir -p "${OUT_DIR}"
if [[ -z "${OUT_FILE}" ]]; then
  suffix=""
  if [[ "${WITH_AI}" -eq 1 ]]; then
    suffix="-ai"
  fi
  OUT_FILE="${OUT_DIR}/prompt-piper-images${suffix}-${STAMP}.tar"
fi

echo "==> Building API and web images..."
podman build -f infra/Containerfile.api -t "${API_TAG}" .
podman build -f infra/Containerfile.web \
  --build-arg "VITE_API_BASE_URL=${VITE_API_BASE_URL:-http://127.0.0.1:8000}" \
  -t "${WEB_TAG}" .

# Also tag compose-style names so either Quadlet method can resolve images.
podman tag "${API_TAG}" "localhost/prompt-piper_api:latest" 2>/dev/null || true
podman tag "${WEB_TAG}" "localhost/prompt-piper_web:latest" 2>/dev/null || true

echo "==> Pulling Postgres (pgvector) base image..."
podman pull "${POSTGRES_IMAGE}"

images=("${API_TAG}" "${WEB_TAG}" "${POSTGRES_IMAGE}")

if [[ "${WITH_AI}" -eq 1 ]]; then
  echo "==> Pulling llama.cpp server image (AI / offline SLM)..."
  podman pull "${LLAMA_IMAGE}"
  images+=("${LLAMA_IMAGE}")
fi

echo "==> Saving ${#images[@]} images to ${OUT_FILE}"
podman save -o "${OUT_FILE}" "${images[@]}"

# Companion manifest for operators moving the bundle offline.
manifest="${OUT_FILE%.tar}.txt"
{
  echo "Nautilius Prompting Workbench offline image bundle"
  echo "created: $(date -Iseconds)"
  echo "host: $(hostname 2>/dev/null || echo unknown)"
  echo "images:"
  for img in "${images[@]}"; do
    echo "  - ${img}"
  done
  echo ""
  echo "Load on target:"
  echo "  podman load -i $(basename "${OUT_FILE}")"
  echo ""
  echo "Then either:"
  echo "  SKIP_BUILD=1 make persistent-install-cpu"
  echo "  SKIP_BUILD=1 make persistent-install-ai"
  echo "or install Quadlets manually: ./scripts/install-quadlets.sh --method compose --start"
} >"${manifest}"

size="$(du -h "${OUT_FILE}" | awk '{print $1}')"
cat <<EOF

Export complete.

  Archive:  ${OUT_FILE} (${size})
  Manifest: ${manifest}

Copy both files to the disconnected host, then:
  podman load -i $(basename "${OUT_FILE}")
EOF
