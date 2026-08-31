#!/usr/bin/env bash
# Stop the Nautilius Prompting Workbench Podman stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

podman compose -f infra/podman-compose.yml down

echo "Nautilius Prompting Workbench containers stopped."
