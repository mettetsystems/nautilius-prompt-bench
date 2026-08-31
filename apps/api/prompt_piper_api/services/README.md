# Services (`services/`)

Business logic layer. Routes should delegate here rather than mutating domain objects directly.

## Core workflow

| Module | Role |
|--------|------|
| `session_service.py` | Session state machine — create, clarify, edit, finalize, optimize, approve, export, re-open, template, delete |
| `session_record.py` | Persisted aggregate — session + drafts + optimization/similarity results |
| `session_store.py` | `FileSessionStore` / in-memory store (`SESSIONS_PATH`) |
| `state_transitions.py` | Allowed actions per `SessionState` |

## Clarification and drafts

| Module | Role |
|--------|------|
| `requirement_card_extractor.py` | Parse initial request into task identity + agent contract |
| `clarification_question_ranker.py` | CPU-fast next-question selection (16 contract leaves) |
| `clarification_suggestion_service.py` | Optional LLM quick-reply suggestions |
| `draft_generator.py` | 17-section long-horizon contract after clarification |
| `draft_patch_service.py` | Apply natural-language edits to the card + draft |

## Quality, similarity, export

| Module | Role |
|--------|------|
| `similarity_check_service.py` | Local index search at finalize |
| `embedding_service.py` | Text embeddings for similarity and capture scoring |
| `requirement_capture.py` | Semantic requirement capture evaluator |
| `semantic_precision.py` | Regex vague-language detection and replacement helpers |
| `wordnet_lexicon.py` | Offline WordNet + glossary precision lookups |
| `precision_lexicon_service.py` | CPU-only precision suggestion orchestration |
| `precision_suggestion_service.py` | LLM suggestions with WordNet CPU fallback |
| `pre_inference_metrics_service.py` | Pre-inference metric bundle (includes `semantic_precision_score`) |
| `quality_gate_service.py` | Approval gate thresholds |
| `optimization/` | [Five-pass clarity-first optimizer](optimization/README.md) |
| `git_registry_service.py` | Local-directory canonical prompt registry |
| `artifact_export_service.py` | Timestamped export folders, coding specs, manifests |
| `artifact_service.py` | HTML/PDF/MD + coding_prompt_spec generation (Pandoc/WeasyPrint) |
| `external_inference_service.py` | Gated send-to-model (local LLM or external provider) with audit |
| `audit_log_service.py` | JSONL audit trail |

Supporting utilities: `path_safety.py`, `format_checker.py`, `regression_evaluator.py`, `logging_config.py`, `exceptions.py`.
