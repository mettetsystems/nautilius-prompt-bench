import type { SessionDetailResponse } from "../api/types";
import { ClarificationQuestionPanel } from "../components/ClarificationQuestionPanel";
import { RequirementCardPanel } from "../components/RequirementCardPanel";
import { DraftBlock, PageHeader, Panel } from "../components/ui";

interface ClarificationPageProps {
  sessionId: string;
  session: SessionDetailResponse;
  readOnly?: boolean;
}

export function ClarificationPage({ sessionId, session, readOnly = false }: ClarificationPageProps) {
  const questionNumber = session.clarification_question_number ?? 1;
  const totalQuestions = session.clarification_total_questions ?? 16;

  return (
    <div className="page">
      <PageHeader
        title="Architecture consultation"
        subtitle={
          readOnly
            ? "Captured requirement answers for this session"
            : `Question ${questionNumber} of up to ${totalQuestions} — architectural requirements for your coding-agent prompt`
        }
      />
      <div className={readOnly ? "grid-workflow is-review" : "grid-workflow"}>
        <div className="workflow-main stack-form">
          {readOnly ? (
            <p className="muted clarification-review-note">
              Answers are on the agent contract. The draft below was generated from this step.
            </p>
          ) : (
            <ClarificationQuestionPanel
              sessionId={sessionId}
              session={session}
              showFinishButton
            />
          )}
          {session.current_draft && (
            <Panel title="Draft preview" className="draft-preview-panel">
              <DraftBlock body={session.current_draft.body} />
            </Panel>
          )}
        </div>
        <RequirementCardPanel card={session.requirement_card} />
      </div>
    </div>
  );
}
