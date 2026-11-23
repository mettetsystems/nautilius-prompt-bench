import { Label } from "@patternfly/react-core";
import type { SessionState } from "../api/types";
import { formatSessionState } from "../lib/sessionRouting";

const STATE_LABELS: Partial<Record<SessionState, string>> = {
  intake: "Intake",
  clarifying: "Clarifying",
  edit: "Draft edit",
  similarity_check: "Similarity",
  optimization: "Optimize",
  approval: "Approved",
  exported: "Exported",
};

const STATE_STATUS: Partial<Record<SessionState, "info" | "warning" | "success" | "danger">> = {
  intake: "info",
  clarifying: "info",
  edit: "warning",
  similarity_check: "warning",
  optimization: "info",
  approval: "success",
  artifact_generation: "info",
  exported: "success",
  finalized: "success",
};

export function StatusBadge({ state }: { state: SessionState }) {
  return <Label status={STATE_STATUS[state] ?? "custom"}>{STATE_LABELS[state] ?? formatSessionState(state)}</Label>;
}
