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
    compatibility: str = ""
    delivery: str = ""
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
            "What development machine, operating system, tools, and build "
            "constraints matter? Keep these separate from target-system "
            "requirements."
        ),
        [],
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
