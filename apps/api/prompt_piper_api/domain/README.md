# Domain models (`domain/`)

Pure data types and enums for the Nautilius Prompting Workbench long-horizon coding-agent workflow. No I/O, no HTTP — safe to import from tests and services.

| Module | Contents |
|--------|----------|
| `session.py` | `PromptSession` — id, title, state, requirement card, prompt_id |
| `draft.py` | `PromptDraft` — versioned prompt text, canonical/frozen flags |
| `requirement_card.py` | Task identity + 16-question `AgentContract` + leaf helpers + OptimizationTargets |
| `agent_contract.py` | Clarification questions, recommended defaults, and option expansions |
| `harness.py` | Long-horizon contract section titles and system prompt |
| `enums.py` | `SessionState` — intake through exported |
| `optimization.py` | Constraint graph, metrics, `OptimizationResult` |
| `similarity.py` | Similarity check results and matches |
| `artifacts.py` | Export manifest and generation result |
| `pre_inference_metrics.py` | Quality gate scores (including semantic precision) |
| `precision.py` | Vague-language findings and precision review result |
| `audit.py` | Append-only audit event types |
| `inference.py` | Send-to-model result and external inference audit events |
| `registry.py` | Registry metadata shapes (`domain=coding`, task_family) |
| `limits.py` | Max string lengths and clarification caps |
| `errors.py` | API error codes (e.g. `invalid_state`) |
| `edit_intent.py` | Classified edit instruction intents |

These models are the contract between clarification, draft generation, optimization, and dual export (rendered prompt + coding_prompt_spec).
