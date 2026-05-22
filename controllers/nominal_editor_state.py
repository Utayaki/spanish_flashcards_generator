from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from widgets.form_state import apply_gender_availability_to_forms, empty_nominal_forms, validate_gender_availability

NOMINAL_WORD_TYPES = {"noun", "adjective", "determiner"}
GENDER_LABEL_BY_WORD_TYPE = {
    "noun": "Gender",
    "adjective": "Forms",
    "determiner": "Forms",
}
WORD_TYPE_LABELS = {
    "noun": "Noun",
    "adjective": "Adjective",
    "determiner": "Determiner",
}
GENDER_CHOICES = (
    ("masc", "masc"),
    ("fem", "fem"),
    ("both", "both"),
    ("ambiguous", "ambiguous"),
)


class NominalEditorStateError(ValueError):
    """Raised when nominal editor state is invalid."""


def ensure_nominal_word_type(word_type: str) -> str:
    if word_type not in NOMINAL_WORD_TYPES:
        allowed = ", ".join(sorted(NOMINAL_WORD_TYPES))
        raise NominalEditorStateError(f"expected nominal word type ({allowed}), got: {word_type}")
    return word_type


def editor_title(word_type: str, lemma: str) -> str:
    ensure_nominal_word_type(word_type)
    clean_lemma = lemma.strip() or "Untitled"
    return f"{WORD_TYPE_LABELS[word_type]}: {clean_lemma}"


def gender_field_label(word_type: str) -> str:
    ensure_nominal_word_type(word_type)
    return GENDER_LABEL_BY_WORD_TYPE[word_type]


def nested_inflections_to_tuple_map(
    inflections: dict[str, dict[str, str | None]] | None,
) -> dict[tuple[str, str], str | None]:
    forms = empty_nominal_forms()
    if not inflections:
        return forms

    for number, gender_map in inflections.items():
        for gender, form in gender_map.items():
            key = (number, gender)
            if key in forms:
                forms[key] = form
    return forms


def tuple_map_to_nested_inflections(
    forms: dict[tuple[str, str], str | None],
) -> dict[str, dict[str, str | None]]:
    nested: dict[str, dict[str, str | None]] = {
        "singular": {"masc": None, "fem": None},
        "plural": {"masc": None, "fem": None},
    }
    for (number, gender), form in forms.items():
        if number in nested and gender in nested[number]:
            nested[number][gender] = form
    return nested


@dataclass(frozen=True)
class NominalSavePayload:
    lemma: str
    english: str
    gender_availability: str
    forms: dict[tuple[str, str], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        english: str,
        gender_availability: str,
        forms: dict[tuple[str, str], str | None],
    ) -> "NominalSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise NominalEditorStateError("lemma cannot be empty")

        clean_gender = validate_gender_availability(gender_availability)
        clean_forms = apply_gender_availability_to_forms(forms, clean_gender)
        return cls(
            lemma=clean_lemma,
            english=english.strip(),
            gender_availability=clean_gender,
            forms=clean_forms,
        )

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "gender_availability": self.gender_availability,
            "inflections": tuple_map_to_nested_inflections(self.forms),
        }
