from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from word_bank.word_types.verb_forms import VERB_FORM_CODES

if TYPE_CHECKING:
    from word_bank.db.database import WordBankDatabase


VERB_META = {"button": "Verb", "singular": "verb", "plural": "verbs"}


def empty_verb_forms() -> dict[str, dict[str, Any]]:
    return {code: {"form": None} for code in sorted(VERB_FORM_CODES)}


@dataclass(frozen=True)
class Verb:
    headword: str
    explanation: str
    forms: dict[str, dict[str, Any]]

    def __post_init__(self) -> None:
        clean_forms = empty_verb_forms()
        clean_forms.update(self.forms)
        object.__setattr__(self, "forms", clean_forms)

    def create(self, db: WordBankDatabase) -> int:
        return db.create_verb_lexical_item(
            headword=self.headword,
            explanation=self.explanation,
            forms=self.forms,
        )

    def update(self, db: WordBankDatabase, lexical_item_id: int) -> None:
        db.update_verb_lexical_item(
            lexical_item_id,
            headword=self.headword,
            explanation=self.explanation,
            forms=self.forms,
        )
