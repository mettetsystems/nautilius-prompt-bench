from enum import StrEnum


class EditIntent(StrEnum):
    ADD_REQUIREMENT = "add_requirement"
    REMOVE_REQUIREMENT = "remove_requirement"
    CHANGE_TONE = "change_tone"
    CHANGE_OUTPUT_SHAPE = "change_output_shape"
    ADD_CONSTRAINT = "add_constraint"
    REMOVE_CONSTRAINT = "remove_constraint"
    TIGHTEN_LANGUAGE = "tighten_language"
    EXPAND_DETAIL = "expand_detail"
    OPTIMIZE_FOR_TOKENS = "optimize_for_tokens"
    CLARIFY_UNSPECIFIED_FIELD = "clarify_unspecified_field"
    DIRECT_EDIT = "direct_edit"
    OTHER = "other"
