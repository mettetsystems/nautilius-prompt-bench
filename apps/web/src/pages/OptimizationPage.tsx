import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { formatApiError } from "../api/http";
import type { SessionDetailResponse } from "../api/types";
import { useApproveOptimization, useUserSettings } from "../api/hooks";
import { fetchLlmHealth } from "../api/sessions";
import { formatPercent, sessionPath, sessionStepForState } from "../lib/sessionRouting";
import {
  DraftBlock,
  ErrorBanner,
  PageHeader,
  Panel,
  WarningBanner,
} from "../components/ui";

interface OptimizationPageProps {
  sessionId: string;
  session: SessionDetailResponse;
  readOnly?: boolean;
}

const DEFAULT_PRECISION_THRESHOLD = 0.75;

function readinessReady(session: SessionDetailResponse): boolean {
  return session.first_shot_readiness?.ready ?? true;
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
    approve.error != null
      ? formatApiError(approve.error, "Approval failed.")
      : null;

  const approvalBlocked = (optimization?.hard_conflicts.length ?? 0) > 0;

  if (!optimization) {
    return (
      <div className="page">
        <PageHeader title="Optimization" subtitle="Run optimization from the similarity step." />
        <Panel>
          <p className="muted">No optimization result is available for this session.</p>
        </Panel>
      </div>
    );
  }

  const metrics = optimization.metrics;

  return (
    <div className="page">
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

      <div className="grid-two">
        <Panel title="Optimized prompt">
          <DraftBlock body={optimization.optimized_body} label="Optimized" />
        </Panel>

        <Panel title="Metrics">
          <dl className="metrics-grid">
            <div>
              <dt>Clarity</dt>
              <dd>{formatPercent(metrics.targets.clarity ?? 0)}</dd>
            </div>
            <div>
              <dt>Original tokens</dt>
              <dd>{metrics.original_token_count}</dd>
            </div>
            <div>
              <dt>Result tokens</dt>
              <dd>{metrics.optimized_token_count}</dd>
            </div>
            <div>
              <dt>Token reduction</dt>
              <dd>{metrics.token_reduction_pct.toFixed(1)}%</dd>
            </div>
            <div>
              <dt>Constraints / token</dt>
              <dd>{metrics.constraints_per_token.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Richness</dt>
              <dd>{formatPercent(metrics.targets.richness)}</dd>
            </div>
            <div>
              <dt>Density</dt>
              <dd>{formatPercent(metrics.targets.density)}</dd>
            </div>
            <div>
              <dt>Efficiency</dt>
              <dd>{formatPercent(metrics.targets.efficiency)}</dd>
            </div>
            <div>
              <dt>Denoising</dt>
              <dd>{formatPercent(metrics.targets.denoising)}</dd>
            </div>
            <div>
              <dt>Deconfliction</dt>
              <dd>{formatPercent(metrics.targets.deconfliction)}</dd>
            </div>
            <div>
              <dt>Semantic precision</dt>
              <dd>
                {formatPercent(semanticPrecisionScore)}
                {vagueLanguageCount > 0 ? ` (${vagueLanguageCount} vague)` : ""}
              </dd>
            </div>
            {typeof firstShotScore === "number" && (
              <div>
                <dt>First-shot readiness</dt>
                <dd>
                  {formatPercent(firstShotScore)}
                  {firstShotReady ? "" : " (gaps)"}
                </dd>
              </div>
            )}
            {typeof sectionCoverage === "number" && (
              <div>
                <dt>Section coverage</dt>
                <dd>
                  {sectionCoverage}/17
                </dd>
              </div>
            )}
          </dl>
          {!modelEnabled && showPrecisionRefinement && (
            <p className="muted">
              Semantic precision uses regex detection plus offline WordNet/glossary suggestions.
              Run <code>make build-lexicon-index</code> for semantic vector ranking; the local
              model reranks candidates when available.
            </p>
          )}
          {showPrecisionWarning && (
            <WarningBanner
                  message={`Your semantic precision score is ${formatPercent(semanticPrecisionScore)} (below ${formatPercent(precisionThreshold)}). Vague wording hurts long-horizon agents more than extra tokens. Refine precision before approving export.`}
            />
          )}
          {showPrecisionRefinement && (
            <div className="button-row">
              <button
                type="button"
                className="button secondary"
                onClick={() => navigate(`/sessions/${sessionId}/precision`)}
              >
                Refine precision
              </button>
            </div>
          )}
          <p className="muted">Passes: {optimization.passes_completed.join(" → ")}</p>
        </Panel>
      </div>

      <div className="grid-three">
        <Panel title="Removed">
          {optimization.changes.removed.length === 0 ? (
            <p className="muted">None</p>
          ) : (
            <ul className="compact-list">
              {optimization.changes.removed.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Clarified">
          {(optimization.changes.clarified ?? optimization.changes.compressed).length === 0 ? (
            <p className="muted">None</p>
          ) : (
            <ul className="compact-list">
              {(optimization.changes.clarified ?? optimization.changes.compressed).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Conflicts resolved">
          {optimization.changes.conflicts_resolved.length === 0 ? (
            <p className="muted">None</p>
          ) : (
            <ul className="compact-list">
              {optimization.changes.conflicts_resolved.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Precision improvements">
          {(optimization.changes.precision_improvements?.length ?? 0) === 0 ? (
            <p className="muted">None</p>
          ) : (
            <ul className="compact-list">
              {optimization.changes.precision_improvements.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {!readOnly && (
      <Panel title="Approve export">
        <p className="muted">
          Approval runs the pre-inference quality gate. Export artifacts are generated in the next
          step.
        </p>
        {approveError && <ErrorBanner message={approveError} />}
        {optimization.approved ? (
          <button
            type="button"
            className="button primary"
            onClick={() => navigate(sessionPath(sessionId, "export"))}
          >
            Continue to export
          </button>
        ) : (
          <button
            type="button"
            className="button primary"
            disabled={approve.isPending || approvalBlocked}
            onClick={() =>
              void approve.mutateAsync().then((data) => {
                navigate(sessionPath(sessionId, sessionStepForState(data.session.state)));
              })
            }
          >
            {approve.isPending ? "Approving…" : "Approve export"}
          </button>
        )}
      </Panel>
      )}
    </div>
  );
}
