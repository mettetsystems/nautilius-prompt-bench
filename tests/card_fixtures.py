from prompt_piper_api.domain.requirement_card import RequirementCard


def empty_contract() -> dict[str, str]:
    return {
        "definition_of_done": "",
        "change_scope": "",
        "architecture_policy": "",
        "discovery_policy": "",
        "execution_strategy": "",
        "validation_strategy": "",
        "failure_recovery": "",
        "autonomy_policy": "",
        "persistent_memory": "",
        "completion_contract": "",
        "resource_budget": "",
        "tool_safety": "",
        "context_compaction": "",
        "rollback_protocol": "",
        "escalation_rules": "",
        "dependency_security": "",
    }


def sample_contract(**overrides: str) -> dict[str, str]:
    data = empty_contract()
    data.update(
        {
            "definition_of_done": (
                "COMPLETE only when acceptance criteria are evidenced. "
                "Otherwise PARTIAL, BLOCKED, or FAILED."
            ),
            "change_scope": "Follow a minimum-necessary change policy.",
            "architecture_policy": "Reuse existing project patterns before new abstractions.",
            "discovery_policy": "Inspect the repo and write a short plan before substantial edits.",
            "execution_strategy": "Implement small reversible units and test each unit.",
            "validation_strategy": "Record real test commands; never claim tests probably pass.",
            "failure_recovery": "Diagnose, apply a minimal fix, and never suppress errors blindly.",
            "autonomy_policy": "Autonomous on low-risk work; escalate high-impact changes.",
            "persistent_memory": "Maintain .agent/PLAN.md, STATUS.md, DECISIONS.md, and ISSUES.md.",
            "completion_contract": "Produce an evidence report before declaring COMPLETE.",
            "resource_budget": "Pause after 150 API calls or 2 hours per sub-task.",
            "tool_safety": "No force-push, no secret dumps, sandboxed execution.",
            "context_compaction": "Compact at 80%; preserve the task contract and .agent/ files.",
            "rollback_protocol": "Checkpoint on green tests; reset after 3 failed fixes.",
            "escalation_rules": "Pause on missing secrets, conflicts, or exhausted recovery.",
            "dependency_security": "SAST and audit; MIT/Apache/BSD; pin minor versions.",
        }
    )
    data.update(overrides)
    return data


def sample_card(
    *,
    objective: str = "Implement a FastAPI user create endpoint",
    task_type: str = "new feature logic",
    environment: str = "Python 3.12 with FastAPI and Pydantic v2",
    extra_constraints: list[str] | None = None,
    contract: dict[str, str] | None = None,
) -> RequirementCard:
    return RequirementCard(
        task_identity={
            "objective": objective,
            "task_type": task_type,
            "environment": environment,
            "additional_constraints": list(extra_constraints or []),
        },
        agent_contract=contract if contract is not None else sample_contract(),
    )
