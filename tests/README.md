# Backend tests (`tests/`)

pytest suite for API, services, and integration. Config: root `pyproject.toml` (`pythonpath = ["apps/api"]`).

| Area | Example files |
|------|----------------|
| Session workflow | `test_session_state_machine.py`, `test_workflow_reopen.py`, `test_session_persistence.py` |
| Clarification | `test_clarification_loop.py`, `test_clarification_suggestions.py` |
| Draft / finalize | `test_draft_edit.py`, `test_registry_finalize.py` |
| Similarity | `test_similarity_search.py` |
| Optimization / gate | `test_token_optimizer.py`, `test_quality_gate.py`, `test_optimization_binding.py`, `test_requirement_capture.py`, `test_semantic_precision.py` |
| Artifacts / export | `test_artifacts.py`, `test_artifact_export.py` |
| Hardening / inference | `test_hardening.py`, `test_external_inference.py` |
| Setup / LLM | `test_setup_wizard.py`, `test_ensure_llm.py`, `test_maya_startup.py`, `test_llm_health.py` |

| Directory | README |
|-----------|--------|
| [`integration/`](integration/README.md) | API startup smoke tests |
| [`evals/`](evals/README.md) | Regression YAML cases for quality gate |

Shared helpers: `conftest.py` (TestClient, isolated export paths), `clarification_helpers.py`.

```bash
# Run full suite from repo root
make test

# Single file
PYTHONPATH=apps/api:. apps/api/.venv/bin/pytest tests/test_workflow_reopen.py -q
```
