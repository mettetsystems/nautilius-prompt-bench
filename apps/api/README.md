# API package (`apps/api/`)

Python backend for Nautilius Prompting Workbench. Installed as editable package `prompt-piper-api` with two code roots:

| Path | Package | Purpose |
|------|---------|---------|
| [`prompt_piper_api/`](prompt_piper_api/README.md) | `prompt_piper_api` | HTTP API, domain models, session state machine, services |
| [`prompt_piper/`](prompt_piper/README.md) | `prompt_piper` | CLI helpers — setup wizard, demo runner, quality eval |

## Install and run

```bash
# Create venv and install dev dependencies (from repo root)
make install-api

# Start uvicorn with GPU/llama probe and hot reload on API source only
make dev-api
```

## Tests

```bash
# From repo root; PYTHONPATH includes apps/api
make test
```

Configuration is loaded from the repo-root `.env` via `prompt_piper_api.config.get_settings()`.
