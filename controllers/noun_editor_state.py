from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from widgets.form_state import clean_form_mapping, validate_gender_availability

if TYPE_CHECKING:
    from database import SpanishLexicalItemDatabase


GENDER_CHOICES = (
    ("masculine", "Always masculine"),
    ("feminine", "Always feminine"),
    ("both", "Masculine and feminine"),
)


class NounEditorStateError(ValueError):
    """Raised when noun editor state is invalid."""


@dataclass(frozen=True)
class NounSavePayload:
    headword: str
    explanation: str
    gender_availability: str
    forms: dict[tuple[str, str | None], str | None]

    @classmethod
    def from_inputs(
        cls,
        *,
        headword: str,
        explanation: str,
        gender_availability: str,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "NounSavePayload":
        clean_headword = headword.strip()
        if not clean_headword:
            raise NounEditorStateError("headword cannot be empty")
        clean_explanation = explanation.strip()
        if not clean_explanation:
            raise NounEditorStateError("explanation cannot be empty")
        clean_gender = validate_gender_availability(gender_availability)
        return cls(clean_headword, clean_explanation, clean_gender, clean_form_mapping(forms))

    def create(self, db: "SpanishLexicalItemDatabase") -> int:
        return db.create_noun_lexical_item(
            headword=self.headword,
            explanation=self.explanation,
            gender_availability=self.gender_availability,
            forms=self.forms,
        )

    def update(self, db: "SpanishLexicalItemDatabase", lexical_item_id: int) -> None:
        db.save_lexical_item_base(lexical_item_id, headword=self.headword, explanation=self.explanation)
        db.save_noun_details(lexical_item_id, self.gender_availability)
        db.save_noun_forms(lexical_item_id, self.forms)
