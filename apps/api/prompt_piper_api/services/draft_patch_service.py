import json
import re

from pydantic import BaseModel

from prompt_piper_api.domain.edit_intent import EditIntent
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.llm.base import ChatMessage, LLMClient
from prompt_piper_api.llm.fallback import with_llm_fallback
from prompt_piper_api.services.draft_generator import DraftGenerator
from prompt_piper_api.services.requirement_card_extractor import RequirementCardExtractor

_TIGHTEN_CONSTRAINT = "Keep language precise without omitting operational rules"
_EXPAND_CONSTRAINT = "Provide thorough detail where helpful"
_TOKEN_CONSTRAINT = "Do not compress operational rules to save tokens; prefer clarity"


class EditPatchResult(BaseModel):
    intent: EditIntent
    semantic_diff: str
    change_summary: str
    updated_body: str
    updated_requirement_card: RequirementCard


class DraftPatchService:
    """Classifies edit intent, patches the requirement card, and regenerates drafts."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm
        self._generator = DraftGenerator(llm=llm)
        self._extractor = RequirementCardExtractor(llm=llm)

    def apply(self, card: RequirementCard, instruction: str, previous_body: str) -> EditPatchResult:
        return with_llm_fallback(
            self._llm,
            lambda client: self._apply_with_llm(client, card, instruction, previous_body),
            lambda: self._apply_rule_based(card, instruction, previous_body),
        )

    def classify(self, instruction: str) -> EditIntent:
        return self._classify_rule_based(instruction)

    def _apply_rule_based(
        self,
        card: RequirementCard,
        instruction: str,
        previous_body: str,
    ) -> EditPatchResult:
        before = card.model_copy(deep=True)
        intent = self._classify_rule_based(instruction)
        self._patch_card(card, intent, instruction)
        generated = self._generator.generate(card)
        card.unresolved_fields = list(generated.unresolved_fields)
        semantic_diff = self._semantic_diff_summary(before, card, intent, instruction)
        return EditPatchResult(
            intent=intent,
            semantic_diff=semantic_diff,
            change_summary=f"Applied {intent.value} edit.",
            updated_body=generated.body,
            updated_requirement_card=card.model_copy(deep=True),
        )

    def _apply_with_llm(
        self,
        llm: LLMClient,
        card: RequirementCard,
        instruction: str,
        previous_body: str,
    ) -> EditPatchResult:
        before = card.model_copy(deep=True)
        response = llm.chat(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "Classify edit intent using the provided enum values, update the "
                        "coding requirement card (task_identity plus 16-question agent_contract), and return JSON with "
                        "intent, semantic_diff, and updated_requirement_card. semantic_diff must "
                        "be one short sentence."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "instruction": instruction,
                            "requirement_card": card.model_dump(),
                            "previous_draft": previous_body,
                            "allowed_intents": [intent.value for intent in EditIntent],
                        }
                    ),
                ),
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.content)
        try:
            intent = EditIntent(str(payload.get("intent", EditIntent.OTHER.value)))
        except ValueError:
            intent = EditIntent.OTHER

        updated = RequirementCard.model_validate(payload.get("updated_requirement_card", card))
        card.task_identity = updated.task_identity
        card.agent_contract = updated.agent_contract
        card.optimization_targets = updated.optimization_targets
        card.unresolved_fields = updated.unresolved_fields

        generated = self._generator.generate(card)
        card.unresolved_fields = list(generated.unresolved_fields)
        semantic_diff = str(payload.get("semantic_diff", "")).strip()
        if not semantic_diff:
            semantic_diff = self._semantic_diff_summary(before, card, intent, instruction)

        return EditPatchResult(
            intent=intent,
            semantic_diff=semantic_diff,
            change_summary=str(payload.get("change_summary", f"Applied {intent.value} edit.")),
            updated_body=generated.body,
            updated_requirement_card=card.model_copy(deep=True),
        )

    def _classify_rule_based(self, instruction: str) -> EditIntent:
        text = instruction.strip().lower()
        if re.search(r"\b(remove requirement|drop requirement|delete requirement)\b", text):
            return EditIntent.REMOVE_REQUIREMENT
        if re.search(r"\b(add requirement|include requirement|also require|must also)\b", text):
            return EditIntent.ADD_REQUIREMENT
        if re.search(r"\b(remove constraint|drop constraint|relax constraint)\b", text):
            return EditIntent.REMOVE_CONSTRAINT
        if re.search(r"\b(add constraint|must not|do not|avoid|never)\b", text):
            return EditIntent.ADD_CONSTRAINT
        if re.search(
            r"\b(clarify|specify|fill in|define)\b.*\b("
            r"objective|environment|stack|done|scope|budget|memory)\b",
            text,
        ):
            return EditIntent.CLARIFY_UNSPECIFIED_FIELD
        if re.search(r"\b(clarify unspecified|specify unspecified)\b", text):
            return EditIntent.CLARIFY_UNSPECIFIED_FIELD
        if re.search(r"\b(token|tokens|token budget|optimize for tokens)\b", text):
            return EditIntent.OPTIMIZE_FOR_TOKENS
        if re.search(r"\b(shorter|concise|brief|trim|tighten)\b", text):
            return EditIntent.TIGHTEN_LANGUAGE
        if re.search(r"\b(longer|expand|more detail|elaborate)\b", text):
            return EditIntent.EXPAND_DETAIL
        if re.search(
            r"\b(tone|style|explanation|code only|step-by-step|formal|casual)\b",
            text,
        ):
            return EditIntent.CHANGE_TONE
        if re.search(
            r"\b(format|output contract|output shape|output:|shape:|json|sql|interface)\b",
            text,
        ):
            return EditIntent.CHANGE_OUTPUT_SHAPE
        return EditIntent.OTHER

    def _patch_card(self, card: RequirementCard, intent: EditIntent, instruction: str) -> None:
        cleaned = instruction.strip()
        if intent is EditIntent.ADD_REQUIREMENT:
            requirement = self._extract_payload(
                cleaned,
                ("add requirement:", "include requirement:"),
            )
            value = requirement or cleaned
            if value not in card.task_identity.additional_constraints:
                card.task_identity.additional_constraints.append(value)
        elif intent is EditIntent.REMOVE_REQUIREMENT:
            target = self._extract_payload(cleaned, ("remove requirement:", "drop requirement:"))
            self._remove_matching(card.task_identity.additional_constraints, target or cleaned)
        elif intent is EditIntent.CHANGE_TONE:
            tone = self._extract_payload(
                cleaned,
                (
                    "explanation:",
                    "explanation level:",
                    "tone:",
                    "style:",
                    "make it",
                    "switch tone to",
                    "change tone to",
                ),
            )
            value = tone or cleaned
            if value not in card.task_identity.additional_constraints:
                card.task_identity.additional_constraints.append(value)
        elif intent is EditIntent.CHANGE_OUTPUT_SHAPE:
            shape = self._extract_payload(
                cleaned,
                (
                    "change output contract to",
                    "change output shape to",
                    "output contract:",
                    "output shape:",
                    "format:",
                    "output:",
                    "shape:",
                    "change output to",
                ),
            )
            card.agent_contract.completion_contract = shape or cleaned
        elif intent is EditIntent.ADD_CONSTRAINT:
            constraint = self._extract_payload(
                cleaned,
                ("add constraint:", "constraint:", "must not", "avoid", "prefer"),
            )
            value = constraint or cleaned.split(" and change tone")[0].strip()
            if value not in card.task_identity.additional_constraints:
                card.task_identity.additional_constraints.append(value)
            if "change tone to" in cleaned.lower() or "explanation" in cleaned.lower():
                tone = self._extract_payload(
                    cleaned,
                    ("change tone to", "tone to", "explanation level:", "explanation:"),
                )
                if tone and tone not in card.task_identity.additional_constraints:
                    card.task_identity.additional_constraints.append(tone)
        elif intent is EditIntent.REMOVE_CONSTRAINT:
            target = self._extract_payload(cleaned, ("remove constraint:", "drop constraint:"))
            self._remove_matching(card.task_identity.additional_constraints, target or cleaned)
        elif intent is EditIntent.TIGHTEN_LANGUAGE:
            if _TIGHTEN_CONSTRAINT not in card.task_identity.additional_constraints:
                card.task_identity.additional_constraints.append(_TIGHTEN_CONSTRAINT)
        elif intent is EditIntent.EXPAND_DETAIL:
            if _EXPAND_CONSTRAINT not in card.task_identity.additional_constraints:
                card.task_identity.additional_constraints.append(_EXPAND_CONSTRAINT)
        elif intent is EditIntent.OPTIMIZE_FOR_TOKENS:
            card.optimization_targets.clarity = (
                "Do not compress operational rules to save tokens; prefer clarity"
            )
            if _TOKEN_CONSTRAINT not in card.task_identity.additional_constraints:
                card.task_identity.additional_constraints.append(_TOKEN_CONSTRAINT)
        elif intent is EditIntent.CLARIFY_UNSPECIFIED_FIELD:
            self._clarify_unspecified_field(card, cleaned)
        else:
            if card.task_identity.objective:
                card.task_identity.objective = f"{card.task_identity.objective} ({cleaned})"
            else:
                card.task_identity.objective = cleaned

    def _clarify_unspecified_field(self, card: RequirementCard, instruction: str) -> None:
        lowered = instruction.lower()
        value = self._extract_payload(
            instruction,
            ("clarify objective:", "objective:", "specify objective:", "set objective to"),
        )
        if "objective" in lowered:
            self._extractor.apply_answer(card, "task_identity.objective", value or instruction)
            return
        value = self._extract_payload(
            instruction,
            ("environment:", "stack:", "specify environment:", "set environment to"),
        )
        if "environment" in lowered or "stack" in lowered:
            self._extractor.apply_answer(
                card,
                "task_identity.environment",
                value or instruction,
            )
            return
        value = self._extract_payload(
            instruction,
            ("done:", "definition of done:", "specify done:", "set done to"),
        )
        if "done" in lowered or "complete" in lowered:
            self._extractor.apply_answer(
                card,
                "agent_contract.definition_of_done",
                value or instruction,
            )
            return
        value = self._extract_payload(
            instruction,
            ("completion:", "completion contract:", "evidence:"),
        )
        if "completion" in lowered or "evidence" in lowered:
            self._extractor.apply_answer(
                card,
                "agent_contract.completion_contract",
                value or instruction,
            )

    def _semantic_diff_summary(
        self,
        before: RequirementCard,
        after: RequirementCard,
        intent: EditIntent,
        instruction: str,
    ) -> str:
        parts: list[str] = []

        added_constraints = [
            item
            for item in after.task_identity.additional_constraints
            if item not in before.task_identity.additional_constraints
        ]
        removed_constraints = [
            item
            for item in before.task_identity.additional_constraints
            if item not in after.task_identity.additional_constraints
        ]
        before_done = before.agent_contract.definition_of_done
        after_done = after.agent_contract.definition_of_done
        before_complete = before.agent_contract.completion_contract
        after_complete = after.agent_contract.completion_contract
        before_env = before.task_identity.environment
        after_env = after.task_identity.environment

        if before_done != after_done and after_done.strip():
            parts.append("updated the definition of done")
        if before_complete != after_complete and after_complete.strip():
            parts.append("updated the completion contract")
        if before_env != after_env and after_env.strip():
            parts.append(f"set environment to {after_env.strip()}")
        if added_constraints:
            parts.append(f"added {added_constraints[0].lower()}")
        if removed_constraints:
            parts.append(f"removed {removed_constraints[0].lower()}")
        if (
            before.optimization_targets.clarity != after.optimization_targets.clarity
            and after.optimization_targets.clarity
        ):
            parts.append("prioritized clarity over token reduction")
        if (
            before.optimization_targets.efficiency != after.optimization_targets.efficiency
            and after.optimization_targets.efficiency
        ):
            parts.append("updated efficiency guidance")
        if before.objective != after.objective and after.objective.strip():
            parts.append("updated the objective")

        if parts:
            sentence = ", ".join(parts)
            return sentence[0].upper() + sentence[1:] + "."

        fallback = {
            EditIntent.TIGHTEN_LANGUAGE: "Tightened language for brevity.",
            EditIntent.EXPAND_DETAIL: "Expanded detail in the draft.",
            EditIntent.OPTIMIZE_FOR_TOKENS: "Reoriented the draft toward clarity rather than token cuts.",
            EditIntent.CLARIFY_UNSPECIFIED_FIELD: "Clarified a previously unspecified field.",
            EditIntent.OTHER: f"Applied edit: {instruction.strip()}.",
        }
        default = f"Updated the draft based on the {intent.value.replace('_', ' ')} request."
        return fallback.get(intent, default)

    def _extract_payload(self, text: str, prefixes: tuple[str, ...]) -> str:
        lowered = text.lower()
        for prefix in prefixes:
            if prefix in lowered:
                index = lowered.index(prefix)
                return text[index + len(prefix) :].strip(" :-")
        return ""

    def _remove_matching(self, values: list[str], target: str) -> None:
        target_lower = target.lower()
        values[:] = [value for value in values if target_lower not in value.lower()]
