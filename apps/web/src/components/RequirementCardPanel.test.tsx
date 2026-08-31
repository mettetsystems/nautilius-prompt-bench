import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RequirementCardPanel } from "../components/RequirementCardPanel";

describe("RequirementCardPanel", () => {
  it("renders objective and unresolved fields", () => {
    render(
      <RequirementCardPanel
        card={{
          task_identity: {
            objective: "Add a health endpoint",
            task_type: "new feature logic",
            environment: "Python 3.12 + FastAPI",
            additional_constraints: [],
          },
          agent_contract: {
            definition_of_done: "COMPLETE only with passing tests",
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
          unresolved_fields: ["agent_contract.change_scope"],
        }}
      />,
    );

    expect(screen.getByText("Add a health endpoint")).toBeInTheDocument();
    expect(screen.getByText("Python 3.12 + FastAPI")).toBeInTheDocument();
    expect(screen.getByText("agent_contract.change_scope")).toBeInTheDocument();
  });

  it("does not crash when the API returns a legacy card without task_identity", () => {
    render(
      <RequirementCardPanel
        card={{
          optimization_targets: {},
          unresolved_fields: [],
        }}
      />,
    );

    expect(screen.getByText("Requirement card unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(/older card schema/i),
    ).toBeInTheDocument();
  });
});
