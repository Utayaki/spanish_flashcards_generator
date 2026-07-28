from __future__ import annotations

import re

CLOZE_BLANK = "_____"
EXAMPLES_PER_FORM = 20

_WORD_CHAR = r"[\wáéíóúñÁÉÍÓÚÑüÜ]"


class ClozeError(Exception):
    pass


def count_standalone_word(text: str, word_form: str) -> int:
    pattern = f"(?<!{_WORD_CHAR}){re.escape(word_form)}(?!{_WORD_CHAR})"
    return len(re.findall(pattern, text))


def find_standalone_word(sentence: str, word_form: str) -> re.Match[str] | None:
    pattern = f"(?<!{_WORD_CHAR}){re.escape(word_form)}(?!{_WORD_CHAR})"
    return re.search(pattern, sentence)


def derive_cloze(sentence: str, word_form: str) -> str:
    match = find_standalone_word(sentence, word_form)
    if match is None:
        raise ClozeError(
            f"could not find target word form '{word_form}' in sentence"
        )
    return sentence[: match.start()] + CLOZE_BLANK + sentence[match.end() :]


def try_validate_sentence(sentence: str, *, word_form: str) -> str | None:
    sentence = sentence.strip()
    if not sentence:
        return None
    if count_standalone_word(sentence, word_form) != 1:
        return None
    try:
        return derive_cloze(sentence, word_form)
    except ClozeError:
        return None
