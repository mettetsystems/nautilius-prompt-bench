# Hardware-aware model setup and quick rebuild

Open **Settings → Scan GPU capabilities**, or run `make hardware-scan`.
The scan reports every visible NVIDIA/ROCm GPU, total/free VRAM, and available
system RAM. It recommends using the single device with the most free memory;
separate GPUs are never assumed to pool VRAM. Missing drivers, unavailable device
access, or unknown memory produce conservative recommendations. Containers only
see their assigned devices: run the CLI on the host for a complete scan.

`make setup` presents three local choices and one remote choice:

| Tier | Recommended model | Planning allowance at modest context |
| --- | --- | --- |
| Low / no GPU, 1B–2B | Qwen3 1.7B Q8_0 | 4 GiB free VRAM and 8 GiB available RAM; CPU inference with 8 GiB available RAM when GPU memory is insufficient |
| Mid, 7B–16B | Qwen3 8B Q4_K_M; Qwen3 14B Q4_K_M when more memory is free | 8B: 6 GiB free VRAM / 12 GiB available RAM; 14B: 16 GiB free VRAM / 16 GiB available RAM |
| High, 17B+ | DeepSeek-R1-Distill-Qwen-32B Q4_K_M | 24 GiB free VRAM / 32 GiB available RAM |
| Remote | Your OpenAI-compatible endpoint and model ID | No local model VRAM required; requests leave this machine |

These ranges describe model parameter counts, not VRAM sizes. Quantization,
context length, backend buffers, and other running programs affect fit. The
1.7B option favors speed and low resource use; 8B/14B provide a middle ground;
32B reasoning can take tens of seconds to minutes. These are planning estimates,
not speed benchmarks. The advanced catalog and model-free rule-based mode remain
available. The remote option disables local model autostart and works without a GPU.

The existing dedicated clarification-model endpoint remains separately configurable.
Neither scanning nor saving model-source preferences loads a model.

Model sources checked:
[official Qwen 1.7B GGUF](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF),
[official Qwen 8B GGUF](https://huggingface.co/Qwen/Qwen3-8B-GGUF),
[official Qwen 14B GGUF](https://huggingface.co/Qwen/Qwen3-14B-GGUF), and
[community DeepSeek 32B GGUF](https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF).
DeepSeek's Q4_K_M conversion is about 19.85 GB; Qwen 14B Q4_K_M is about 9 GB.

## Hugging Face token and local repositories

Settings includes a masked **Hugging Face token** field and a **Local model
repository or GGUF file** field. Setup offers these inputs too. The optional token
is stored in `data/model-source.json` with owner-only permissions, excluded from
Git, and never returned by the settings API. Blank token input preserves the saved
token; **Remove saved token** clears it. The token is passed directly to the Hugging
Face download API, not in shell command arguments. Without it, existing Hugging
Face authentication still works.

After choosing a local tier in setup, choose **Hugging Face download** or **Import
from local repository/folder**. A local repository can be a GGUF file, a directory
of models, or a local Hugging Face cache/repository containing materialized GGUFs.
The wizard finds the recommended filename recursively; if necessary, it asks you
to select a file. Unmaterialized Git LFS pointers and non-GGUF weights are rejected.
It does not convert Safetensors or clone a remote Git repository.

Local models are copied into `data/models/` by the model-import step. The original
file is preserved. Imports check free disk space and use a temporary file plus
atomic replacement, so an interrupted copy does not leave a partial target.
The selected local file is checked against available RAM/VRAM before configuration.
`make download-model` also handles local imports. Paths must be visible to the
process doing the import; mount the repository into a container when applicable.
A missing selected model will not silently load a different older model.

## Quick rebuild after changing hardware

From the repository root:

```bash
./scripts/rebuild-hardware.sh
# Equivalent:
make rebuild-hardware
```

The script rescans hardware, creates a private timestamped `.env.hardware-*.bak`,
opens the model-selection menu, clears stale `.env` GPU visibility/context/layer
settings, probes embedding support, and rebuilds the web application. It preserves
sessions, exports, downloaded weights, and the existing lexicon index. It does not
download or start chat models and does not replace GPU drivers or CUDA/ROCm toolkits.
Restart the API/web processes after completion to apply the configuration. Stop old
model servers before starting replacements.

Useful variants:

```bash
./scripts/rebuild-hardware.sh --scan-only          # read-only; no writes or builds
./scripts/rebuild-hardware.sh --skip-build         # configuration and embedding refresh
./scripts/rebuild-hardware.sh --non-interactive cpu-only
./scripts/rebuild-hardware.sh --containers         # build Podman images; no restart
./scripts/rebuild-hardware.sh --llama-source /path/to/llama.cpp
```

The optional llama.cpp build uses an existing source checkout, a fresh CMake cache
(CMake 3.24+), and CUDA/HIP/CPU selection from the scan. It builds only `llama-server`
with two build jobs and records the new binary path in `.env`. The matching compiler,
drivers and development toolkit must already be installed. This matters when a
binary built for the old GPU does not support the replacement hardware. Current
[llama.cpp build guidance](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
describes the required toolchains. No source checkout is downloaded automatically.
Unset inherited shell GPU visibility overrides too if they refer to removed devices;
the script only resets overrides stored in `.env`.
