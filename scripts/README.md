# Scripts (`scripts/`)

Bash helpers invoked by `Makefile` targets. Run from repo root unless noted.

| Script | Make target | Purpose |
|--------|-------------|---------|
| `setup.sh` | `make setup` | Wizard + optional GGUF download + lexicon |
| `download-model.sh` | `make download-model` | Download GGUF from `.env` into `data/models/` |
| `dev-api.sh` | `make dev-api` | `ensure_llm` + uvicorn with reload on API dirs only |
| `ensure-llm.sh` | `make ensure-llm` | GPU probe and llama-server start |
| `shutdown.sh` | `make shutdown` (`make stop`) | SIGTERM/SIGKILL native API+Vite, llama-server, Quadlets, Podman compose |
| `dev-up.sh` | `make podman-up` | Create export dirs, `podman compose up` |
| `dev-down.sh` | `make podman-down` | Stop compose stack |
| `dev-logs.sh` | `make podman-logs` | Follow service logs (`api`, `web`, `postgres`, …) |
| `init-db.sh` | `make podman-init-db` | Verify pgvector and app tables |
| `init-db-quadlet.sh` | — | DB init variant for Quadlet deployments |
| `install-quadlets.sh` | — | Install user systemd Quadlet units |
| `persistent-install.sh` | `make persistent-install-cpu` / `make persistent-install-ai` | Build, test, Quadlet+systemd install, open browser |
| `wipe-registry.sh` | `make wipe-registry` | Delete local finalized-prompt registry (`--sessions`, `--similarity`, `--yes`) |

```bash
# Example: start native API with auto-LLM
./scripts/dev-api.sh

# Example: stop native API, Vite, llama-server, Quadlets, and Podman
make shutdown

# Example: tail API container logs
./scripts/dev-logs.sh api

# Boot-persistent CPU or AI install (Quadlets + systemd)
make persistent-install-cpu
make persistent-install-ai
# Optional: ./scripts/persistent-install.sh ai --preset qwen3-4b

# Offline image bundle for disconnected hosts
make export
./scripts/export-images.sh --with-ai
./scripts/export-images.sh --import dist/prompt-piper-images-....tar
```

All scripts use `set -euo pipefail` and resolve repo root relative to their own path.
