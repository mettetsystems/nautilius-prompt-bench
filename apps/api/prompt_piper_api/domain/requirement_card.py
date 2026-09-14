from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from prompt_piper_api.domain.agent_contract import CONTRACT_FIELD_NAMES, CONTRACT_SECTION_TITLES
from prompt_piper_api.domain.application_requirements import (
    APPLICATION_FIELD_NAMES,
    ApplicationRequirements,
)


class OptimizationTargets(BaseModel):
    """Tuning dimensions for the clarity-first optimizer."""

    model_config = ConfigDict(extra="forbid")

    clarity: str | None = Field(
        default=None,
        description="Make operational rules explicit; never sacrifice clarity for brevity.",
    )
    richness: str | None = Field(
        default=None,
        description="Increase detail, nuance, and contextual depth.",
    )
    density: str | None = Field(
        default=None,
        description="Pack more signal into fewer tokens (secondary to clarity).",
    )
    efficiency: str | None = Field(
        default=None,
        description="Reduce latency or cognitive load without dropping required rules.",
    )
    denoising: str | None = Field(
        default=None,
        description="Remove ambiguity, filler, and off-topic content.",
    )
    deconfliction: str | None = Field(
        default=None,
        description="Resolve contradictory instructions or constraints.",
    )


class TaskIdentity(BaseModel):
    """The coding task itself, extracted from the initial request (not a control question)."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(default="", description="Primary long-horizon coding goal.")
    task_type: str = Field(
        default="",
        description="Feature, refactor, debug, tests, or other coding job type.",
    )
    environment: str = Field(
        default="",
        description="Language, framework, and key dependencies when known.",
    )
    additional_constraints: list[str] = Field(
        default_factory=list,
        description="Free-form constraints added during edits.",
    )


class AgentContract(BaseModel):
    """Sixteen operational-control policies for a long-horizon coding agent."""

    model_config = ConfigDict(extra="forbid")

    definition_of_done: str = Field(default="", description="Evidence-based completion states.")
    change_scope: str = Field(default="", description="Minimum-necessary change policy.")
    architecture_policy: str = Field(default="", description="Reuse, priorities, and coupling.")
    discovery_policy: str = Field(default="", description="Inspect-before-modify rules.")
    execution_strategy: str = Field(default="", description="Incremental lifecycle.")
    validation_strategy: str = Field(default="", description="Continuous verification pyramid.")
    failure_recovery: str = Field(default="", description="Diagnose-then-fix protocol.")
    autonomy_policy: str = Field(default="", description="Risk-weighted autonomy.")
    persistent_memory: str = Field(default="", description=".agent/ working memory.")
    completion_contract: str = Field(default="", description="Evidence required to finish.")
    resource_budget: str = Field(default="", description="API/loop/time pause limits.")
    tool_safety: str = Field(default="", description="Shell, network, and secret restrictions.")
    context_compaction: str = Field(default="", description="Context-window survival rules.")
    rollback_protocol: str = Field(default="", description="Checkpoint and backtracking.")
    escalation_rules: str = Field(default="", description="Human-in-the-loop stop conditions.")
    dependency_security: str = Field(default="", description="License, SAST, and audit rules.")


# Leaf paths used by clarification, unresolved tracking, and edit patches.
LEAF_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "task_identity.objective",
        "task_identity.task_type",
        "task_identity.environment",
        "task_identity.additional_constraints",
        *CONTRACT_FIELD_NAMES,
        *APPLICATION_FIELD_NAMES,
        "optimization_targets",
    }
)

LIST_LEAF_FIELDS: frozenset[str] = frozenset(
    {
        "task_identity.additional_constraints",
    }
)

REQUIREMENT_CARD_FIELD_NAMES = LEAF_FIELD_NAMES

DIMENSION_SECTION_TITLES: tuple[str, ...] = ("Task Identity", *CONTRACT_SECTION_TITLES)


class RequirementCard(BaseModel):
    """Long-horizon coding-agent intake card: task identity plus a 16-question contract."""

    model_config = ConfigDict(extra="forbid")

    application_requirements: ApplicationRequirements = Field(default_factory=ApplicationRequirements)
    task_identity: TaskIdentity = Field(default_factory=TaskIdentity)
    agent_contract: AgentContract = Field(default_factory=AgentContract)
    optimization_targets: OptimizationTargets = Field(default_factory=OptimizationTargets)
    unresolved_fields: list[str] = Field(
        default_factory=list,
        description="Leaf field paths still needing clarification.",
    )

    @property
    def objective(self) -> str:
        """Convenience accessor used by titles, precision, and metrics."""
        return self.task_identity.objective

    @objective.setter
    def objective(self, value: str) -> None:
        self.task_identity.objective = value

    def mark_unresolved(self, *field_names: str) -> None:
        """Replace unresolved_fields with validated leaf field names."""
        unknown = set(field_names) - LEAF_FIELD_NAMES
        if unknown:
            msg = f"Unknown requirement card fields: {sorted(unknown)}"
            raise ValueError(msg)
        self.unresolved_fields = list(field_names)

    def get_leaf(self, field_name: str) -> Any:
        """Return a leaf value by dotted path (or optimization_targets model)."""
        if field_name == "optimization_targets":
            return self.optimization_targets
        parent_name, leaf_name = _split_leaf(field_name)
        parent = getattr(self, parent_name)
        return getattr(parent, leaf_name)

    def set_leaf(self, field_name: str, value: Any) -> None:
        """Set a leaf value by dotted path."""
        if field_name == "optimization_targets":
            if isinstance(value, OptimizationTargets):
                self.optimization_targets = value
            elif isinstance(value, dict):
                self.optimization_targets = OptimizationTargets.model_validate(value)
            else:
                msg = "optimization_targets expects a model or dict"
                raise TypeError(msg)
            return
        parent_name, leaf_name = _split_leaf(field_name)
        parent = getattr(self, parent_name)
        setattr(parent, leaf_name, value)

    def is_leaf_missing(self, field_name: str) -> bool:
        """True when a leaf is empty or still marked unresolved."""
        if field_name not in LEAF_FIELD_NAMES:
            return False
        if field_name in self.unresolved_fields:
            return True
        if field_name == "optimization_targets":
            targets = self.optimization_targets.model_dump()
            return all(value is None for value in targets.values())
        value = self.get_leaf(field_name)
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, list):
            return len(value) == 0
        return False

    def clear_leaf(self, field_name: str) -> None:
        """Empty a leaf without inventing a value (used for unspecified answers)."""
        if field_name == "optimization_targets":
            self.optimization_targets = OptimizationTargets()
            return
        if field_name in LIST_LEAF_FIELDS:
            self.set_leaf(field_name, [])
            return
        self.set_leaf(field_name, "")

    def coding_spec_dict(self) -> dict[str, Any]:
        """Structured coding-prompt spec for JSON/YAML export (no unresolved list)."""
        data = self.model_dump()
        data.pop("unresolved_fields", None)
        return data


def _split_leaf(field_name: str) -> tuple[str, str]:
    if field_name not in LEAF_FIELD_NAMES or field_name == "optimization_targets":
        msg = f"Unknown or non-leaf field: {field_name}"
        raise ValueError(msg)
    parent_name, leaf_name = field_name.split(".", 1)
    return parent_name, leaf_name
