# Registry format

The prompt registry is a **local file-based store** on this installation under `REGISTRY_PATH` (default `./data/registry`). Each finalized coding prompt occupies one directory. The registry is the source of truth for canonical prompt text; `data/artifacts/` holds generated exports that reference registry content.

## Directory layout

```
data/registry/
  {prompt_id}/
    metadata.yaml
    canonical_prompt.txt
    canonical_prompt.md
    requirement_card.json
    coding_prompt_spec.json
    coding_prompt_spec.yaml
    lineage.json
```

`prompt_id` format: `{slug-from-title}-{session_uuid_prefix}` (e.g. `fastapi-user-create-coding-prompt-59ffd96f`).

There is **no nested `versions/` folder** in v1. Version number is stored in `metadata.yaml` and matches the session draft version at finalize time. Re-finalizing the same session with a new draft version overwrites files in the same directory and increments `metadata.yaml` version.

## `metadata.yaml`

Written by `GitRegistryService.finalize_prompt()`. Schema: `RegistryMetadata` (`domain/registry.py`).

```yaml
prompt_id: fastapi-user-create-coding-prompt-59ffd96f
version: 3
title: FastAPI user-create coding prompt
abstract: Implement a FastAPI + Pydantic POST /users endpoint with typed JSON and pytest coverage.
tags: []
domain: coding
task_family: new feature logic
output_form: TypeScript-style interface plus FastAPI handler with pytest
target_provider: ''
target_model: ''
preferred_prompt_length: ''
evaluation_scores:
  requirement_capture_score: 1.0
  unspecified_field_honesty: 1.0
  instruction_clarity: 0.55
  format_adherence: 1.0
  richness_score: 1.0
  density_score: 1.0
  efficiency_score: 0.922
  denoising_score: 0.8
  deconfliction_score: 1.0
artifact_paths:
  metadata: metadata.yaml
  canonical_md: canonical_prompt.md
  canonical_txt: canonical_prompt.txt
  requirement_card: requirement_card.json
  coding_prompt_spec_json: coding_prompt_spec.json
  coding_prompt_spec_yaml: coding_prompt_spec.yaml
  lineage: lineage.json
  optimized_md: optimized_prompt.md
  optimized_txt: optimized_prompt.txt
  metrics: metrics.json
  similarity_report: similarity_report.json
  lessons_learned: lessons_learned.md
  manifest: artifact_manifest.json
  optimized_html: optimized_prompt.html
  optimized_pdf: optimized_prompt.pdf
created_at: '2026-06-15T22:36:15.679629+00:00'
updated_at: '2026-06-15T22:36:15.746106+00:00'
```

| Field | Description |
|-------|-------------|
| `prompt_id` | Stable directory name and API identifier |
| `version` | Draft version at finalize/artifact time (integer ≥ 1) |
| `title` | Human-readable session title |
| `abstract` | Short summary; defaults to truncated `task_identity.objective` |
| `tags`, `domain`, `task_family` | Taxonomy; finalize sets `domain=coding` and `task_family` from `task_identity.task_type` |
| `output_form` | From `agent_contract.completion_contract` on RequirementCard |
| `target_provider`, `target_model` | Optional dispatch hints (not auto-populated) |
| `preferred_prompt_length` | Optional length guidance |
| `evaluation_scores` | Pre-inference and optimization metrics after artifact export |
| `artifact_paths` | Map of logical name → filename (registry-relative or artifact dir) |
| `created_at`, `updated_at` | ISO 8601 UTC timestamps |

Initial finalize writes registry-only paths. After artifact generation, `GitRegistryService.update_artifact_paths()` merges export filenames and evaluation scores and updates `updated_at`.

## `canonical_prompt.txt`

The frozen plain-text coding prompt body exactly as approved at finalization. This is the authoritative text for:

- Similarity indexing (canonical document kind)
- Clarity-first optimization input (`original_body`)
- Canonical columns in artifact exports

Format: plain text with Task Identity plus sixteen operational-control section labels and underline dividers (see `DraftGenerator`). Not Markdown syntax in the body itself.

Expected section titles:

1. Task Identity
2. Definition of Done
3. Change Scope
4. Architecture Policy
5. Discovery Policy
6. Execution Strategy
7. Validation Strategy
8. Failure Recovery
9. Autonomy Policy
10. Persistent Agent Memory
11. Completion Contract
12. Resource and Budget Governance
13. Tool Safety and Shell Restrictions
14. Context Compaction and State Persistence
15. Rollback and Backtracking
16. Escalation and HITL Interruption
17. Dependency and Security Verification

## `canonical_prompt.md`

Same body with an optional Markdown title prefix:

```markdown
# {title}

{body}
```

Used for human review and Pandoc-based HTML/PDF export of the canonical version.

## `requirement_card.json`

JSON serialization of the nested coding `RequirementCard` at finalize time (`model_dump_json(indent=2)`). Includes `unresolved_fields` (dotted leaf paths such as `agent_contract.change_scope`) as they stood when the canonical draft was frozen.

Also copied to the artifact directory during export.

## `coding_prompt_spec.json` / `coding_prompt_spec.yaml`

Structured coding-prompt spec: `task_identity` plus the 16-question `agent_contract` and `optimization_targets`, without `unresolved_fields`. Written at registry finalize and again on artifact export for programmatic reuse alongside the rendered prompt body.

Example shape:

```yaml
task_identity:
  objective: Implement POST /users with validation
  task_type: new feature logic
  environment: Python 3.12 with FastAPI and Pydantic v2
  additional_constraints:
    - sanitize email input against injection
agent_contract:
  definition_of_done: COMPLETE only when acceptance criteria are evidenced.
  change_scope: Follow a minimum-necessary change policy.
  architecture_policy: Reuse existing project patterns before new abstractions.
  discovery_policy: Inspect the repo and write a short plan before substantial edits.
  execution_strategy: Implement small reversible units and test each unit.
  validation_strategy: Record real test commands; never claim tests probably pass.
  failure_recovery: Diagnose, apply a minimal fix, and never suppress errors blindly.
  autonomy_policy: Autonomous on low-risk work; escalate high-impact changes.
  persistent_memory: Maintain .agent/PLAN.md, STATUS.md, DECISIONS.md, and ISSUES.md.
  completion_contract: Produce an evidence report before declaring COMPLETE.
  resource_budget: Pause after 150 API calls or 2 hours per sub-task.
  tool_safety: No force-push, no secret dumps, sandboxed execution.
  context_compaction: Compact at 80%; preserve the task contract and .agent/ files.
  rollback_protocol: Checkpoint on green tests; reset after 3 failed fixes.
  escalation_rules: Pause on missing secrets, conflicts, or exhausted recovery.
  dependency_security: SAST and audit; MIT/Apache/BSD; pin minor versions.
optimization_targets:
  clarity: Prefer explicit operational rules over brevity. Long-horizon prompts may be long.
  richness: null
  density: null
  efficiency: null
  denoising: null
  deconfliction: null
```

## `lineage.json`

Schema: `RegistryLineageFile`.

```json
{
  "lineage": [
    {
      "prompt_id": "prior-prompt-abc12345",
      "version": 2,
      "relationship": "derived_from"
    }
  ],
  "source_session_id": "59ffd96f-aec9-47fa-9f4b-e1d672a9b4fd"
}
```

| Field | Description |
|-------|-------------|
| `lineage` | List of ancestor prompts (empty when no explicit lineage supplied) |
| `source_session_id` | UUID of the workbench session that produced this record |

Lineage is optional at finalize; the session ID is always recorded.

## `lessons_learned.md`

Not stored in the registry directory at finalize. Generated at artifact export and indexed as the third similarity document.

Content from `build_lessons_learned()`:

- Additional constraints joined
- Change-scope policy excerpt
- Failure-recovery excerpt
- Tool-safety excerpt

Example:

```markdown
Constraints: sanitize email input against injection; Keep responses concise
Change scope: Follow a minimum-necessary change policy. ...
```

If none apply: `No lessons captured yet.`

## `artifact_manifest.json`

Written to `data/artifacts/{prompt_id}/`, not the registry. Schema: `ArtifactManifest` (`domain/artifacts.py`).

```json
{
  "prompt_id": "fastapi-user-create-coding-prompt-59ffd96f",
  "version": 3,
  "artifact_dir": "/absolute/path/to/data/artifacts/...",
  "generated_at": "2026-06-15T22:36:15.743380Z",
  "files": [
    {
      "name": "canonical_prompt.txt",
      "format": "txt",
      "size_bytes": 748,
      "optional": false
    },
    {
      "name": "coding_prompt_spec.json",
      "format": "json",
      "size_bytes": 1204,
      "optional": false
    },
    {
      "name": "optimized_prompt.html",
      "format": "html",
      "size_bytes": 907,
      "optional": true
    }
  ],
  "warnings": [
    "Pandoc is not available; using built-in HTML fallback.",
    "WeasyPrint and Pandoc are not available; PDF export skipped."
  ]
}
```

| Field | Description |
|-------|-------------|
| `files` | Every generated file with format and byte size |
| `optional` | `true` for HTML/PDF when dependencies may be absent |
| `warnings` | Non-fatal export issues (missing Pandoc, WeasyPrint, etc.) |

Core required artifact files:

- `canonical_prompt.txt`, `canonical_prompt.md`
- `optimized_prompt.txt`, `optimized_prompt.md`
- `metadata.yaml`
- `requirement_card.json`
- `coding_prompt_spec.json`, `coding_prompt_spec.yaml`
- `metrics.json`
- `similarity_report.json`
- `lessons_learned.md`
- `artifact_manifest.json`

Optional: `optimized_prompt.html`, `optimized_prompt.pdf`, `inference_response.txt` (after external inference).

## `metrics.json`

Pre-inference metrics from the approved optimization (`PreInferenceMetrics`):

```json
{
  "requirement_capture_score": 1.0,
  "unspecified_field_honesty": 1.0,
  "instruction_clarity": 0.55,
  "hard_conflict_count": 0,
  "format_adherence": 1.0,
  "token_cost_estimate": 120,
  "richness_score": 1.0,
  "density_score": 1.0,
  "efficiency_score": 0.922,
  "denoising_score": 0.8,
  "deconfliction_score": 1.0
}
```

## `similarity_report.json`

Serialized `SimilarityCheckResult` from finalize: matches (prompt IDs, scores, titles) and optional warning string. Empty matches array when no prior prompts indexed.

## Versioning rules

1. **Draft versions** — Monotonic integers per session (`PromptDraft.version`). Each edit creates a new version. Only one draft is marked `is_canonical` after finalize.

2. **Registry version** — Equals the canonical draft version at finalize. Stored in `metadata.yaml` and artifact manifest.

3. **Immutability** — After finalize, the canonical draft body in the registry must not change. Further work requires a new session or a future re-finalize flow (not exposed in v1 UI).

4. **Local files only** — Finalize writes prompt directories under `REGISTRY_PATH`. There is no Git history and no remote. Wipe with `./scripts/wipe-registry.sh` if the store needs a clean slate.

5. **Artifacts vs registry** — Registry holds canonical source + coding spec + metadata. Artifacts add optimized text, metrics, manifest, and optional rendered formats. Artifacts may be regenerated; registry canonical files should not change without a new finalize.

6. **Similarity index** — Indexed on finalize with `(prompt_id, version)`. Three documents per prompt: canonical body, abstract, lessons learned.

## Local storage

```bash
ls data/registry
```

Do **not** copy API keys, customer PII, or `.env` values into the registry. Prompt bodies may contain sensitive instructions—treat the registry as confidential if prompts are. The store is local to this installation and is not versioned with Git.

## API access

| Endpoint | Purpose |
|----------|---------|
| `GET /registry/prompts` | List `metadata.yaml` records |
| `GET /registry/prompts/{prompt_id}` | Full detail including coding requirement card and canonical prompt |
| `GET /registry/prompts/{prompt_id}/artifacts/{filename}` | Raw registry or linked artifact file contents |

Filenames are path-validated (no traversal). Typical registry files: `metadata.yaml`, `canonical_prompt.txt`, `canonical_prompt.md`, `requirement_card.json`, `coding_prompt_spec.json`, `coding_prompt_spec.yaml`, `lineage.json`.
