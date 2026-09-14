import { ModelSourceSettings } from "../components/ModelSourceSettings";
import { HardwareRecommendations } from "../components/HardwareRecommendations";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { LlmHealthResponse } from "@prompt-piper/shared";
import { formatApiError } from "../api/http";
import type { ApiEndpointUpdate, UserSettingsResponse } from "../api/types";
import { useUpdateUserSettings, useUserSettings } from "../api/hooks";
import { fetchLlmHealth } from "../api/sessions";
import { ErrorBanner, LoadingState, PageHeader, Panel, WarningBanner } from "../components/ui";

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

  if (settingsQuery.isLoading || !draft) {
    return <LoadingState label="Loading settings…" />;
  }

  if (settingsQuery.isError) {
    return (
      <div className="page narrow">
        <ErrorBanner message={formatApiError(settingsQuery.error, "Could not load settings.")} />
      </div>
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
    <div className="page narrow">
      <PageHeader
        title="Settings"
        subtitle="Runtime preferences for AI assistance, precision warnings, similarity scope, and external model APIs."
        actions={
          <Link to="/" className="button secondary">
            Back to dashboard
          </Link>
        }
      />

      <HardwareRecommendations />
      <ModelSourceSettings />
      <Panel title="AI assistance">
        <label className="field checkbox-field">
          <input
            type="checkbox"
            checked={draft.llm_enabled}
            onChange={(event) => setDraft({ ...draft, llm_enabled: event.target.checked })}
          />
          <span>Enable AI assistance (clarification, precision reranking)</span>
        </label>
        <p className="muted">
          When disabled, Nautilius Prompting Workbench uses CPU-only rule-based fallbacks. External send-to-model
          endpoints are configured separately below.
        </p>
        <div className="setup-ai-tooling">
          <p className="muted">
            <strong>Current AI tooling model</strong> ({draft.setup_ai_tooling.source})
          </p>
          <p>
            <code>{draft.setup_ai_tooling.chat_model}</code> at{" "}
            <code>{draft.setup_ai_tooling.base_url}</code>
          </p>
          {draft.ai_tooling_override_active && (
            <p className="muted">
              A saved override is configured and will replace this model after you restart the API.
              The test below probes the connection the API is using right now.
            </p>
          )}
          <p className="muted">
            Test connection probes the live API process. If make dev-api could not start
            llama-server (often no CUDA/ROCm GPU), it disables the chat model even when this
            panel still shows the configured model name.
          </p>
          <div className="button-row">
            <button
              type="button"
              className="button secondary"
              disabled={toolingTestPending || !draft.llm_enabled}
              title={
                draft.llm_enabled
                  ? "Probe the active AI tooling model endpoint"
                  : "Enable AI assistance to test the model connection"
              }
              onClick={() => void testCurrentAiTooling()}
            >
              {toolingTestPending ? "Testing…" : "Test connection"}
            </button>
          </div>
          {toolingTestError && <ErrorBanner message={toolingTestError} />}
          {toolingTestResult?.status === "ok" && (
            <div className="callout callout-ok" role="status">
              Connected to <code>{toolingTestResult.model_name}</code>
              {toolingTestResult.endpoint ? (
                <>
                  {" "}
                  at <code>{toolingTestResult.endpoint}</code>
                </>
              ) : null}
              {toolingTestResult.message ? ` — ${toolingTestResult.message}` : ""}
            </div>
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
              <WarningBanner
                message={`${toolingTestResult.status}: ${toolingTestResult.message}`}
              />
            )}
        </div>
      </Panel>

      <Panel title="Clarification question versions">
        <p className="muted">
          Choose which wording levels appear during clarification. Standard opens by default;
          Beginner and Advanced stay collapsed until expanded.
        </p>
        <label className="field checkbox-field">
          <input
            type="checkbox"
            checked={draft.clarification_versions.beginner}
            onChange={(event) =>
              setDraft({
                ...draft,
                clarification_versions: {
                  ...draft.clarification_versions,
                  beginner: event.target.checked,
                },
              })
            }
          />
          <span>Beginner — plain language with why-it-matters explanations</span>
        </label>
        <label className="field checkbox-field">
          <input
            type="checkbox"
            checked={draft.clarification_versions.standard}
            onChange={(event) =>
              setDraft({
                ...draft,
                clarification_versions: {
                  ...draft.clarification_versions,
                  standard: event.target.checked,
                },
              })
            }
          />
          <span>Standard — developer-oriented wording (default open)</span>
        </label>
        <label className="field checkbox-field">
          <input
            type="checkbox"
            checked={draft.clarification_versions.advanced}
            onChange={(event) =>
              setDraft({
                ...draft,
                clarification_versions: {
                  ...draft.clarification_versions,
                  advanced: event.target.checked,
                },
              })
            }
          />
          <span>Advanced — compact, thorough wording for experts</span>
        </label>
      </Panel>

      <Panel title="Semantic precision warning">
        <label className="field">
          <span>Warn when score is below {Math.round(draft.precision_warning_threshold * 100)}%</span>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={Math.round(draft.precision_warning_threshold * 100)}
            onChange={(event) =>
              setDraft({
                ...draft,
                precision_warning_threshold: Number(event.target.value) / 100,
              })
            }
          />
        </label>
      </Panel>

      <Panel title="Similarity time scope">
        <label className="field">
          <span>{draft.similarity_time_scope_labels[draft.similarity_time_scope_index]}</span>
          <input
            type="range"
            min={0}
            max={draft.similarity_time_scope_labels.length - 1}
            step={1}
            value={draft.similarity_time_scope_index}
            onChange={(event) =>
              setDraft({
                ...draft,
                similarity_time_scope_index: Number(event.target.value),
              })
            }
          />
        </label>
        <p className="muted">
          Limits which prior finalized prompts are considered during similarity checks.
        </p>
      </Panel>

      <Panel title="External API endpoints">
        <p className="muted">
          Up to six external OpenAI-compatible endpoints for send-to-model only. These do not
          include the local model from setup.
        </p>
        {draft.api_endpoints.map((endpoint, index) => (
          <div key={endpoint.id} className="endpoint-slot">
            <h3>Slot {index + 1}</h3>
            <label className="field">
              <span>Label</span>
              <input
                type="text"
                value={endpoint.label}
                onChange={(event) => updateEndpoint(index, { label: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Base URL</span>
              <input
                type="url"
                value={endpoint.base_url}
                placeholder="https://api.openai.com/v1"
                onChange={(event) => updateEndpoint(index, { base_url: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Model</span>
              <input
                type="text"
                value={endpoint.chat_model}
                placeholder="gpt-4o-mini"
                onChange={(event) => updateEndpoint(index, { chat_model: event.target.value })}
              />
            </label>
            <label className="field">
              <span>
                API key {endpoint.api_key_configured ? "(configured — leave blank to keep)" : ""}
              </span>
              <input
                type="password"
                value={apiKeyDrafts[index] ?? ""}
                autoComplete="off"
                onChange={(event) =>
                  setApiKeyDrafts((current) => {
                    const next = [...current];
                    next[index] = event.target.value;
                    return next;
                  })
                }
              />
            </label>
          </div>
        ))}
      </Panel>

      <Panel title="Alternative AI tooling API">
        <p className="muted">
          Optionally point clarification and precision reranking at a different OpenAI-compatible
          API. Replaces the setup wizard model after you restart the API (
          <code>make dev-api</code> or your container).
        </p>
        <label className="field">
          <span>Label</span>
          <input
            type="text"
            value={draft.ai_tooling_api_override.label}
            onChange={(event) =>
              setDraft({
                ...draft,
                ai_tooling_api_override: {
                  ...draft.ai_tooling_api_override,
                  label: event.target.value,
                },
              })
            }
          />
        </label>
        <label className="field">
          <span>Base URL</span>
          <input
            type="url"
            value={draft.ai_tooling_api_override.base_url}
            placeholder="https://api.openai.com/v1"
            onChange={(event) =>
              setDraft({
                ...draft,
                ai_tooling_api_override: {
                  ...draft.ai_tooling_api_override,
                  base_url: event.target.value,
                },
              })
            }
          />
        </label>
        <label className="field">
          <span>Model</span>
          <input
            type="text"
            value={draft.ai_tooling_api_override.chat_model}
            placeholder="gpt-4o-mini"
            onChange={(event) =>
              setDraft({
                ...draft,
                ai_tooling_api_override: {
                  ...draft.ai_tooling_api_override,
                  chat_model: event.target.value,
                },
              })
            }
          />
        </label>
        <label className="field">
          <span>
            API key{" "}
            {draft.ai_tooling_api_override.api_key_configured
              ? "(configured — leave blank to keep)"
              : ""}
          </span>
          <input
            type="password"
            value={aiToolingApiKeyDraft}
            autoComplete="off"
            onChange={(event) => setAiToolingApiKeyDraft(event.target.value)}
          />
        </label>
      </Panel>

      <Panel title="Ask The Locals API">
        <p className="muted">
          Optional OpenAI-compatible API used only by the Ask The Locals button during
          clarification. When blank, Ask The Locals uses the current AI tooling model. Takes effect
          immediately (no API restart).
        </p>
        <label className="field">
          <span>Label</span>
          <input
            type="text"
            value={draft.ask_the_locals_api_override.label}
            onChange={(event) =>
              setDraft({
                ...draft,
                ask_the_locals_api_override: {
                  ...draft.ask_the_locals_api_override,
                  label: event.target.value,
                },
              })
            }
          />
        </label>
        <label className="field">
          <span>Base URL</span>
          <input
            type="url"
            value={draft.ask_the_locals_api_override.base_url}
            placeholder="https://api.openai.com/v1"
            onChange={(event) =>
              setDraft({
                ...draft,
                ask_the_locals_api_override: {
                  ...draft.ask_the_locals_api_override,
                  base_url: event.target.value,
                },
              })
            }
          />
        </label>
        <label className="field">
          <span>Model</span>
          <input
            type="text"
            value={draft.ask_the_locals_api_override.chat_model}
            placeholder="gpt-4o-mini"
            onChange={(event) =>
              setDraft({
                ...draft,
                ask_the_locals_api_override: {
                  ...draft.ask_the_locals_api_override,
                  chat_model: event.target.value,
                },
              })
            }
          />
        </label>
        <label className="field">
          <span>
            API key{" "}
            {draft.ask_the_locals_api_override.api_key_configured
              ? "(configured — leave blank to keep)"
              : ""}
          </span>
          <input
            type="password"
            value={askTheLocalsApiKeyDraft}
            autoComplete="off"
            onChange={(event) => setAskTheLocalsApiKeyDraft(event.target.value)}
          />
        </label>
      </Panel>

      {saveError && <ErrorBanner message={saveError} />}
      <div className="button-row">
        <button
          type="button"
          className="button primary"
          disabled={saveSettings.isPending}
          onClick={() =>
            void saveSettings.mutateAsync(
              toUpdatePayload(draft, apiKeyDrafts, aiToolingApiKeyDraft, askTheLocalsApiKeyDraft),
            )
          }
        >
          {saveSettings.isPending ? "Saving…" : "Save settings"}
        </button>
      </div>
    </div>
  );
}
