from __future__ import annotations

from dataclasses import dataclass

from widgets.form_state import NUMBERS, empty_gendered_forms, empty_shared_forms, normalize_optional_form


OTHER_INFLECTION_TYPES = {"none", "plurality", "gender_plurality"}


class OtherEditorStateError(ValueError):
    """Raised when other-editor state is invalid."""


def validate_inflection_type(value: str | None) -> str:
    if value is None or not value.strip():
        raise OtherEditorStateError("choose inflection type")
    cleaned = value.strip()
    if cleaned not in OTHER_INFLECTION_TYPES:
        raise OtherEditorStateError(f"invalid inflection type: {cleaned}")
    return cleaned


def clean_gender_plurality_forms(forms: dict[tuple[str, str | None], str | None]) -> dict[tuple[str, str | None], str | None]:
    cleaned = empty_gendered_forms()
    for key, value in forms.items():
        if key in cleaned:
            cleaned[key] = normalize_optional_form(value)
    return cleaned


def clean_plurality_forms(forms: dict[tuple[str, str | None], str | None]) -> dict[tuple[str, str | None], str | None]:
    cleaned = empty_shared_forms()
    for number in NUMBERS:
        cleaned[(number, None)] = normalize_optional_form(forms.get((number, None)))
    return cleaned


@dataclass(frozen=True)
class OtherSavePayload:
    lemma: str
    explanation: str
    inflection_type: str
    forms: dict[tuple[str, str | None], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        explanation: str,
        inflection_type: str | None,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "OtherSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise OtherEditorStateError("lemma cannot be empty")
        clean_explanation = explanation.strip()
        if not clean_explanation:
            raise OtherEditorStateError("explanation cannot be empty")
        clean_type = validate_inflection_type(inflection_type)
        return cls(
            lemma=clean_lemma,
            explanation=clean_explanation,
            inflection_type=clean_type,
            forms=(
                clean_plurality_forms(forms)
                if clean_type == "plurality"
                else clean_gender_plurality_forms(forms)
                if clean_type == "gender_plurality"
                else empty_gendered_forms()
            ),
        )
