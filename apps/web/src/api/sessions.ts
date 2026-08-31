import type { HealthResponse, LlmHealthResponse } from "@prompt-piper/shared";
import { apiFetch } from "./http";
import type {
  AskTheLocalsResponse,
  ClarificationSuggestionsResponse,
  InferenceSettingsResponse,
  PrecisionReviewResponse,
  PrecisionSuggestResponse,
  RegistryPromptDetail,
  RegistryPromptSummary,
  SendToInferenceResponse,
  SessionDetailResponse,
} from "./types";

export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export function fetchLlmHealth(): Promise<LlmHealthResponse> {
  return apiFetch<LlmHealthResponse>("/health/llm");
}

export function createSession(payload: {
  initial_request: string;
  title?: string;
}): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>("/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createSessionFromTemplate(
  sessionId: string,
  title?: string,
): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/template`, {
    method: "POST",
    body: JSON.stringify(title ? { title } : {}),
  });
}

export function fetchSession(sessionId: string): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}`);
}

export function deleteSession(sessionId: string): Promise<void> {
  return apiFetch<void>(`/sessions/${sessionId}/delete`, { method: "POST" });
}

export function answerClarification(
  sessionId: string,
  answer: string,
): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/answer`, {
    method: "POST",
    body: JSON.stringify({ answer }),
  });
}

export function completeClarification(sessionId: string): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/clarify/complete`, {
    method: "POST",
  });
}

export function suggestClarification(
  sessionId: string,
): Promise<ClarificationSuggestionsResponse> {
  return apiFetch<ClarificationSuggestionsResponse>(`/sessions/${sessionId}/clarify/suggest`, {
    method: "POST",
  });
}

export function askTheLocals(sessionId: string): Promise<AskTheLocalsResponse> {
  return apiFetch<AskTheLocalsResponse>(`/sessions/${sessionId}/clarify/locals`, {
    method: "POST",
  });
}

export function editDraft(
  sessionId: string,
  payload: { instruction: string } | { body: string },
): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/edit`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function finalizeSession(
  sessionId: string,
  options?: { acknowledgeFirstShotRisk?: boolean },
): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/finalize`, {
    method: "POST",
    body: JSON.stringify({
      acknowledge_first_shot_risk: options?.acknowledgeFirstShotRisk ?? false,
    }),
  });
}

export function reopenForEdit(sessionId: string): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/workflow/reopen/edit`, {
    method: "POST",
  });
}

export function rerunSimilarityCheck(sessionId: string): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/workflow/rerun/similarity`, {
    method: "POST",
  });
}

export function rerunOptimization(sessionId: string): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/workflow/rerun/optimize`, {
    method: "POST",
  });
}

export function optimizeSession(sessionId: string): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/optimize`, {
    method: "POST",
  });
}

export function approveOptimization(sessionId: string): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/optimize/approve`, {
    method: "POST",
  });
}

export function fetchPrecisionReview(sessionId: string): Promise<PrecisionReviewResponse> {
  return apiFetch<PrecisionReviewResponse>(`/sessions/${sessionId}/precision`);
}

export function suggestPrecisionReplacement(
  sessionId: string,
  findingId: string,
): Promise<PrecisionSuggestResponse> {
  return apiFetch<PrecisionSuggestResponse>(`/sessions/${sessionId}/precision/suggest`, {
    method: "POST",
    body: JSON.stringify({ finding_id: findingId }),
  });
}

export function applyPrecisionReplacement(
  sessionId: string,
  findingId: string,
  replacement: string,
): Promise<SessionDetailResponse> {
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/precision/apply`, {
    method: "POST",
    body: JSON.stringify({ finding_id: findingId, replacement }),
  });
}

export function generateArtifacts(
  sessionId: string,
  options?: { includePdf?: boolean; exportFolderLabel?: string },
): Promise<SessionDetailResponse> {
  const includePdf = options?.includePdf ?? true;
  const payload: { include_pdf: boolean; export_folder_label?: string } = {
    include_pdf: includePdf,
  };
  const label = options?.exportFolderLabel?.trim();
  if (label) {
    payload.export_folder_label = label;
  }
  return apiFetch<SessionDetailResponse>(`/sessions/${sessionId}/artifacts`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchRegistryPrompts(): Promise<RegistryPromptSummary[]> {
  return apiFetch<RegistryPromptSummary[]>("/registry/prompts");
}

export function fetchRegistryPrompt(promptId: string): Promise<RegistryPromptDetail> {
  return apiFetch<RegistryPromptDetail>(`/registry/prompts/${encodeURIComponent(promptId)}`);
}

export function fetchInferenceSettings(): Promise<InferenceSettingsResponse> {
  return apiFetch<InferenceSettingsResponse>("/settings/inference");
}

export function sendToInference(
  sessionId: string,
  options?: { apiEndpointId?: string | null },
): Promise<SendToInferenceResponse> {
  return apiFetch<SendToInferenceResponse>(`/sessions/${sessionId}/send-to-inference`, {
    method: "POST",
    body: JSON.stringify({
      explicit_approval: true,
      api_endpoint_id: options?.apiEndpointId ?? null,
    }),
  });
}
