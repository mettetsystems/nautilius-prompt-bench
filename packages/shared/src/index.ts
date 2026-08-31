/**
 * Shared types for Nautilius Prompting Workbench.
 * OpenAPI-generated types can be added here as the API surface grows.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  timestamp: string;
  database: "sqlite" | "postgresql" | string;
}

export interface LlmHealthResponse {
  llm_enabled: boolean;
  status: "ok" | "disabled" | "unreachable" | string;
  endpoint: string | null;
  model_name: string | null;
  message: string;
  checked_at: string;
}

export const APP_NAME = "Nautilius Prompting Workbench";

export const APP_TAGLINE =
  "Design long-horizon coding-agent contracts locally. Clarify operational policy, optimize for clarity, and export a ready-to-run prompt.";
