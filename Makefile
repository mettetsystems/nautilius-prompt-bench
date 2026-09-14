.PHONY: help install install-api install-web setup setup-lexicon setup-lexicon-embed build-lexicon-index setup-lexicon-all setup-model-deps download-model ensure-llm llama-down shutdown stop dev dev-api dev-web test lint typecheck format clean demo eval eval-assistive podman-up podman-down podman-logs podman-init-db persistent-install-cpu persistent-install-ai export wipe-registry

ROOT := $(CURDIR)
API_DIR := $(ROOT)/apps/api
WEB_DIR := $(ROOT)/apps/web
VENV := $(API_DIR)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

help:
	@echo "Nautilius Prompting Workbench — common tasks"
	@echo ""
	@echo "  make install           Install backend, frontend, and WordNet lexicon deps"
	@echo "  make setup             Interactive wizard + optional GGUF download + lexicon"
	@echo "  make setup-model-deps  Install hf (Hugging Face Hub CLI) into the API venv"
	@echo "  make download-model    Download the GGUF named in .env into data/models/"
	@echo "  make setup-lexicon     Download WordNet data for CPU precision suggestions"
	@echo "  make setup-lexicon-embed Install sentence-transformers for vector index"
	@echo "  make build-lexicon-index Build semantic precision vector index (CPU embed)"
	@echo "  make setup-lexicon-all WordNet + embeddings + index (skips index if present)"
	@echo "  make ensure-llm        Probe GPU and start llama-server, or fall back to CPU mode"
	@echo "  make llama-down        Stop Nautilius-managed llama-server"
	@echo "  make shutdown          Stop API, Vite, llama-server, Podman, and Quadlets"
	@echo "  make stop              Same as make shutdown"
	@echo "  make persistent-install-cpu  Quadlet+systemd CPU install (build, test, browser)"
	@echo "  make persistent-install-ai   Quadlet+systemd AI/SLM install (build, test, browser)"
	@echo "  make export            Build container images and save an offline .tar bundle"
	@echo "                         (add WITH_AI=1 to include llama.cpp server image)"
	@echo "  make dev               Reminders for running API + web (two terminals)"
	@echo "  make dev-api           Run FastAPI (auto-starts local SLM when GPU available)"
	@echo "  make dev-web           Run Vite dev server"
	@echo "  make test              Run backend and integration tests"
	@echo "  make eval              Run local pre-inference quality gate evals"
	@echo "  make eval-assistive    Run assistive extraction leaf-match evals"
	@echo "  make lint              Run ruff on backend"
	@echo "  make typecheck         Run mypy on backend"
	@echo "  make format            Format backend with ruff"
	@echo "  make demo              Run the coding-prompt local demo flow"
	@echo "  make podman-up         Start full Podman stack (postgres + api + web)"
	@echo "  make podman-down       Stop Podman stack"
	@echo "  make podman-logs       Follow Podman service logs"
	@echo "  make podman-init-db    Ensure pgvector + app tables"
	@echo "  make clean             Remove build artifacts and caches"
	@echo "  make wipe-registry     Delete local finalized prompts (add --sessions via script)"

install: install-api install-web setup-lexicon-embed setup-lexicon
	@echo ""
	@echo "Dependencies installed."
	@echo "Next (from repo root):"
	@echo "  make setup            # choose CPU-only or local SLM; offers GGUF download"
	@echo "  make download-model   # if you skipped download during setup"
	@echo "  make ensure-llm       # needs GPU + llama-server + GGUF in data/models/"
	@echo "  make dev-api && make dev-web"

setup:
	$(ROOT)/scripts/setup.sh

setup-lexicon:
	$(ROOT)/scripts/setup-lexicon.sh --wordnet-only

setup-lexicon-embed:
	$(ROOT)/scripts/setup-lexicon.sh --embed-only

build-lexicon-index:
	$(ROOT)/scripts/setup-lexicon.sh --index-only

setup-lexicon-all:
	$(ROOT)/scripts/setup-lexicon.sh

setup-model-deps:
	$(PIP) install -e "$(API_DIR)[setup]"

download-model:
	$(ROOT)/scripts/download-model.sh

install-api:
	cd $(API_DIR) && python3 -m venv --clear .venv
	$(PIP) install -e "$(API_DIR)[dev,lexicon]"

install-web:
	cd $(ROOT) && npm install

dev-api:
	$(ROOT)/scripts/dev-api.sh

ensure-llm:
	$(ROOT)/scripts/ensure-llm.sh

llama-down:
	$(ROOT)/scripts/ensure-llm.sh --stop

shutdown:
	$(ROOT)/scripts/shutdown.sh

stop: shutdown

dev-web:
	cd $(WEB_DIR) && npm run dev
	@echo "Web UI: http://127.0.0.1:5174 (requires 'make dev-api' in another terminal)"

dev:
	@echo "Run 'make dev-api' and 'make dev-web' in separate terminals."

test:
	cd $(ROOT) && $(PYTHON) -m pytest tests/ -v

test-web:
	cd $(WEB_DIR) && npm run test

build-web:
	cd $(WEB_DIR) && npm run build

lint:
	cd $(API_DIR) && $(VENV)/bin/ruff check prompt_piper_api prompt_piper ../../tests

typecheck:
	cd $(API_DIR) && $(VENV)/bin/mypy prompt_piper_api prompt_piper

eval:
	cd $(ROOT) && $(PYTHON) -m prompt_piper.eval run

eval-assistive:
	cd $(ROOT) && $(PYTHON) -m prompt_piper.eval.assistive

demo:
	cd $(ROOT) && $(PYTHON) -m prompt_piper.demo

format:
	cd $(API_DIR) && $(VENV)/bin/ruff format prompt_piper_api ../../tests
	cd $(API_DIR) && $(VENV)/bin/ruff check --fix prompt_piper_api ../../tests

podman-up:
	$(ROOT)/scripts/dev-up.sh

podman-down:
	$(ROOT)/scripts/dev-down.sh

podman-logs:
	$(ROOT)/scripts/dev-logs.sh

podman-init-db:
	$(ROOT)/scripts/init-db.sh

persistent-install-cpu:
	$(ROOT)/scripts/persistent-install.sh cpu

persistent-install-ai:
	$(ROOT)/scripts/persistent-install.sh ai

export:
	$(ROOT)/scripts/export-images.sh $(if $(WITH_AI),--with-ai,)

wipe-registry:
	$(ROOT)/scripts/wipe-registry.sh

clean:
	rm -rf $(API_DIR)/.venv $(WEB_DIR)/node_modules $(ROOT)/packages/shared/node_modules
	rm -rf $(API_DIR)/dist $(WEB_DIR)/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

.PHONY: hardware-scan rebuild-hardware
hardware-scan:
	$(PYTHON) -m prompt_piper.setup --hardware-scan

rebuild-hardware:
	$(ROOT)/scripts/rebuild-hardware.sh
