from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from widgets.form_state import NUMBERS, empty_gendered_forms, empty_shared_forms, normalize_optional_form

if TYPE_CHECKING:
    from database import SpanishLexicalItemDatabase


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
    headword: str
    explanation: str
    inflection_type: str
    forms: dict[tuple[str, str | None], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        headword: str,
        explanation: str,
        inflection_type: str | None,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "OtherSavePayload":
        clean_headword = headword.strip()
        if not clean_headword:
            raise OtherEditorStateError("headword cannot be empty")
        clean_explanation = explanation.strip()
        if not clean_explanation:
            raise OtherEditorStateError("explanation cannot be empty")
        clean_type = validate_inflection_type(inflection_type)
        return cls(
            headword=clean_headword,
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

    def create(self, db: "SpanishLexicalItemDatabase") -> int:
        return db.create_other_lexical_item(
            headword=self.headword,
            explanation=self.explanation,
            inflection_type=self.inflection_type,
            forms=self.forms,
        )

    def update(self, db: "SpanishLexicalItemDatabase", lexical_item_id: int) -> None:
        db.save_lexical_item_base(lexical_item_id, headword=self.headword, explanation=self.explanation)
        db.save_other_details(lexical_item_id, self.inflection_type)
        db.save_other_inflections(lexical_item_id, self.forms)
