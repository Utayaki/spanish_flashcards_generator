from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from widgets.form_state import empty_nominal_forms, normalize_optional_form


OTHER_INFLECTION_TYPES = {"none", "gender_plurality", "person_gender_plurality"}
OTHER_PERSONS = (
    "yo",
    "tu",
    "vos",
    "el_ella_usted",
    "nosotros",
    "vosotros",
    "ellos_ellas_ustedes",
)
OTHER_PERSON_FORM_KEYS = {(person, gender) for person in OTHER_PERSONS for gender in ("masc", "fem")}


class OtherEditorStateError(ValueError):
    """Raised when other-editor state is invalid."""


def ensure_other_word_type(word_type: str) -> str:
    if word_type != "other":
        raise OtherEditorStateError(f"expected other word type, got: {word_type}")
    return word_type


def validate_inflection_type(value: str | None) -> str:
    if value is None or not value.strip():
        raise OtherEditorStateError("choose inflection type")
    cleaned = value.strip()
    if cleaned not in OTHER_INFLECTION_TYPES:
        raise OtherEditorStateError(f"invalid inflection type: {cleaned}")
    return cleaned


def editor_title(lemma: str) -> str:
    clean_lemma = lemma.strip() or "Untitled"
    return f"Other: {clean_lemma}"


def empty_person_forms() -> dict[tuple[str, str], str | None]:
    return {(person, gender): None for person in OTHER_PERSONS for gender in ("masc", "fem")}


def nested_inflections_to_tuple_map(inflections: dict[str, dict[str, str | None]] | None) -> dict[tuple[str, str], str | None]:
    forms = empty_nominal_forms()
    if not inflections:
        return forms
    for number, gender_map in inflections.items():
        for gender, form in gender_map.items():
            key = (number, gender)
            if key in forms:
                forms[key] = form
    return forms


def clean_unrestricted_forms(forms: dict[tuple[str, str], str | None]) -> dict[tuple[str, str], str | None]:
    cleaned = empty_nominal_forms()
    for key, value in forms.items():
        if key in cleaned:
            cleaned[key] = normalize_optional_form(value)
    return cleaned


def clean_person_forms(forms: dict[tuple[str, str], str | None]) -> dict[tuple[str, str], str | None]:
    cleaned = empty_person_forms()
    for key, value in forms.items():
        if key in cleaned:
            cleaned[key] = normalize_optional_form(value)
    return cleaned


@dataclass(frozen=True)
class OtherSavePayload:
    lemma: str
    english: str
    inflection_type: str
    forms: dict[tuple[str, str], str | None]
    person_forms: dict[tuple[str, str], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        english: str,
        inflection_type: str | None,
        forms: dict[tuple[str, str], str | None],
        person_forms: dict[tuple[str, str], str | None],
    ) -> "OtherSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise OtherEditorStateError("lemma cannot be empty")
        clean_english = english.strip()
        if not clean_english:
            raise OtherEditorStateError("english definition cannot be empty")
        clean_type = validate_inflection_type(inflection_type)
        return cls(
            lemma=clean_lemma,
            english=clean_english,
            inflection_type=clean_type,
            forms=clean_unrestricted_forms(forms) if clean_type == "gender_plurality" else empty_nominal_forms(),
            person_forms=clean_person_forms(person_forms) if clean_type == "person_gender_plurality" else empty_person_forms(),
        )

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "inflection_type": self.inflection_type,
            "forms": self.forms,
            "person_forms": self.person_forms,
        }
