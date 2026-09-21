# Clarification: application requirements and optional model expansion

Clarification now collects application decisions before the existing operational
contract: project context, target environment, supported operating systems,
hosting, runtime versions, fixed versus open technology choices, development
machine, compatibility, installation and updates, storage, connectivity,
constraints, and observable acceptance criteria. Target requirements are separate
from development-machine details.

The question count is based on applicable decisions, not capped at 16. An
explicit **New application** skips existing-code compatibility; **Non-application
task** skips application deployment questions while preserving generic prompting.
Offline requirements reveal a synchronization follow-up. Uncertain applicability
is left open. Explicitly labeled intake lines such as `Supported Operating
Systems: Windows 11` are captured without asking the same question again.

**Unsure**, **Not applicable**, and **Recommend an option** remain literal answers.
Unanswered architecture, deployment, runtime, and acceptance decisions appear in
an advisory list before leaving clarification. Users can generate a draft with
open decisions; nothing chooses requirements for them. Additional model follow-up
questions can be answered in the custom answer or deliberately left open.

Choosing **Use receiving harness controls** skips scheduling/lifecycle, retry,
working-memory, budget, compaction, and rollback policy questions and delegates
those sections. Explicit existing policies are preserved. This suits MobyAI,
whose local README describes a deterministic harness owning state and retries,
and works with other harnesses too. Approval requirements and existing export
formats are unchanged. No integration or feedback loop was introduced.

## Editable model suggestions

Enter a short answer, choose **Current lightweight model** or **Dedicated large
clarification model**, then click **Get model suggestions**. The model receives
that answer, the initial request, and accepted card values. The panel separates:

- Your original answer and an editable proposed expansion.
- Recommendations and their tradeoffs, which are not requirements.
- Unconfirmed assumptions, conflicts, and consequential follow-up questions.

**Use edited proposal** copies text to the answer editor; **Submit answer** records
it. Reject discards the proposal; regenerate requests another. Conflicting model
responses cannot be adopted through the proposal button. Suggestions are advisory,
not a semantic guarantee: review before submission. No model response updates the
requirement card. Generation history is stored in the session for provenance;
old saved sessions default to an empty history and application-requirements object.
Manual answers remain available during generation and after model failure. Late
responses for a different question are ignored. Ask The Locals also waits for an
explicit **Use answer** action.

## Dedicated model setup

`make setup` now offers a separate clarification-model selection after the
existing lightweight-model setup. To configure only clarification, from the
repository root run:

```bash
apps/api/.venv/bin/python -m prompt_piper.setup --clarification-only
```

The large-model default is **DeepSeek-R1-Distill-Qwen-32B**, the precise name of the
requested DeepSeek R1 distilled 32B model. Other choices are **Qwen3-14B** or any
local OpenAI-compatible endpoint/model name. Lightweight-only remains available.
The wizard inspects detected GPU memory, writes only dedicated configuration,
and never downloads or starts the large model. Existing installations remain
opt-in until configured.

| Option | Weights | Planning allowance | Responsiveness |
| --- | --- | --- | --- |
| DeepSeek-R1-Distill-Qwen-32B Q4_K_M | Approximately 19.85 GB | Start with at least 24 GiB free VRAM and 32 GiB available RAM; context and buffers need additional space | Reasoning can take tens of seconds to minutes; not benchmarked here |
| Qwen3-14B Q4_K_M | Approximately 9 GB | Approximately 16 GiB free VRAM for a modest context | Generally lighter than 32B; hardware and answer length determine speed |
| Current lightweight model | Existing selected preset | Existing setup guidance | Lowest resource demand |

These are conservative planning estimates, not guaranteed allocations. Q4_K_M
uses roughly four-bit quantization with mixed precision; it trades some fidelity
for much lower memory than the approximately 64 GB of 16-bit 32B weights.
The model's advertised maximum context is not a promise that it fits in your VRAM.

On 2026-09-13 the host probe found an RTX 5090 with 32,130 MiB free out of 32,607
MiB, an RTX 2070 with 7,786 MiB free out of 8,192 MiB, and approximately 49 GiB
available system RAM. The 5090 is the appropriate device for 32B Q4 at a modest
context; the 2070 alone is insufficient. Resources change: recheck immediately
before loading, especially if the lightweight model or another application shares
the GPU. No 32B model was downloaded, launched, or benchmarked during this change.

Sources checked September 2026:
[DeepSeek model card](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B),
[community GGUF quantization and size table](https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF),
and [official Qwen 14B GGUF file](https://huggingface.co/Qwen/Qwen3-14B-GGUF/blob/main/Qwen3-14B-Q4_K_M.gguf).
The DeepSeek GGUF is a community conversion, not a DeepSeek-published binary.

### Starting your endpoint

Check `nvidia-smi` and `free -h` first. After confirming resources, an operator can
download the community GGUF with `hf download` and serve the file with a CUDA-enabled
llama.cpp build compatible with the GPU. For example:

```bash
hf download bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF \
  DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf --local-dir data/models
# Set CUDA_VISIBLE_DEVICES to the 5090's UUID from nvidia-smi, then:
llama-server -m data/models/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf \
  --alias DeepSeek-R1-Distill-Qwen-32B --host 127.0.0.1 --port 8081 -ngl 999 -c 8192
```

Start with a modest context and monitor memory. A long intake plus many accepted
answers may require a larger context or a shorter request; generation failure
keeps the manual answer intact. Stop this operator-managed process with Ctrl+C
when finished to release its GPU allocation. The header's existing Offload model
button controls only the application's managed primary model, not this separately
hosted endpoint.

The dedicated client reads:

```dotenv
PROMPT_PIPER_CLARIFICATION_ENABLED=true
PROMPT_PIPER_CLARIFICATION_MODEL=DeepSeek-R1-Distill-Qwen-32B
PROMPT_PIPER_CLARIFICATION_BASE_URL=http://127.0.0.1:8081/v1
PROMPT_PIPER_CLARIFICATION_TIMEOUT=180
```

Restart the API after changing configuration. For containerized APIs, use a
host-reachable URL instead of container loopback. The client uses temperature 0.6
and a 4,096-token generation budget. For DeepSeek R1 it places instructions in
the user message, following the model card guidance. It uses the existing OpenAI-compatible
adapter and JSON parsing/fallback path. Unreachable endpoints, malformed output,
and timeout failures offer manual clarification rather than applying a guess.

### Agent build environments

Environment intake separates the agent's actual machine (OS/version, architecture,
location and shell) from the application's target. Follow-up questions cover build
isolation, versioned toolchains, hardware and GPU backends, network/dependency
access, workspace persistence, reproducible setup and recovery, validation
infrastructure, and differences between build and deployment environments.
Project Permissions records user/sudo requirements separately. Credential questions
ask for secret variable or store names, never secret values. Each answer is retained
in the requirement card and generated prompt/spec exports. Unknown answers remain
explicit; old sessions receive empty defaults for the new fields.
