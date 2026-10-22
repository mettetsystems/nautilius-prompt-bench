"""Resolve a full execution contract without modifying accepted user requirements."""

from __future__ import annotations

from dataclasses import dataclass

from prompt_piper_api.domain.agent_contract import CONTRACT_QUESTIONS
from prompt_piper_api.domain.application_requirements import APPLICATION_FIELD_NAMES
from prompt_piper_api.domain.consultation import (
    CONSULTATION_TOPICS,
    UNKNOWN_ANSWERS,
    open_architectural_decisions,
)
from prompt_piper_api.domain.requirement_card import RequirementCard

TOOLCHAIN_DELEGATION = (
    "Determine the build toolchain from repository instructions, manifests, lockfiles, and "
    "authoritative version files. Reuse established tooling where compatible with accepted "
    "requirements. If no toolchain exists, select and document a maintainable option, "
    "establish a reproducible build, and verify it before implementation proceeds."
)

_DELEGATIONS = {
    "operating_systems": (
        "Derive required platform compatibility from accepted target requirements; do not "
        "infer target OS from the development machine. Verify supported platforms and "
        "report untested ones."
    ),
    "runtime": (
        "Discover runtime constraints from accepted technology mandates and repository "
        "version files; select compatible versions only where delegated and verify them on"
        " the target environment."
    ),
    "development_environment": (
        "Inspect the actual execution environment, OS, architecture, shell, and available "
        "tools. Do not assume installed software or confuse the build machine with the "
        "target system."
    ),
    "build_isolation": (
        "Follow existing project isolation and receiving-harness requirements. Otherwise "
        "choose the least-privileged reproducible build environment compatible with "
        "accepted constraints."
    ),
    "build_toolchain": TOOLCHAIN_DELEGATION,
    "build_hardware": (
        "Inspect available CPU, memory, storage, and accelerators. Verify required "
        "hardware and backends; report unmet requirements without assuming GPU "
        "availability or silently changing target constraints."
    ),
    "build_access": (
        "Check permitted network, registry, mirror, and offline dependency access. Use "
        "only authorized credential mechanisms; never print or invent credentials. Report "
        "unavailable dependencies."
    ),
    "build_workspace": (
        "Inspect the supplied workspace and writable paths. Respect existing user changes "
        "and shared files; place artifacts and caches only in permitted locations."
    ),
    "environment_bootstrap": (
        "Use existing setup instructions where available. Establish and document "
        "reproducible setup and preflight checks without assuming installed dependencies "
        "or permissions."
    ),
    "environment_parity": (
        "Compare the actual build and target environments. Verify material platform, "
        "runtime, service, and hardware differences; report checks that require "
        "unavailable target infrastructure."
    ),
    "harness_controls": (
        "Use the receiving harness controls and applicable project instructions for "
        "scheduling, retries, budgets, and context management; preserve explicit user "
        "restrictions."
    ),
}

# Start from the established conservative policies. Replace harness-specific or
# numerical defaults with actionable instructions that do not invent resources.
_DEFAULT_POLICIES = {q.field_name: q.options[0].body for q in CONTRACT_QUESTIONS}
_DEFAULT_POLICIES.update(
    {
        "agent_contract.discovery_policy": _DEFAULT_POLICIES["agent_contract.discovery_policy"]
        + " "
        + TOOLCHAIN_DELEGATION,
        "agent_contract.autonomy_policy": (
            "Choose routine implementation details and compatible tools autonomously within "
            "accepted constraints. Document consequential choices and their justification. "
            "Request approval before changing architectural constraints, scope, security "
            "boundaries, public compatibility, or acceptance criteria, and before destructive "
            "or unauthorized production actions."
        ),
        "agent_contract.persistent_memory": (
            "Use the receiving harness or project's durable progress mechanism. If none is "
            "supplied, maintain concise progress notes in an authorized workspace location: "
            "plan, completed work, current state, decisions, validation evidence, issues, and "
            "next actions. Preserve enough context for another agent to resume."
        ),
        "agent_contract.resource_budget": (
            "Honor explicit user budgets and receiving-harness time, token, and iteration "
            "limits. Do not invent numeric limits. If a limit is reached or repeated attempts "
            "make no progress, pause, persist state, and report the blocker and next useful "
            "action rather than looping indefinitely."
        ),
        "agent_contract.tool_safety": (
            "Respect receiving-harness permissions, approved network access, and writable "
            "paths. Do not force-push, discard user changes, weaken security controls, or run "
            "destructive commands without explicit authorization. Never print, log, or commit "
            "secrets. Request missing access through authorized mechanisms."
        ),
        "agent_contract.context_compaction": (
            "Follow the receiving harness context-management controls. Before context loss or "
            "handoff, preserve the task contract, accepted constraints, current plan, changed "
            "files, decisions, validation evidence, and next actions in durable progress "
            "state. Summarize verbose logs without discarding requirements."
        ),
        "agent_contract.rollback_protocol": (
            "Keep changes small and reversible, recording known-good checkpoints using "
            "project-supported mechanisms. Diagnose failures before changing approach. Revert "
            "only your own changes when safe; preserve user work and request authorization for"
            " destructive recovery. Record failed approaches and recovery evidence."
        ),
        "agent_contract.escalation_rules": (
            "Pause the affected work for missing required access, conflicting or unresolved "
            "architectural requirements, or proposed changes to scope, security boundaries, "
            "compatibility, or acceptance criteria. Respect explicit approval boundaries. "
            "Persist progress and present the specific decision, impact, and recommendation; "
            "continue independent authorized work when possible."
        ),
        "agent_contract.dependency_security": (
            "Follow project and user dependency, licensing, and security policies. Reuse "
            "existing dependencies first; justify additions, lock versions with the project's "
            "supported mechanism, and run applicable vulnerability and static checks. Report "
            "unavailable checks and unresolved vulnerabilities; do not claim security "
            "validation without evidence."
        ),
    }
)


@dataclass(frozen=True)
class ResolvedContract:
    card: RequirementCard
    sources: dict[str, str]
    unresolved_fields: list[str]

    def coding_spec_dict(self) -> dict[str, object]:
        # Existing field shapes remain intact; provenance is additive export metadata.
        return {**self.card.coding_spec_dict(), "decision_sources": self.sources}


def resolve_contract(card: RequirementCard) -> ResolvedContract:
    effective = card.model_copy(deep=True)
    sources: dict[str, str] = {}
    unresolved = open_architectural_decisions(card)
    for field_name in (*APPLICATION_FIELD_NAMES, *_DEFAULT_POLICIES):
        raw = str(card.get_leaf(field_name)).strip()
        unknown = raw.casefold() in UNKNOWN_ANSWERS
        delegated_request = raw.casefold() == "recommend an option"
        if raw and not unknown and not delegated_request:
            sources[field_name] = "user"
            continue
        if field_name in _DEFAULT_POLICIES:
            value = _DEFAULT_POLICIES[field_name]
            sources[field_name] = "default"
        elif field_name not in CONSULTATION_TOPICS:
            value = _DELEGATIONS[field_name.split(".")[1]]
            sources[field_name] = "delegated"
        elif delegated_request:
            value = (
                "Recommend a decision within accepted constraints, explain its "
                "architectural impact, and obtain acceptance before treating it as a "
                "requirement."
            )
            sources[field_name] = "delegated"
            if field_name not in unresolved:
                unresolved.append(field_name)
        else:
            sources[field_name] = "unresolved" if field_name in unresolved else "not_applicable"
            continue
        if raw:
            value = f"User response: {raw}. {value}"
        effective.set_leaf(field_name, value)
    effective.unresolved_fields = list(unresolved)
    return ResolvedContract(effective, sources, unresolved)
