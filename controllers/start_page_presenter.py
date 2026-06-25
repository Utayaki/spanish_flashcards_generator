from __future__ import annotations


LEXICAL_ITEM_CLASS_META: dict[str, dict[str, str]] = {
    "noun": {"button": "Noun", "singular": "noun", "plural": "nouns"},
    "verb": {"button": "Verb", "singular": "verb", "plural": "verbs"},
    "adjective": {"button": "Adjective", "singular": "adjective", "plural": "adjectives"},
    "other": {"button": "Other", "singular": "other lexical item", "plural": "other lexical items"},
}


def validate_lexical_item_type(lexical_item_type: str) -> str:
    if lexical_item_type not in LEXICAL_ITEM_CLASS_META:
        raise ValueError(f"invalid lexical item type: {lexical_item_type}")
    return lexical_item_type
