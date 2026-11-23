import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Form } from "@patternfly/react-core";
import { formatApiError } from "../api/http";
import { useCreateSession } from "../api/hooks";
import { clipboardToMarkdown, insertText } from "../lib/pastedTable";
import { sessionPath, sessionStepForState } from "../lib/sessionRouting";
import { ErrorBanner, PageFrame, PageHeader, Panel, TextAreaField, TextField } from "../components/ui";

export function NewSessionPage() {
  const navigate = useNavigate();
  const createSession = useCreateSession();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [request, setRequest] = useState("");
  const [title, setTitle] = useState("");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!request.trim()) {
      return;
    }
    try {
      const data = await createSession.mutateAsync({
        initial_request: request.trim(),
        title: title.trim() || undefined,
      });
      navigate(sessionPath(data.session.id, sessionStepForState(data.session.state)));
    } catch {
      // surfaced below
    }
  }

  function handlePaste(event: React.ClipboardEvent<HTMLTextAreaElement>) {
    const converted = clipboardToMarkdown(
      event.clipboardData.getData("text/html"),
      event.clipboardData.getData("text/plain"),
    );
    if (!converted.foundTable) {
      return;
    }
    event.preventDefault();
    const target = event.currentTarget;
    const next = insertText(request, target.selectionStart, target.selectionEnd, converted.text);
    setRequest(next.value);
    queueMicrotask(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(next.cursor, next.cursor);
      }
    });
  }

  const errorMessage =
    createSession.error != null
      ? formatApiError(createSession.error, "Failed to create session.")
      : null;

  return (
    <PageFrame limited>
      <PageHeader
        title="Initial prompt"
        subtitle="Describe the long-horizon coding task. Nautilius will extract the task identity and ask 16 operational-control questions with conservative defaults."
      />
      <Panel>
        <Form onSubmit={handleSubmit}>
          <TextAreaField
            id="initial-prompt"
            label="Initial prompt"
            inputRef={textareaRef}
            rows={12}
            value={request}
            onChange={setRequest}
            onPaste={handlePaste}
            placeholder="Describe the coding task. Pasted tables become markdown."
            isRequired
          />
          <TextField
            id="session-title"
            label="Title (optional)"
            value={title}
            onChange={setTitle}
            placeholder="FastAPI feature coding prompt"
          />
          {errorMessage && <ErrorBanner message={errorMessage} />}
          <Button type="submit" variant="primary" isDisabled={createSession.isPending}>
            {createSession.isPending ? "Creating…" : "Create session"}
          </Button>
        </Form>
      </Panel>
    </PageFrame>
  );
}
