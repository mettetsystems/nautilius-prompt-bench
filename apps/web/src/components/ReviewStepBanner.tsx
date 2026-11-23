import { Alert } from "@patternfly/react-core";
import type { SessionState } from "../api/types";
import {
  SESSION_STEP_LABELS,
  sessionPath,
  sessionStepForState,
  type SessionStep,
} from "../lib/sessionRouting";
import { LinkButton } from "./ui";

interface ReviewStepBannerProps {
  sessionId: string;
  state: SessionState;
}

export function ReviewStepBanner({ sessionId, state }: ReviewStepBannerProps) {
  const currentStep = sessionStepForState(state);

  return (
    <Alert variant="warning" isInline role="status" title="Review mode">
      <p>
        You are viewing a completed step. Use the action below to re-open this step, or continue
        from the current step.
      </p>
      <LinkButton to={sessionPath(sessionId, currentStep)} variant="secondary">
        Continue at {SESSION_STEP_LABELS[currentStep]}
      </LinkButton>
    </Alert>
  );
}

export type { SessionStep };
