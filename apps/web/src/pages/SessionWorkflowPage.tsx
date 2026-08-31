import { Navigate, useParams } from "react-router-dom";
import { useEffect } from "react";
import { ApiError, formatApiError } from "../api/http";
import { useSession } from "../api/hooks";
import { upsertRecentSession } from "../lib/recentSessions";
import {
  isSessionClosed,
  isStepAhead,
  sessionPath,
  sessionStepForState,
  type SessionStep,
} from "../lib/sessionRouting";
import { ReviewStepBanner } from "../components/ReviewStepBanner";
import { SessionClosedBanner } from "../components/SessionClosedBanner";
import { WorkflowReopenActions } from "../components/WorkflowReopenActions";
import { SessionWorkflowNav } from "../components/SessionWorkflowNav";
import { LoadingState, ErrorBanner } from "../components/ui";
import { ClarificationPage } from "./ClarificationPage";
import { DraftEditorPage } from "./DraftEditorPage";
import { SimilarityCheckPage } from "./SimilarityCheckPage";
import { OptimizationPage } from "./OptimizationPage";
import { CompletePage, ExportPage } from "./ExportPage";

function sessionLoadErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === "session_not_found") {
    return (
      "This session no longer exists (the API may have restarted). " +
      "In-memory sessions are cleared on reload — start a new session."
    );
  }
  if (error instanceof ApiError && error.code === "validation_error") {
    return formatApiError(
      error,
      "This session cannot be loaded with the current API schema. Start a new session.",
    );
  }
  return formatApiError(error, "Session not found or API unavailable.");
}

interface SessionWorkflowPageProps {
  step?: SessionStep;
}

export function SessionWorkflowPage({ step }: SessionWorkflowPageProps) {
  const { sessionId = "" } = useParams();
  const sessionQuery = useSession(sessionId);

  useEffect(() => {
    if (sessionQuery.data) {
      upsertRecentSession(sessionQuery.data);
    }
  }, [sessionQuery.data]);

  if (sessionQuery.isLoading) {
    return <LoadingState label="Loading session…" />;
  }

  if (sessionQuery.isError || !sessionQuery.data) {
    return (
      <div className="page narrow">
        <ErrorBanner message={sessionLoadErrorMessage(sessionQuery.error)} />
      </div>
    );
  }

  const session = sessionQuery.data;
  const currentStep = sessionStepForState(session.session.state);
  const activeStep = step ?? currentStep;

  if (step && isStepAhead(step, session.session.state)) {
    return <Navigate to={sessionPath(sessionId, currentStep)} replace />;
  }

  const readOnly = activeStep !== currentStep;
  const sessionClosed = isSessionClosed(session.session.state);

  return (
    <div className="session-workflow">
      <SessionWorkflowNav
        sessionId={sessionId}
        state={session.session.state}
        activeStep={activeStep}
      />
      {sessionClosed && activeStep !== "complete" && (
        <SessionClosedBanner sessionId={sessionId} />
      )}
      {readOnly && !sessionClosed && (
        <>
          <ReviewStepBanner sessionId={sessionId} state={session.session.state} />
          <WorkflowReopenActions sessionId={sessionId} activeStep={activeStep} />
        </>
      )}
      {renderWorkflowStep(activeStep, sessionId, session, readOnly || sessionClosed)}
    </div>
  );
}

function renderWorkflowStep(
  activeStep: SessionStep,
  sessionId: string,
  session: import("../api/types").SessionDetailResponse,
  readOnly: boolean,
) {
  switch (activeStep) {
    case "clarify":
      return <ClarificationPage sessionId={sessionId} session={session} readOnly={readOnly} />;
    case "edit":
      return <DraftEditorPage sessionId={sessionId} session={session} readOnly={readOnly} />;
    case "similarity":
      return (
        <SimilarityCheckPage sessionId={sessionId} session={session} readOnly={readOnly} />
      );
    case "optimize":
      return <OptimizationPage sessionId={sessionId} session={session} readOnly={readOnly} />;
    case "export":
      return <ExportPage sessionId={sessionId} session={session} readOnly={readOnly} />;
    case "complete":
      return <CompletePage sessionId={sessionId} session={session} />;
    default:
      return <DraftEditorPage sessionId={sessionId} session={session} readOnly={readOnly} />;
  }
}

export function SessionRedirectPage() {
  const { sessionId = "" } = useParams();
  const sessionQuery = useSession(sessionId);

  if (sessionQuery.isLoading) {
    return <LoadingState label="Loading session…" />;
  }

  if (sessionQuery.isError || !sessionQuery.data) {
    return (
      <div className="page narrow">
        <ErrorBanner message={sessionLoadErrorMessage(sessionQuery.error)} />
      </div>
    );
  }

  const step = sessionStepForState(sessionQuery.data.session.state);
  return <Navigate to={sessionPath(sessionId, step)} replace />;
}
