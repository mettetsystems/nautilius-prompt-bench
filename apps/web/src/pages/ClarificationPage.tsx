import { Content, Grid, GridItem, Stack } from "@patternfly/react-core";
import type { SessionDetailResponse } from "../api/types";
import { ClarificationQuestionPanel } from "../components/ClarificationQuestionPanel";
import { RequirementCardPanel } from "../components/RequirementCardPanel";
import { DraftBlock, PageFrame, PageHeader, Panel } from "../components/ui";

interface ClarificationPageProps {
  sessionId: string;
  session: SessionDetailResponse;
  readOnly?: boolean;
}

export function ClarificationPage({ sessionId, session, readOnly = false }: ClarificationPageProps) {
  const questionNumber = session.clarification_question_number ?? 1;
  const totalQuestions = session.clarification_total_questions ?? 16;

  return (
    <PageFrame>
      <PageHeader
        title="Architecture consultation"
        subtitle={
          readOnly
            ? "Captured requirement answers for this session"
            : `Question ${questionNumber} of up to ${totalQuestions} — architectural requirements for your coding-agent prompt`
        }
      />
      <Grid hasGutter>
        <GridItem md={8}>
          <Stack hasGutter>
            {readOnly ? (
              <Content component="p">
                Answers are on the agent contract. The draft below was generated from this step.
              </Content>
            ) : (
              <ClarificationQuestionPanel sessionId={sessionId} session={session} showFinishButton />
            )}
            {session.current_draft && (
              <Panel title="Draft preview">
                <DraftBlock body={session.current_draft.body} />
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
