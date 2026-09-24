#!/usr/bin/env bash
# Native Apple Silicon installation; deliberately does not use Linux containers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo "This installer requires a native Apple Silicon macOS terminal (no Rosetta)." >&2
  exit 1
fi
if [[ -f .env ]] && ! grep -q '^# Nautilius native Mac profile$' .env; then
  echo "Existing .env preserved. Use a fresh checkout for the Mac install, or move .env to a backup first." >&2
  exit 1
fi
if ! command -v brew >/dev/null; then
  echo "Install Apple Silicon Homebrew from https://brew.sh, then run this installer again." >&2
  exit 1
fi
if [[ "$(brew --prefix)" != /opt/homebrew ]]; then
  echo "Use native Apple Silicon Homebrew in /opt/homebrew." >&2
  exit 1
fi
brew install python@3.12 node@22 llama.cpp
export PATH="$(brew --prefix node@22)/bin:/opt/homebrew/bin:$PATH"
PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
"$PYTHON" -c 'import platform; assert platform.machine() == "arm64", "Python must be arm64"'
"$PYTHON" -m venv apps/api/.venv
PYTHON="$ROOT/apps/api/.venv/bin/python"
"$PYTHON" -m pip install -e './apps/api[setup,lexicon]'
npm ci
mkdir -p data/models
if [[ ! -f .env ]]; then
  cp infra/env.macos.example .env
  chmod 600 .env
fi
npm run build:web
bash scripts/setup-lexicon.sh --wordnet-only
"$PYTHON" -m prompt_piper.setup.download_model
printf '\nInstalled. Start with: bash scripts/start-macos.sh\n'
