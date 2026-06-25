from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from controllers.verb_form_catalog import VERB_FORM_CODES
from widgets.form_state import normalize_optional_form


class VerbEditorStateError(ValueError):
    """Raised when verb-editor state is invalid."""


def normalize_form_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {"form": normalize_optional_form(payload.get("form"))}


def empty_verb_forms() -> dict[str, dict[str, Any]]:
    return {code: {"form": None} for code in sorted(VERB_FORM_CODES)}


@dataclass(frozen=True)
class VerbSavePayload:
    headword: str
    explanation: str
    forms: dict[str, dict[str, Any]]

    @classmethod
    def from_inputs(
        cls,
        *,
        headword: str,
        explanation: str,
        forms: dict[str, dict[str, Any]],
    ) -> "VerbSavePayload":
        clean_headword = headword.strip()
        if not clean_headword:
            raise VerbEditorStateError("headword cannot be empty")

        clean_explanation = explanation.strip()
        if not clean_explanation:
            raise VerbEditorStateError("explanation cannot be empty")

        clean_forms = empty_verb_forms()
        for code, payload in forms.items():
            if code not in VERB_FORM_CODES:
                raise VerbEditorStateError(f"invalid verb form code: {code}")
            clean_forms[code] = normalize_form_payload(payload)

        return cls(headword=clean_headword, explanation=clean_explanation, forms=clean_forms)
