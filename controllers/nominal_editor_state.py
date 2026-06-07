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

NOMINAL_LEMMA_TYPES = {"noun", "adjective"}
GENDER_LABEL_BY_LEMMA_TYPE = {"noun": "Gender", "adjective": "Forms"}
LEMMA_TYPE_LABELS = {"noun": "Noun", "adjective": "Adjective"}
GENDER_CHOICES = (
    ("masculine", "Always masculine"),
    ("feminine", "Always feminine"),
    ("both", "Masculine and feminine"),
)
ADJECTIVE_INFLECTION_TYPES = {"plurality", "gender_plurality"}


class NominalEditorStateError(ValueError):
    """Raised when nominal editor state is invalid."""


def ensure_nominal_lemma_type(lemma_type: str) -> str:
    if lemma_type not in NOMINAL_LEMMA_TYPES:
        allowed = ", ".join(sorted(NOMINAL_LEMMA_TYPES))
        raise NominalEditorStateError(f"expected nominal lemma type ({allowed}), got: {lemma_type}")
    return lemma_type


def editor_title(lemma_type: str, lemma: str) -> str:
    ensure_nominal_lemma_type(lemma_type)
    clean_lemma = lemma.strip() or "Untitled"
    return f"{LEMMA_TYPE_LABELS[lemma_type]}: {clean_lemma}"


def gender_field_label(lemma_type: str) -> str:
    ensure_nominal_lemma_type(lemma_type)
    return GENDER_LABEL_BY_LEMMA_TYPE[lemma_type]


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


def validate_adjective_inflection_type(value: str | None) -> str:
    cleaned = (value or "gender_plurality").strip()
    if cleaned not in ADJECTIVE_INFLECTION_TYPES:
        raise NominalEditorStateError(f"invalid adjective inflection type: {cleaned}")
    return cleaned


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
            raise NominalEditorStateError("lemma cannot be empty")
        clean_english = english.strip()
        if not clean_english:
            raise NominalEditorStateError("english definition cannot be empty")
        clean_gender = validate_gender_availability(gender_availability)
        return cls(clean_lemma, clean_english, clean_gender, _clean_forms(forms))

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "gender_availability": self.gender_availability,
            "inflections": tuple_map_to_nested_inflections(self.forms),
        }


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
            raise NominalEditorStateError("lemma cannot be empty")
        clean_english = english.strip()
        if not clean_english:
            raise NominalEditorStateError("english definition cannot be empty")
        clean_type = validate_adjective_inflection_type(inflection_type)
        return cls(clean_lemma, clean_english, clean_type, _clean_forms(forms))

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "adjective_inflection_type": self.inflection_type,
            "inflections": tuple_map_to_nested_inflections(self.forms),
        }
