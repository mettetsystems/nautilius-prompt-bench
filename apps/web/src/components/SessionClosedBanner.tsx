import { Alert } from "@patternfly/react-core";
import { SessionTemplateButton } from "./SessionTemplateButton";

interface SessionClosedBannerProps {
  sessionId: string;
}

export function SessionClosedBanner({ sessionId }: SessionClosedBannerProps) {
  return (
    <Alert variant="warning" isInline role="status" title="Session closed">
      <p>
        This session is complete and preserved for audit. Previous steps are read-only and cannot
        be re-run.
      </p>
      <SessionTemplateButton sessionId={sessionId} />
    </Alert>
  );
}
