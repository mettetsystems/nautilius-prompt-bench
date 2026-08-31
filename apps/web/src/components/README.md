# Components (`src/components/`)

Shared React UI used across workflow pages.

| Component | Role |
|-----------|------|
| `AppLayout.tsx` | Shell, header, logo, navigation |
| `SessionWorkflowNav.tsx` | Step stepper (clarify → complete) |
| `ReviewStepBanner.tsx` | Read-only notice when viewing a past step |
| `WorkflowReopenActions.tsx` | Re-open edit / re-run similarity or optimization |
| `SessionClosedBanner.tsx` | Completed session is immutable |
| `SessionTemplateButton.tsx` | Create new session from completed template |
| `RequirementCardPanel.tsx` | Sidebar task-identity + 16-question agent contract |
| `ClarificationQuestionPanel.tsx` | Shared clarify / edit unresolved Q&A panel |
| `StatusBadge.tsx` | Session state badge |
| `ui.tsx` | `PageHeader`, `Panel`, `ErrorBanner`, `LoadingState`, … |

Co-located tests: `RequirementCardPanel.test.tsx`.
