from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma4:12b"
OLLAMA_TIMEOUT_SECONDS = 300
OLLAMA_OPTIONS = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 50,
    "repeat_penalty": 1.15,
}
CLOZE_BLANK = "_____"
EXAMPLES_PER_FORM = 5


class OllamaError(Exception):
    pass


class OllamaNotRunningError(OllamaError):
    pass


def ensure_ollama_running() -> None:
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/tags",
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status >= 400:
                raise OllamaNotRunningError("ollama serve is not running")
    except urllib.error.URLError as exc:
        raise OllamaNotRunningError("ollama serve is not running") from exc


def _build_prompt(record: dict[str, Any]) -> str:
    headword = str(record["headword"])
    explanation = str(record["explanation"])
    lexical_item_type = str(record["lexical_item_type"])
    word_form = str(record["word_form"])
    form_descriptor = str(record["form_descriptor"])

    return f"""You are a Spanish example-sentence generator. Follow every rule exactly.

INPUT:
Lexical item (lemma): {headword}
English meaning: {explanation}
Word type: {lexical_item_type}
Target word form: {word_form}
Form descriptor: {form_descriptor}

GOAL:
Generate exactly 5 natural, grammatically correct Spanish sentences.

Every sentence must use the exact target word form:

{word_form}

SENTENCE RULES:

1. Every sentence must contain the exact text "{word_form}" exactly once.
2. The target must appear as a separate word or complete lexical unit, not inside another word.
3. Preserve the exact spelling, accents, capitalization, and spacing of "{word_form}".
4. Use "{word_form}" as the grammatical form described by "{form_descriptor}" of the lemma "{headword}".
5. Do not substitute another inflection of the lemma.
6. Include enough grammatical and semantic context to clearly support the required person, number, gender, tense, aspect, or mood.
7. If the written form could have multiple grammatical interpretations, make the intended interpretation clear from context.
8. For nouns, adjectives, determiners, and participles, ensure that all relevant gender and number agreement supports the target form.
9. Use common, modern, natural Spanish.
10. Prefer simple, realistic situations.
11. Each sentence must contain between 6 and 18 words.
12. Each sentence must describe a meaningfully different situation.
13. Do not place "{word_form}" at the beginning of a sentence.
14. Avoid fragments, quotations, dialogue, lists, poetry, wordplay, metalinguistic examples, and unnecessary proper names.
15. Do not mention the lemma, target form, grammar rule, or language-learning exercise inside the sentences.

OUTPUT FORMAT:
Return only one valid JSON array containing exactly 5 strings.

Required output shape:
[
"... {word_form} ...",
"... {word_form} ...",
"... {word_form} ...",
"... {word_form} ...",
"... {word_form} ..."
]

Before answering, silently verify:

* The response is valid JSON.
* The array contains exactly 5 strings.
* Every string is a complete, natural Spanish sentence.
* Every sentence contains "{word_form}" exactly once.
* Every use of "{word_form}" matches "{form_descriptor}".
* No sentence uses a different inflection instead.
* Every sentence contains between 6 and 18 words.
* All 5 sentences describe different situations.
* There is no text before or after the JSON array.

Do not output markdown.
Do not output a code block.
Do not output objects.
Do not output answer fields.
Do not output cloze fields.
Do not output comments.
Do not output explanations.
Do not output numbering.
Do not output any text before or after the JSON array.
"""


_WORD_CHAR = r"[\wáéíóúñÁÉÍÓÚÑüÜ]"


def _count_standalone_word(text: str, word_form: str) -> int:
    pattern = f"(?<!{_WORD_CHAR}){re.escape(word_form)}(?!{_WORD_CHAR})"
    return len(re.findall(pattern, text))


def _find_standalone_word(sentence: str, word_form: str) -> re.Match[str] | None:
    pattern = f"(?<!{_WORD_CHAR}){re.escape(word_form)}(?!{_WORD_CHAR})"
    return re.search(pattern, sentence)


def _derive_cloze(sentence: str, word_form: str) -> str:
    match = _find_standalone_word(sentence, word_form)
    if match is None:
        raise OllamaError(
            f"could not find target word form '{word_form}' in sentence"
        )
    return sentence[: match.start()] + CLOZE_BLANK + sentence[match.end() :]


def _validate_sentence(sentence: str, *, word_form: str, index: int) -> str:
    sentence = sentence.strip()
    if not sentence:
        raise OllamaError(f"sentence {index + 1} cannot be empty")

    occurrences = _count_standalone_word(sentence, word_form)
    if occurrences != 1:
        raise OllamaError(
            f"sentence {index + 1} must contain the target word form "
            f"exactly once as a separate word, found {occurrences}"
        )

    return _derive_cloze(sentence, word_form)


def _parse_json_array(text: str) -> list[Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        try:
            parsed = json.loads(array_match.group(0))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    raise OllamaError("response is not a valid JSON array")


def _parse_examples(raw_response: str, *, record: dict[str, Any]) -> list[str]:
    text = raw_response.strip()
    if not text:
        raise OllamaError("empty response from Ollama")

    word_form = str(record["word_form"])
    items = _parse_json_array(text)
    if len(items) != EXAMPLES_PER_FORM:
        raise OllamaError(f"expected {EXAMPLES_PER_FORM} sentences, got {len(items)}")

    clozes: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise OllamaError(f"sentence {index + 1} must be a string")
        clozes.append(_validate_sentence(item, word_form=word_form, index=index))
    return clozes


def generate_examples(
    record: dict[str, Any],
    *,
    on_chunk: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[str]:
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": _build_prompt(record),
            "stream": True,
            "think": False,
            "options": OLLAMA_OPTIONS,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            parts: list[str] = []
            for raw_line in response:
                if cancel_check is not None and cancel_check():
                    raise OllamaError("generation cancelled")
                line_text = raw_line.decode("utf-8").strip()
                if not line_text:
                    continue
                try:
                    chunk_data = json.loads(line_text)
                except json.JSONDecodeError:
                    continue
                response_chunk = str(chunk_data.get("response", ""))
                thinking_chunk = str(chunk_data.get("thinking", ""))
                if response_chunk:
                    parts.append(response_chunk)
                display_chunk = response_chunk or thinking_chunk
                if display_chunk and on_chunk is not None:
                    on_chunk(display_chunk)
                if chunk_data.get("done"):
                    break
    except urllib.error.URLError as exc:
        raise OllamaNotRunningError("ollama serve is not running") from exc

    response_text = "".join(parts)
    return _parse_examples(response_text, record=record)
