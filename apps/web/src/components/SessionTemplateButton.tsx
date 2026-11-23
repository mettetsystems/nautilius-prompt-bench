import { useNavigate } from "react-router-dom";
import { Button } from "@patternfly/react-core";
import { formatApiError } from "../api/http";
import { useCreateSessionFromTemplate } from "../api/hooks";
import { sessionPath } from "../lib/sessionRouting";
import { ErrorBanner } from "./ui";

interface SessionTemplateButtonProps {
  sessionId: string;
}

export function SessionTemplateButton({ sessionId }: SessionTemplateButtonProps) {
  const navigate = useNavigate();
  const createTemplate = useCreateSessionFromTemplate(sessionId);

  const error =
    createTemplate.error != null
      ? formatApiError(createTemplate.error, "Could not create a session from this template.")
      : null;

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <Button
        variant="primary"
        isDisabled={createTemplate.isPending}
        onClick={() =>
          void createTemplate.mutateAsync(undefined).then((data) => {
            navigate(sessionPath(data.session.id, "edit"));
          })
        }
      >
        {createTemplate.isPending ? "Creating session…" : "Use as template"}
      </Button>
    </div>
  );
}
