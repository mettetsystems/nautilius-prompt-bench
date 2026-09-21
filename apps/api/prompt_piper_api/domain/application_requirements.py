"""Application decisions, kept separate from agent execution policies."""

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from prompt_piper_api.domain.agent_contract import ContractOption, ContractQuestion

if TYPE_CHECKING:
    from prompt_piper_api.domain.requirement_card import RequirementCard


class ApplicationRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_context: str = ""
    target_environment: str = ""
    operating_systems: str = ""
    hosting: str = ""
    runtime: str = ""
    technology: str = ""
    development_environment: str = ""
    build_isolation: str = ""
    build_toolchain: str = ""
    build_hardware: str = ""
    build_access: str = ""
    build_workspace: str = ""
    environment_bootstrap: str = ""
    validation_environment: str = ""
    environment_parity: str = ""
    compatibility: str = ""
    delivery: str = ""
    permissions: str = ""
    storage: str = ""
    connectivity: str = ""
    offline_sync: str = ""
    constraints: str = ""
    acceptance: str = ""
    harness_controls: str = ""


def _question(name: str, title: str, prompt: str, choices: list[str]) -> ContractQuestion:
    labels = [*choices, "Unsure", "Not applicable", "Recommend an option", "unspecified"]
    return ContractQuestion(
        field_name=f"application_requirements.{name}",
        section_title=title,
        standard_prompt=prompt,
        beginner_prompt=prompt,
        beginner_rationale=(
            "This decision can affect implementation and validation. Leave unknowns explicit."
        ),
        advanced_prompt=prompt,
        options=tuple(
            ContractOption(
                label=x,
                body=x if x != "unspecified" else "",
                explanation="Record your choice without assuming unstated requirements.",
                when_to_use="Choose only if it matches your intent; custom text is welcome.",
            )
            for x in labels
        ),
    )


APPLICATION_QUESTIONS = (
    _question(
        "project_context",
        "Project Context",
        (
            "Is this a new application, an improvement to an existing codebase, or "
            "a non-application task?"
        ),
        ["New application", "Existing codebase", "Non-application task"],
    ),
    _question(
        "target_environment",
        "Target Environment",
        (
            "Where will the finished application run: desktop, mobile, browser, "
            "server, embedded device, or elsewhere? This may differ from the "
            "development machine."
        ),
        ["Desktop", "Browser", "Server"],
    ),
    _question(
        "operating_systems",
        "Supported Operating Systems",
        (
            "Which operating systems and versions must the finished application "
            "support? Include browser or mobile versions where relevant."
        ),
        [],
    ),
    _question(
        "hosting",
        "Hosting",
        (
            "Where will it be hosted: locally, on premises, cloud provider, managed"
            " platform, or self-hosted infrastructure?"
        ),
        [],
    ),
    _question(
        "runtime",
        "Runtime Compatibility",
        "Which runtime environments and versions are required on the target system?",
        [],
    ),
    _question(
        "technology",
        "Technology Choices",
        (
            "Which languages, frameworks, and dependencies are fixed, and which are"
            " open for recommendation?"
        ),
        [],
    ),
    _question(
        "development_environment",
        "Development Environment",
        (
            "On which machine will the long-horizon agent work: local workstation, "
            "remote server, CI runner, or managed sandbox? Specify its OS/distribution "
            "and version, CPU architecture, and shell. Describe the actual agent "
            "environment separately from the finished application’s target system."
        ),
        [],
    ),
    _question(
        'build_isolation',
        'Build Isolation',
        'Where should the agent execute builds: directly on the host, in a project virtual environment, container, VM, or remote builder? Specify the required tool (for example venv, Conda, Docker, Podman, or Nix) and image or configuration version.',
        ['Project virtual environment', 'Containerized build', 'Native host build', 'VM or remote builder'],
    ),
    _question(
        'build_toolchain',
        'Build Toolchain',
        'Which compiler, SDK, language runtime, package manager, and exact versions must the agent use to build the project? Identify lockfiles or version files that are authoritative, and whether changing them is allowed.',
        [],
    ),
    _question(
        'build_hardware',
        'Build Hardware and Accelerators',
        'What CPU architecture, RAM, disk space, and GPU are available to the agent? If GPU acceleration is required, specify driver and CUDA/ROCm versions and how the actual build or inference backend must be verified. Say when CPU fallback is acceptable.',
        ['CPU only', 'GPU required; no silent CPU fallback', 'GPU preferred; CPU fallback allowed'],
    ),
    _question(
        'build_access',
        'Build Network and Dependency Access',
        'Can the build environment access the internet, package registries, and model repositories? Specify offline caches, mirrors, proxies, and how credentials are provided. Name secret variables or credential stores; do not paste secret values.',
        ['Online dependency access', 'Approved mirrors only', 'Offline; use local dependencies'],
    ),
    _question(
        'build_workspace',
        'Agent Workspace and Persistence',
        'What repository path and working directory should the agent use? Which paths are writable, where should build artifacts and caches go, and what survives restarts or context resets? Identify shared directories the agent must preserve.',
        [],
    ),
    _question(
        'environment_bootstrap',
        'Environment Setup and Recovery',
        'How should the agent reproduce the environment from a clean machine or checkout? Specify setup and preflight commands, permitted environment changes, and recovery steps if dependencies or hardware differ.',
        ['Use existing setup scripts; report missing prerequisites', 'Create a reproducible setup script', 'Use a pinned container or environment definition'],
    ),
    _question(
        'validation_environment',
        'Validation Environment',
        'Where must builds and tests be verified: the agent machine, a matching container or VM, CI, staging, or target hardware? Give test commands, required services and fixtures, and checks that cannot run locally.',
        ['Local and CI validation', 'Matching container or VM', 'Target hardware validation'],
    ),
    _question(
        'environment_parity',
        'Build and Target Differences',
        'How does the build environment differ from deployment or production (OS, CPU architecture, runtime versions, GPU backend, services, paths, or permissions)? Specify cross-compilation needs and which differences must be tested before completion.',
        ['Build and target environments match', 'Build and target differ; specify differences'],
    ),
    _question(
        "compatibility",
        "Existing Compatibility",
        (
            "Which existing behavior, public interfaces, file formats, and data "
            "must remain compatible? What migrations are allowed?"
        ),
        [],
    ),
    _question(
        "delivery",
        "Installation and Updates",
        "What installation, packaging, deployment, and update process is expected?",
        [],
    ),
    _question(
        "permissions",
        "Project Permissions",
        (
            "What permission scope does this project require: standard user permissions "
            "or elevated administrator/root access (sudo)? Distinguish development, "
            "installation and updates, and normal runtime. If elevation is needed, "
            "specify which operations require it and how approval should be obtained."
        ),
        [
            "Standard user permissions only; no sudo",
            "Sudo for installation and updates only; run as a standard user",
            "Sudo required for specific runtime operations; specify operations and approval",
        ],
    ),
    _question(
        "storage",
        "Storage and Data",
        "What data must be stored, where, for how long, and with what backup or migration needs?",
        [],
    ),
    _question(
        "connectivity",
        "Integrations and Connectivity",
        "What integrations, networking, authentication, and offline capabilities are needed?",
        [],
    ),
    _question(
        "offline_sync",
        "Offline Synchronization",
        (
            "When offline changes reconnect, how should synchronization and "
            "conflicting edits work? If no local changes are stored, say not "
            "applicable."
        ),
        [],
    ),
    _question(
        "constraints",
        "Application Constraints",
        (
            "What performance, scale, hardware, accessibility, monitoring, and "
            "operational constraints matter? Give measurable limits where known."
        ),
        [],
    ),
    _question(
        "acceptance",
        "Observable Acceptance Criteria",
        (
            "What observable user outcomes and checks establish that this "
            "application or change is complete?"
        ),
        [],
    ),
    _question(
        "harness_controls",
        "Harness Controls",
        (
            "Should scheduling, retry budgets, and context management follow the "
            "receiving harness, or do you need custom operational controls?"
        ),
        ["Use receiving harness controls", "Specify custom controls"],
    ),
)
APPLICATION_FIELD_NAMES = tuple(q.field_name for q in APPLICATION_QUESTIONS)


# Only omit follow-ups when an explicit answer establishes they do not apply.
def applicable_application_fields(card: "RequirementCard") -> tuple[str, ...]:
    app = card.application_requirements
    excluded = set()
    if app.project_context.casefold().strip() == "new application":
        excluded.add("compatibility")
    if app.project_context.casefold().strip() == "non-application task":
        excluded.update(
            {
                "target_environment",
                "operating_systems",
                "hosting",
                "runtime",
                "delivery",
                "storage",
                "connectivity",
                "offline_sync",
                "compatibility",
            }
        )
    connectivity = app.connectivity.casefold()
    if (
        not connectivity
        or "offline" not in connectivity
        or any(x in connectivity for x in ("no offline", "online only", "online-only"))
    ):
        excluded.add("offline_sync")
    return tuple(f for f in APPLICATION_FIELD_NAMES if f.split(".")[1] not in excluded)


def material_open_decisions(card: "RequirementCard") -> list[str]:
    critical = {
        "project_context",
        "target_environment",
        "operating_systems",
        "hosting",
        "runtime",
        "technology",
        "development_environment",
        "build_isolation",
        "build_toolchain",
        "validation_environment",
        "compatibility",
        "acceptance",
    }
    return [
        f
        for f in applicable_application_fields(card)
        if f.split(".")[1] in critical
        and (
            not card.get_leaf(f).strip()
            or card.get_leaf(f).casefold().strip()
            in {"unsure", "unknown", "not sure", "unspecified", "skip"}
        )
    ]
