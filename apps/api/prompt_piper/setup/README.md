# Setup wizard (`prompt_piper/setup/`)

Configures local development: model paths, API URLs, CPU vs GPU mode. Writes repo-root `.env`.

| Module | Role |
|--------|------|
| `wizard.py` | Interactive prompts — catalog pick, custom endpoint, CPU-only |
| `catalog.py` | Known model presets (Gemma, Qwen, etc.) |
| `env_writer.py` | Merge answers into `.env` without clobbering secrets |
| `gpu_detect.py` | Detect NVIDIA GPU and VRAM for model sizing |
| `deployment_budget.py` | Specification workload budgets: weights, 32K context cache, runtime and reserve |
| `hardware.py` | Shared memory-aware recommendations for setup and Settings |
| `download_model.py` | Download GGUF from `.env` (`make download-model`) |
| `ensure_llm.py` | Entry for `make ensure-llm` / `dev-api.sh` — start or skip llama |
| `llama_launcher.py` | Spawn and health-check `llama-server` subprocess |
| `model_deps.py` | Optional Hugging Face download helpers |
| `lexicon_setup.py` | WordNet, sentence-transformers, vector index setup |
| `embedding_device.py` | GPU compatibility probe for embedding runtime device |

## Run

```bash
# From repo root
make setup              # model wizard + optional GGUF download + lexicon
make download-model     # re-fetch GGUF from .env into data/models/
make setup-lexicon-all  # WordNet + embeddings + vector index
```
