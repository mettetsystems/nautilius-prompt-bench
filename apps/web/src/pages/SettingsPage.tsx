import { ModelSourceSettings } from "../components/ModelSourceSettings";
import { HardwareRecommendations } from "../components/HardwareRecommendations";
import { useEffect, useState } from "react";
import { Button, Checkbox, Content, FormGroup, Slider, Title } from "@patternfly/react-core";
import type { LlmHealthResponse } from "@prompt-piper/shared";
import { formatApiError } from "../api/http";
import type { ApiEndpointUpdate, UserSettingsResponse } from "../api/types";
import { useUpdateUserSettings, useUserSettings } from "../api/hooks";
import { fetchLlmHealth } from "../api/sessions";
import {
  ErrorBanner,
  LinkButton,
  LoadingState,
  PageFrame,
  PageHeader,
  Panel,
  SuccessBanner,
  TextField,
  WarningBanner,
} from "../components/ui";

function toUpdatePayload(
  settings: UserSettingsResponse,
  apiKeyDrafts: string[],
  aiToolingApiKeyDraft: string,
  askTheLocalsApiKeyDraft: string,
) {
  const aiToolingOverride = {
    label: settings.ai_tooling_api_override.label,
    base_url: settings.ai_tooling_api_override.base_url,
    chat_model: settings.ai_tooling_api_override.chat_model,
  };
  const aiToolingKey = aiToolingApiKeyDraft.trim();
  const localsOverride = {
    label: settings.ask_the_locals_api_override.label,
    base_url: settings.ask_the_locals_api_override.base_url,
    chat_model: settings.ask_the_locals_api_override.chat_model,
  };
  const localsKey = askTheLocalsApiKeyDraft.trim();
  return {
    llm_enabled: settings.llm_enabled,
    precision_warning_threshold: settings.precision_warning_threshold,
    similarity_time_scope_index: settings.similarity_time_scope_index,
    clarification_versions: settings.clarification_versions,
    default_api_endpoint_id: settings.default_api_endpoint_id,
    ai_tooling_api_override: aiToolingKey
      ? { ...aiToolingOverride, api_key: aiToolingKey }
      : aiToolingOverride,
    ask_the_locals_api_override: localsKey
      ? { ...localsOverride, api_key: localsKey }
      : localsOverride,
    api_endpoints: settings.api_endpoints.map((endpoint, index) => {
      const update: ApiEndpointUpdate = {
        id: endpoint.id,
        label: endpoint.label,
        base_url: endpoint.base_url,
        chat_model: endpoint.chat_model,
      };
      const draft = apiKeyDrafts[index]?.trim();
      if (draft) {
        update.api_key = draft;
      }
      return update;
    }),
  };
}

export function SettingsPage() {
  const settingsQuery = useUserSettings();
  const saveSettings = useUpdateUserSettings();
  const [draft, setDraft] = useState<UserSettingsResponse | null>(null);
  const [apiKeyDrafts, setApiKeyDrafts] = useState<string[]>(Array(6).fill(""));
  const [aiToolingApiKeyDraft, setAiToolingApiKeyDraft] = useState("");
  const [askTheLocalsApiKeyDraft, setAskTheLocalsApiKeyDraft] = useState("");
  const [toolingTestPending, setToolingTestPending] = useState(false);
  const [toolingTestResult, setToolingTestResult] = useState<LlmHealthResponse | null>(null);
  const [toolingTestError, setToolingTestError] = useState<string | null>(null);

  useEffect(() => {
    if (settingsQuery.data) {
      setDraft(settingsQuery.data);
      setApiKeyDrafts(Array(settingsQuery.data.max_api_endpoint_slots).fill(""));
      setAiToolingApiKeyDraft("");
      setAskTheLocalsApiKeyDraft("");
      setToolingTestResult(null);
      setToolingTestError(null);
    }
  }, [settingsQuery.data]);

  if (settingsQuery.isError) {
    return (
      <PageFrame limited>
        <PageHeader
          title="Settings"
          subtitle="Runtime preferences for AI assistance, precision warnings, similarity scope, and external model APIs."
        />
        <ErrorBanner message={formatApiError(settingsQuery.error, "Could not load settings.")} />
      </PageFrame>
    );
  }

  if (settingsQuery.isLoading || !draft) {
    return (
      <PageFrame limited>
        <LoadingState label="Loading settings…" />
      </PageFrame>
    );
  }

  const saveError =
    saveSettings.error != null
      ? formatApiError(saveSettings.error, "Could not save settings.")
      : null;

  function updateEndpoint(index: number, patch: Partial<ApiEndpointUpdate>) {
    setDraft((current) => {
      if (!current) {
        return current;
      }
      const endpoints = current.api_endpoints.map((endpoint, slot) =>
        slot === index ? { ...endpoint, ...patch } : endpoint,
      );
      return { ...current, api_endpoints: endpoints };
    });
  }

  async function testCurrentAiTooling() {
    setToolingTestPending(true);
    setToolingTestError(null);
    setToolingTestResult(null);
    try {
      const result = await fetchLlmHealth();
      setToolingTestResult(result);
    } catch (error) {
      setToolingTestError(formatApiError(error, "Could not reach the AI tooling health check."));
    } finally {
      setToolingTestPending(false);
    }
  }

  return (
    <PageFrame limited>
      <PageHeader
        title="Settings"
        subtitle="Runtime preferences for AI assistance, precision warnings, similarity scope, and external model APIs."
        actions={
          <LinkButton to="/" variant="secondary">
            Back to dashboard
          </LinkButton>
        }
      />

      <HardwareRecommendations />
      <ModelSourceSettings />
      <Panel title="AI assistance">
        <Checkbox
          id="llm-enabled"
          label="Enable AI assistance (clarification, precision reranking)"
          isChecked={draft.llm_enabled}
          onChange={(_event, checked) => setDraft({ ...draft, llm_enabled: checked })}
        />
        <Content component="small">
          When disabled, Nautilius Prompting Workbench uses CPU-only rule-based fallbacks. External send-to-model
          endpoints are configured separately below.
        </Content>
        <div>
          <Content component="p">
            <strong>Current AI tooling model</strong> ({draft.setup_ai_tooling.source})
          </Content>
          <Content component="p">
            <code>{draft.setup_ai_tooling.chat_model}</code> at <code>{draft.setup_ai_tooling.base_url}</code>
          </Content>
          {draft.ai_tooling_override_active && (
            <Content component="small">
              A saved override is configured and will replace this model after you restart the API.
              The test below probes the connection the API is using right now.
            </Content>
          )}
          <Content component="small">
            Test connection probes the live API process. If make dev-api could not start
            llama-server (often no CUDA/ROCm GPU), it disables the chat model even when this
            panel still shows the configured model name.
          </Content>
          <Button
            variant="secondary"
            isDisabled={toolingTestPending || !draft.llm_enabled}
            title={
              draft.llm_enabled
                ? "Probe the active AI tooling model endpoint"
                : "Enable AI assistance to test the model connection"
            }
            onClick={() => void testCurrentAiTooling()}
          >
            {toolingTestPending ? "Testing…" : "Test connection"}
          </Button>
          {toolingTestError && <ErrorBanner message={toolingTestError} />}
          {toolingTestResult?.status === "ok" && (
            <SuccessBanner
              message={`Connected to ${toolingTestResult.model_name ?? "the model"}${
                toolingTestResult.endpoint ? ` at ${toolingTestResult.endpoint}` : ""
              }${toolingTestResult.message ? ` — ${toolingTestResult.message}` : ""}`}
            />
          )}
          {toolingTestResult && toolingTestResult.status === "disabled" && (
            <WarningBanner
              message={
                toolingTestResult.message ||
                "AI tooling is disabled. Enable AI assistance to use the model."
              }
            />
          )}
          {toolingTestResult && toolingTestResult.status === "unreachable" && (
            <ErrorBanner
              message={
                toolingTestResult.message ||
                `Could not reach ${toolingTestResult.model_name ?? "the model"} at ${
                  toolingTestResult.endpoint ?? "the configured endpoint"
                }.`
              }
            />
          )}
          {toolingTestResult &&
            toolingTestResult.status !== "ok" &&
            toolingTestResult.status !== "disabled" &&
            toolingTestResult.status !== "unreachable" && (
              <WarningBanner message={`${toolingTestResult.status}: ${toolingTestResult.message}`} />
            )}
        </div>
      </Panel>

      <Panel title="Clarification question versions">
        <Content component="small">
          Choose which wording levels appear during clarification. Standard opens by default;
          Beginner and Advanced stay collapsed until expanded.
        </Content>
        <Checkbox
          id="clarification-beginner"
          label="Beginner — plain language with why-it-matters explanations"
          isChecked={draft.clarification_versions.beginner}
          onChange={(_event, checked) =>
            setDraft({
              ...draft,
              clarification_versions: { ...draft.clarification_versions, beginner: checked },
            })
          }
        />
        <Checkbox
          id="clarification-standard"
          label="Standard — developer-oriented wording (default open)"
          isChecked={draft.clarification_versions.standard}
          onChange={(_event, checked) =>
            setDraft({
              ...draft,
              clarification_versions: { ...draft.clarification_versions, standard: checked },
            })
          }
        />
        <Checkbox
          id="clarification-advanced"
          label="Advanced — compact, thorough wording for experts"
          isChecked={draft.clarification_versions.advanced}
          onChange={(_event, checked) =>
            setDraft({
              ...draft,
              clarification_versions: { ...draft.clarification_versions, advanced: checked },
            })
          }
        />
      </Panel>

      <Panel title="Semantic precision warning">
        <FormGroup
          label={`Warn when score is below ${Math.round(draft.precision_warning_threshold * 100)}%`}
          fieldId="precision-threshold"
        >
          <Slider
            min={0}
            max={100}
            step={5}
            value={Math.round(draft.precision_warning_threshold * 100)}
            inputAriaLabel="Precision warning threshold"
            onChange={(_event, value) =>
              setDraft({
                ...draft,
                precision_warning_threshold: value / 100,
              })
            }
          />
        </FormGroup>
      </Panel>

      <Panel title="Similarity time scope">
        <FormGroup
          label={draft.similarity_time_scope_labels[draft.similarity_time_scope_index]}
          fieldId="similarity-scope"
        >
          <Slider
            min={0}
            max={draft.similarity_time_scope_labels.length - 1}
            step={1}
            value={draft.similarity_time_scope_index}
            inputAriaLabel="Similarity time scope"
            onChange={(_event, value) =>
              setDraft({
                ...draft,
                similarity_time_scope_index: value,
              })
            }
          />
        </FormGroup>
        <Content component="small">
          Limits which prior finalized prompts are considered during similarity checks.
        </Content>
      </Panel>

      <Panel title="External API endpoints">
        <Content component="small">
          Up to six external OpenAI-compatible endpoints for send-to-model only. These do not
          include the local model from setup.
        </Content>
        {draft.api_endpoints.map((endpoint, index) => (
          <div key={endpoint.id}>
            <Title headingLevel="h3" size="md">
              Slot {index + 1}
            </Title>
            <TextField
              id={`endpoint-${index}-label`}
              label="Label"
              value={endpoint.label}
              onChange={(value) => updateEndpoint(index, { label: value })}
            />
            <TextField
              id={`endpoint-${index}-url`}
              label="Base URL"
              type="url"
              value={endpoint.base_url}
              placeholder="https://api.openai.com/v1"
              onChange={(value) => updateEndpoint(index, { base_url: value })}
            />
            <TextField
              id={`endpoint-${index}-model`}
              label="Model"
              value={endpoint.chat_model}
              placeholder="gpt-4o-mini"
              onChange={(value) => updateEndpoint(index, { chat_model: value })}
            />
            <TextField
              id={`endpoint-${index}-key`}
              label={`API key ${endpoint.api_key_configured ? "(configured — leave blank to keep)" : ""}`}
              type="password"
              autoComplete="off"
              value={apiKeyDrafts[index] ?? ""}
              onChange={(value) =>
                setApiKeyDrafts((current) => {
                  const next = [...current];
                  next[index] = value;
                  return next;
                })
              }
            />
          </div>
        ))}
      </Panel>

      <Panel title="Alternative AI tooling API">
        <Content component="small">
          Optionally point clarification and precision reranking at a different OpenAI-compatible
          API. Replaces the setup wizard model after you restart the API (<code>make dev-api</code> or
          your container).
        </Content>
        <TextField
          id="ai-tooling-label"
          label="Label"
          value={draft.ai_tooling_api_override.label}
          onChange={(value) =>
            setDraft({
              ...draft,
              ai_tooling_api_override: { ...draft.ai_tooling_api_override, label: value },
            })
          }
        />
        <TextField
          id="ai-tooling-url"
          label="Base URL"
          type="url"
          value={draft.ai_tooling_api_override.base_url}
          placeholder="https://api.openai.com/v1"
          onChange={(value) =>
            setDraft({
              ...draft,
              ai_tooling_api_override: { ...draft.ai_tooling_api_override, base_url: value },
            })
          }
        />
        <TextField
          id="ai-tooling-model"
          label="Model"
          value={draft.ai_tooling_api_override.chat_model}
          placeholder="gpt-4o-mini"
          onChange={(value) =>
            setDraft({
              ...draft,
              ai_tooling_api_override: { ...draft.ai_tooling_api_override, chat_model: value },
            })
          }
        />
        <TextField
          id="ai-tooling-key"
          label={`API key ${
            draft.ai_tooling_api_override.api_key_configured ? "(configured — leave blank to keep)" : ""
          }`}
          type="password"
          autoComplete="off"
          value={aiToolingApiKeyDraft}
          onChange={setAiToolingApiKeyDraft}
        />
      </Panel>

      <Panel title="Ask The Locals API">
        <Content component="small">
          Optional OpenAI-compatible API used only by the Ask The Locals button during
          clarification. When blank, Ask The Locals uses the current AI tooling model. Takes effect
          immediately (no API restart).
        </Content>
        <TextField
          id="locals-label"
          label="Label"
          value={draft.ask_the_locals_api_override.label}
          onChange={(value) =>
            setDraft({
              ...draft,
              ask_the_locals_api_override: { ...draft.ask_the_locals_api_override, label: value },
            })
          }
        />
        <TextField
          id="locals-url"
          label="Base URL"
          type="url"
          value={draft.ask_the_locals_api_override.base_url}
          placeholder="https://api.openai.com/v1"
          onChange={(value) =>
            setDraft({
              ...draft,
              ask_the_locals_api_override: { ...draft.ask_the_locals_api_override, base_url: value },
            })
          }
        />
        <TextField
          id="locals-model"
          label="Model"
          value={draft.ask_the_locals_api_override.chat_model}
          placeholder="gpt-4o-mini"
          onChange={(value) =>
            setDraft({
              ...draft,
              ask_the_locals_api_override: { ...draft.ask_the_locals_api_override, chat_model: value },
            })
          }
        />
        <TextField
          id="locals-key"
          label={`API key ${
            draft.ask_the_locals_api_override.api_key_configured
              ? "(configured — leave blank to keep)"
              : ""
          }`}
          type="password"
          autoComplete="off"
          value={askTheLocalsApiKeyDraft}
          onChange={setAskTheLocalsApiKeyDraft}
        />
      </Panel>

      {saveError && <ErrorBanner message={saveError} />}
      <Button
        variant="primary"
        isDisabled={saveSettings.isPending}
        onClick={() =>
          void saveSettings.mutateAsync(
            toUpdatePayload(draft, apiKeyDrafts, aiToolingApiKeyDraft, askTheLocalsApiKeyDraft),
          )
        }
      >
        {saveSettings.isPending ? "Saving…" : "Save settings"}
      </Button>
    </PageFrame>
  );
}
