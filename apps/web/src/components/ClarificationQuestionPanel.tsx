import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  ClipboardCopy,
  Content,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
  ExpandableSection,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Title,
  ToggleGroup,
  ToggleGroupItem,
} from "@patternfly/react-core";
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
import { ButtonRow, ErrorBanner, Panel, TextAreaField } from "./ui";

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
    <div>
      <Title headingLevel="h4" size="md">
        What each default option means
      </Title>
      <DescriptionList isCompact>
        {guides.map((guide) => (
          <DescriptionListGroup key={guide.option}>
            <DescriptionListTerm>{guide.option}</DescriptionListTerm>
            <DescriptionListDescription>
              <Content component="p">{guide.explanation}</Content>
              <Content component="p">
                <strong>Best when: </strong>
                {guide.when_to_use}
              </Content>
            </DescriptionListDescription>
          </DescriptionListGroup>
        ))}
      </DescriptionList>
    </div>
  );
}

function VersionSection({
  version,
  defaultExpanded,
  questionNumber,
  totalQuestions,
  sharedRationale,
  optionGuides,
}: {
  version: ClarificationVersionText;
  defaultExpanded: boolean;
  questionNumber: number;
  totalQuestions: number;
  sharedRationale: string | null | undefined;
  optionGuides: QuickReplyGuide[];
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  return (
    <ExpandableSection
      isExpanded={isExpanded}
      onToggle={(_event, expanded) => setIsExpanded(expanded)}
      toggleContent={
        <>
          <span>{version.label}</span>{" "}
          <span>
            Question {questionNumber} of {totalQuestions}
          </span>
        </>
      }
    >
      <Content component="p">{version.prompt}</Content>
      {(version.rationale || sharedRationale) && (
        <Content component="p">
          <span>Why this matters: </span>
          {version.rationale || sharedRationale}
        </Content>
      )}
      {(version.blind_spots?.length ?? 0) > 0 && (
        <div>
          <Content component="p">Potential blind spots (unconfirmed)</Content>
          <Content component="ul">
            {version.blind_spots?.map((spot, index) => (
              <Content key={index} component="li">
                {spot}
              </Content>
            ))}
          </Content>
        </div>
      )}
      {version.level === "beginner" && <BeginnerOptionGuides guides={optionGuides} />}
    </ExpandableSection>
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
  // Older saved questions supplied an explanation only in the beginner wording.
  const sharedRationale = versions.find((version) => version.rationale)?.rationale;

  return (
    <div key={questionKey} role="group" aria-label="Question wording versions">
      {visible.map((version) => (
        <VersionSection
          key={version.level}
          version={version}
          defaultExpanded={version.level === "standard"}
          questionNumber={questionNumber}
          totalQuestions={totalQuestions}
          sharedRationale={sharedRationale}
          optionGuides={optionGuides}
        />
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

  const questionKey = `${session.clarification_question_number ?? 0}:${session.clarification_field ?? ""}`;

  activeQuestion.current = questionKey;
  useEffect(() => {
    setProposedAnswer("");
    setSelectedOptions([]);
    setCustomAnswer("");
    setModelSuggestions(null);
    setLocalsInsight(null);
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
    : "Answer one question at a time to sharpen your prompt goal. With AI assistance, the model prioritizes open decisions, explains why they matter, and highlights potential blind spots for you to confirm. Quick replies and custom answers also work offline.";

  const suggestionLabels = {
    recommendations: "Recommendations (not requirements)",
    assumptions: "Unconfirmed assumptions",
    conflicts: "Conflicts with accepted answers",
    follow_up_questions: "Useful follow-up questions",
  } as const;

  return (
    <Panel title={title}>
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
        <Content component="p">{session.clarification_question}</Content>
      )}
      {modelSuggestions?.suggested_question && (
        <Content component="small">Model rephrase: {modelSuggestions.suggested_question}</Content>
      )}
      {session.clarification_field && !readOnly && (
        <Content component="small">
          Field: <code>{session.clarification_field}</code>
        </Content>
      )}
      <Content component="small">{helpText ?? defaultHelp}</Content>
      {!readOnly && (
        <>
          <ToggleGroup aria-label="Quick reply options">
            {(session.clarification_quick_replies ?? []).map((option) => {
              const isSelected = selectedOptions.includes(option);
              return (
                <ToggleGroupItem
                  key={option}
                  text={option}
                  isSelected={isSelected}
                  isDisabled={isBusy}
                  onChange={() =>
                    setSelectedOptions((current) => toggleClarificationOption(current, option))
                  }
                />
              );
            })}
          </ToggleGroup>
          <ButtonRow>
            <Button
              variant="secondary"
              isDisabled={locals.isPending || !localsEnabled || answer.isPending}
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
            </Button>
            <Button
              variant="secondary"
              isDisabled={isBusy || suggest.isPending}
              title={
                modelEnabled
                  ? "Ask the local model for contextual answer suggestions"
                  : "Model unavailable — use quick replies or custom text"
              }
              onClick={() => void requestModelSuggestions()}
            >
              {suggest.isPending ? "Querying model…" : "Get model suggestions"}
            </Button>
          </ButtonRow>
          <FormGroup label="Suggestion model" fieldId="suggestion-model">
            <FormSelect
              id="suggestion-model"
              value={suggestionModel}
              onChange={(_event, value) => setSuggestionModel(value as "lightweight" | "large")}
              isDisabled={suggest.isPending}
              aria-label="Suggestion model"
            >
              <FormSelectOption value="lightweight" label="Current lightweight model" />
              <FormSelectOption value="large" label="Dedicated large clarification model" />
            </FormSelect>
          </FormGroup>
          {suggest.isPending && (
            <p role="status">
              Generating suggestions. Large models may take up to several minutes. You can continue manually.
            </p>
          )}
          {modelSuggestions && (
            <div>
              <Content component="small">
                {modelSuggestions.message ??
                  (modelSuggestions.model_available
                    ? "Select any model suggestions below."
                    : "Model suggestions unavailable.")}
              </Content>
              <Content component="p">
                <strong>Your original answer:</strong> {modelSuggestions.original_answer || "No answer supplied"}
              </Content>
              {proposedAnswer && (
                <TextAreaField
                  id="model-proposal"
                  label="Model proposal"
                  ariaLabel="Model proposal"
                  value={proposedAnswer}
                  onChange={setProposedAnswer}
                  rows={4}
                  maxLength={4096}
                />
              )}
              {(["recommendations", "assumptions", "conflicts", "follow_up_questions"] as const).map(
                (kind) =>
                  (modelSuggestions[kind]?.length ?? 0) > 0 && (
                    <div key={kind}>
                      <strong>{suggestionLabels[kind]}</strong>
                      <Content component="ul">
                        {modelSuggestions[kind]?.map((text, index) => (
                          <Content key={index} component="li">
                            {text}
                          </Content>
                        ))}
                      </Content>
                    </div>
                  ),
              )}
              <ButtonRow>
                <Button
                  variant="secondary"
                  isDisabled={!proposedAnswer.trim() || isBusy || Boolean(modelSuggestions.conflicts?.length)}
                  onClick={() => {
                    setSelectedOptions([]);
                    setCustomAnswer(proposedAnswer);
                  }}
                >
                  Use edited proposal
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setModelSuggestions(null);
                    setProposedAnswer("");
                  }}
                >
                  Reject suggestion
                </Button>
                <Button
                  variant="secondary"
                  isDisabled={suggest.isPending || isBusy}
                  onClick={() => void requestModelSuggestions()}
                >
                  Regenerate
                </Button>
              </ButtonRow>
              <Content component="small">
                Only Submit answer records your choice. Suggestions do not change accepted answers. Answer useful follow-ups in your custom text, or leave them explicitly open.
              </Content>
              {modelSuggestions.suggested_answers.length > 0 && (
                <ToggleGroup aria-label="Model suggestions">
                  {modelSuggestions.suggested_answers.map((option) => {
                    const isSelected = selectedOptions.includes(option);
                    return (
                      <ToggleGroupItem
                        key={option}
                        text={option}
                        isSelected={isSelected}
                        isDisabled={isBusy}
                        onChange={() =>
                          setSelectedOptions((current) => toggleClarificationOption(current, option))
                        }
                      />
                    );
                  })}
                </ToggleGroup>
              )}
            </div>
          )}
          <TextAreaField
            id="custom-answer"
            label="Custom answer (optional)"
            inputRef={customAnswerRef}
            rows={3}
            value={customAnswer}
            onChange={setCustomAnswer}
            placeholder="Add details or combine with the options above"
            isDisabled={selectedOptions.includes("unspecified")}
          />
          {localsInsight && localsIsShortAnswer && (
            <div aria-live="polite">
              <ClipboardCopy
                isReadOnly
                hoverTip="Copy"
                clickTip="Copied"
                variant="expansion"
                isExpanded
              >
                {localsCopyText}
              </ClipboardCopy>
              <Button
                variant="primary"
                isDisabled={selectedOptions.includes("unspecified")}
                onClick={() => useLocalsAnswer(localsCopyText)}
              >
                Use answer
              </Button>
              <Content component="small">
                {localsInsight.message ?? "Short recommendation ready."}
                {localsInsight.model_source ? ` · ${localsInsight.model_source}` : ""}
              </Content>
            </div>
          )}
          {localsInsight && !localsIsShortAnswer && (
            <div aria-live="polite">
              <Title headingLevel="h3" size="md">
                Ask The Locals recommendation
              </Title>
              <Content component="small">
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
              </Content>
              <Button
                variant="secondary"
                isDisabled={!localsCopyText || selectedOptions.includes("unspecified")}
                onClick={() => useLocalsAnswer(localsCopyText)}
              >
                Use answer
              </Button>
              {localsCopyText ? (
                <ClipboardCopy
                  isReadOnly
                  hoverTip="Copy"
                  clickTip="Copied"
                  variant="expansion"
                  isExpanded
                  textAriaLabel="Ask The Locals copyable recommendation"
                >
                  {localsCopyText}
                </ClipboardCopy>
              ) : (
                <Content component="small">No recommendation text was returned.</Content>
              )}
              {localsHasInsight && <Content component="p">{localsInsight.insight}</Content>}
            </div>
          )}
          {errorMessage && <ErrorBanner message={errorMessage} />}
          {(session.clarification_open_decisions?.length ?? 0) > 0 && (
            <div role="status">
              <strong>Open decisions that may affect implementation</strong>
              <Content component="ul">
                {session.clarification_open_decisions?.map((field) => (
                  <Content key={field} component="li">
                    {field.split(".").pop()?.replaceAll("_", " ")}
                  </Content>
                ))}
              </Content>
              <Content component="p">
                You can continue with these open. No requirements will be assumed; use “Recommend an option” or explain a deliberate deferral.
              </Content>
            </div>
          )}
          <ButtonRow>
            <Button
              variant="primary"
              isDisabled={isBusy || !canSubmit}
              onClick={() => combinedAnswer && void submitAnswer(combinedAnswer)}
            >
              {answer.isPending ? "Submitting…" : "Submit answer"}
            </Button>
            {canFinish && (
              <Button variant="secondary" isDisabled={isBusy} onClick={() => void complete.mutateAsync()}>
                {complete.isPending ? "Generating…" : "Generate draft now"}
              </Button>
            )}
          </ButtonRow>
        </>
      )}
    </Panel>
  );
}
