<p align="center">
  <img src="assets/logo/logo.png" alt="Nautilius Prompting Workbench" width="280" />
</p>

Local-first **long-horizon coding-agent** prompting workbench. Design, clarify, edit, finalize, optimize for clarity, store, and retrieve agent contracts on your machine. Only a user-approved final prompt may be sent to an external model, and only when you explicitly choose to.

### Workflow highlights

- **16-question agent contract** — definition of done, change scope, architecture, discovery, execution, validation, failure recovery, autonomy, persistent `.agent/` memory, completion evidence, budget, tool safety, context compaction, rollback, escalation, and dependency security. Conservative defaults are one click away.
- **Clarity-first optimization** — expand and deconflict operational rules instead of compressing for token cost. Long-horizon prompts are expected to be large.
- **Dual export** — rendered `canonical_prompt` / `optimized_prompt` plus structured `coding_prompt_spec.json` and `.yaml`.
- **Persistent sessions** — progress survives browser refresh and API restarts (`SESSIONS_PATH`, default `./data/sessions/`). **Breaking schema note:** clear `./data/sessions/` after upgrading from the old six-dimension card format.
- **Rich clarification** — multi-select quick replies plus custom text; optional **Get model suggestions** per question (CPU-fast ranker by default).
- **Step navigation** — revisit earlier steps from the workflow stepper; **re-open** edit, similarity, or optimization when you need to change course mid-session.
- **Closed completed sessions** — exported sessions are read-only for audit; start a new session with **Use as template** from the Complete page.
- **Binding-aware approval** — the pre-inference gate scores optimized prompts against constraint-graph bindings (not every optional card field), and the optimizer preserves those bindings while expanding for clarity.
- **Semantic precision** — regex scoring for vague language on the Optimize step; **Refine precision** merges WordNet/glossary with an optional semantic vector index, then reranks with the local model when available.
- **Send to model after export** — on the Complete page, optionally run the approved optimized prompt through the local or external model API; responses are saved as `inference_response.txt` beside other artifacts.
- **Native dev ergonomics** — `make dev-api` probes GPU availability and can auto-start a local llama.cpp server; Vite proxies session API routes correctly during dev.

See [User workflow](docs/user-workflow.md) for step-by-step API details.

## Monorepo layout

Each top-level folder has a **README** describing its files and how they fit together.

| Path | Purpose | Folder guide |
|------|---------|--------------|
| [`assets/`](assets/README.md) | Brand logos and shared static artwork | logos, favicon |
| [`apps/`](apps/README.md) | API + web applications | runnable packages |
| [`packages/`](packages/README.md) | Shared TypeScript types | `@prompt-piper/shared` |
| [`data/`](data/README.md) | Runtime storage (sessions, registry, exports) | local-only data |
| [`infra/`](infra/README.md) | Podman images and compose | containers, nginx, DB init |
| [`scripts/`](scripts/README.md) | Dev and deploy shell helpers | `make` targets |
| [`docs/`](docs/README.md) | Architecture and workflow guides | design docs |
| [`tests/`](tests/README.md) | pytest suite | backend tests |
| [`demo/`](demo/README.md) | Demo scenario fixtures | `make demo` input |
| `~/Documents/Nautilius` | Host export root (registry, exports, audit) | production-style paths on Fedora |

## Quick start (native dev)

**Prerequisites:** Python 3.12+, Node.js 20+, Make  
**For local SLM:** NVIDIA/AMD GPU drivers, [`llama-server`](https://github.com/ggerganov/llama.cpp) on `PATH`, and a GGUF under `data/models/`

Run all commands from the **Nautilius Prompting Workbench repo root**.

```bash
# 1) Environment + Python/Node/WordNet deps
cp .env.example .env
make install

# 2) Choose CPU-only or a local SLM (Gemma / Qwen / custom).
#    For SLM presets, setup installs hf tooling, offers to download the GGUF,
#    and checks for llama-server.
make setup

# 3) If you skipped the download prompt (or need to re-fetch):
make download-model

# Optional: full semantic vector index (~20–60 min CPU; skipped if already built)
make setup-lexicon-all
```

On **low-VRAM GPUs** (e.g. GTX 1050 2GB), `build-lexicon-index` forces CPU embedding (`CUDA_VISIBLE_DEVICES=`) so it does not compete with llama.cpp on the GPU. Runtime vector search also uses CPU unless you have headroom; the local model still reranks candidates on GPU when healthy.

Run the API and web app in separate terminals (from a host shell where `nvidia-smi` / `rocm-smi` works):

```bash
# Terminal 1 — FastAPI on :8010 (not PromptPiper's :8000); ensure_llm starts llama-server when GPU + GGUF + binary exist
make ensure-llm   # optional dry-run of the GPU/model probe
make dev-api

# Terminal 2 — Vite dev server on :5174; proxies API routes to :8010
make dev-web
```

Stop both terminals, the managed local model, and any Podman/Quadlet stack from a third shell:

```bash
make shutdown
```

Sessions are written to `./data/sessions/` by default, so you can refresh the browser or restart the API without losing in-progress work. Completed (`exported`) sessions stay immutable; use **Use as template** on the Complete page to iterate in a new session.

Verify the API:

```bash
# Confirm API is listening
curl http://127.0.0.1:8010/health

# Run backend + integration tests
make test
```

## Fedora setup

Nautilius Prompting Workbench is developed and tested on Fedora first. Install native dev tools:

```bash
# Python 3.12, Node, build tools, Podman
sudo dnf install python3.12 python3.12-devel nodejs npm make git \
  podman podman-compose

# Local SLM server used by make ensure-llm / make dev-api
sudo dnf install llama-cpp

# Optional: HTML/PDF export when running API natively (not in container)
sudo dnf install pandoc
pip install weasyprint   # run inside apps/api/.venv
```

For PDF/HTML export inside Podman, dependencies are pre-installed in `infra/Containerfile.api`.

## Podman setup (Fedora, local-first, no cloud)

Nautilius Prompting Workbench runs entirely through Podman containers. No Docker Desktop, Kubernetes, or cloud services are required for v1.

### Quick start on Fedora

```bash
# Create host export directory for registry + artifacts
mkdir -p ~/Documents/Nautilius

# First-time environment (skip if .env already exists)
cp .env.example .env

# Build images and start web + API + Postgres
podman compose -f infra/podman-compose.yml up --build
```

Then:

1. Open the frontend at http://127.0.0.1:5174
2. Create a prompt session and walk through clarify → edit → finalize → similarity → optimize → approve → export → complete
3. Use the workflow stepper to review earlier steps; re-open a step if you need to revise before completion
4. Export artifacts from the session; on **Complete**, optionally **Send to model** to run the optimized prompt
5. Confirm files appear under `~/Documents/Nautilius/exports/` in a unique timestamped folder

Or use the helper script (creates directories and starts the stack):

```bash
# Wrapper: creates dirs, runs podman compose (same as make podman-up)
./scripts/dev-up.sh
```

Services:

| Service  | URL / port              | Image                          |
|----------|-------------------------|--------------------------------|
| Web UI   | http://127.0.0.1:5174   | nginx (built from `Containerfile.web`) |
| API      | http://127.0.0.1:8010   | python:3.12-slim (built from `Containerfile.api`) |
| Postgres | localhost:5432          | `pgvector/pgvector:pg16`       |
| llama (optional) | localhost:8080  | `llama.cpp` server (`--profile llama`) |
| worker (optional) | —              | placeholder worker (`--profile worker`) |

Stop and view logs:

```bash
# Stop all compose services
./scripts/dev-down.sh

# Follow logs for every service, or one service (api, web, postgres, …)
./scripts/dev-logs.sh
./scripts/dev-logs.sh api
```

### Volume mounts

| Host path                         | Container path | Purpose                    |
|-----------------------------------|----------------|----------------------------|
| `~/Documents/Nautilius`         | `/exports`     | Registry, exports, audit   |
| `~/Documents/Nautilius/exports` | `/exports/exports` | Unique artifact folders |
| `~/Documents/Nautilius/registry`| `/exports/registry` | Local prompt registry  |
| `data/model-cache`                | `/models`      | Embedding model cache      |
| `data/postgres`                   | `/var/lib/postgresql/data` | PostgreSQL files |

Native dev also stores sessions under `./data/sessions/` (`SESSIONS_PATH`); Podman compose does not mount this yet — see **Remaining / planned**.

Bind mounts use the `:Z` flag for rootless Podman on Fedora (SELinux).

### Boot-time persistence (Quadlet)

To run Nautilius Prompting Workbench as user systemd services that start at login/boot:

```bash
# Full install: deps + build + tests + Quadlets + open browser
make persistent-install-cpu   # rule-based / CPU-only
make persistent-install-ai    # local SLM (compose llama profile; default qwen3-1.7b)

# Or install units only, then follow printed build/enable steps
./scripts/install-quadlets.sh --method compose

# Keep user services running after logout (optional; persistent-install enables this)
loginctl enable-linger "$USER"
```

See [infra/quadlets/README.md](infra/quadlets/README.md) for compose vs individual container units, build steps, and troubleshooting.

### Offline image export

Build API + web images (plus Postgres base) and save a single archive for disconnected hosts:

```bash
make export
# Include llama.cpp server image as well:
./scripts/export-images.sh --with-ai

# On the target machine:
podman load -i dist/prompt-piper-images-....tar
SKIP_BUILD=1 make persistent-install-cpu   # or persistent-install-ai
```

Each export creates a new folder:

`~/Documents/Nautilius/exports/YYYY-MM-DD_HH-MM-SS__{prompt_id}__{safe_slug}/`

Existing folders are never overwritten; collisions append `__export_002`, `__export_003`, and so on.

### Environment variables

Copy `.env.example` to `.env` at the repo root. For container-specific defaults see `infra/env.podman.example`.

| Variable | Default (native) | Podman notes |
|----------|------------------|--------------|
| `PROMPT_PIPER_EXPORT_ROOT` | `~/Documents/Nautilius` | `/exports` in API container |
| `PROMPT_PIPER_HOST_EXPORT_ROOT` | `~/Documents/Nautilius` | Host path recorded in manifests |
| `PROMPT_PIPER_REGISTRY_ROOT` | `{export_root}/registry` | Local prompt registry |
| `PROMPT_PIPER_ARTIFACT_ROOT` | `{export_root}/exports` | Unique export folders |
| `SESSIONS_PATH` | `./data/sessions` | JSON session store (survives API restart) |
| `PROMPT_PIPER_MODEL_CACHE` | `./data/model-cache` | `/models` in API container |
| `DATABASE_URL` | SQLite file | Overridden to PostgreSQL in `podman-compose.yml` |
| `HF_HOME` / `TRANSFORMERS_CACHE` | — | `/models` (embedding downloads) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `prompt_piper` | Postgres container |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8010` | Browser → API (build arg for web image) |
| `PROMPT_PIPER_LOCAL_BASE_URL` | `http://127.0.0.1:8080/v1` | Use `http://host.containers.internal:8080/v1` in Podman |
| `PROMPT_PIPER_EXTERNAL_INFERENCE_ENABLED` | `false` | Keep `false` unless you explicitly opt in |
| `PROMPT_PIPER_EXTERNAL_API_KEY` | unset | **Never commit**; set only in `.env` |

Initialize or re-run database setup:

```bash
# Verify pgvector and create application tables
./scripts/init-db.sh
```

Postgres-only (without API/web containers):

```bash
# Database container only — pair with native make dev-api
podman compose -f infra/compose.yaml up -d
```

### Manual image builds

```bash
# API image (Python + pandoc + weasyprint)
podman build -f infra/Containerfile.api -t prompt-piper-api .

# Web image (nginx + static build)
podman build -f infra/Containerfile.web -t prompt-piper-web .
```

## Local model endpoint setup

Nautilius Prompting Workbench talks to an **OpenAI-compatible** server for clarification suggestions, draft generation, and optional chat. Clarification **ranking and extraction stay CPU-fast** unless you click **Get model suggestions** or your setup wizard enabled a local model.

`make dev-api` runs `ensure_llm`: it detects GPU memory, can start `llama-server` with a configured GGUF, or falls back to CPU-only mode (rule-based clarification). Stop a managed server with `make llama-down`, or stop the whole local app with `make shutdown`.

**Native dev** — in `.env`:

```env
# OpenAI-compatible local server (llama.cpp, vLLM, etc.)
PROMPT_PIPER_LOCAL_BASE_URL=http://127.0.0.1:8080/v1
PROMPT_PIPER_LOCAL_CHAT_MODEL=llama
PROMPT_PIPER_LOCAL_EMBED_MODEL=llama
```

Example llama.cpp server:

```bash
# Serve a GGUF on localhost:8080
./llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8080
```

**Podman stack** — the API container reaches the host via `host.containers.internal`:

```env
PROMPT_PIPER_LOCAL_BASE_URL=http://host.containers.internal:8080/v1
```

External inference remains **disabled by default** (`PROMPT_PIPER_EXTERNAL_ENABLED=false`). Sending a prompt to a model requires explicit user approval on the **Complete** page (local LLM when external inference is off, external provider when enabled).

## pgvector setup

The Podman stack uses `pgvector/pgvector:pg16`. On first start:

1. `infra/init-db.sql` enables the `vector` extension.
2. `./scripts/init-db.sh` verifies the extension and runs `init_db()` for application tables.

To use PostgreSQL from native dev (without full Podman stack):

```bash
# Start Postgres only for native API development
podman compose -f infra/compose.yaml up -d
```

Then in `.env`:

```env
# Point native API at containerized Postgres
DATABASE_URL=postgresql+psycopg://prompt_piper:prompt_piper@localhost:5432/prompt_piper
```

## Artifact generation dependencies

Artifact export uses Markdown as canonical source with optional conversions:

| Output | Tool | Native Fedora | API container |
|--------|------|---------------|---------------|
| TXT / MD / JSON / YAML | built-in | yes | yes |
| HTML | Pandoc (fallback: built-in HTML) | `dnf install pandoc` | included |
| PDF | WeasyPrint (fallback: Pandoc) | `pip install weasyprint` | included |

Missing tools produce **warnings**, not crashes. Export folders are created under `~/Documents/Nautilius/exports/` (or `PROMPT_PIPER_ARTIFACT_ROOT`); the built-in HTML fallback still produces a readable `optimized_prompt.html` when Pandoc is absent.

## Troubleshooting

### Podman / SELinux (Fedora)

If the API cannot write to `data/registry` or `data/artifacts`:

```bash
# Inspect SELinux labels on registry mount
ls -Z data/registry

# Restart stack to re-apply :Z volume contexts
./scripts/dev-down.sh && ./scripts/dev-up.sh
```

Ensure compose bind mounts keep the `:Z` suffix (already set in `infra/podman-compose.yml`).

### `host.containers.internal` unreachable

If the API container cannot reach your local model:

1. Confirm the model server listens on `127.0.0.1:8080` on the host.
2. Set `PROMPT_PIPER_LOCAL_BASE_URL=http://host.containers.internal:8080/v1` in `.env`.
3. Restart: `./scripts/dev-down.sh && ./scripts/dev-up.sh`.

On older Podman versions, try adding to `infra/podman-compose.yml` under `api`:

```yaml
# Under the api: service in infra/podman-compose.yml
extra_hosts:
  - "host.docker.internal:host-gateway"   # map host gateway for older Podman
```

and use `http://host.docker.internal:8080/v1`.

### PostgreSQL not ready

```bash
# Check Postgres container logs
./scripts/dev-logs.sh postgres

# Re-run extension + table bootstrap
./scripts/init-db.sh
```

If `data/postgres` has stale data from a failed init, stop containers and remove the directory **only if you accept data loss**:

```bash
./scripts/dev-down.sh
rm -rf data/postgres/*    # destructive — only if you accept losing DB data
./scripts/dev-up.sh
```

### Embedding model download slow or failing

Models cache under `data/model-cache`. Ensure the directory is writable and you have disk space. First similarity search after startup may download `PROMPT_PIPER_EMBEDDING_MODEL` (default: `BAAI/bge-small-en-v1.5`).

### Web UI cannot reach API

**Native dev:** Vite proxies `/health`, `/sessions`, `/registry`, and `/settings` to the API — keep `make dev-api` running on port 8010. Session workflow URLs (e.g. `/sessions/{id}/edit`, `/sessions/{id}/precision`) are routed to the SPA; matching API paths are never served as `index.html`.

**Podman:** `VITE_API_BASE_URL` is baked in at **web image build time**. It must be a URL your **browser** can open (typically `http://127.0.0.1:8010`). After changing it, rebuild:

```bash
./scripts/dev-down.sh
podman compose -f infra/podman-compose.yml build web   # rebake VITE_API_BASE_URL
./scripts/dev-up.sh
```

### Port already in use

Change host ports in `infra/podman-compose.yml` (e.g. `127.0.0.1:8001:8000`) and update `VITE_API_BASE_URL` accordingly.

## Documentation

Design guides in [`docs/`](docs/README.md):

- [Architecture](docs/architecture.md)
- [User workflow](docs/user-workflow.md)
- [Developer guide](docs/developer-guide.md)
- [Local setup](docs/local-setup.md)
- [Privacy model](docs/privacy-model.md)
- [Registry format](docs/registry-format.md)

Folder READMEs under `apps/`, `data/`, `infra/`, etc. document **where code and runtime files live**.

## Development

```bash
make test         # pytest — backend and integration
make lint         # ruff check
make typecheck    # mypy on API package
make format       # ruff format
make eval         # pre-inference quality gate regression suite
make ensure-llm   # GPU probe + llama-server (also runs via dev-api)
make llama-down   # stop Nautilius-managed llama-server
make shutdown     # stop API, Vite, llama-server, Podman compose, and Quadlets
```

## Worker container

No separate worker is required for v1. Background tasks (embedding index, artifact generation, registry writes) run inside the API process. If long-running jobs are added later, a `Containerfile.worker` can be introduced.

## Status

Use this checklist to verify a local install. All commands run from the repo root.

| Area | Status | Verify |
|------|--------|--------|
| Clarification loop + multi-select answers | Done | `test_clarification_loop.py`, UI clarify page |
| On-demand clarification model suggestions | Done | `test_clarification_suggestions.py` |
| Persistent session storage (JSON) | Done | `test_session_persistence.py`, `SESSIONS_PATH` |
| Workflow step navigation + re-open steps | Done | `test_workflow_reopen.py`, workflow stepper UI |
| Completed sessions + template flow | Done | `test_workflow_reopen.py`, Complete page |
| Draft editing + versioning | Done | `test_draft_edit.py` |
| Registry finalization (local files) | Done | `test_registry_finalize.py` |
| Similarity index + warnings | Done | `test_similarity_search.py` |
| Token optimizer + binding-aware quality gate | Done | `test_token_optimizer.py`, `test_optimization_binding.py`, `test_quality_gate.py` |
| Semantic requirement capture scoring | Done | `test_requirement_capture.py` |
| Semantic precision (regex + optional LLM refinement) | Done | `test_semantic_precision.py`, Optimize + Precision UI |
| CPU WordNet precision suggestions | Done | `test_wordnet_lexicon.py`, `make setup-lexicon` |
| Semantic vector precision index | Done | `test_lexicon_vector_index.py`, `make build-lexicon-index` |
| Versioned artifact export | Done | `test_artifacts.py`, `test_hardening.py` |
| Send to model (local or external) + audit | Done | `test_external_inference.py`, Complete page UI |
| GPU / llama auto-start (native dev) | Done | `test_ensure_llm.py`, `make dev-api` |
| Structured API errors | Done | `test_hardening.py` |
| Path / prompt ID sanitization | Done | `test_hardening.py` |
| Web workflow UI | Done | `make test-web` |
| Local demo flow | Done | `make demo` |
| Podman stack | Done | `make podman-up` |

```bash
make test          # backend + integration (pytest)
make test-web      # frontend unit tests (vitest)
make lint          # ruff
make typecheck     # mypy
make build-web     # production Vite build
make demo          # end-to-end coding-prompt demo (demo/coding_prompt.yaml)
```

### Remaining / planned

- Session DB migration from file store to Postgres for multi-user deployments
- CI workflow file (run checks above on push)
- Podman volume mount for `SESSIONS_PATH` in compose (native dev uses `./data/sessions` today)
