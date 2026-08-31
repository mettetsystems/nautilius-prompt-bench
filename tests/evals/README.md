# Regression eval cases (`tests/evals/`)

YAML fixtures for pre-inference quality gate regression testing.

| File | Role |
|------|------|
| `regression_cases.yaml` | Task-identity + agent-contract cards, 17-section baseline bodies, `must_preserve` phrases |

Consumed by:

- `tests/test_quality_gate.py`
- `prompt_piper.eval.runner` (`make eval`)

Each case runs baseline vs optimized pairwise comparison; aggregate loss rate must stay ≤ 10% for the gate to pass.
