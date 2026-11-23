import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Checkbox, Content, Grid, GridItem, ToggleGroup, ToggleGroupItem } from "@patternfly/react-core";
import { formatApiError } from "../api/http";
import {
  queryKeys,
  useApplyPrecisionReplacement,
  useSession,
  useSuggestPrecisionReplacement,
} from "../api/hooks";
import { fetchPrecisionReview } from "../api/sessions";
import type { PrecisionSuggestResponse, VagueLanguageFinding } from "../api/types";
import { formatPercent, sessionPath } from "../lib/sessionRouting";
import {
  ButtonRow,
  ErrorBanner,
  HighlightedDraft,
  LinkButton,
  LoadingState,
  PageFrame,
  PageHeader,
  Panel,
  TextAreaField,
} from "../components/ui";

interface PrecisionPageProps {
  sessionId: string;
}

export function PrecisionPage({ sessionId }: PrecisionPageProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const sessionQuery = useSession(sessionId);
  const precisionQuery = useQuery({
    queryKey: queryKeys.precisionReview(sessionId),
    queryFn: () => fetchPrecisionReview(sessionId),
    enabled: Boolean(sessionId) && sessionQuery.data?.session.state === "optimization",
  });

  const suggest = useSuggestPrecisionReplacement(sessionId);
  const apply = useApplyPrecisionReplacement(sessionId);

  const [index, setIndex] = useState(0);
  const [useLlm, setUseLlm] = useState(true);
  const [selected, setSelected] = useState<string>("");
  const [custom, setCustom] = useState("");
  const [suggestions, setSuggestions] = useState<PrecisionSuggestResponse | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const customInputRef = useRef<HTMLTextAreaElement | null>(null);

  const findings = precisionQuery.data?.findings ?? [];
  const current: VagueLanguageFinding | undefined = findings[index];

  useEffect(() => {
    if (!current) {
      return;
    }
    const findingId = current.id;
    let cancelled = false;
    setSelected("");
    setCustom("");
    setSuggestions(null);
    setSuggestionsLoading(true);

    void suggest
      .mutateAsync({ findingId, useLlm })
      .then((result) => {
        if (cancelled) {
          return;
        }
        setSuggestions(result);
        // Don't clobber a custom replacement the user already typed while waiting.
        if (customInputRef.current?.value.trim()) {
          return;
        }
        if (result.suggested_replacements.length > 0) {
          setSelected(result.suggested_replacements[0] ?? "");
        }
      })
      .catch(() => {
        // Error surfaced via suggest.error; keep the custom field usable.
      })
      .finally(() => {
        if (!cancelled) {
          setSuggestionsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch when finding or mode changes
  }, [current?.id, useLlm]);

  const replacement = useMemo(() => {
    if (custom.trim()) {
      return custom.trim();
    }
    return selected.trim();
  }, [custom, selected]);

  const highlight = useMemo(() => {
    if (!current) {
      return null;
    }
    return {
      lineNumber: current.line_number,
      start: current.start,
      end: current.end,
    };
  }, [current]);

  if (sessionQuery.isLoading || precisionQuery.isLoading) {
    return (
      <PageFrame>
        <LoadingState label="Loading precision review…" />
      </PageFrame>
    );
  }

  if (sessionQuery.isError || !sessionQuery.data) {
    return (
      <PageFrame limited>
        <ErrorBanner message={formatApiError(sessionQuery.error, "Session unavailable.")} />
      </PageFrame>
    );
  }

  if (sessionQuery.data.session.state !== "optimization") {
    return <Navigate to={sessionPath(sessionId, "optimize")} replace />;
  }

  if (precisionQuery.isError || !precisionQuery.data) {
    return (
      <PageFrame limited>
        <ErrorBanner message={formatApiError(precisionQuery.error, "Precision review failed.")} />
      </PageFrame>
    );
  }

  const review = precisionQuery.data;

  if (!review.refinement_available) {
    return <Navigate to={sessionPath(sessionId, "optimize")} replace />;
  }

  const suggestError =
    suggest.error != null
      ? formatApiError(suggest.error, "Could not fetch replacement suggestions.")
      : null;
  const applyError =
    apply.error != null ? formatApiError(apply.error, "Could not apply replacement.") : null;

  // Keep the custom field and navigation usable while lexicon/LLM suggestions load.
  const isApplying = apply.isPending;

  async function handleApply() {
    if (!current || !replacement || isApplying) {
      return;
    }
    await apply.mutateAsync({ findingId: current.id, replacement });
    const refreshed = await queryClient.fetchQuery({
      queryKey: queryKeys.precisionReview(sessionId),
      queryFn: () => fetchPrecisionReview(sessionId),
    });
    if (refreshed.findings.length === 0) {
      navigate(sessionPath(sessionId, "optimize"));
      return;
    }
    if (index >= refreshed.findings.length) {
      setIndex(refreshed.findings.length - 1);
    }
  }

  if (findings.length === 0) {
    return (
      <PageFrame>
        <PageHeader
          title="Semantic precision"
          subtitle="No vague language remains in the optimized prompt."
        />
        <Panel>
          <Content component="p">
            Semantic precision score: {formatPercent(review.score)} (threshold{" "}
            {formatPercent(review.threshold)}).
          </Content>
          <LinkButton to={sessionPath(sessionId, "optimize")}>Back to optimization</LinkButton>
        </Panel>
      </PageFrame>
    );
  }

  return (
    <PageFrame>
      <PageHeader
        title="Refine semantic precision"
        subtitle={`Finding ${index + 1} of ${findings.length} · score ${formatPercent(review.score)} · ${
          useLlm && review.llm_available
            ? "model-ranked lexicon"
            : review.vector_index_available
              ? "vector lexicon"
              : "WordNet (CPU-only)"
        }`}
      />

      <Grid hasGutter md={6}>
        <GridItem>
          <Panel title="Optimized prompt">
            <HighlightedDraft body={review.optimized_body} label="Optimized" highlight={highlight} />
            <Content component="p">
              Vague {current?.category === "lazy_adjective" ? "adjective" : "noun"}:{" "}
              <strong>{current?.term}</strong>
              {current ? ` (line ${current.line_number})` : ""}
            </Content>
          </Panel>
        </GridItem>

        <GridItem>
          <Panel title="Choose a precise replacement">
            <Checkbox
              id="use-ai-tooling"
              label="Use AI tooling model"
              isChecked={useLlm}
              onChange={(_event, checked) => setUseLlm(checked)}
            />
            <Content component="small">
              {useLlm
                ? "Uses your current AI tooling model with the full optimized prompt. CPU-only suggestions are available if the model is unavailable."
                : "CPU-only: WordNet, glossary, and available vector suggestions."}
            </Content>
            {suggestError && <ErrorBanner message={suggestError} />}
            {applyError && <ErrorBanner message={applyError} />}

            {suggestionsLoading && <Content component="small">Loading replacement suggestions…</Content>}

            {suggestions?.message && !suggestionsLoading && (
              <Content component="small">{suggestions.message}</Content>
            )}

            {!suggestionsLoading && suggestions && suggestions.suggested_replacements.length > 0 && (
              <ToggleGroup aria-label="Suggested replacements">
                {suggestions.suggested_replacements.map((option) => (
                  <ToggleGroupItem
                    key={option}
                    text={option}
                    isSelected={selected === option && !custom.trim()}
                    isDisabled={isApplying}
                    onChange={() => {
                      setSelected(option);
                      setCustom("");
                    }}
                  />
                ))}
              </ToggleGroup>
            )}

            <TextAreaField
              id="custom-replacement"
              label="Or enter your own word or phrase"
              inputRef={customInputRef}
              rows={3}
              value={custom}
              isDisabled={isApplying}
              placeholder="Replace the highlighted word with a word or a short phrase"
              onChange={(value) => {
                setCustom(value);
                setSelected("");
              }}
            />

            <ButtonRow>
              <Button variant="secondary" isDisabled={isApplying || index === 0} onClick={() => setIndex((value) => Math.max(0, value - 1))}>
                Previous
              </Button>
              <Button variant="primary" isDisabled={isApplying || !replacement} onClick={() => void handleApply()}>
                {apply.isPending ? "Applying…" : "Apply and continue"}
              </Button>
              <Button
                variant="secondary"
                isDisabled={isApplying || index >= findings.length - 1}
                onClick={() => setIndex((value) => Math.min(findings.length - 1, value + 1))}
              >
                Skip for now
              </Button>
            </ButtonRow>
          </Panel>
        </GridItem>
      </Grid>

      <Content component="p">
        <Link to={sessionPath(sessionId, "optimize")}>Return to optimization</Link>
      </Content>
    </PageFrame>
  );
}
