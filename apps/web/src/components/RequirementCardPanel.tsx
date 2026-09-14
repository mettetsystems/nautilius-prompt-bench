import type { AgentContract, RequirementCard } from "../api/types";

interface RequirementCardPanelProps {
  card: RequirementCard;
  title?: string;
}

function FieldBlock({ label, value }: { label: string; value: string | undefined }) {
  if (!value?.trim()) {
    return null;
  }
  return (
    <div className="field-block">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function ListBlock({ label, items }: { label: string; items: string[] | undefined }) {
  if (!items || items.length === 0) {
    return null;
  }
  return (
    <div className="field-block">
      <dt>{label}</dt>
      <dd>
        <ul className="compact-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </dd>
    </div>
  );
}

function DimensionGroup({
  heading,
  children,
}: {
  heading: string;
  children: React.ReactNode;
}) {
  return (
    <div className="dimension-group">
      <h3 className="dimension-heading">{heading}</h3>
      <dl className="field-list">{children}</dl>
    </div>
  );
}

const CONTRACT_FIELDS: { key: keyof AgentContract; label: string }[] = [
  { key: "definition_of_done", label: "Definition of done" },
  { key: "change_scope", label: "Change scope" },
  { key: "architecture_policy", label: "Architecture policy" },
  { key: "discovery_policy", label: "Discovery policy" },
  { key: "execution_strategy", label: "Execution strategy" },
  { key: "validation_strategy", label: "Validation strategy" },
  { key: "failure_recovery", label: "Failure recovery" },
  { key: "autonomy_policy", label: "Autonomy policy" },
  { key: "persistent_memory", label: "Persistent memory" },
  { key: "completion_contract", label: "Completion contract" },
  { key: "resource_budget", label: "Resource budget" },
  { key: "tool_safety", label: "Tool safety" },
  { key: "context_compaction", label: "Context compaction" },
  { key: "rollback_protocol", label: "Rollback protocol" },
  { key: "escalation_rules", label: "Escalation rules" },
  { key: "dependency_security", label: "Dependency and security" },
];

export function RequirementCardPanel({
  card,
  title = "Agent contract",
}: RequirementCardPanelProps) {
  const task = card.task_identity;
  const contract = card.agent_contract;
  const unresolved = card.unresolved_fields ?? [];

  if (!task || !contract) {
    return (
      <aside className="panel side-panel">
        <h2>{title}</h2>
        <div className="callout callout-warn">
          <strong>Requirement card unavailable</strong>
          <p>
            This session was saved with an older card schema, so the page cannot
            render it. Start a new session from the same initial prompt, and run
            the API from this workspace with make dev-api.
          </p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="panel side-panel">
      <h2>{title}</h2>
      {unresolved.length > 0 && (
        <div className="callout callout-warn">
          <strong>Unresolved</strong>
          <p>{unresolved.join(", ")}</p>
        </div>
      )}

      <DimensionGroup heading="Task Identity">
        <FieldBlock label="Objective" value={task.objective} />
        <FieldBlock label="Task type" value={task.task_type} />
        <FieldBlock label="Environment" value={task.environment} />
        <ListBlock label="Additional constraints" items={task.additional_constraints} />
      </DimensionGroup>

      {card.application_requirements && <DimensionGroup heading="Application requirements">
        {Object.entries(card.application_requirements).map(([key, value]) => <FieldBlock key={key} label={key.replaceAll("_", " ")} value={value} />)}
      </DimensionGroup>}
      <DimensionGroup heading="Operational control (16 questions)">
        {CONTRACT_FIELDS.map((field) => (
          <FieldBlock key={field.key} label={field.label} value={contract[field.key]} />
        ))}
      </DimensionGroup>
    </aside>
  );
}
