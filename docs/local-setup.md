# Local setup

Nautilius Prompting Workbench local development and Podman deployment.

## Prerequisites

- Python 3.12+
- Node.js 20+ and npm
- Make
- Podman (optional, for PostgreSQL with pgvector)

## Quick start

Run these from the **Nautilius Prompting Workbench repo root**:

```bash
cp .env.example .env
make install
make setup           # CPU-only or local SLM; offers GGUF download for SLM presets
make download-model  # if you skipped download during setup
make ensure-llm      # verify GPU + llama-server + GGUF
make dev-api         # terminal 1
make dev-web         # terminal 2
make shutdown        # stop API, Vite, llama-server, and any Podman/Quadlet stack
```

- API: http://127.0.0.1:8010
- API docs: http://127.0.0.1:8010/docs
- Web: http://127.0.0.1:5174

## Environment

Copy `.env.example` to `.env` at the repo root. Key variables:

| Variable           | Default                              | Description                    |
|--------------------|--------------------------------------|--------------------------------|
| `DATABASE_URL`     | `sqlite:///./data/prompt_piper.db`   | SQLite or PostgreSQL URL       |
| `REGISTRY_PATH`    | `./data/registry`                    | Local prompt storage           |
| `ARTIFACTS_PATH`   | `./data/artifacts`                   | Generated export files         |
| `VITE_API_BASE_URL`| `http://127.0.0.1:8010`              | Frontend → API base URL        |

### Local model wizard

After `make install`, run the interactive setup wizard from the repo root:

```bash
make setup
```

Choices:

1. **CPU-only** — disables the chat LLM (`PROMPT_PIPER_LLM_ENABLED=false`); clarification uses rule-based fallbacks.
2. **Gemma 3** — official `google/*-qat-q4_0-gguf` releases (1B, 4B, 12B prosumer). Requires Hugging Face Gemma license (`hf auth login`).
3. **Gemma 3n** — efficient E4B (~3–4B class); community GGUF from official `google/gemma-3n-E4B-it` weights until Google publishes QAT GGUF.
4. **Qwen3** — official `Qwen/Qwen3-*-GGUF` releases (0.6B–8B). No Gemma license.
5. **Other** — your own OpenAI-compatible URL (vLLM, Ollama, etc.).

The wizard detects GPU VRAM when available and groups presets:

| Tier | VRAM guide | Examples |
|------|------------|----------|
| Compact | ~2–4GB | Qwen3 0.6B/1.7B, Gemma 3 1B |
| Standard (~3–4B class) | ~8GB+ | Qwen3 4B, Gemma 3 4B, Gemma 3n E4B |
| Prosumer (~8B+) | ~16GB+ (4090/5080/5090 class) | Qwen3 8B, Gemma 3 12B |

When you pick a Gemma/Qwen preset, `make setup` also:

1. Installs Hugging Face Hub CLI into the API venv (`make setup-model-deps`)
2. Offers to download the configured GGUF into `data/models/` (same as `make download-model`)
3. Checks whether `llama-server` is on `PATH`

Non-interactive (CI/scripted):

```bash
./scripts/setup.sh --non-interactive cpu-only
./scripts/setup.sh --non-interactive gemma3-1b
./scripts/setup.sh --non-interactive qwen3-4b
./scripts/setup.sh --non-interactive qwen3-8b
./scripts/setup.sh --non-interactive gemma3-12b
./scripts/setup.sh --non-interactive gemma3n-e4b
./scripts/setup.sh --non-interactive podman:qwen3-1.7b
# legacy aliases still work: qwen3-1.5b, qwen3-3b, gemma3-3b
```

You can download (or re-download) later without re-running the wizard:

```bash
make download-model
# force refresh:
./scripts/download-model.sh --force
```

Gated Gemma repos still need:

```bash
hf auth login
```

### llama-server

`make dev-api` / `make ensure-llm` auto-start a managed `llama-server` only when:

- a CUDA/ROCm GPU is detected,
- the GGUF exists under `data/models/`, and
- `llama-server` is on `PATH` (or `LLAMA_SERVER` points to the binary).

**Fedora (recommended):**

```bash
sudo dnf install llama-cpp
# provides /usr/bin/llama-server
command -v llama-server
make ensure-llm
```

Other options: install [llama.cpp](https://github.com/ggerganov/llama.cpp) from source or a pre-built release, then ensure `llama-server` is on `PATH` (or set `LLAMA_SERVER=/path/to/llama-server`).

## PostgreSQL (optional)

Start PostgreSQL with pgvector:

```bash
make podman-up
```

Then set in `.env`:

```
DATABASE_URL=postgresql+psycopg://prompt_piper:prompt_piper@localhost:5432/prompt_piper
```

## Development commands

```bash
make test       # pytest
make lint       # ruff check
make typecheck  # mypy
make format     # ruff format + fix
```

## Manual backend setup

```bash
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn prompt_piper_api.main:app --reload
```

## Manual frontend setup

```bash
cd apps/web
npm install
npm run dev
```

## Container builds (Podman)

Full local stack:

```bash
./scripts/dev-up.sh
```

See [README](../README.md#podman-setup-local-first-no-cloud) for Fedora setup, volumes, and troubleshooting.

### Persistent install (Quadlet + systemd)

Boot-persistent installs build images, run tests, install user Quadlets, enable linger, wait for API health, and open the default browser:

```bash
make persistent-install-cpu
make persistent-install-ai
./scripts/persistent-install.sh ai --preset qwen3-4b
```

| Mode | `.env` | Compose |
|------|--------|---------|
| CPU | `cpu-only` | api + web + postgres |
| AI | `podman:<preset>` + GGUF under `data/models/model.gguf` | adds `llama` profile |

Useful overrides: `SKIP_TESTS=1`, `SKIP_BROWSER=1`, `SKIP_BUILD=1` (after loading an offline image archive).

### Offline image export

```bash
make export
./scripts/export-images.sh --with-ai
# On disconnected host:
podman load -i dist/prompt-piper-images-....tar
SKIP_BUILD=1 make persistent-install-cpu
```

Postgres only:

```bash
podman compose -f infra/compose.yaml up -d
./scripts/init-db.sh   # after full stack is up; for postgres-only, run psql manually
```

Manual image builds:

```bash
podman build -f infra/Containerfile.api -t prompt-piper-api .
podman build -f infra/Containerfile.web -t prompt-piper-web .
```

Container environment reference: `infra/env.podman.example`.
