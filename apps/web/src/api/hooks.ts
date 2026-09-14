import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  answerClarification,
  applyPrecisionReplacement,
  approveOptimization,
  askTheLocals,
  completeClarification,
  createSession,
  createSessionFromTemplate,
  deleteSession,
  editDraft,
  fetchRegistryPrompt,
  fetchRegistryPrompts,
  fetchSession,
  finalizeSession,
  generateArtifacts,
  optimizeSession,
  reopenForEdit,
  rerunOptimization,
  rerunSimilarityCheck,
  sendToInference,
  suggestClarification,
  suggestPrecisionReplacement,
} from "../api/sessions";
import { fetchUserSettings, updateUserSettings } from "../api/settings";
import { ApiError } from "./http";
import { removeRecentSession, upsertRecentSession } from "../lib/recentSessions";

export const queryKeys = {
  health: ["health"] as const,
  session: (id: string) => ["session", id] as const,
  precisionReview: (id: string) => ["precision-review", id] as const,
  inferenceSettings: ["inference-settings"] as const,
  userSettings: ["user-settings"] as const,
  registry: ["registry", "prompts"] as const,
  registryPrompt: (id: string) => ["registry", "prompt", id] as const,
  recentSessions: ["recent-sessions"] as const,
};

function trackSession(
  queryClient: ReturnType<typeof useQueryClient>,
  data: import("./types").SessionDetailResponse,
) {
  upsertRecentSession(data);
  void queryClient.invalidateQueries({ queryKey: queryKeys.recentSessions });
}

export function useSession(sessionId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.session(sessionId ?? ""),
    queryFn: () => fetchSession(sessionId!),
    enabled: Boolean(sessionId),
  });
}

export function useRegistryPrompts() {
  return useQuery({
    queryKey: queryKeys.registry,
    queryFn: fetchRegistryPrompts,
  });
}

export function useRegistryPrompt(promptId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.registryPrompt(promptId ?? ""),
    queryFn: () => fetchRegistryPrompt(promptId!),
    enabled: Boolean(promptId),
  });
}

export function useDeleteSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sessionId: string) => {
      try {
        await deleteSession(sessionId);
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404)) {
          throw error;
        }
      }
      removeRecentSession(sessionId);
      return sessionId;
    },
    onSuccess: (sessionId) => {
      queryClient.removeQueries({ queryKey: queryKeys.session(sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.recentSessions });
    },
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createSession,
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(data.session.id), data);
    },
  });
}

export function useCreateSessionFromTemplate(sourceSessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) => createSessionFromTemplate(sourceSessionId, title),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(data.session.id), data);
    },
  });
}

export function useAnswerClarification(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (answer: string) => answerClarification(sessionId, answer),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
    },
  });
}

export function useCompleteClarification(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => completeClarification(sessionId),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
    },
  });
}

export function useSuggestClarification(sessionId: string) {
  return useMutation({
    mutationFn: (payload?: { current_answer: string; model: "lightweight" | "large"; field_name?: string }) => suggestClarification(sessionId, payload),
  });
}

export function useAskTheLocals(sessionId: string) {
  return useMutation({
    mutationFn: () => askTheLocals(sessionId),
  });
}

export function useEditDraft(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { instruction: string } | { body: string }) =>
      editDraft(sessionId, payload),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
    },
  });
}

export function useFinalizeSession(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (options?: { acknowledgeFirstShotRisk?: boolean }) =>
      finalizeSession(sessionId, options),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.registry });
    },
  });
}

function useSessionMutation(sessionId: string, mutationFn: () => Promise<import("./types").SessionDetailResponse>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
    },
  });
}

export function useReopenForEdit(sessionId: string) {
  return useSessionMutation(sessionId, () => reopenForEdit(sessionId));
}

export function useRerunSimilarityCheck(sessionId: string) {
  return useSessionMutation(sessionId, () => rerunSimilarityCheck(sessionId));
}

export function useRerunOptimization(sessionId: string) {
  return useSessionMutation(sessionId, () => rerunOptimization(sessionId));
}

export function useOptimizeSession(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => optimizeSession(sessionId),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
    },
  });
}

export function useApproveOptimization(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => approveOptimization(sessionId),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
    },
  });
}

export function useSuggestPrecisionReplacement(sessionId: string) {
  return useMutation({
    mutationFn: (findingId: string) => suggestPrecisionReplacement(sessionId, findingId),
  });
}

export function useApplyPrecisionReplacement(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { findingId: string; replacement: string }) =>
      applyPrecisionReplacement(sessionId, payload.findingId, payload.replacement),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.precisionReview(sessionId) });
    },
  });
}

export function useUserSettings() {
  return useQuery({
    queryKey: queryKeys.userSettings,
    queryFn: fetchUserSettings,
  });
}

export function useUpdateUserSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updateUserSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.userSettings, data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.inferenceSettings });
      void queryClient.invalidateQueries({ queryKey: ["health", "llm"] });
    },
  });
}

export function useSendToInference(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (apiEndpointId?: string | null) =>
      sendToInference(sessionId, { apiEndpointId }),
    onSuccess: (data) => {
      queryClient.setQueryData(
        queryKeys.session(sessionId),
        (current: import("./types").SessionDetailResponse | undefined) =>
          current ? { ...current, inference_result: data } : current,
      );
    },
  });
}

export function useGenerateArtifacts(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (options?: { includePdf?: boolean; exportFolderLabel?: string }) =>
      generateArtifacts(sessionId, options),
    onSuccess: (data) => {
      trackSession(queryClient, data);
      queryClient.setQueryData(queryKeys.session(sessionId), data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.registry });
    },
  });
}
