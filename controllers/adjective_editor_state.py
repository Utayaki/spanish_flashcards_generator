from __future__ import annotations

from dataclasses import dataclass

from widgets.form_state import normalize_optional_form, validate_gender, validate_number


ADJECTIVE_INFLECTION_TYPES = {"plurality", "gender_plurality"}


class AdjectiveEditorStateError(ValueError):
    """Raised when adjective editor state is invalid."""


def validate_adjective_inflection_type(value: str | None) -> str:
    cleaned = (value or "gender_plurality").strip()
    if cleaned not in ADJECTIVE_INFLECTION_TYPES:
        raise AdjectiveEditorStateError(f"invalid adjective inflection type: {cleaned}")
    return cleaned


def _clean_forms(forms: dict[tuple[str, str | None], str | None]) -> dict[tuple[str, str | None], str | None]:
    cleaned: dict[tuple[str, str | None], str | None] = {}
    for (number, gender), value in forms.items():
        validate_number(number)
        validate_gender(gender)
        cleaned[(number, gender)] = normalize_optional_form(value)
    return cleaned


@dataclass(frozen=True)
class AdjectiveSavePayload:
    lemma: str
    english: str
    inflection_type: str
    forms: dict[tuple[str, str | None], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        english: str,
        inflection_type: str,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "AdjectiveSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise AdjectiveEditorStateError("lemma cannot be empty")
        clean_english = english.strip()
        if not clean_english:
            raise AdjectiveEditorStateError("english definition cannot be empty")
        clean_type = validate_adjective_inflection_type(inflection_type)
        return cls(clean_lemma, clean_english, clean_type, _clean_forms(forms))
