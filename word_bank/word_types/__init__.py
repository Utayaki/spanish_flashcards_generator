from __future__ import annotations

from word_bank.word_types.adjective import ADJECTIVE_META, Adjective
from word_bank.word_types.noun import GENDER_CHOICES, NOUN_META, Noun
from word_bank.word_types.other import OTHER_META, Other
from word_bank.word_types.verb import VERB_META, Verb

LEXICAL_ITEM_CLASS_META: dict[str, dict[str, str]] = {
    "noun": NOUN_META,
    "verb": VERB_META,
    "adjective": ADJECTIVE_META,
    "other": OTHER_META,
}


def validate_lexical_item_type(lexical_item_type: str) -> str:
    if lexical_item_type not in LEXICAL_ITEM_CLASS_META:
        raise ValueError(f"invalid lexical item type: {lexical_item_type}")
    return lexical_item_type


__all__ = [
    "Adjective",
    "GENDER_CHOICES",
    "LEXICAL_ITEM_CLASS_META",
    "Noun",
    "Other",
    "Verb",
    "validate_lexical_item_type",
]
