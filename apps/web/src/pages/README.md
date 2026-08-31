# Pages (`src/pages/`)

One page component per workflow stage or registry view.

| Page | Route | Role |
|------|-------|------|
| `DashboardPage.tsx` | `/` | Recent sessions (delete removes the session file) and registry shortcuts |
| `NewSessionPage.tsx` | `/sessions/new` | Initial prompt — paste tables become markdown |
| `ClarificationPage.tsx` | `…/clarify` | Multi-select answers for the 16-question agent contract |
| `DraftEditorPage.tsx` | `…/edit` | NL edit instructions, finalize |
| `SimilarityCheckPage.tsx` | `…/similarity` | Match review, continue to optimize |
| `OptimizationPage.tsx` | `…/optimize` | Metrics, semantic precision score, approve export gate |
| `PrecisionPage.tsx` | `…/precision` | Iterate vague-language findings with model suggestions (optimization state only) |
| `ExportPage.tsx` | `…/export` | Generate artifacts (rendered prompts + coding_prompt_spec) |
| `ExportPage.tsx` (`CompletePage`) | `…/complete` | Export summary, **Send to model**, template button |
| `RegistryPage.tsx` | `/registry` | Prompt list |
| `RegistryDetailPage.tsx` | `/registry/:id` | Single prompt artifacts |
| `SessionWorkflowPage.tsx` | `…/:step` | Wrapper — nav, read-only, step render |

`SessionRedirectPage` sends `/sessions/:id` to the current workflow step.
