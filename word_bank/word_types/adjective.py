from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from word_bank.db.constants import FormKey

if TYPE_CHECKING:
    from word_bank.db.database import WordBankDatabase


ADJECTIVE_META = {
    "button": "Adjective",
    "singular": "adjective",
    "plural": "adjectives",
}


@dataclass(frozen=True)
class Adjective:
    headword: str
    explanation: str
    inflection_type: str
    forms: dict[FormKey, str | None]

    def create(self, db: WordBankDatabase) -> int:
        return db.create_adjective_lexical_item(
            headword=self.headword,
            explanation=self.explanation,
            inflection_type=self.inflection_type,
            forms=self.forms,
        )

    def update(self, db: WordBankDatabase, lexical_item_id: int) -> None:
        db.update_adjective_lexical_item(
            lexical_item_id,
            headword=self.headword,
            explanation=self.explanation,
            inflection_type=self.inflection_type,
            forms=self.forms,
        )
