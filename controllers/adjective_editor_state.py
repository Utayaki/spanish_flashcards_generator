from __future__ import annotations

from dataclasses import dataclass

from widgets.form_state import clean_form_mapping


ADJECTIVE_INFLECTION_TYPES = {"plurality", "gender_plurality"}


class AdjectiveEditorStateError(ValueError):
    """Raised when adjective editor state is invalid."""


def validate_adjective_inflection_type(value: str | None) -> str:
    cleaned = (value or "gender_plurality").strip()
    if cleaned not in ADJECTIVE_INFLECTION_TYPES:
        raise AdjectiveEditorStateError(f"invalid adjective inflection type: {cleaned}")
    return cleaned


@dataclass(frozen=True)
class AdjectiveSavePayload:
    headword: str
    explanation: str
    inflection_type: str
    forms: dict[tuple[str, str | None], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        headword: str,
        explanation: str,
        inflection_type: str,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "AdjectiveSavePayload":
        clean_headword = headword.strip()
        if not clean_headword:
            raise AdjectiveEditorStateError("headword cannot be empty")
        clean_explanation = explanation.strip()
        if not clean_explanation:
            raise AdjectiveEditorStateError("explanation cannot be empty")
        clean_type = validate_adjective_inflection_type(inflection_type)
        return cls(clean_headword, clean_explanation, clean_type, clean_form_mapping(forms))
