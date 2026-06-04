from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Literal


WORD_CLASS_META: dict[str, dict[str, str]] = {
    "noun": {"button": "Noun", "singular": "noun", "plural": "nouns"},
    "verb": {"button": "Verb", "singular": "verb", "plural": "verbs"},
    "adjective": {"button": "Adjective", "singular": "adjective", "plural": "adjectives"},
    "other": {"button": "Other", "singular": "other word", "plural": "other words"},
}

ActionName = Literal["none", "open", "create"]


@dataclass(frozen=True)
class PrimaryAction:
    name: ActionName
    word_id: int | None = None
    lemma: str | None = None


def validate_word_type(word_type: str) -> str:
    if word_type not in WORD_CLASS_META:
        raise ValueError(f"invalid word type: {word_type}")
    return word_type


def normalize_lemma_input(text: str) -> str:
    return text.strip()


def class_button_label(word_type: str) -> str:
    validate_word_type(word_type)
    return WORD_CLASS_META[word_type]["button"]


def class_singular_label(word_type: str) -> str:
    validate_word_type(word_type)
    return WORD_CLASS_META[word_type]["singular"]


def already_added_title(word_type: str) -> str:
    validate_word_type(word_type)
    return f"Already added {WORD_CLASS_META[word_type]['plural']}"


def create_button_text(word_type: str, lemma: str, *, exact_match_exists: bool = False) -> str:
    validate_word_type(word_type)
    cleaned = normalize_lemma_input(lemma)
    label = WORD_CLASS_META[word_type]["singular"]
    if not cleaned:
        return f"Create new {label}"
    if exact_match_exists:
        return f"Create duplicate {label}: {cleaned}"
    return f"Create new {label}: {cleaned}"


def find_exact_match(results: list[dict[str, Any]], lemma: str) -> dict[str, Any] | None:
    cleaned = normalize_lemma_input(lemma).casefold()
    if not cleaned:
        return None
    for result in results:
        result_lemma = str(result.get("lemma", "")).strip().casefold()
        if result_lemma == cleaned:
            return result
    return None


def primary_action_for_enter(results: list[dict[str, Any]], lemma: str) -> PrimaryAction:
    cleaned = normalize_lemma_input(lemma)
    if not cleaned:
        return PrimaryAction("none")
    exact = find_exact_match(results, cleaned)
    if exact is not None:
        return PrimaryAction("open", word_id=int(exact["id"]), lemma=str(exact["lemma"]))
    return PrimaryAction("create", lemma=cleaned)


def highlight_match_html(lemma: str, query: str) -> str:
    if not query:
        return escape(lemma)
    lower_lemma = lemma.casefold()
    lower_query = query.casefold()
    start = lower_lemma.find(lower_query)
    if start < 0:
        return escape(lemma)
    end = start + len(query)
    return "".join([escape(lemma[:start]), "<b>", escape(lemma[start:end]), "</b>", escape(lemma[end:])])
