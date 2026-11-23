import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Checkbox, Content, Flex, FormGroup, FormSelect, FormSelectOption } from "@patternfly/react-core";
import { formatApiError } from "../api/http";
import type { SendToInferenceResponse, SessionDetailResponse } from "../api/types";
import { queryKeys, useGenerateArtifacts, useSendToInference } from "../api/hooks";
import { fetchInferenceSettings, fetchLlmHealth } from "../api/sessions";
import { buildExportFolderPreview } from "../lib/exportFolder";
import { sessionPath, sessionStepForState } from "../lib/sessionRouting";
import { ButtonRow, DraftBlock, ErrorBanner, LinkButton, PageFrame, PageHeader, Panel, TextField, WarningBanner } from "../components/ui";
import { SessionTemplateButton } from "../components/SessionTemplateButton";

interface ExportPageProps {
  sessionId: string;
  session: SessionDetailResponse;
  readOnly?: boolean;
}

export function ExportPage({ sessionId, session, readOnly = false }: ExportPageProps) {
  const navigate = useNavigate();
  const generate = useGenerateArtifacts(sessionId);
  const defaultFolderLabel = session.session.title;
  const [folderLabel, setFolderLabel] = useState(defaultFolderLabel);
  const folderPreview = useMemo(
    () => buildExportFolderPreview(folderLabel || defaultFolderLabel),
    [defaultFolderLabel, folderLabel],
  );

  const errorMessage =
    generate.error != null ? formatApiError(generate.error, "Artifact generation failed.") : null;

  return (
    <PageFrame>
      <PageHeader
        title="Export artifacts"
        subtitle="Generate stable local artifacts: rendered prompts plus coding_prompt_spec.json/yaml."
      />

      {session.registry_warning && <WarningBanner message={session.registry_warning} />}

      <Panel>
        <Content component="p">
          Prompt ID: <code>{session.prompt_id ?? session.session.prompt_id}</code>
        </Content>
        <Content component="small">
          Artifacts are written under the configured export root (native dev:{" "}
          <code>./data/artifacts/</code> in the repo).
        </Content>
        {!readOnly && (
          <>
            <TextField
              id="export-folder-label"
              label="Export folder label"
              value={folderLabel}
              onChange={setFolderLabel}
              placeholder={defaultFolderLabel}
            />
            <Content component="small">
              Folder name preview: <code>{folderPreview}</code>
            </Content>
            <Content component="small">
              Uses your session title by default (from the new-session screen). Edit the label
              above for a shorter name, or leave it unchanged.
            </Content>
          </>
        )}
        {errorMessage && <ErrorBanner message={errorMessage} />}
        {session.artifact_warning && <WarningBanner message={session.artifact_warning} />}
        {!readOnly && (
          <Button
            variant="primary"
            isDisabled={generate.isPending}
            onClick={() =>
              void generate
                .mutateAsync({
                  exportFolderLabel: folderLabel.trim() || undefined,
                })
                .then((data) => {
                  navigate(sessionPath(sessionId, sessionStepForState(data.session.state)));
                })
            }
          >
            {generate.isPending ? "Generating…" : "Generate artifacts"}
          </Button>
        )}
      </Panel>
    </PageFrame>
  );
}

export function CompletePage({
  sessionId,
  session,
}: {
  sessionId: string;
  session: SessionDetailResponse;
}) {
  const promptId = session.prompt_id ?? session.session.prompt_id;
  const inferenceSettings = useQuery({
    queryKey: queryKeys.inferenceSettings,
    queryFn: fetchInferenceSettings,
  });
  const llmHealth = useQuery({
    queryKey: ["health", "llm"],
    queryFn: fetchLlmHealth,
    staleTime: 15_000,
  });
  const sendToModel = useSendToInference(sessionId);
  const [approvedSend, setApprovedSend] = useState(false);
  const [oneTimeEndpointId, setOneTimeEndpointId] = useState("");
  const [latestResponse, setLatestResponse] = useState<SendToInferenceResponse | null>(null);

  const inferenceResult = latestResponse ?? session.inference_result;
  const settings = inferenceSettings.data;
  const configuredEndpoints = useMemo(
    () => settings?.api_endpoints.filter((endpoint) => endpoint.configured) ?? [],
    [settings],
  );
  const localModelReady = llmHealth.data?.llm_enabled === true && llmHealth.data.status === "ok";
  const hasEndpointSlots = configuredEndpoints.length > 0;
  const canSend =
    settings?.send_to_inference_available === true &&
    (hasEndpointSlots ||
      (settings.external_inference_enabled
        ? settings.external_provider_api_key_configured
        : localModelReady));
  const sendError =
    sendToModel.error != null
      ? formatApiError(sendToModel.error, "Could not send prompt to the model.")
      : null;

  return (
    <PageFrame limited>
      <PageHeader
        title="Export complete"
        subtitle="This session is closed and preserved for audit. Start a new session from this template to iterate."
      />
      <Panel>
        {promptId && (
          <Content component="p">
            Registry entry: <code>{promptId}</code>
          </Content>
        )}
        {session.expected_host_export_path && (
          <Content component="small">
            {session.generated_files.length} files written to <code>{session.expected_host_export_path}</code>
          </Content>
        )}
        {!session.expected_host_export_path && session.artifact_manifest && (
          <Content component="small">
            {session.artifact_manifest.files.length} files written to{" "}
            <code>{session.artifact_manifest.expected_host_export_path}</code>
          </Content>
        )}
        {session.artifact_warning && <WarningBanner message={session.artifact_warning} />}
        <ButtonRow>
          <SessionTemplateButton sessionId={sessionId} />
          {promptId && (
            <LinkButton to={`/registry/${promptId}`} variant="secondary">
              Open in registry
            </LinkButton>
          )}
        </ButtonRow>
      </Panel>

      <Panel title="Send to model">
        {inferenceSettings.isLoading ? (
          <Content component="small">Checking model API settings…</Content>
        ) : !settings?.send_to_inference_available ? (
          <Content component="small">
            No external model API is configured. Add endpoints in <Link to="/settings">Settings</Link>, enable
            the setup local model, or use the .env external provider to run the optimized prompt.
          </Content>
        ) : hasEndpointSlots ? (
          <Content component="small">
            Sends the approved optimized prompt to the selected API endpoint. The response is saved as{" "}
            <code>inference_response.txt</code> in the artifact folder.
          </Content>
        ) : settings.external_inference_enabled ? (
          <Content component="small">
            Sends the approved optimized prompt to <code>{settings.external_provider_model}</code> via the
            configured external provider. The response is saved as <code>inference_response.txt</code> in the
            artifact folder.
          </Content>
        ) : (
          <Content component="small">
            Sends the approved optimized prompt to your local model (<code>{settings.local_chat_model}</code>
            ). The response is saved as <code>inference_response.txt</code> in the artifact folder.
          </Content>
        )}

        {settings?.send_to_inference_available && !canSend && (
          <WarningBanner
            message={
              hasEndpointSlots
                ? "Selected endpoint is not available."
                : settings.external_inference_enabled
                  ? "External inference is enabled but no API key is configured."
                  : "Local model API is not reachable. Start the LLM server (make ensure-llm) and retry."
            }
          />
        )}

        {canSend && configuredEndpoints.length > 0 && (
          <Content component="small">
            Choose a one-time API override next to Send, or leave the default from the dashboard.
          </Content>
        )}

        {inferenceResult && (
          <div>
            <Content component="small">
              Last run: {inferenceResult.model} · saved to{" "}
              <code>{inferenceResult.inference_response_artifact_path}</code>
            </Content>
            <DraftBlock body={inferenceResult.response_text} label="Model response" />
          </div>
        )}

        {canSend && (
          <>
            <Checkbox
              id="approve-send"
              label="I approve sending the optimized prompt to the model API"
              isChecked={approvedSend}
              isDisabled={sendToModel.isPending}
              onChange={(_event, checked) => setApprovedSend(checked)}
            />
            {sendError && <ErrorBanner message={sendError} />}
            <Flex
              spaceItems={{ default: "spaceItemsSm" }}
              alignItems={{ default: "alignItemsFlexEnd" }}
              flexWrap={{ default: "wrap" }}
            >
              <Button
                variant="primary"
                isDisabled={!approvedSend || sendToModel.isPending}
                onClick={() =>
                  void sendToModel.mutateAsync(oneTimeEndpointId || null).then((data) => {
                    setLatestResponse(data);
                    setApprovedSend(false);
                  })
                }
              >
                {sendToModel.isPending ? "Sending…" : "Send to model"}
              </Button>
              {configuredEndpoints.length > 0 && (
                <FormGroup label="API for this send" fieldId="send-endpoint">
                  <span className="sr-only">API for this send</span>
                  <FormSelect
                    id="send-endpoint"
                    value={oneTimeEndpointId}
                    isDisabled={sendToModel.isPending}
                    onChange={(_event, value) => setOneTimeEndpointId(value)}
                    aria-label="API endpoint for this send"
                  >
                    <FormSelectOption
                      value=""
                      label={`Default${
                        settings?.default_api_endpoint_id
                          ? ` (${configuredEndpoints.find((item) => item.id === settings.default_api_endpoint_id)?.label || "configured"})`
                          : ""
                      }`}
                    />
                    {configuredEndpoints.map((endpoint) => (
                      <FormSelectOption
                        key={endpoint.id}
                        value={endpoint.id}
                        label={endpoint.label || endpoint.chat_model}
                      />
                    ))}
                  </FormSelect>
                </FormGroup>
              )}
            </Flex>
          </>
        )}
      </Panel>
    </PageFrame>
  );
}
