from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from word_bank.database import WordBankDatabase


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
        return cls(headword, explanation, inflection_type, forms)

    def create(self, db: "WordBankDatabase") -> int:
        return db.create_adjective_lexical_item(
            headword=self.headword,
            explanation=self.explanation,
            inflection_type=self.inflection_type,
            forms=self.forms,
        )

    def update(self, db: "WordBankDatabase", lexical_item_id: int) -> None:
        db.save_lexical_item_base(lexical_item_id, headword=self.headword, explanation=self.explanation)
        db.save_adjective_details(lexical_item_id, self.inflection_type)
        db.save_adjective_forms(lexical_item_id, self.forms)
