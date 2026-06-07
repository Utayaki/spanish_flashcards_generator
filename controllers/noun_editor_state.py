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
    lemma: str
    english: str
    gender_availability: str
    forms: dict[tuple[str, str | None], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        english: str,
        gender_availability: str,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "NounSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise NounEditorStateError("lemma cannot be empty")
        clean_english = english.strip()
        if not clean_english:
            raise NounEditorStateError("english definition cannot be empty")
        clean_gender = validate_gender_availability(gender_availability)
        return cls(clean_lemma, clean_english, clean_gender, clean_form_mapping(forms))
