# Privacy model

Nautilius Prompting Workbench is designed so prompt content stays on your machine unless you take an explicit, gated action to send an approved optimized prompt to an external model.

## What stays local

| Data | Location | Sent externally? |
|------|----------|-------------------|
| Session state and draft versions | API process memory (v1) | Never |
| RequirementCard (task identity + 16-question agent contract) | Session + registry JSON / coding_prompt_spec | Never (unless you copy files) |
| Canonical prompt text | `data/registry/{prompt_id}/` | Never by default |
| Optimized prompt text | `data/artifacts/{prompt_id}/` | Only via explicit send-to-inference |
| Similarity embeddings | JSON index or local DB | Never |
| Embedding model weights | `data/model-cache/` | Downloaded once from Hugging Face if using local embeddings |
| Artifact exports | `data/artifacts/` | Never |
| Audit log | `data/audit/external_inference.jsonl` | Never |
| External inference responses | `data/artifacts/{prompt_id}/inference_response.txt` | Written locally after optional call |

Clarification, draft generation, clarity-first optimization, quality gating, similarity search, and artifact export run **entirely on the local API** with deterministic or locally hosted models.

The web UI communicates only with `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`).

## No external calls by default

Out of the box (`.env.example`):

```env
PROMPT_PIPER_EXTERNAL_ENABLED=false
REQUIRE_APPROVAL_BEFORE_EXTERNAL_CALL=true
PROMPT_PIPER_LLM_ENABLED=true
PROMPT_PIPER_LOCAL_BASE_URL=http://127.0.0.1:8080/v1
```

| Call type | Default behavior |
|-----------|------------------|
| External cloud LLM | **Disabled** — factory raises if requested without opt-in |
| Local LLM (clarification/drafts) | Points to localhost; falls back to rules if unreachable |
| Embeddings | Local sentence-transformers or hash fallback when configured |
| Pandoc / WeasyPrint | Local subprocess for HTML/PDF (optional) |
| Telemetry / analytics | **None** in the codebase |

There is no background sync, no automatic cloud backup, and no hidden model usage.

## When external inference is allowed

External inference is a **single optional step** after the full local workflow: finalize → optimize → approve → export.

Endpoint: `POST /sessions/{session_id}/send-to-inference`

Request body:

```json
{ "explicit_approval": true }
```

`ExternalInferenceService` enforces all of the following before calling the provider:

1. **`REQUIRE_APPROVAL_BEFORE_EXTERNAL_CALL`** is `true` (hard-coded policy in v1; setting it `false` fails settings validation).
2. **`explicit_approval`** is `true` in the request body.
3. **`PROMPT_PIPER_EXTERNAL_ENABLED`** is `true`.
4. Session has a **finalized, frozen canonical draft** with assigned `prompt_id`.
5. **Optimization is approved** (`optimization_result.approved == true`).
6. Session state is **`approval`** or **`exported`**.

What is transmitted on success:

- The **optimized prompt body** only (`optimization_result.optimized_body`) as a single user message to the configured external OpenAI-compatible API.
- Provider/model from `PROMPT_PIPER_EXTERNAL_BASE_URL`, `PROMPT_PIPER_EXTERNAL_CHAT_MODEL`, `PROMPT_PIPER_EXTERNAL_API_KEY`.

What is **not** sent:

- Raw initial user request (unless it remains in optimized text)
- Full clarification transcript
- Non-canonical draft versions
- RequirementCard / coding_prompt_spec as a separate payload
- Similarity index or registry metadata

Settings introspection: `GET /settings/inference` returns enabled flags without exposing API keys.

## Block reasons

When a call is blocked, the API returns HTTP 403 with `reason`:

| `block_reason` | Cause |
|----------------|-------|
| `approval_policy_violation` | Internal policy check failed |
| `explicit_approval_required` | Missing `explicit_approval: true` |
| `external_inference_disabled` | `PROMPT_PIPER_EXTERNAL_ENABLED=false` |
| `prompt_not_finalized` | No frozen canonical draft |
| `prompt_not_optimized` | Optimization not approved |
| `invalid_session_state` | State not `approval` or `exported` |

Every blocked attempt is logged locally (see below).

## Audit trail

All external inference attempts—blocked, successful, or errored—append one JSON line to:

```
data/audit/external_inference.jsonl
```

Implemented by `AuditLogService` (`services/audit_log_service.py`).

Event schema (`ExternalInferenceAuditEvent`):

```json
{
  "timestamp": "2026-06-15T22:40:00+00:00",
  "session_id": "59ffd96f-aec9-47fa-9f4b-e1d672a9b4fd",
  "prompt_id": "fastapi-user-create-coding-prompt-59ffd96f",
  "version": 3,
  "outcome": "blocked",
  "block_reason": "external_inference_disabled",
  "provider": null,
  "model": null,
  "explicit_approval": true,
  "artifact_location": null,
  "inference_response_artifact_path": null,
  "error_message": null
}
```

| `outcome` | Meaning |
|-----------|---------|
| `blocked` | Guardrail prevented the call |
| `success` | Response received; `inference_response.txt` written |
| `error` | Provider call failed; `error_message` set |

The audit log is append-only, local, and never uploaded. Read programmatically via `AuditLogService.read_external_inference_events()`.

## Pre-inference gate (export privacy)

Separate from external inference: **optimization approval** runs a local quality gate (`QualityGateService`) before artifacts can be exported. This ensures the optimized prompt still captures requirements and honestly marks unspecified fields—without calling any external model.

Failed gate → HTTP 409; no artifacts, no export, no inference.

## Secrets and registry

- Store `PROMPT_PIPER_EXTERNAL_API_KEY` and local API keys in `.env` (gitignored).
- Never commit secrets into `data/registry` prompt files.
- Pushing `data/registry` to a remote Git remote is a **user decision**; the workbench does not push automatically.

## Network assumptions

- CORS allows local dev origins on the API.
- Podman stack binds services to localhost; see [local-setup.md](local-setup.md) for `host.containers.internal` when the API container reaches a host-local LLM.
- Embedding model download requires network once unless models are pre-cached in `data/model-cache/`.

## Enabling external inference (explicit opt-in)

Only when you intentionally want cloud model execution on an approved prompt:

```env
PROMPT_PIPER_EXTERNAL_ENABLED=true
PROMPT_PIPER_EXTERNAL_API_KEY=sk-...
PROMPT_PIPER_EXTERNAL_BASE_URL=https://api.openai.com/v1
PROMPT_PIPER_EXTERNAL_CHAT_MODEL=gpt-4o-mini
```

Then call the API with `explicit_approval: true` after completing the local workflow. Review `data/audit/external_inference.jsonl` for a record of every attempt.

## Related docs

- [Architecture — privacy/export gate](architecture.md#privacy--export-gate)
- [User workflow — optional external inference](user-workflow.md#10-optional-external-inference)
