from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from widgets.form_state import clean_form_mapping

if TYPE_CHECKING:
    from database import SpanishLexicalItemDatabase


ADJECTIVE_INFLECTION_TYPES = {"plurality", "gender_plurality"}


class AdjectiveEditorStateError(ValueError):
    """Raised when adjective editor state is invalid."""


def validate_adjective_inflection_type(value: str | None) -> str:
    cleaned = (value or "gender_plurality").strip()
    if cleaned not in ADJECTIVE_INFLECTION_TYPES:
        raise AdjectiveEditorStateError(f"invalid adjective inflection type: {cleaned}")
    return cleaned


@dataclass(frozen=True)
class AdjectiveSavePayload:
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
        inflection_type: str,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "AdjectiveSavePayload":
        clean_headword = headword.strip()
        if not clean_headword:
            raise AdjectiveEditorStateError("headword cannot be empty")
        clean_explanation = explanation.strip()
        if not clean_explanation:
            raise AdjectiveEditorStateError("explanation cannot be empty")
        clean_type = validate_adjective_inflection_type(inflection_type)
        return cls(clean_headword, clean_explanation, clean_type, clean_form_mapping(forms))

    def create(self, db: "SpanishLexicalItemDatabase") -> int:
        return db.create_adjective_lexical_item(
            headword=self.headword,
            explanation=self.explanation,
            inflection_type=self.inflection_type,
            forms=self.forms,
        )

    def update(self, db: "SpanishLexicalItemDatabase", lexical_item_id: int) -> None:
        db.save_lexical_item_base(lexical_item_id, headword=self.headword, explanation=self.explanation)
        db.save_adjective_details(lexical_item_id, self.inflection_type)
        db.save_adjective_forms(lexical_item_id, self.forms)
