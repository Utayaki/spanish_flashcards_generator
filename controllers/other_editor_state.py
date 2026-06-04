from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from widgets.form_state import empty_nominal_forms, normalize_optional_form


class OtherEditorStateError(ValueError):
    """Raised when other-editor state is invalid."""


def ensure_other_word_type(word_type: str) -> str:
    if word_type != "other":
        raise OtherEditorStateError(f"expected other word type, got: {word_type}")
    return word_type


def validate_has_inflections(value: bool | None) -> bool:
    if value is None:
        raise OtherEditorStateError("choose whether this word has inflections")
    return bool(value)


def editor_title(lemma: str) -> str:
    clean_lemma = lemma.strip() or "Untitled"
    return f"Other: {clean_lemma}"


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


@dataclass(frozen=True)
class OtherSavePayload:
    lemma: str
    english: str
    has_inflections: bool
    forms: dict[tuple[str, str], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        english: str,
        has_inflections: bool | None,
        forms: dict[tuple[str, str], str | None],
    ) -> "OtherSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise OtherEditorStateError("lemma cannot be empty")
        clean_english = english.strip()
        if not clean_english:
            raise OtherEditorStateError("english definition cannot be empty")
        clean_has_inflections = validate_has_inflections(has_inflections)
        return cls(
            lemma=clean_lemma,
            english=clean_english,
            has_inflections=clean_has_inflections,
            forms=clean_unrestricted_forms(forms) if clean_has_inflections else empty_nominal_forms(),
        )

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "has_inflections": self.has_inflections,
            "forms": self.forms,
        }
