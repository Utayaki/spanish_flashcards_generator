from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from widgets.form_state import (
    GENDERS,
    NUMBERS,
    SHARED_GENDER_KEY,
    normalize_optional_form,
    validate_gender,
    validate_number,
)

ADJECTIVE_INFLECTION_TYPES = {"plurality", "gender_plurality"}


class AdjectiveEditorStateError(ValueError):
    """Raised when adjective editor state is invalid."""


def ensure_adjective_lemma_type(lemma_type: str) -> str:
    if lemma_type != "adjective":
        raise AdjectiveEditorStateError(f"expected adjective lemma type, got: {lemma_type}")
    return lemma_type


def editor_title(lemma: str) -> str:
    clean_lemma = lemma.strip() or "Untitled"
    return f"Adjective: {clean_lemma}"


def validate_adjective_inflection_type(value: str | None) -> str:
    cleaned = (value or "gender_plurality").strip()
    if cleaned not in ADJECTIVE_INFLECTION_TYPES:
        raise AdjectiveEditorStateError(f"invalid adjective inflection type: {cleaned}")
    return cleaned


def nested_inflections_to_tuple_map(
    inflections: dict[str, dict[str, str | None]] | None,
) -> dict[tuple[str, str | None], str | None]:
    forms: dict[tuple[str, str | None], str | None] = {}
    if not inflections:
        return forms
    for number, gender_map in inflections.items():
        if number not in NUMBERS:
            continue
        for gender, form in gender_map.items():
            key = (number, None if gender == SHARED_GENDER_KEY else gender)
            if key[1] is None or key[1] in GENDERS:
                forms[key] = form
    return forms


def tuple_map_to_nested_inflections(
    forms: dict[tuple[str, str | None], str | None],
) -> dict[str, dict[str, str | None]]:
    nested: dict[str, dict[str, str | None]] = {
        "singular": {"masculine": None, "feminine": None, SHARED_GENDER_KEY: None},
        "plural": {"masculine": None, "feminine": None, SHARED_GENDER_KEY: None},
    }
    for (number, gender), form in forms.items():
        if number not in nested:
            continue
        nested[number][SHARED_GENDER_KEY if gender is None else gender] = form
    return nested


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

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "adjective_inflection_type": self.inflection_type,
            "inflections": tuple_map_to_nested_inflections(self.forms),
        }
