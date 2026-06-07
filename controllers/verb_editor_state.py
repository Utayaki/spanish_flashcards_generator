from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from controllers.verb_form_catalog import VERB_FORM_CODES, VERB_FORM_COUNT
from widgets.form_state import normalize_optional_form


class VerbEditorStateError(ValueError):
    """Raised when verb-editor state is invalid."""


def ensure_verb_lemma_type(lemma_type: str) -> str:
    if lemma_type != "verb":
        raise VerbEditorStateError(f"expected verb lemma type, got: {lemma_type}")
    return lemma_type


def editor_title(lemma: str) -> str:
    clean_lemma = lemma.strip() or "Untitled"
    return f"Verb: {clean_lemma}"


def normalize_form_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {"form": normalize_optional_form(payload.get("form"))}


def empty_verb_forms() -> dict[str, dict[str, Any]]:
    return {code: {"form": None} for code in sorted(VERB_FORM_CODES)}


def extract_forms_from_loaded_verb(loaded_verb: dict[str, Any]) -> dict[str, dict[str, Any]]:
    forms = empty_verb_forms()
    loaded_forms = loaded_verb.get("forms", {})
    if not isinstance(loaded_forms, dict):
        return forms
    for code, payload in loaded_forms.items():
        if code in forms and isinstance(payload, dict):
            forms[str(code)] = normalize_form_payload(payload)
    return forms


@dataclass(frozen=True)
class VerbSavePayload:
    lemma: str
    english: str
    forms: dict[str, dict[str, Any]]

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        english: str,
        forms: dict[str, dict[str, Any]],
    ) -> "VerbSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise VerbEditorStateError("lemma cannot be empty")

        clean_english = english.strip()
        if not clean_english:
            raise VerbEditorStateError("english definition cannot be empty")

        clean_forms = empty_verb_forms()
        for code, payload in forms.items():
            if code not in VERB_FORM_CODES:
                raise VerbEditorStateError(f"invalid verb form code: {code}")
            clean_forms[code] = normalize_form_payload(payload)

        return cls(lemma=clean_lemma, english=clean_english, forms=clean_forms)

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "form_count": len(self.forms),
            "expected_form_count": VERB_FORM_COUNT,
        }
