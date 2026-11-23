import { Alert, Button, Content } from "@patternfly/react-core";
import { formatApiError } from "../api/http";
import {
  useReopenForEdit,
  useRerunOptimization,
  useRerunSimilarityCheck,
} from "../api/hooks";
import { SESSION_STEP_LABELS, type SessionStep } from "../lib/sessionRouting";
import { ErrorBanner } from "./ui";

interface WorkflowReopenActionsProps {
  sessionId: string;
  activeStep: SessionStep;
}

const REOPEN_COPY: Partial<
  Record<
    SessionStep,
    { title: string; description: string; button: string; pending: string }
  >
> = {
  edit: {
    title: "Re-open this step",
    description:
      "Return to draft editing. Finalization, similarity, optimization, and export results will be cleared.",
    button: "Re-open for editing",
    pending: "Re-opening…",
  },
  similarity: {
    title: "Re-run this step",
    description:
      "Run the similarity check again against the current canonical draft. Optimization and export results will be cleared.",
    button: "Re-run similarity check",
    pending: "Re-running check…",
  },
  optimize: {
    title: "Re-run this step",
    description:
      "Run token optimization again from the canonical draft. Approval and export results will be cleared.",
    button: "Re-run optimization",
    pending: "Re-running optimization…",
  },
};

export function WorkflowReopenActions({ sessionId, activeStep }: WorkflowReopenActionsProps) {
  const reopenEdit = useReopenForEdit(sessionId);
  const rerunSimilarity = useRerunSimilarityCheck(sessionId);
  const rerunOptimization = useRerunOptimization(sessionId);

  const copy = REOPEN_COPY[activeStep];
  if (!copy) {
    return null;
  }

  const mutation =
    activeStep === "edit"
      ? reopenEdit
      : activeStep === "similarity"
        ? rerunSimilarity
        : rerunOptimization;

  const error =
    mutation.error != null
      ? formatApiError(mutation.error, "Could not re-open this step.")
      : null;

  return (
    <Alert variant="warning" isInline role="status" title={copy.title}>
      <p>{copy.description}</p>
      {error && <ErrorBanner message={error} />}
      <Button variant="primary" isDisabled={mutation.isPending} onClick={() => void mutation.mutateAsync()}>
        {mutation.isPending ? copy.pending : copy.button}
      </Button>
      <Content component="small">
        After re-opening, you can edit {SESSION_STEP_LABELS[activeStep].toLowerCase()} here without
        returning to the latest step first.
      </Content>
    </Alert>
  );
}
