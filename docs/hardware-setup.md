# Hardware-aware model setup and quick rebuild

Open **Settings → Scan GPU capabilities**, or run `make hardware-scan`.
The scan reports every visible NVIDIA/ROCm GPU, total/free VRAM, and available
system RAM. It recommends using the single device with the most free memory;
separate GPUs are never assumed to pool VRAM. Missing drivers, unavailable device
access, or unknown memory produce conservative recommendations. Containers only
see their assigned devices: run the CLI on the host for a complete scan.

`make setup` prioritizes a software-specification workload: **32,768 total tokens,
including 8,192 output tokens, for one active request**. The remaining 24,576 input
tokens include system instructions, chat history, retrieved code, requirements and
the existing spec. Reasoning tokens also consume the output allowance when the
model emits them. Output is part of the context window, not an extra window.

The planner compares **weights + KV cache + runtime buffers + safety reserve**
against verified **free** VRAM. It budgets F16 K and V separately from weight
quantization, 1 GiB for runtime, and a safety reserve of the greater of 2 GiB or
15% of total device VRAM. Available system RAM must also pass the model's budget.
The CLI and Settings display each component; these are estimates, not measured
peak allocations or model-quality scores.

| Model | Weight allowance | F16 KV at 32K | Typical placement with this policy |
| --- | --- | --- | --- |
| Qwen3 1.7B Q8_0 | 1.8 GiB | 3.5 GiB | Light assistance or slow CPU fallback; not the recommended spec author |
| Qwen3 8B Q4_K_M | 4.8 GiB | 4.5 GiB | Mostly free 16 GiB GPU |
| Qwen3 14B Q4_K_M | 8.5 GiB | 5 GiB | Mostly free 24–32 GiB GPU |
| DeepSeek-R1-Distill-Qwen-32B Q4_K_M | 18.6 GiB | 8 GiB | Larger GPU, such as 48 GiB; a 32 GiB card fails the reserve policy |

The mid tier selects 14B only when the complete workload fits, otherwise 8B.
The highest eligible mid/high candidate is suggested; if neither qualifies,
remote is suggested and the light/CPU option remains available. Choosing remote
does not send requests or start a local server during setup. The remote provider
must support the desired context and output separately.

Standard local setup saves `PROMPT_PIPER_DEPLOYMENT_PROFILE=specification`.
The native launcher checks available resources again before launch, uses the
actual GGUF file size when larger than the catalog allowance, and fixes 32K
context, one slot, F16 cache, batch 512 / microbatch 128, and full GPU offload.
CPU fallback retains the context and requires enough available RAM. Insufficient
or unknown memory stops launch with an explanation; it never silently shrinks
the specification context or partially offloads the model. Conflicting context
or layer overrides are rejected. The local API client's default generation
allowance becomes 8K; explicit per-call limits and external overrides are separate.
Context shifting is disabled, so oversized requests must be shortened explicitly.
Readiness also checks the server's reported context and slot count, so a running
4K endpoint cannot pass merely by answering a short health-check prompt.

Existing installations and Advanced/non-interactive preset selection retain
`manual` deployment behavior until standard setup selects the specification
profile. Advanced catalog size tiers are not a 32K fit check. Automatic budgeting
supports the four listed catalog artifacts and their filenames; arbitrary imports
need a manual architecture/cache assessment. A filename is an estimate of model
identity, not a provenance check. Renaming a different model does not validate it.
The optional Compose llama service and separately managed remote/clarification
endpoints do not use the native launch guard; configure their context, slots,
cache and memory limits explicitly before using them for this workload.

Run one model at a time on the selected GPU. A second resident model needs its
own weight/cache budget; current free VRAM already excludes existing allocations.
Keep embeddings on CPU unless they have a separate allowance. Do not count memory
on another GPU as additional capacity for this deployment.

Before relying on the model, test a representative spec with close to 24K input
tokens and an 8K generation allowance. Record peak memory, prompt-processing time,
generation speed, truncation and failures. Check requirements coverage, consistent
interfaces, explicit acceptance tests, dependencies, migration/rollback plans and
whether the model preserves constraints through revisions. Memory fit alone does
not establish that a model can produce a reliable software spec. For long-horizon
coding, keep the spec, decisions and progress checkpoints in durable files and
retrieve relevant sections rather than growing the conversation indefinitely.

The existing dedicated clarification-model endpoint remains separately configurable.
Neither scanning nor saving model-source preferences loads a model.

Model sources checked:
[official Qwen 1.7B GGUF](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF),
[official Qwen 8B GGUF](https://huggingface.co/Qwen/Qwen3-8B-GGUF),
[official Qwen 14B GGUF](https://huggingface.co/Qwen/Qwen3-14B-GGUF), and
[community DeepSeek 32B GGUF](https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF).
DeepSeek's Q4_K_M conversion is about 19.85 GB; Qwen 14B Q4_K_M is about 9 GB.
KV estimates use `2 × layers × KV heads × head dimension × 2 bytes × total tokens`
per active request. Upstream architecture sources:
[Qwen3 1.7B](https://huggingface.co/Qwen/Qwen3-1.7B/blob/main/config.json),
[Qwen3 8B](https://huggingface.co/Qwen/Qwen3-8B/blob/main/config.json),
[Qwen3 14B](https://huggingface.co/Qwen/Qwen3-14B/blob/main/config.json), and
[DeepSeek 32B](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B/blob/main/config.json).
The Qwen policy caps automatic context at 32K; extending it needs separate model
and backend validation. See [llama.cpp server options](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)
for context, parallel slots, cache types and batching.

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
