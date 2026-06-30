from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from word_bank.database import WordBankDatabase


GENDER_CHOICES = (
    ("masculine", "Always masculine"),
    ("feminine", "Always feminine"),
    ("both", "Masculine and feminine"),
)


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
        return cls(headword, explanation, gender_availability, forms)

    def create(self, db: "WordBankDatabase") -> int:
        return db.create_noun_lexical_item(
            headword=self.headword,
            explanation=self.explanation,
            gender_availability=self.gender_availability,
            forms=self.forms,
        )

    def update(self, db: "WordBankDatabase", lexical_item_id: int) -> None:
        db.update_noun_lexical_item(
            lexical_item_id,
            headword=self.headword,
            explanation=self.explanation,
            gender_availability=self.gender_availability,
            forms=self.forms,
        )
