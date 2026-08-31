# Clarity optimization (`services/optimization/`)

Five-pass local optimizer run after finalization on long-horizon coding-agent contracts. Rebuilds the 16-question task contract. Clarity of operational rules takes priority over token reduction.

| Pass | Module | What it does |
|------|--------|--------------|
| 1 | `constraint_graph_pass.py` | Slot task-contract + body requirements into typed constraint graph; detect contradictions |
| 2 | `rewrite_pass.py` | Rebuild the long-horizon contract; expand for explicitness |
| 3 | `denoising_pass.py` | Remove repetition and filler (protects binding phrases) |
| 4 | `deconfliction_pass.py` | Resolve or flag hard conflicts |
| 5 | `binding_preservation_pass.py` | Re-inject binding requirements when missing after denoising |
| — | `metrics.py` | Clarity-first metrics and `ApprovalExportPass` packaging |
| — | `engine.py` | `TokenOptimizationEngine.optimize()` orchestration |

Approval scoring uses **binding phrases** from the constraint graph (see `requirement_capture.collect_optimization_binding_phrases`). Token counts remain informational.

**Semantic precision** is evaluated separately in `semantic_precision.py` and surfaced on the Optimize step; optional LLM-guided refinement runs via `/sessions/{id}/precision/*` when score is below 0.75 and a model is available.
