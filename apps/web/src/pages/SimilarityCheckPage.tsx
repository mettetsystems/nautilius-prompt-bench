import { Button, Content, DataList, DataListCell, DataListItem, DataListItemCells, DataListItemRow, Grid, GridItem } from "@patternfly/react-core";
import type { SessionDetailResponse } from "../api/types";
import { ApiError, formatApiError } from "../api/http";
import { useOptimizeSession } from "../api/hooks";
import { ButtonRow, DraftBlock, ErrorBanner, LinkButton, PageFrame, PageHeader, Panel, WarningBanner } from "../components/ui";

interface SimilarityCheckPageProps {
  sessionId: string;
  session: SessionDetailResponse;
  readOnly?: boolean;
}

export function SimilarityCheckPage({
  sessionId,
  session,
  readOnly = false,
}: SimilarityCheckPageProps) {
  const optimize = useOptimizeSession(sessionId);
  const topMatch = session.similarity_matches[0];
  const hasWarning = Boolean(session.similarity_warning);
  const optimizeError =
    optimize.error instanceof ApiError
      ? formatApiError(optimize.error)
      : optimize.error
        ? "Optimization failed."
        : null;

  return (
    <PageFrame>
      <PageHeader
        title="Similarity check"
        subtitle="Compare this prompt against indexed patterns in the local registry before optimization."
      />

      {optimizeError && <ErrorBanner message={optimizeError} />}

      {hasWarning && session.similarity_warning && (
        <WarningBanner message={session.similarity_warning} />
      )}

      <Grid hasGutter md={6}>
        <GridItem>
          <Panel title="Current canonical draft">
            {session.current_draft ? (
              <DraftBlock body={session.current_draft.body} label="Canonical" />
            ) : (
              <Content component="p">No draft loaded.</Content>
            )}
            {session.prompt_id && (
              <Content component="small">
                Registry ID: <code>{session.prompt_id}</code>
              </Content>
            )}
          </Panel>
        </GridItem>

        <GridItem>
          <Panel title="Similar matches">
            {session.similarity_matches.length === 0 ? (
              <Content component="p">No close matches found in the local index.</Content>
            ) : (
              <DataList aria-label="Similar matches">
                {session.similarity_matches.map((match) => (
                  <DataListItem key={`${match.prompt_id}-${match.document_kind ?? "unknown"}`}>
                    <DataListItemRow>
                      <DataListItemCells
                        dataListCells={[
                          <DataListCell key="match">
                            <strong>{match.title}</strong>
                            <Content component="small">
                              <code>{match.prompt_id}</code> · score {Math.round(match.similarity_score * 100)}%
                            </Content>
                            {match.artifact_paths.canonical_txt && (
                              <Content component="small">
                                Artifact: <code>{match.artifact_paths.canonical_txt}</code>
                              </Content>
                            )}
                            {match.delta && <Content component="small">{match.delta}</Content>}
                          </DataListCell>,
                          <DataListCell key="review" alignRight>
                            <LinkButton to={`/registry/${match.prompt_id}`} variant="secondary">
                              Review
                            </LinkButton>
                          </DataListCell>,
                        ]}
                      />
                    </DataListItemRow>
                  </DataListItem>
                ))}
              </DataList>
            )}
          </Panel>
        </GridItem>
      </Grid>

      {!readOnly && (
        <Panel title="Next step">
          {topMatch && hasWarning ? (
            <Content component="p">
              A similar pattern exists for <code>{topMatch.prompt_id}</code>. Review it or continue
              to token optimization.
            </Content>
          ) : (
            <Content component="p">No blocking similarity issues detected. Continue to optimization.</Content>
          )}
          <ButtonRow>
            {topMatch && (
              <LinkButton to={`/registry/${topMatch.prompt_id}`} variant="secondary">
                Review matched prompt
              </LinkButton>
            )}
            <Button variant="primary" isDisabled={optimize.isPending} onClick={() => void optimize.mutateAsync()}>
              {optimize.isPending ? "Starting optimization…" : "Continue to optimization"}
            </Button>
          </ButtonRow>
        </Panel>
      )}
    </PageFrame>
  );
}
