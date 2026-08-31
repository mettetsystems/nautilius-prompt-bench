import { beforeEach, describe, expect, it } from "vitest";
import {
  RECENT_SESSIONS_KEY,
  loadRecentSessions,
  removeRecentSession,
  saveRecentSessions,
  upsertRecentSession,
} from "./recentSessions";
import type { SessionDetailResponse } from "../api/types";

const sampleSession = {
  session: {
    id: "session-1",
    title: "Weekly status",
    state: "edit",
    current_draft_id: null,
    prompt_id: null,
    template_source_session_id: null,
    clarification_turn: 2,
    created_at: "2026-06-15T12:00:00Z",
    updated_at: "2026-06-15T12:05:00Z",
  },
  requirement_card: {
    task_identity: {
      objective: "Summarize status",
      task_type: "",
      environment: "",
      additional_constraints: [],
    },
    agent_contract: {
      definition_of_done: "",
      change_scope: "",
      architecture_policy: "",
      discovery_policy: "",
      execution_strategy: "",
      validation_strategy: "",
      failure_recovery: "",
      autonomy_policy: "",
      persistent_memory: "",
      completion_contract: "",
      resource_budget: "",
      tool_safety: "",
      context_compaction: "",
      rollback_protocol: "",
      escalation_rules: "",
      dependency_security: "",
    },
    optimization_targets: {},
    unresolved_fields: [],
  },
  clarification_question: null,
  clarification_field: null,
  clarification_question_number: null,
  clarification_total_questions: null,
  clarification_quick_replies: null,
  clarification_quick_reply_guides: null,
  clarification_versions: null,
  clarification_can_finish: null,
  current_draft: null,
  revised_draft: null,
  semantic_diff: null,
  change_summary: null,
  edit_intent: null,
  updated_requirement_card: null,
  prompt_id: null,
  registry_warning: null,
  similarity_warning: "A similar prompt pattern may already exist.",
  similarity_matches: [],
  optimization_result: null,
  pre_inference_metrics: null,
  inference_result: null,
  artifact_manifest: null,
  artifact_warning: null,
  export_id: null,
  container_export_path: null,
  expected_host_export_path: null,
  manifest_path: null,
  generated_files: [],
  warnings: [],
} satisfies SessionDetailResponse;

describe("recentSessions", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("persists and loads recent sessions", () => {
    saveRecentSessions([
      {
        id: "a",
        title: "A",
        state: "edit",
        promptId: null,
        similarityWarning: null,
        updatedAt: "2026-06-15T12:00:00Z",
      },
    ]);
    expect(loadRecentSessions()).toHaveLength(1);
    expect(localStorage.getItem(RECENT_SESSIONS_KEY)).toContain("A");
  });

  it("upserts by session id", () => {
    upsertRecentSession(sampleSession);
    const updated = upsertRecentSession({
      ...sampleSession,
      session: { ...sampleSession.session, title: "Updated title" },
    });
    expect(updated).toHaveLength(1);
    expect(updated[0]?.title).toBe("Updated title");
    expect(updated[0]?.similarityWarning).toContain("similar prompt");
  });

  it("removes a session by id", () => {
    upsertRecentSession(sampleSession);
    upsertRecentSession({
      ...sampleSession,
      session: { ...sampleSession.session, id: "session-2", title: "Other" },
    });
    const next = removeRecentSession("session-1");
    expect(next).toHaveLength(1);
    expect(next[0]?.id).toBe("session-2");
    expect(loadRecentSessions()).toHaveLength(1);
  });

  it("does not share PromptPiper dashboard recents", () => {
    expect(RECENT_SESSIONS_KEY).toBe("nautilius.recent-sessions");
    localStorage.setItem(
      "prompt-piper.recent-sessions",
      JSON.stringify([
        {
          id: "foreign",
          title: "PromptPiper session",
          state: "edit",
          promptId: null,
          similarityWarning: null,
          updatedAt: "2026-06-15T12:00:00Z",
        },
      ]),
    );
    expect(loadRecentSessions()).toEqual([]);
  });
});
