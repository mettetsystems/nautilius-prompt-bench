import { Link } from "react-router-dom";
import { ProgressStep, ProgressStepper } from "@patternfly/react-core";
import type { SessionState } from "../api/types";
import {
  SESSION_STEP_LABELS,
  SESSION_STEPS,
  canVisitStep,
  sessionPath,
  sessionStepForState,
  type SessionStep,
} from "../lib/sessionRouting";

interface SessionWorkflowNavProps {
  sessionId: string;
  state: SessionState;
  activeStep: SessionStep;
}

export function SessionWorkflowNav({ sessionId, state, activeStep }: SessionWorkflowNavProps) {
  const currentStep = sessionStepForState(state);

  return (
    <ProgressStepper aria-label="Session workflow">
      {SESSION_STEPS.map((step) => {
        const reachable = canVisitStep(step, state);
        const isActive = step === activeStep;
        const isCurrent = step === currentStep;
        const label = SESSION_STEP_LABELS[step];
        const variant = !reachable ? "pending" : isCurrent ? "info" : "success";

        return (
          <ProgressStep
            key={step}
            id={`workflow-${step}`}
            titleId={`workflow-${step}-title`}
            variant={variant}
            isCurrent={isActive}
            aria-label={reachable ? label : `${label}, unavailable`}
          >
            {reachable ? (
              <Link to={sessionPath(sessionId, step)}>{label}</Link>
            ) : (
              <span aria-disabled="true">{label}</span>
            )}
          </ProgressStep>
        );
      })}
    </ProgressStepper>
  );
}
