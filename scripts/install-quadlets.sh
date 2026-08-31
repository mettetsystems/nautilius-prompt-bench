#!/usr/bin/env bash
# Install Nautilius Prompting Workbench Quadlet units for rootless Podman (Fedora).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUADLET_SRC="${ROOT}/infra/quadlets"
QUADLET_DEST="${HOME}/.config/containers/systemd"
METHOD="compose"
PROFILES=""
START=0
QUIET=0

# Path token used in shipped Quadlet files (repo expected under $HOME by default).
DEFAULT_REPO_TOKEN="%h/nautilius-prompt-bench"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--method compose|containers] [--profiles LIST] [--start] [--quiet]

Install Nautilius Prompting Workbench Quadlet units into:
  ${QUADLET_DEST}

Methods:
  compose     Install prompt-piper.compose (recommended; uses podman-compose.yml)
  containers  Install .network + postgres + api + web container units

Options:
  --profiles LIST   Comma-separated compose profiles (e.g. llama for local SLM)
  --start           daemon-reload, enable linger hint, enable --now the units
  --quiet           Skip the long "Next steps" footer (still prints paths)

After install (without --start):
  loginctl enable-linger "\$USER"    # start at boot without login
  systemctl --user daemon-reload
  systemctl --user enable --now prompt-piper.service   # compose method
  # or enable individual units — see infra/quadlets/README.md
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --method)
      METHOD="${2:-}"
      shift 2
      ;;
    --profiles)
      PROFILES="${2:-}"
      shift 2
      ;;
    --start)
      START=1
      shift
      ;;
    --quiet)
      QUIET=1
      shift
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

mkdir -p \
  "${HOME}/Documents/Nautilius/exports" \
  "${HOME}/Documents/Nautilius/registry" \
  "${HOME}/Documents/Nautilius/audit" \
  "${ROOT}/data/postgres" \
  "${ROOT}/data/model-cache" \
  "${ROOT}/data/nltk_data" \
  "${ROOT}/data/lexicon" \
  "${ROOT}/data/models" \
  "${QUADLET_DEST}"

if [[ ! -f "${ROOT}/.env" ]]; then
  cp "${ROOT}/.env.example" "${ROOT}/.env"
  echo "Created ${ROOT}/.env from .env.example"
fi

if [[ -x "${ROOT}/apps/api/.venv/bin/python" ]]; then
  echo "Ensuring precision lexicon data (WordNet + embeddings)..."
  "${ROOT}/scripts/setup-lexicon.sh" --skip-index || true
fi

# Rewrite shipped %h/nautilius-prompt-bench tokens when the clone is elsewhere.
rewrite_quadlet_paths() {
  local file="$1"
  if [[ "${ROOT}" == "${HOME}/nautilius-prompt-bench" ]]; then
    return 0
  fi
  # Prefer absolute paths so units work from any clone location.
  sed -i "s|${DEFAULT_REPO_TOKEN}|${ROOT}|g" "${file}"
}

case "${METHOD}" in
  compose)
    cp "${QUADLET_SRC}/prompt-piper.compose" "${QUADLET_DEST}/"
    rewrite_quadlet_paths "${QUADLET_DEST}/prompt-piper.compose"
    if [[ -n "${PROFILES}" ]]; then
      if grep -q '^Profiles=' "${QUADLET_DEST}/prompt-piper.compose"; then
        sed -i "s|^Profiles=.*|Profiles=${PROFILES}|" "${QUADLET_DEST}/prompt-piper.compose"
      else
        # Insert after WorkingDirectory= in the [Compose] section.
        sed -i "/^WorkingDirectory=/a Profiles=${PROFILES}" "${QUADLET_DEST}/prompt-piper.compose"
      fi
      echo "Compose profiles enabled: ${PROFILES}"
    fi
    echo "Installed compose Quadlet: ${QUADLET_DEST}/prompt-piper.compose"
    echo "Generates user unit: prompt-piper.service"
    ;;
  containers)
    if [[ -n "${PROFILES}" ]]; then
      echo "warning: --profiles only applies to --method compose; ignoring for containers" >&2
    fi
    cp \
      "${QUADLET_SRC}/prompt-piper.network" \
      "${QUADLET_SRC}/prompt-piper-postgres.container" \
      "${QUADLET_SRC}/prompt-piper-api.container" \
      "${QUADLET_SRC}/prompt-piper-web.container" \
      "${QUADLET_DEST}/"
    for unit in \
      prompt-piper.network \
      prompt-piper-postgres.container \
      prompt-piper-api.container \
      prompt-piper-web.container
    do
      rewrite_quadlet_paths "${QUADLET_DEST}/${unit}"
    done
    echo "Installed container Quadlets in ${QUADLET_DEST}/"
    echo "Units: prompt-piper-network, prompt-piper-postgres, prompt-piper-api, prompt-piper-web"
    ;;
  *)
    echo "error: --method must be 'compose' or 'containers'" >&2
    exit 1
    ;;
esac

if [[ "${START}" -eq 1 ]]; then
  if ! loginctl show-user "${USER}" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
    echo "Enabling linger so user services start at boot without login..."
    if ! loginctl enable-linger "${USER}" 2>/dev/null; then
      echo "warning: could not enable linger automatically. Run: loginctl enable-linger \"\$USER\"" >&2
    fi
  fi

  systemctl --user daemon-reload

  if [[ "${METHOD}" == "compose" ]]; then
    systemctl --user enable --now prompt-piper.service
    "${ROOT}/scripts/init-db.sh"
  else
    systemctl --user enable --now prompt-piper-network.service
    systemctl --user enable --now prompt-piper-postgres.service
    systemctl --user enable --now prompt-piper-api.service
    systemctl --user enable --now prompt-piper-web.service
    "${ROOT}/scripts/init-db-quadlet.sh"
  fi
fi

if [[ "${QUIET}" -eq 1 ]]; then
  exit 0
fi

cat <<EOF

Next steps:

1. Enable linger (required for boot-time start without logging in):
     loginctl enable-linger "\$USER"

2. Build container images (once, or after code changes):
EOF

if [[ "${METHOD}" == "compose" ]]; then
  if [[ -n "${PROFILES}" ]]; then
    cat <<EOF
     cd ${ROOT}
     podman compose -f infra/podman-compose.yml --profile ${PROFILES//,/ --profile } build
EOF
  else
    cat <<EOF
     cd ${ROOT}
     podman compose -f infra/podman-compose.yml build
EOF
  fi
else
  cat <<EOF
     cd ${ROOT}
     podman build -f infra/Containerfile.api -t localhost/prompt-piper-api:latest .
     podman build -f infra/Containerfile.web \\
       --build-arg VITE_API_BASE_URL=http://127.0.0.1:8000 \\
       -t localhost/prompt-piper-web:latest .
EOF
fi

cat <<EOF

3. Reload systemd user units:
     systemctl --user daemon-reload

4. Enable and start:
EOF

if [[ "${METHOD}" == "compose" ]]; then
  cat <<EOF
     systemctl --user enable --now prompt-piper.service
     ${ROOT}/scripts/init-db.sh
EOF
else
  cat <<EOF
     systemctl --user enable --now prompt-piper-network.service
     systemctl --user enable --now prompt-piper-postgres.service
     systemctl --user enable --now prompt-piper-api.service
     systemctl --user enable --now prompt-piper-web.service
     ${ROOT}/scripts/init-db-quadlet.sh
EOF
fi

cat <<EOF

5. Precision lexicon (host, once per machine):
     make setup-lexicon-all
     # Or skip the long index build: make setup-lexicon && make setup-lexicon-embed

6. Verify:
     curl http://127.0.0.1:8000/health
     # Web UI: http://127.0.0.1:5173

Full guide: ${ROOT}/infra/quadlets/README.md
EOF
