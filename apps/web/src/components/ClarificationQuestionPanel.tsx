import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { formatApiError } from "../api/http";
import type {
  AskTheLocalsResponse,
  ClarificationSuggestionsResponse,
  ClarificationVersionText,
  ClarificationVersionsSettings,
  QuickReplyGuide,
  SessionDetailResponse,
} from "../api/types";
import {
  useAnswerClarification,
  useAskTheLocals,
  useCompleteClarification,
  useSuggestClarification,
  useUserSettings,
} from "../api/hooks";
import { fetchLlmHealth } from "../api/sessions";
import {
  buildClarificationAnswer,
  toggleClarificationOption,
} from "../lib/clarificationAnswer";
import { ErrorBanner, Panel } from "./ui";

const DEFAULT_VERSIONS: ClarificationVersionsSettings = {
  beginner: true,
  standard: true,
  advanced: true,
};

function isVersionEnabled(
  level: ClarificationVersionText["level"],
  availability: ClarificationVersionsSettings,
): boolean {
  const enabled = availability[level];
  if (availability.beginner || availability.standard || availability.advanced) {
    return enabled;
  }
  return level === "standard";
}

function BeginnerOptionGuides({ guides }: { guides: QuickReplyGuide[] }) {
  if (guides.length === 0) {
    return null;
  }
  return (
    <div className="option-guides">
      <p className="option-guides-title">What each default option means</p>
      <ul className="option-guide-list">
        {guides.map((guide) => (
          <li key={guide.option} className="option-guide-item">
            <p className="option-guide-option">{guide.option}</p>
            <p className="option-guide-explanation">{guide.explanation}</p>
            <p className="option-guide-when">
              <span className="clarification-rationale-label">Best when: </span>
              {guide.when_to_use}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ClarificationVersionAccordions({
  versions,
  availability,
  questionNumber,
  totalQuestions,
  questionKey,
  optionGuides,
}: {
  versions: ClarificationVersionText[];
  availability: ClarificationVersionsSettings;
  questionNumber: number;
  totalQuestions: number;
  questionKey: string;
  optionGuides: QuickReplyGuide[];
}) {
  const visible = versions.filter((version) => isVersionEnabled(version.level, availability));

  return (
    <div
      key={questionKey}
      className="clarification-versions"
      role="group"
      aria-label="Question wording versions"
    >
      {visible.map((version) => (
        <details
          key={version.level}
          className="clarification-version"
          open={version.level === "standard"}
        >
          <summary className="clarification-version-summary">
            <span className="clarification-version-label">{version.label}</span>
            <span className="muted">
              Question {questionNumber} of {totalQuestions}
            </span>
          </summary>
          <div className="clarification-version-body">
            <p className="question-text">{version.prompt}</p>
            {version.rationale && (
              <p className="clarification-rationale">
                <span className="clarification-rationale-label">Why this matters: </span>
                {version.rationale}
              </p>
            )}
            {version.level === "beginner" && <BeginnerOptionGuides guides={optionGuides} />}
          </div>
        </details>
      ))}
    </div>
  );
}

export interface ClarificationQuestionPanelProps {
  sessionId: string;
  session: SessionDetailResponse;
  readOnly?: boolean;
  title?: string;
  helpText?: string;
  /** When true, show “Generate draft now” if the session allows early finish. */
  showFinishButton?: boolean;
}

export function ClarificationQuestionPanel({
  sessionId,
  session,
  readOnly = false,
  title,
  helpText,
  showFinishButton = false,
}: ClarificationQuestionPanelProps) {
  const answer = useAnswerClarification(sessionId);
  const complete = useCompleteClarification(sessionId);
  const suggest = useSuggestClarification(sessionId);
  const locals = useAskTheLocals(sessionId);
  const userSettings = useUserSettings();
  const llmHealth = useQuery({
    queryKey: ["health", "llm"],
    queryFn: fetchLlmHealth,
    staleTime: 15_000,
  });
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [customAnswer, setCustomAnswer] = useState("");
  const [suggestionModel, setSuggestionModel] = useState<"lightweight" | "large">("lightweight");
  const [proposedAnswer, setProposedAnswer] = useState("");
  const activeQuestion = useRef("");
  const [modelSuggestions, setModelSuggestions] = useState<ClarificationSuggestionsResponse | null>(
    null,
  );
  const [localsInsight, setLocalsInsight] = useState<AskTheLocalsResponse | null>(null);
  const [localsCopied, setLocalsCopied] = useState(false);

  const questionKey = `${session.clarification_question_number ?? 0}:${session.clarification_field ?? ""}`;

  activeQuestion.current = questionKey;
  useEffect(() => {
    setProposedAnswer("");
    setSelectedOptions([]);
    setCustomAnswer("");
    setModelSuggestions(null);
    setLocalsInsight(null);
    setLocalsCopied(false);
  }, [questionKey]);

  const questionNumber = session.clarification_question_number ?? 1;
  const totalQuestions = session.clarification_total_questions ?? 16;
  const canFinish = showFinishButton && (session.clarification_can_finish ?? false);
  // Keep quick replies usable while Ask The Locals is in flight.
  const isBusy = answer.isPending || complete.isPending;
  const combinedAnswer = buildClarificationAnswer(selectedOptions, customAnswer);
  const canSubmit = combinedAnswer !== null;
  const modelEnabled = llmHealth.data?.llm_enabled === true && llmHealth.data.status === "ok";
  const localsOverrideActive = userSettings.data?.ask_the_locals_override_active === true;
  const localsEnabled =
    userSettings.data?.llm_enabled !== false && (localsOverrideActive || modelEnabled);
  const availability = userSettings.data?.clarification_versions ?? DEFAULT_VERSIONS;
  const versions = useMemo(
    () => session.clarification_versions ?? [],
    [session.clarification_versions],
  );
  const optionGuides = useMemo(
    () => session.clarification_quick_reply_guides ?? [],
    [session.clarification_quick_reply_guides],
  );
  const hasVersions = versions.length > 0;
  const customAnswerRef = useRef<HTMLTextAreaElement | null>(null);

  async function submitAnswer(value: string) {
    if (!value.trim()) {
      return;
    }
    try {
      await answer.mutateAsync(value.trim());
    } catch { /* Keep the draft answer available for retry. */ }
  }

  async function requestModelSuggestions() {
    const requestedQuestion = questionKey;
    try {
      const result = await suggest.mutateAsync({ current_answer: combinedAnswer ?? "", model: suggestionModel, field_name: session.clarification_field ?? undefined });
      if (activeQuestion.current !== requestedQuestion) return;
      setModelSuggestions(result);
      setProposedAnswer(result.proposed_answer ?? "");
    } catch { /* Error banner is supplied by the mutation. Manual answers remain usable. */ }
  }

  async function requestLocalsInsight() {
    const result = await locals.mutateAsync();
    setLocalsInsight(result);
    setLocalsCopied(false);

  }

  function useLocalsAnswer(text: string) {
    if (!text.trim() || selectedOptions.includes("unspecified")) {
      return;
    }
    setCustomAnswer(text.trim());
    window.requestAnimationFrame(() => {
      customAnswerRef.current?.focus();
      customAnswerRef.current?.select();
    });
  }

  async function copyLocalsRecommendation(text: string) {
    if (!text.trim()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setLocalsCopied(true);
      window.setTimeout(() => setLocalsCopied(false), 2000);
    } catch {
      setLocalsCopied(false);
    }
  }

  const localsCopyText =
    localsInsight?.recommended_answer?.trim() || localsInsight?.insight?.trim() || "";
  const localsHasInsight =
    Boolean(localsInsight?.insight?.trim()) &&
    localsInsight?.insight?.trim() !== localsCopyText;
  const localsIsShortAnswer =
    Boolean(localsInsight?.model_available) &&
    Boolean(localsCopyText) &&
    !localsHasInsight;

  const errorMessage =
    locals.error != null
      ? formatApiError(locals.error, "Ask The Locals failed.")
      : suggest.error != null
        ? formatApiError(suggest.error, "Could not fetch model suggestions.")
        : answer.error != null
          ? formatApiError(answer.error, "Clarification action failed.")
          : complete.error != null
            ? formatApiError(complete.error, "Clarification action failed.")
            : null;

  const defaultHelp = readOnly
    ? "Review the requirement card for answers captured during clarification."
    : "Pick quick replies and/or add custom text, then submit. Expand Beginner for option guides, or Ask The Locals for a contextual recommendation under your custom answer.";

  return (
    <Panel
      title={title}
      className={readOnly ? "clarification-instruction is-compact" : "clarification-instruction"}
    >
      {!readOnly && hasVersions && (
        <ClarificationVersionAccordions
          versions={versions}
          availability={availability}
          questionNumber={questionNumber}
          totalQuestions={totalQuestions}
          questionKey={questionKey}
          optionGuides={optionGuides}
        />
      )}
      {!readOnly && !hasVersions && session.clarification_question && (
        <p className="question-text">{session.clarification_question}</p>
      )}
      {modelSuggestions?.suggested_question && (
        <p className="muted model-suggested-question">
          Model rephrase: {modelSuggestions.suggested_question}
        </p>
      )}
      {session.clarification_field && !readOnly && (
        <p className="muted">
          Field: <code>{session.clarification_field}</code>
        </p>
      )}
      <p className="muted">{helpText ?? defaultHelp}</p>
      {!readOnly && (
        <>
          <div className="quick-replies" role="group" aria-label="Quick reply options">
            {(session.clarification_quick_replies ?? []).map((option) => {
              const isSelected = selectedOptions.includes(option);
              return (
                <button
                  key={option}
                  type="button"
                  className={isSelected ? "button secondary is-selected" : "button secondary"}
                  disabled={isBusy}
                  aria-pressed={isSelected}
                  onClick={() =>
                    setSelectedOptions((current) => toggleClarificationOption(current, option))
                  }
                >
                  {option}
                </button>
              );
            })}
          </div>
          <div className="button-row">
            <button
              type="button"
              className="button secondary"
              disabled={locals.isPending || !localsEnabled || answer.isPending}
              title={
                localsEnabled
                  ? localsOverrideActive
                    ? "Ask your configured Ask The Locals model for a short recommendation"
                    : "Ask the current AI tooling model for a short recommendation"
                  : "Configure AI tooling or an Ask The Locals API in Settings"
              }
              onClick={() => void requestLocalsInsight()}
            >
              {locals.isPending ? "Asking locals…" : "Ask The Locals"}
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={isBusy || suggest.isPending}
              title={
                modelEnabled
                  ? "Ask the local model for contextual answer suggestions"
                  : "Model unavailable — use quick replies or custom text"
              }
              onClick={() => void requestModelSuggestions()}
            >
              {suggest.isPending ? "Querying model…" : "Get model suggestions"}
            </button>
          </div>
          <label className="field">
            <span>Suggestion model</span>
            <select value={suggestionModel} onChange={(event) => setSuggestionModel(event.target.value as "lightweight" | "large")} disabled={suggest.isPending}>
              <option value="lightweight">Current lightweight model</option>
              <option value="large">Dedicated large clarification model</option>
            </select>
          </label>
          {suggest.isPending && <p role="status">Generating suggestions. Large models may take up to several minutes. You can continue manually.</p>}
          {modelSuggestions && (
            <div className="model-suggestions">
              <p className="muted">
                {modelSuggestions.message ??
                  (modelSuggestions.model_available
                    ? "Select any model suggestions below."
                    : "Model suggestions unavailable.")}
              </p>
              <p><strong>Your original answer:</strong> {modelSuggestions.original_answer || "No answer supplied"}</p>
              {proposedAnswer && <label className="field"><span>Model proposal — edit before accepting</span>
                <textarea aria-label="Model proposal" value={proposedAnswer} onChange={(event) => setProposedAnswer(event.target.value)} rows={4} maxLength={4096} />
              </label>}
              {(["recommendations", "assumptions", "conflicts", "follow_up_questions"] as const).map((kind) =>
                (modelSuggestions[kind]?.length ?? 0) > 0 && <div key={kind}>
                  <strong>{{ recommendations: "Recommendations (not requirements)", assumptions: "Unconfirmed assumptions", conflicts: "Conflicts with accepted answers", follow_up_questions: "Useful follow-up questions" }[kind]}</strong>
                  <ul>{modelSuggestions[kind]?.map((text, i) => <li key={i}>{text}</li>)}</ul>
                </div>)}
              <div className="button-row">
                <button type="button" disabled={!proposedAnswer.trim() || isBusy || Boolean(modelSuggestions.conflicts?.length)} onClick={() => { setSelectedOptions([]); setCustomAnswer(proposedAnswer); }}>Use edited proposal</button>
                <button type="button" onClick={() => { setModelSuggestions(null); setProposedAnswer(""); }}>Reject suggestion</button>
                <button type="button" disabled={suggest.isPending || isBusy} onClick={() => void requestModelSuggestions()}>Regenerate</button>
              </div>
              <p className="muted">Only Submit answer records your choice. Suggestions do not change accepted answers. Answer useful follow-ups in your custom text, or leave them explicitly open.</p>
              {modelSuggestions.suggested_answers.length > 0 && (
                <div className="quick-replies" role="group" aria-label="Model suggestions">
                  {modelSuggestions.suggested_answers.map((option) => {
                    const isSelected = selectedOptions.includes(option);
                    return (
                      <button
                        key={option}
                        type="button"
                        className={
                          isSelected
                            ? "button secondary is-selected is-model"
                            : "button secondary is-model"
                        }
                        disabled={isBusy}
                        aria-pressed={isSelected}
                        onClick={() =>
                          setSelectedOptions((current) =>
                            toggleClarificationOption(current, option),
                          )
                        }
                      >
                        {option}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          <label className="field">
            <span>Custom answer (optional)</span>
            <textarea
              ref={customAnswerRef}
              rows={3}
              value={customAnswer}
              onChange={(event) => setCustomAnswer(event.target.value)}
              placeholder="Add details or combine with the options above"
              disabled={selectedOptions.includes("unspecified")}
            />
          </label>
          {localsInsight && localsIsShortAnswer && (
            <div className="locals-short-answer" aria-live="polite">
              <p className="locals-short-answer-text">{localsCopyText}</p>
              <div className="button-row locals-copy-actions">
                <button
                  type="button"
                  className="button primary"
                  disabled={selectedOptions.includes("unspecified")}
                  onClick={() => useLocalsAnswer(localsCopyText)}
                >
                  Use answer
                </button>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => void copyLocalsRecommendation(localsCopyText)}
                >
                  {localsCopied ? "Copied" : "Copy"}
                </button>
              </div>
              <p className="muted locals-copy-meta">
                {localsInsight.message ?? "Short recommendation ready."}
                {localsInsight.model_source ? ` · ${localsInsight.model_source}` : ""}
              </p>
            </div>
          )}
          {localsInsight && !localsIsShortAnswer && (
            <div className="locals-insight locals-copy-window" aria-live="polite">
              <div className="locals-copy-header">
                <div>
                  <p className="locals-copy-title">Ask The Locals recommendation</p>
                  <p className="muted locals-copy-meta">
                    {localsInsight.message ??
                      (localsInsight.model_available
                        ? "Contextual recommendation"
                        : "Ask The Locals unavailable.")}
                    {localsInsight.model_source ? ` · ${localsInsight.model_source}` : ""}
                    {localsInsight.previous_answers_used.length > 0
                      ? ` · grounded in ${localsInsight.previous_answers_used.length} prior answer${
                          localsInsight.previous_answers_used.length === 1 ? "" : "s"
                        }`
                      : ""}
                  </p>
                </div>
                <div className="button-row locals-copy-actions">
                  <button
                    type="button"
                    className="button secondary"
                    disabled={!localsCopyText}
                    onClick={() => void copyLocalsRecommendation(localsCopyText)}
                  >
                    {localsCopied ? "Copied" : "Copy"}
                  </button>
                  <button
                    type="button"
                    className="button secondary"
                    disabled={!localsCopyText || selectedOptions.includes("unspecified")}
                    onClick={() => useLocalsAnswer(localsCopyText)}
                  >
                    Use answer
                  </button>
                </div>
              </div>
              {localsCopyText ? (
                <textarea
                  className="locals-copy-text"
                  rows={4}
                  readOnly
                  value={localsCopyText}
                  aria-label="Ask The Locals copyable recommendation"
                />
              ) : (
                <p className="muted">No recommendation text was returned.</p>
              )}
              {localsHasInsight && (
                <p className="locals-insight-body">{localsInsight.insight}</p>
              )}
            </div>
          )}
          {errorMessage && <ErrorBanner message={errorMessage} />}
          {(session.clarification_open_decisions?.length ?? 0) > 0 && <div role="status">
            <strong>Open decisions that may affect implementation</strong>
            <ul>{session.clarification_open_decisions?.map((field) => <li key={field}>{field.split(".").pop()?.replaceAll("_", " ")}</li>)}</ul>
            <p>You can continue with these open. No requirements will be assumed; use “Recommend an option” or explain a deliberate deferral.</p>
          </div>}
          <div className="button-row">
            <button
              type="button"
              className="button primary"
              disabled={isBusy || !canSubmit}
              onClick={() => combinedAnswer && void submitAnswer(combinedAnswer)}
            >
              {answer.isPending ? "Submitting…" : "Submit answer"}
            </button>
            {canFinish && (
              <button
                type="button"
                className="button secondary"
                disabled={isBusy}
                onClick={() => void complete.mutateAsync()}
              >
                {complete.isPending ? "Generating…" : "Generate draft now"}
              </button>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
