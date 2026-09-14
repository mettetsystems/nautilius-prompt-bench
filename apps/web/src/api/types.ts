export type SessionState =
  | "intake"
  | "clarifying"
  | "edit"
  | "finalized"
  | "similarity_check"
  | "artifact_generation"
  | "optimization"
  | "approval"
  | "exported";

export interface OptimizationTargets {
  clarity?: string | null;
  richness?: string | null;
  density?: string | null;
  efficiency?: string | null;
  denoising?: string | null;
  deconfliction?: string | null;
}

export interface TaskIdentity {
  objective: string;
  task_type: string;
  environment: string;
  additional_constraints: string[];
}

export interface AgentContract {
  definition_of_done: string;
  change_scope: string;
  architecture_policy: string;
  discovery_policy: string;
  execution_strategy: string;
  validation_strategy: string;
  failure_recovery: string;
  autonomy_policy: string;
  persistent_memory: string;
  completion_contract: string;
  resource_budget: string;
  tool_safety: string;
  context_compaction: string;
  rollback_protocol: string;
  escalation_rules: string;
  dependency_security: string;
}

export interface RequirementCard {
  application_requirements?: Record<string, string>;
  task_identity?: TaskIdentity;
  agent_contract?: AgentContract;
  optimization_targets: OptimizationTargets;
  unresolved_fields?: string[];
}

export interface ClarificationSuggestionsResponse {
  field_name: string;
  original_answer?: string;
  proposed_answer?: string;
  recommendations?: string[];
  assumptions?: string[];
  conflicts?: string[];
  follow_up_questions?: string[];
  model_source?: string;
  suggested_question: string | null;
  suggested_answers: string[];
  model_available: boolean;
  message: string | null;
}

export interface PromptDraft {
  id: string;
  session_id: string;
  version: number;
  body: string;
  change_summary: string;
  semantic_diff: string;
  created_at: string;
  is_canonical: boolean;
  is_frozen: boolean;
}

export interface SessionSummary {
  id: string;
  title: string;
  state: SessionState;
  current_draft_id: string | null;
  prompt_id: string | null;
  template_source_session_id: string | null;
  clarification_turn: number;
  created_at: string;
  updated_at: string;
}

export interface SimilarityMatch {
  prompt_id: string;
  title: string;
  similarity_score: number;
  artifact_paths: Record<string, string>;
  delta: string;
  document_kind: string | null;
}

export interface DetectedConflict {
  left_instruction: string;
  right_instruction: string;
  description: string;
  requires_human_decision: boolean;
  resolved: boolean;
  resolution: string | null;
}

export interface OptimizationMetrics {
  original_token_count: number;
  optimized_token_count: number;
  token_reduction_pct: number;
  constraints_per_token: number;
  targets: {
    clarity?: number;
    richness: number;
    density: number;
    efficiency: number;
    denoising: number;
    deconfliction: number;
  };
}

export interface OptimizationResult {
  original_body: string;
  optimized_body: string;
  metrics: OptimizationMetrics;
  changes: {
    removed: string[];
    compressed: string[];
    clarified?: string[];
    conflicts_resolved: string[];
    precision_improvements: string[];
  };
  hard_conflicts: DetectedConflict[];
  export_ready: boolean;
  approved: boolean;
  passes_completed: string[];
}

export interface PreInferenceMetrics {
  requirement_capture_score: number;
  unspecified_field_honesty: number;
  instruction_clarity: number;
  hard_conflict_count: number;
  format_adherence: number;
  token_cost_estimate: number;
  richness_score: number;
  density_score: number;
  efficiency_score: number;
  denoising_score: number;
  deconfliction_score: number;
  semantic_precision_score: number;
  vague_language_count: number;
  first_shot_readiness_score?: number;
  first_shot_ready?: boolean;
  section_coverage?: number;
}

export interface FirstShotRisk {
  code: string;
  field_name: string | null;
  message: string;
}

export interface FirstShotReadiness {
  ready: boolean;
  score: number;
  risks: FirstShotRisk[];
  checklist: string[];
}

export type VagueLanguageCategory = "lazy_adjective" | "catch_all_noun";

export interface VagueLanguageFinding {
  id: string;
  term: string;
  category: VagueLanguageCategory;
  line_number: number;
  line: string;
  /** Start offset of the term within `line`. */
  start: number;
  /** End offset of the term within `line`. */
  end: number;
  resolved: boolean;
}

export interface PrecisionReviewResponse {
  score: number;
  threshold: number;
  vague_language_count: number;
  findings: VagueLanguageFinding[];
  llm_available: boolean;
  lexicon_available: boolean;
  vector_index_available: boolean;
  refinement_available: boolean;
  optimized_body: string;
}

export type PrecisionSuggestionSource = "llm" | "vector" | "wordnet" | "none";

export interface PrecisionSuggestResponse {
  finding_id: string;
  suggested_replacements: string[];
  model_available: boolean;
  source: PrecisionSuggestionSource;
  message: string | null;
}

export interface ArtifactFileEntry {
  name: string;
  format: string;
  size_bytes: number;
  sha256?: string;
  optional?: boolean;
}

export interface ArtifactManifest {
  export_id: string;
  prompt_id: string;
  prompt_version: number;
  created_at: string;
  container_export_path: string;
  expected_host_export_path: string;
  files: ArtifactFileEntry[];
  generated_by: string;
  tool_versions: Record<string, string>;
  warnings: string[];
  version: number;
  artifact_dir: string;
  generated_at: string;
  export_folder_host_path: string;
  export_folder_container_path: string;
  generation_warnings: string[];
  checksums: Record<string, string>;
}

export interface SendToInferenceResponse {
  provider: string;
  model: string;
  prompt_id: string;
  version: number;
  timestamp: string;
  artifact_location: string;
  inference_response_artifact_path: string;
  response_text: string;
}

export interface InferenceEndpointOption {
  id: string;
  label: string;
  base_url: string;
  chat_model: string;
  configured: boolean;
  is_default: boolean;
}

export interface InferenceSettingsResponse {
  local_model_endpoint: string;
  local_chat_model: string;
  local_embed_model: string;
  embedding_model: string;
  external_inference_enabled: boolean;
  external_provider_base_url: string;
  external_provider_model: string;
  external_provider_api_key_configured: boolean;
  require_approval_before_external_call: boolean;
  send_to_inference_available: boolean;
  uses_local_model: boolean;
  llm_enabled: boolean;
  api_endpoints: InferenceEndpointOption[];
  default_api_endpoint_id: string | null;
}

export interface ApiEndpointSettings {
  id: string;
  label: string;
  base_url: string;
  chat_model: string;
  api_key_configured: boolean;
  configured: boolean;
}

export interface SetupAiToolingInfo {
  base_url: string;
  chat_model: string;
  source: string;
}

export interface AiToolingApiOverrideSettings {
  label: string;
  base_url: string;
  chat_model: string;
  api_key_configured: boolean;
  configured: boolean;
}

export interface AiToolingApiOverrideUpdate {
  label: string;
  base_url: string;
  chat_model: string;
  api_key?: string | null;
}

export interface ClarificationVersionText {
  level: "beginner" | "standard" | "advanced";
  label: string;
  prompt: string;
  rationale: string | null;
}

export interface QuickReplyGuide {
  option: string;
  explanation: string;
  when_to_use: string;
}

export interface ClarificationVersionsSettings {
  beginner: boolean;
  standard: boolean;
  advanced: boolean;
}

export interface AskTheLocalsResponse {
  field_name: string;
  insight: string;
  recommended_answer: string;
  previous_answers_used: string[];
  model_available: boolean;
  model_source: string | null;
  message: string | null;
}

export interface UserSettingsResponse {
  llm_enabled: boolean;
  precision_warning_threshold: number;
  similarity_time_scope_index: number;
  similarity_time_scope_label: string;
  similarity_time_scope_labels: string[];
  clarification_versions: ClarificationVersionsSettings;
  default_api_endpoint_id: string | null;
  api_endpoints: ApiEndpointSettings[];
  max_api_endpoint_slots: number;
  setup_ai_tooling: SetupAiToolingInfo;
  ai_tooling_api_override: AiToolingApiOverrideSettings;
  ai_tooling_override_active: boolean;
  ask_the_locals_api_override: AiToolingApiOverrideSettings;
  ask_the_locals_override_active: boolean;
}

export interface ApiEndpointUpdate {
  id: string;
  label: string;
  base_url: string;
  chat_model: string;
  api_key?: string | null;
}

export interface UserSettingsUpdateRequest {
  llm_enabled: boolean;
  precision_warning_threshold: number;
  similarity_time_scope_index: number;
  clarification_versions: ClarificationVersionsSettings;
  default_api_endpoint_id: string | null;
  api_endpoints: ApiEndpointUpdate[];
  ai_tooling_api_override: AiToolingApiOverrideUpdate;
  ask_the_locals_api_override: AiToolingApiOverrideUpdate;
}

export interface SessionDetailResponse {
  clarification_open_decisions?: string[];
  session: SessionSummary;
  requirement_card: RequirementCard;
  clarification_question: string | null;
  clarification_field: string | null;
  clarification_question_number: number | null;
  clarification_total_questions: number | null;
  clarification_quick_replies: string[] | null;
  clarification_quick_reply_guides: QuickReplyGuide[] | null;
  clarification_versions: ClarificationVersionText[] | null;
  clarification_can_finish: boolean | null;
  current_draft: PromptDraft | null;
  revised_draft: PromptDraft | null;
  semantic_diff: string | null;
  change_summary: string | null;
  edit_intent: string | null;
  updated_requirement_card: RequirementCard | null;
  prompt_id: string | null;
  registry_warning: string | null;
  similarity_warning: string | null;
  similarity_matches: SimilarityMatch[];
  optimization_result: OptimizationResult | null;
  pre_inference_metrics: PreInferenceMetrics | null;
  inference_result: SendToInferenceResponse | null;
  artifact_manifest: ArtifactManifest | null;
  artifact_warning: string | null;
  export_id: string | null;
  container_export_path: string | null;
  expected_host_export_path: string | null;
  manifest_path: string | null;
  generated_files: string[];
  warnings: string[];
  first_shot_readiness?: FirstShotReadiness | null;
  quality_gate_warnings?: string[];
}

export interface RegistryPromptSummary {
  prompt_id: string;
  version: number;
  title: string;
  abstract: string;
  tags: string[];
  output_form: string;
  evaluation_scores: Record<string, number>;
  artifact_paths: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface RegistryMetadata {
  prompt_id: string;
  version: number;
  title: string;
  abstract: string;
  tags: string[];
  domain: string;
  task_family: string;
  output_form: string;
  target_provider: string;
  target_model: string;
  preferred_prompt_length: string;
  evaluation_scores: Record<string, number>;
  artifact_paths: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface RegistryPromptDetail {
  metadata: RegistryMetadata;
  requirement_card: RequirementCard;
  canonical_prompt: string;
  artifact_manifest: ArtifactManifest | null;
  artifact_dir: string | null;
}

export interface RecentSessionEntry {
  id: string;
  title: string;
  state: SessionState;
  promptId: string | null;
  similarityWarning: string | null;
  updatedAt: string;
}

export interface ApiErrorDetail {
  message?: string;
  state?: string;
  action?: string;
}
