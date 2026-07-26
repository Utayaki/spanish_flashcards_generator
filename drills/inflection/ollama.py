from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma4:26b"
OLLAMA_TIMEOUT_SECONDS = 300
OLLAMA_OPTIONS = {
    "num_ctx": 2048,
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 50,
    "repeat_penalty": 1.15,
}
CLOZE_BLANK = "_____"
EXAMPLES_PER_FORM = 15
REGENERATE_BELOW_COUNT = 5
SENTENCES_PER_REQUEST = 20
MAX_GENERATION_ATTEMPTS = 10


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
    example_lines = "\n".join(f'  "... {word_form} ...",' for _ in range(SENTENCES_PER_REQUEST))

    return f"""You are a Spanish example-sentence generator. Follow every rule exactly.

INPUT:
Lexical item (lemma): {headword}
English meaning: {explanation}
Word type: {lexical_item_type}
Target word form: {word_form}
Form descriptor: {form_descriptor}

GOAL:
Generate exactly {SENTENCES_PER_REQUEST} natural, grammatically correct Spanish sentences.

CRITICAL LITERAL-MATCH RULE:
Every sentence must contain the exact character sequence "{word_form}" exactly once.

For a multiword target:
- Keep every word adjacent and in the same order.
- Do not insert, remove, replace, or reorder any word.
- Do not replace any preposition, article, pronoun, or other part of the target.
- A phrase with a similar meaning is incorrect unless it contains the exact text "{word_form}".

SENTENCE RULES:
1. Every sentence must contain the literal text "{word_form}" exactly once.
2. The target must appear as a separate word or complete lexical unit.
3. Preserve the exact spelling, accents, capitalization, word order, and spacing of "{word_form}".
4. Use "{word_form}" with the grammatical function described by "{form_descriptor}".
5. Do not substitute a synonym, paraphrase, or different inflection.
6. Include enough context to make the target natural and meaningful.
7. If the form has multiple grammatical interpretations, make "{form_descriptor}" clear from context.
8. Ensure all relevant gender, number, person, tense, and mood agreement is correct.
9. Use common, modern, natural Spanish.
10. Each sentence must contain between 6 and 18 words.
11. All {SENTENCES_PER_REQUEST} sentences must describe meaningfully different situations.
12. Avoid fragments, quotations, dialogue, poetry, wordplay, and metalinguistic examples.

OUTPUT:
Return only one valid JSON array containing exactly {SENTENCES_PER_REQUEST} strings.

Required shape:
[
{example_lines}
]

Before answering, silently perform this exact check for every sentence:
- Count the literal occurrences of "{word_form}".
- The count must equal exactly 1.
- If the count is 0 or greater than 1, rewrite that sentence.
- Confirm the final response is valid JSON containing exactly {SENTENCES_PER_REQUEST} strings.

Do not output markdown.
Do not output a code block.
Do not output objects.
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


def _try_validate_sentence(sentence: str, *, word_form: str) -> str | None:
    sentence = sentence.strip()
    if not sentence:
        return None
    if _count_standalone_word(sentence, word_form) != 1:
        return None
    try:
        return _derive_cloze(sentence, word_form)
    except OllamaError:
        return None


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


def _parse_sentence_batch(raw_response: str) -> list[str]:
    text = raw_response.strip()
    if not text:
        raise OllamaError("empty response from Ollama")

    items = _parse_json_array(text)
    sentences = [item.strip() for item in items if isinstance(item, str) and item.strip()]
    if not sentences:
        raise OllamaError("response contains no valid sentence strings")
    return sentences


def _request_ollama_response(
    record: dict[str, Any],
    *,
    on_chunk: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> str:
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

    return "".join(parts)


def generate_examples(
    record: dict[str, Any],
    *,
    target_count: int | None = None,
    on_chunk: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[str]:
    word_form = str(record["word_form"])
    needed = EXAMPLES_PER_FORM if target_count is None else max(1, target_count)
    valid_clozes: list[str] = []
    seen: set[str] = set()

    for _ in range(MAX_GENERATION_ATTEMPTS):
        if cancel_check is not None and cancel_check():
            raise OllamaError("generation cancelled")

        response_text = _request_ollama_response(
            record,
            on_chunk=on_chunk,
            cancel_check=cancel_check,
        )
        try:
            sentences = _parse_sentence_batch(response_text)
        except OllamaError:
            continue

        for sentence in sentences:
            cloze = _try_validate_sentence(sentence, word_form=word_form)
            if cloze is not None and cloze not in seen:
                seen.add(cloze)
                valid_clozes.append(cloze)

        if len(valid_clozes) >= needed:
            if len(valid_clozes) <= needed:
                return valid_clozes
            return random.sample(valid_clozes, needed)

    raise OllamaError(
        f"only {len(valid_clozes)} valid sentence(s) after "
        f"{MAX_GENERATION_ATTEMPTS} attempt(s), need {needed}"
    )
