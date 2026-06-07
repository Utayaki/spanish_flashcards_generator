from __future__ import annotations


LEMMA_CLASS_META: dict[str, dict[str, str]] = {
    "noun": {"button": "Noun", "singular": "noun", "plural": "nouns"},
    "verb": {"button": "Verb", "singular": "verb", "plural": "verbs"},
    "adjective": {"button": "Adjective", "singular": "adjective", "plural": "adjectives"},
    "other": {"button": "Other", "singular": "other lemma", "plural": "other lemmas"},
}


def validate_lemma_type(lemma_type: str) -> str:
    if lemma_type not in LEMMA_CLASS_META:
        raise ValueError(f"invalid lemma type: {lemma_type}")
    return lemma_type
