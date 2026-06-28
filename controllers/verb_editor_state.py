from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from controllers.verb_form_catalog import VERB_FORM_CODES

if TYPE_CHECKING:
    from database import SpanishLexicalItemDatabase


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
        clean_forms = empty_verb_forms()
        clean_forms.update(forms)
        return cls(headword=headword, explanation=explanation, forms=clean_forms)

    def create(self, db: "SpanishLexicalItemDatabase") -> int:
        return db.create_verb_lexical_item(
            headword=self.headword,
            explanation=self.explanation,
            forms=self.forms,
        )

    def update(self, db: "SpanishLexicalItemDatabase", lexical_item_id: int) -> None:
        db.save_lexical_item_base(lexical_item_id, headword=self.headword, explanation=self.explanation)
        db.save_verb_forms(lexical_item_id, self.forms)
