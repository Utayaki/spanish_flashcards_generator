from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from widgets.form_state import (
    GENDERS,
    NUMBERS,
    SHARED_GENDER_KEY,
    normalize_optional_form,
    validate_gender,
    validate_gender_availability,
    validate_number,
)

GENDER_CHOICES = (
    ("masculine", "Always masculine"),
    ("feminine", "Always feminine"),
    ("both", "Masculine and feminine"),
)


class NounEditorStateError(ValueError):
    """Raised when noun editor state is invalid."""


def ensure_noun_lemma_type(lemma_type: str) -> str:
    if lemma_type != "noun":
        raise NounEditorStateError(f"expected noun lemma type, got: {lemma_type}")
    return lemma_type


def editor_title(lemma: str) -> str:
    clean_lemma = lemma.strip() or "Untitled"
    return f"Noun: {clean_lemma}"


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
            if key[1] in GENDERS:
                forms[key] = form
    return forms


def tuple_map_to_nested_inflections(
    forms: dict[tuple[str, str | None], str | None],
) -> dict[str, dict[str, str | None]]:
    nested: dict[str, dict[str, str | None]] = {
        "singular": {"masculine": None, "feminine": None},
        "plural": {"masculine": None, "feminine": None},
    }
    for (number, gender), form in forms.items():
        if number in nested and gender in GENDERS:
            nested[number][gender] = form
    return nested


def _clean_forms(forms: dict[tuple[str, str | None], str | None]) -> dict[tuple[str, str | None], str | None]:
    cleaned: dict[tuple[str, str | None], str | None] = {}
    for (number, gender), value in forms.items():
        validate_number(number)
        validate_gender(gender)
        cleaned[(number, gender)] = normalize_optional_form(value)
    return cleaned


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
        return cls(clean_lemma, clean_english, clean_gender, _clean_forms(forms))

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "gender_availability": self.gender_availability,
            "inflections": tuple_map_to_nested_inflections(self.forms),
        }
