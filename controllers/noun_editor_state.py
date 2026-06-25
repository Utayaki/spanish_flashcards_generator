from __future__ import annotations

from dataclasses import dataclass

from widgets.form_state import clean_form_mapping, validate_gender_availability


GENDER_CHOICES = (
    ("masculine", "Always masculine"),
    ("feminine", "Always feminine"),
    ("both", "Masculine and feminine"),
)


class NounEditorStateError(ValueError):
    """Raised when noun editor state is invalid."""


@dataclass(frozen=True)
class NounSavePayload:
    headword: str
    explanation: str
    gender_availability: str
    forms: dict[tuple[str, str | None], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        headword: str,
        explanation: str,
        gender_availability: str,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "NounSavePayload":
        clean_headword = headword.strip()
        if not clean_headword:
            raise NounEditorStateError("headword cannot be empty")
        clean_explanation = explanation.strip()
        if not clean_explanation:
            raise NounEditorStateError("explanation cannot be empty")
        clean_gender = validate_gender_availability(gender_availability)
        return cls(clean_headword, clean_explanation, clean_gender, clean_form_mapping(forms))
