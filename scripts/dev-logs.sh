#!/usr/bin/env bash
# Follow logs from the Nautilius Prompting Workbench Podman stack.
# Usage: ./scripts/dev-logs.sh [service]
#   service: postgres | api | web (optional; default all services)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

podman compose -f infra/podman-compose.yml logs -f "${1:-}"
