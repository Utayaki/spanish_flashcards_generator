from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import SpanishLexicalItemDatabase


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
        inflection_type: str,
        forms: dict[tuple[str, str | None], str | None],
    ) -> "OtherSavePayload":
        return cls(headword, explanation, inflection_type, forms)

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
