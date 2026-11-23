import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Content, DescriptionList, DescriptionListDescription, DescriptionListGroup, DescriptionListTerm, Grid, GridItem } from "@patternfly/react-core";
import { formatApiError } from "../api/http";
import type { SessionDetailResponse } from "../api/types";
import { useApproveOptimization, useUserSettings } from "../api/hooks";
import { fetchLlmHealth } from "../api/sessions";
import { formatPercent, sessionPath, sessionStepForState } from "../lib/sessionRouting";
import { DraftBlock, ErrorBanner, PageFrame, PageHeader, Panel, WarningBanner } from "../components/ui";

interface OptimizationPageProps {
  sessionId: string;
  session: SessionDetailResponse;
  readOnly?: boolean;
}

const DEFAULT_PRECISION_THRESHOLD = 0.75;

function readinessReady(session: SessionDetailResponse): boolean {
  return session.first_shot_readiness?.ready ?? true;
}

function ChangeList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <Content component="p">None</Content>;
  }
  return (
    <Content component="ul">
      {items.map((item) => (
        <Content key={item} component="li">
          {item}
        </Content>
      ))}
    </Content>
  );
}

export function OptimizationPage({
  sessionId,
  session,
  readOnly = false,
}: OptimizationPageProps) {
  const navigate = useNavigate();
  const approve = useApproveOptimization(sessionId);
  const userSettings = useUserSettings();
  const precisionThreshold =
    userSettings.data?.precision_warning_threshold ?? DEFAULT_PRECISION_THRESHOLD;
  const llmHealth = useQuery({ queryKey: ["llm-health"], queryFn: fetchLlmHealth });
  const optimization = session.optimization_result;
  const preMetrics = session.pre_inference_metrics;
  const semanticPrecisionScore = preMetrics?.semantic_precision_score ?? 1;
  const vagueLanguageCount = preMetrics?.vague_language_count ?? 0;
  const modelEnabled = llmHealth.data?.llm_enabled === true && llmHealth.data.status === "ok";
  const showPrecisionRefinement = !readOnly && vagueLanguageCount > 0;
  const showPrecisionWarning =
    showPrecisionRefinement && semanticPrecisionScore < precisionThreshold;
  const firstShotReady = preMetrics?.first_shot_ready ?? readinessReady(session);
  const firstShotScore = preMetrics?.first_shot_readiness_score;
  const sectionCoverage = preMetrics?.section_coverage;
  const gateWarnings = session.quality_gate_warnings ?? [];

  const approveError =
    approve.error != null ? formatApiError(approve.error, "Approval failed.") : null;

  const approvalBlocked = (optimization?.hard_conflicts.length ?? 0) > 0;

  if (!optimization) {
    return (
      <PageFrame>
        <PageHeader title="Optimization" subtitle="Run optimization from the similarity step." />
        <Panel>
          <Content component="p">No optimization result is available for this session.</Content>
        </Panel>
      </PageFrame>
    );
  }

  const metrics = optimization.metrics;

  return (
    <PageFrame>
      <PageHeader
        title="Clarity optimization"
        subtitle="Review the clarified long-horizon contract, metrics, and change log before approving export. Token count is informational — clarity comes first."
      />

      {optimization.hard_conflicts.length > 0 && (
        <WarningBanner
          message={`${optimization.hard_conflicts.length} hard conflict(s) require resolution before export.`}
        />
      )}

      {!firstShotReady && (
        <WarningBanner message="First-shot readiness gaps remain. Prefer filling definition of done, validation, and completion evidence before a long-horizon run." />
      )}
      {showPrecisionWarning && (
        <WarningBanner
          message={`Semantic precision ${formatPercent(semanticPrecisionScore)} is below the ${formatPercent(precisionThreshold)} threshold.`}
        />
      )}
      {typeof sectionCoverage === "number" && sectionCoverage < 17 && (
        <WarningBanner
          message={`Only ${sectionCoverage}/17 contract sections are present; Task Identity plus the 16 operational policies improve long-horizon adherence.`}
        />
      )}
      {gateWarnings.map((warning) => (
        <WarningBanner key={warning} message={warning} />
      ))}

      <Grid hasGutter md={6}>
        <GridItem>
          <Panel title="Optimized prompt">
            <DraftBlock body={optimization.optimized_body} label="Optimized" />
          </Panel>
        </GridItem>

        <GridItem>
          <Panel title="Metrics">
            <DescriptionList isCompact columnModifier={{ default: "2Col" }}>
              <DescriptionListGroup>
                <DescriptionListTerm>Clarity</DescriptionListTerm>
                <DescriptionListDescription>{formatPercent(metrics.targets.clarity ?? 0)}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Original tokens</DescriptionListTerm>
                <DescriptionListDescription>{metrics.original_token_count}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Result tokens</DescriptionListTerm>
                <DescriptionListDescription>{metrics.optimized_token_count}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Token reduction</DescriptionListTerm>
                <DescriptionListDescription>{metrics.token_reduction_pct.toFixed(1)}%</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Constraints / token</DescriptionListTerm>
                <DescriptionListDescription>{metrics.constraints_per_token.toFixed(2)}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Richness</DescriptionListTerm>
                <DescriptionListDescription>{formatPercent(metrics.targets.richness)}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Density</DescriptionListTerm>
                <DescriptionListDescription>{formatPercent(metrics.targets.density)}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Efficiency</DescriptionListTerm>
                <DescriptionListDescription>{formatPercent(metrics.targets.efficiency)}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Denoising</DescriptionListTerm>
                <DescriptionListDescription>{formatPercent(metrics.targets.denoising)}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Deconfliction</DescriptionListTerm>
                <DescriptionListDescription>{formatPercent(metrics.targets.deconfliction)}</DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Semantic precision</DescriptionListTerm>
                <DescriptionListDescription>
                  {formatPercent(semanticPrecisionScore)}
                  {vagueLanguageCount > 0 ? ` (${vagueLanguageCount} vague)` : ""}
                </DescriptionListDescription>
              </DescriptionListGroup>
              {typeof firstShotScore === "number" && (
                <DescriptionListGroup>
                  <DescriptionListTerm>First-shot readiness</DescriptionListTerm>
                  <DescriptionListDescription>
                    {formatPercent(firstShotScore)}
                    {firstShotReady ? "" : " (gaps)"}
                  </DescriptionListDescription>
                </DescriptionListGroup>
              )}
              {typeof sectionCoverage === "number" && (
                <DescriptionListGroup>
                  <DescriptionListTerm>Section coverage</DescriptionListTerm>
                  <DescriptionListDescription>{sectionCoverage}/17</DescriptionListDescription>
                </DescriptionListGroup>
              )}
            </DescriptionList>
            {!modelEnabled && showPrecisionRefinement && (
              <Content component="small">
                Semantic precision uses regex detection plus offline WordNet/glossary suggestions.
                Run <code>make build-lexicon-index</code> for semantic vector ranking; the local
                model reranks candidates when available.
              </Content>
            )}
            {showPrecisionWarning && (
              <WarningBanner
                message={`Your semantic precision score is ${formatPercent(semanticPrecisionScore)} (below ${formatPercent(precisionThreshold)}). Vague wording hurts long-horizon agents more than extra tokens. Refine precision before approving export.`}
              />
            )}
            {showPrecisionRefinement && (
              <Button variant="secondary" onClick={() => navigate(`/sessions/${sessionId}/precision`)}>
                Refine precision
              </Button>
            )}
            <Content component="small">Passes: {optimization.passes_completed.join(" → ")}</Content>
          </Panel>
        </GridItem>
      </Grid>

      <Grid hasGutter md={4}>
        <GridItem>
          <Panel title="Removed">
            <ChangeList items={optimization.changes.removed} />
          </Panel>
        </GridItem>
        <GridItem>
          <Panel title="Clarified">
            <ChangeList items={optimization.changes.clarified ?? optimization.changes.compressed} />
          </Panel>
        </GridItem>
        <GridItem>
          <Panel title="Conflicts resolved">
            <ChangeList items={optimization.changes.conflicts_resolved} />
          </Panel>
        </GridItem>
        <GridItem>
          <Panel title="Precision improvements">
            <ChangeList items={optimization.changes.precision_improvements ?? []} />
          </Panel>
        </GridItem>
      </Grid>

      {!readOnly && (
        <Panel title="Approve export">
          <Content component="p">
            Approval runs the pre-inference quality gate. Export artifacts are generated in the next
            step.
          </Content>
          {approveError && <ErrorBanner message={approveError} />}
          {optimization.approved ? (
            <Button variant="primary" onClick={() => navigate(sessionPath(sessionId, "export"))}>
              Continue to export
            </Button>
          ) : (
            <Button
              variant="primary"
              isDisabled={approve.isPending || approvalBlocked}
              onClick={() =>
                void approve.mutateAsync().then((data) => {
                  navigate(sessionPath(sessionId, sessionStepForState(data.session.state)));
                })
              }
            >
              {approve.isPending ? "Approving…" : "Approve export"}
            </Button>
          )}
        </Panel>
      )}
    </PageFrame>
  );
}
