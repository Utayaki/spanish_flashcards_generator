from __future__ import annotations

from dataclasses import dataclass
from typing import Any

OTHER_SUBTYPES = ("adverb", "preposition", "conjunction", "interjection", "unknown")
OTHER_SUBTYPE_LABELS = {
    "adverb": "Adverb",
    "preposition": "Preposition",
    "conjunction": "Conjunction",
    "interjection": "Interjection",
    "unknown": "Unknown",
}


class OtherEditorStateError(ValueError):
    """Raised when other-editor state is invalid."""


def ensure_other_word_type(word_type: str) -> str:
    if word_type != "other":
        raise OtherEditorStateError(f"expected other word type, got: {word_type}")
    return word_type


def validate_other_subtype(subtype: str) -> str:
    if subtype not in OTHER_SUBTYPES:
        allowed = ", ".join(OTHER_SUBTYPES)
        raise OtherEditorStateError(f"invalid other subtype: {subtype}; expected one of: {allowed}")
    return subtype


def editor_title(lemma: str) -> str:
    clean_lemma = lemma.strip() or "Untitled"
    return f"Other: {clean_lemma}"


@dataclass(frozen=True)
class OtherSavePayload:
    lemma: str
    english: str
    subtype: str

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        english: str,
        subtype: str,
    ) -> "OtherSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise OtherEditorStateError("lemma cannot be empty")

        clean_english = english.strip()
        if not clean_english:
            raise OtherEditorStateError("english definition cannot be empty")

        return cls(
            lemma=clean_lemma,
            english=clean_english,
            subtype=validate_other_subtype(subtype),
        )

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "subtype": self.subtype,
        }
