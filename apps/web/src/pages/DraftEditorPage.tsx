import { useEffect, useState } from "react";
import { Button, Checkbox, Content, Form, Grid, GridItem, Stack } from "@patternfly/react-core";
import { ApiError } from "../api/http";
import type { SessionDetailResponse } from "../api/types";
import { useEditDraft, useFinalizeSession } from "../api/hooks";
import { ClarificationQuestionPanel } from "../components/ClarificationQuestionPanel";
import { RequirementCardPanel } from "../components/RequirementCardPanel";
import { clipboardToMarkdown, insertText } from "../lib/pastedTable";
import {
  DraftBlock,
  ErrorBanner,
  PageFrame,
  PageHeader,
  Panel,
  TextAreaField,
  WarningBanner,
} from "../components/ui";

interface DraftEditorPageProps {
  sessionId: string;
  session: SessionDetailResponse;
  readOnly?: boolean;
}

export function DraftEditorPage({ sessionId, session, readOnly = false }: DraftEditorPageProps) {
  const editDraft = useEditDraft(sessionId);
  const finalize = useFinalizeSession(sessionId);
  const [instruction, setInstruction] = useState("");
  const [draftBody, setDraftBody] = useState(session.current_draft?.body ?? "");
  const [ackFirstShotRisk, setAckFirstShotRisk] = useState(false);

  const draft = session.current_draft;
  const unresolved = session.requirement_card.unresolved_fields ?? [];
  const readiness = session.first_shot_readiness;
  const hasUnresolvedQueue = Boolean(session.clarification_field || session.clarification_question);
  const questionNumber = session.clarification_question_number ?? 1;
  const totalQuestions = session.clarification_total_questions ?? unresolved.length;
  const firstShotBlocked =
    finalize.error instanceof ApiError && finalize.error.code === "first_shot_risk";
  const draftDirty = Boolean(draft && draftBody !== draft.body);

  useEffect(() => {
    if (draft) {
      setDraftBody(draft.body);
    }
  }, [draft?.id]);

  async function handleEdit(event: React.FormEvent) {
    event.preventDefault();
    if (!instruction.trim()) {
      return;
    }
    await editDraft.mutateAsync({ instruction: instruction.trim() });
    setInstruction("");
  }

  async function handleSaveDraft(event: React.FormEvent) {
    event.preventDefault();
    if (!draftBody.trim() || !draftDirty) {
      return;
    }
    await editDraft.mutateAsync({ body: draftBody });
  }

  function handleDraftPaste(event: React.ClipboardEvent<HTMLTextAreaElement>) {
    const converted = clipboardToMarkdown(
      event.clipboardData.getData("text/html"),
      event.clipboardData.getData("text/plain"),
    );
    if (!converted.foundTable) {
      return;
    }
    event.preventDefault();
    const target = event.currentTarget;
    const next = insertText(draftBody, target.selectionStart, target.selectionEnd, converted.text);
    setDraftBody(next.value);
  }

  const editError =
    editDraft.error instanceof ApiError ? editDraft.error.message : editDraft.error ? "Edit failed." : null;
  const finalizeError =
    finalize.error instanceof ApiError
      ? finalize.error.message
      : finalize.error
        ? "Finalization failed."
        : null;

  return (
    <PageFrame>
      <PageHeader
        title="Draft editor"
        subtitle="Type or paste in the draft pane, or revise with natural-language instructions, then finalize to write the canonical prompt to the registry."
      />
      <Grid hasGutter>
        <GridItem md={8}>
          <Stack hasGutter>
            {draft ? (
              <Panel title={`Draft v${draft.version}`}>
                {readOnly ? (
                  <DraftBlock body={draft.body} />
                ) : (
                  <Form onSubmit={handleSaveDraft}>
                    <TextAreaField
                      id="draft-body"
                      ariaLabel="Draft body"
                      rows={18}
                      value={draftBody}
                      onChange={setDraftBody}
                      onPaste={handleDraftPaste}
                      spellCheck={false}
                    />
                    {draftDirty && <Content component="small">Unsaved changes in this pane.</Content>}
                    {editError && <ErrorBanner message={editError} />}
                    <Button
                      type="submit"
                      variant="secondary"
                      isDisabled={editDraft.isPending || !draftDirty || !draftBody.trim()}
                    >
                      {editDraft.isPending ? "Saving…" : "Save draft"}
                    </Button>
                  </Form>
                )}
                {draft.change_summary && <Content component="small">{draft.change_summary}</Content>}
              </Panel>
            ) : (
              <Panel>
                <Content component="p">No draft available yet.</Content>
              </Panel>
            )}

            {!readOnly && hasUnresolvedQueue && (
              <ClarificationQuestionPanel
                sessionId={sessionId}
                session={session}
                title={`Unresolved field ${questionNumber} of ${totalQuestions}`}
                helpText="Answer remaining unspecified fields here. Each answer updates the draft. You can also use free-text edits below."
              />
            )}

            {!readOnly && (
              <Panel title="Edit instruction">
                <Form onSubmit={handleEdit}>
                  <TextAreaField
                    id="edit-instruction"
                    label="Instruction"
                    rows={4}
                    value={instruction}
                    onChange={setInstruction}
                    placeholder="Example: Change tone to analytical and tighten the output contract."
                  />
                  {editError && <ErrorBanner message={editError} />}
                  <Button type="submit" variant="secondary" isDisabled={editDraft.isPending || !instruction.trim()}>
                    {editDraft.isPending ? "Applying…" : "Submit change"}
                  </Button>
                </Form>
              </Panel>
            )}

            {(session.semantic_diff || session.change_summary) && (
              <Panel title="Semantic diff">
                {session.change_summary && <Content component="p">{session.change_summary}</Content>}
                {session.semantic_diff && <DraftBlock body={session.semantic_diff} label="Diff" />}
                {session.edit_intent && (
                  <Content component="small">
                    Intent: <code>{session.edit_intent}</code>
                  </Content>
                )}
              </Panel>
            )}

            {unresolved.length > 0 && (
              <WarningBanner message={`Unresolved fields: ${unresolved.join(", ")}`} />
            )}

            {readiness && !readiness.ready && (
              <Panel title="First-shot readiness">
                <Content component="p">
                  Score {Math.round(readiness.score * 100)}%. Gaps below usually cause multi-iteration
                  coding. Fill them or acknowledge the risk to finalize anyway.
                </Content>
                <Content component="ul">
                  {readiness.risks.map((risk) => (
                    <Content key={risk.code + (risk.field_name ?? "")} component="li">
                      {risk.message}
                    </Content>
                  ))}
                </Content>
              </Panel>
            )}

            {!readOnly && (
              <Panel title="Finalize">
                <Content component="p">
                  Finalization freezes the canonical draft and writes registry files under{" "}
                  <code>data/registry/</code>.
                </Content>
                {draftDirty && (
                  <Content component="small">Save draft edits in the pane above before finalizing.</Content>
                )}
                {(firstShotBlocked || (readiness && !readiness.ready)) && (
                  <Checkbox
                    id="ack-first-shot"
                    label="I acknowledge first-shot contract gaps and want to finalize anyway"
                    isChecked={ackFirstShotRisk}
                    onChange={(_event, checked) => setAckFirstShotRisk(checked)}
                  />
                )}
                {finalizeError && <ErrorBanner message={finalizeError} />}
                <Button
                  variant="primary"
                  isDisabled={
                    finalize.isPending ||
                    !draft ||
                    draftDirty ||
                    (Boolean(readiness && !readiness.ready) && !ackFirstShotRisk)
                  }
                  onClick={() =>
                    void finalize.mutateAsync({
                      acknowledgeFirstShotRisk: ackFirstShotRisk,
                    })
                  }
                >
                  {finalize.isPending ? "Finalizing…" : "Finalize prompt"}
                </Button>
              </Panel>
            )}
          </Stack>
        </GridItem>
        <GridItem md={4}>
          <RequirementCardPanel card={session.requirement_card} />
        </GridItem>
      </Grid>
    </PageFrame>
  );
}
