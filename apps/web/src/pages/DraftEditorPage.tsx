import { useEffect, useState } from "react";
import { ApiError } from "../api/http";
import type { SessionDetailResponse } from "../api/types";
import { useEditDraft, useFinalizeSession } from "../api/hooks";
import { ClarificationQuestionPanel } from "../components/ClarificationQuestionPanel";
import { RequirementCardPanel } from "../components/RequirementCardPanel";
import { clipboardToMarkdown, insertText } from "../lib/pastedTable";
import {
  DraftBlock,
  ErrorBanner,
  PageHeader,
  Panel,
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
    <div className="page">
      <PageHeader
        title="Draft editor"
        subtitle="Type or paste in the draft pane, or revise with natural-language instructions, then finalize to write the canonical prompt to the registry."
      />
      <div className="grid-workflow">
        <div className="workflow-main stack-form">
          {draft ? (
            <Panel title={`Draft v${draft.version}`}>
              {readOnly ? (
                <DraftBlock body={draft.body} />
              ) : (
                <form className="stack-form" onSubmit={handleSaveDraft}>
                  <label className="field">
                    <span className="sr-only">Draft body</span>
                    <textarea
                      className="draft-text draft-editor"
                      rows={18}
                      value={draftBody}
                      onChange={(event) => setDraftBody(event.target.value)}
                      onPaste={handleDraftPaste}
                      spellCheck={false}
                    />
                  </label>
                  {draftDirty && <p className="muted">Unsaved changes in this pane.</p>}
                  {editError && <ErrorBanner message={editError} />}
                  <button
                    type="submit"
                    className="button secondary"
                    disabled={editDraft.isPending || !draftDirty || !draftBody.trim()}
                  >
                    {editDraft.isPending ? "Saving…" : "Save draft"}
                  </button>
                </form>
              )}
              {draft.change_summary && <p className="muted">{draft.change_summary}</p>}
            </Panel>
          ) : (
            <Panel>
              <p className="muted">No draft available yet.</p>
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
            <form className="stack-form" onSubmit={handleEdit}>
              <label className="field">
                <span>Instruction</span>
                <textarea
                  rows={4}
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  placeholder="Example: Change tone to analytical and tighten the output contract."
                />
              </label>
              {editError && <ErrorBanner message={editError} />}
              <button
                type="submit"
                className="button secondary"
                disabled={editDraft.isPending || !instruction.trim()}
              >
                {editDraft.isPending ? "Applying…" : "Submit change"}
              </button>
            </form>
          </Panel>
          )}

          {(session.semantic_diff || session.change_summary) && (
            <Panel title="Semantic diff">
              {session.change_summary && <p>{session.change_summary}</p>}
              {session.semantic_diff && <pre className="diff-text">{session.semantic_diff}</pre>}
              {session.edit_intent && (
                <p className="muted">
                  Intent: <code>{session.edit_intent}</code>
                </p>
              )}
            </Panel>
          )}

          {unresolved.length > 0 && (
            <WarningBanner message={`Unresolved fields: ${unresolved.join(", ")}`} />
          )}

          {readiness && !readiness.ready && (
            <Panel title="First-shot readiness">
              <p className="muted">
                Score {Math.round(readiness.score * 100)}%. Gaps below usually cause multi-iteration
                coding. Fill them or acknowledge the risk to finalize anyway.
              </p>
              <ul className="compact-list">
                {readiness.risks.map((risk) => (
                  <li key={risk.code + (risk.field_name ?? "")}>{risk.message}</li>
                ))}
              </ul>
            </Panel>
          )}

          {!readOnly && (
          <Panel title="Finalize">
            <p className="muted">
              Finalization freezes the canonical draft and writes registry files under{" "}
              <code>data/registry/</code>.
            </p>
            {draftDirty && (
              <p className="muted">Save draft edits in the pane above before finalizing.</p>
            )}
            {(firstShotBlocked || (readiness && !readiness.ready)) && (
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={ackFirstShotRisk}
                  onChange={(event) => setAckFirstShotRisk(event.target.checked)}
                />
                <span>I acknowledge first-shot contract gaps and want to finalize anyway</span>
              </label>
            )}
            {finalizeError && <ErrorBanner message={finalizeError} />}
            <button
              type="button"
              className="button primary"
              disabled={
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
            </button>
          </Panel>
          )}
        </div>
        <RequirementCardPanel card={session.requirement_card} />
      </div>
    </div>
  );
}
