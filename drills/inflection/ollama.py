from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma4:e2b"
OLLAMA_TIMEOUT_SECONDS = 300
CLOZE_BLANK = "_____"
REQUIRED_EXERCISE_KEYS = frozenset({"sentence", "cloze", "answer"})
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

    return f"""You are a Spanish exercise generator. Follow every rule exactly.

INPUT:
Lexical item (lemma): {headword}
English meaning: {explanation}
Word type: {lexical_item_type}
Target word form: {word_form}
Form descriptor: {form_descriptor}

GOAL:
Generate exactly 5 natural, grammatically correct Spanish fill-in-the-blank exercises.

The correct answer to every blank must be exactly:

{word_form}

SENTENCE CONSTRUCTION RULES:

1. First write a complete Spanish sentence containing the exact text "{word_form}" exactly once.
2. The target must appear as a separate word or complete lexical unit, not as part of another word.
3. Use exactly the spelling, accents, capitalization, and spacing provided in "{word_form}".
4. Use "{word_form}" as the grammatical form described by "{form_descriptor}" of the lemma "{headword}".
5. Do not use a different inflection of the lemma in place of the target.
6. Include enough grammatical and semantic context to strongly support the required person, number, gender, tense, aspect, or mood.
7. If the written form could have multiple grammatical interpretations, include context that clearly supports "{form_descriptor}".
8. For nouns, adjectives, determiners, and participles, ensure that all relevant gender and number agreement supports the target form.
9. Prefer common, modern, natural Spanish and realistic situations.
10. Each complete sentence must contain between 6 and 18 words.
11. Each sentence must describe a meaningfully different situation.
12. Avoid fragments, quotations, dialogue, lists, poetry, wordplay, metalinguistic examples, and unnecessary proper names.
13. Do not place "{word_form}" at the beginning of a sentence.
14. After constructing the complete sentence, replace only the single occurrence of "{word_form}" with "_____".
15. The cloze sentence must contain exactly one "_____".
16. Do not show "{word_form}" anywhere inside the cloze sentence.
17. Inserting exactly "{word_form}" into the blank must recreate the complete sentence.
18. Do not create a blank for which another word or inflection would be more natural than "{word_form}".

OUTPUT FORMAT:
Return only one valid JSON array containing exactly 5 objects.

Each object must contain exactly these three fields:

* "sentence": the complete Spanish sentence containing "{word_form}" exactly once
* "cloze": the same sentence with only "{word_form}" replaced by "_____"
* "answer": exactly "{word_form}"

Required output shape:
[
{{
"sentence": "... {word_form} ...",
"cloze": "... _____ ...",
"answer": "{word_form}"
}},
{{
"sentence": "... {word_form} ...",
"cloze": "... _____ ...",
"answer": "{word_form}"
}},
{{
"sentence": "... {word_form} ...",
"cloze": "... _____ ...",
"answer": "{word_form}"
}},
{{
"sentence": "... {word_form} ...",
"cloze": "... _____ ...",
"answer": "{word_form}"
}},
{{
"sentence": "... {word_form} ...",
"cloze": "... _____ ...",
"answer": "{word_form}"
}}
]

Before answering, silently verify all of the following:

* The response is valid JSON.
* The array contains exactly 5 objects.
* Every object contains only "sentence", "cloze", and "answer".
* Every complete sentence is natural and grammatically correct Spanish.
* Every complete sentence contains the exact text "{word_form}" exactly once.
* Every cloze sentence contains exactly one "_____".
* No cloze sentence contains "{word_form}".
* Every "answer" value is exactly "{word_form}".
* Replacing "_____" with "{word_form}" recreates the corresponding complete sentence exactly.
* Every use of "{word_form}" matches "{form_descriptor}".
* All 5 sentences describe different situations.

Do not output markdown.
Do not output a code block.
Do not output comments.
Do not output explanations.
Do not output numbering.
Do not output any text before or after the JSON array.
"""


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


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


def _validate_exercise(item: Any, *, word_form: str, index: int) -> str:
    if not isinstance(item, dict):
        raise OllamaError(f"exercise {index + 1} must be an object")

    if set(item.keys()) != REQUIRED_EXERCISE_KEYS:
        raise OllamaError(
            f"exercise {index + 1} must contain only sentence, cloze, and answer"
        )

    sentence = str(item["sentence"]).strip()
    cloze = str(item["cloze"]).strip()
    answer = str(item["answer"]).strip()

    if not sentence:
        raise OllamaError(f"exercise {index + 1}: sentence cannot be empty")
    if not cloze:
        raise OllamaError(f"exercise {index + 1}: cloze cannot be empty")

    if answer != word_form:
        raise OllamaError(
            f"exercise {index + 1}: expected answer '{word_form}', got '{answer}'"
        )

    if cloze.count(CLOZE_BLANK) != 1:
        raise OllamaError(
            f"exercise {index + 1}: cloze must contain exactly one '{CLOZE_BLANK}'"
        )

    if word_form in cloze:
        raise OllamaError(
            f"exercise {index + 1}: cloze must not contain the target word form"
        )

    reconstructed = cloze.replace(CLOZE_BLANK, word_form, 1)
    if _normalize_whitespace(reconstructed) != _normalize_whitespace(sentence):
        raise OllamaError(
            f"exercise {index + 1}: cloze does not reconstruct the complete sentence"
        )

    return cloze


def _parse_examples(raw_response: str, *, record: dict[str, Any]) -> list[str]:
    text = raw_response.strip()
    if not text:
        raise OllamaError("empty response from Ollama")

    word_form = str(record["word_form"])
    items = _parse_json_array(text)
    if len(items) != EXAMPLES_PER_FORM:
        raise OllamaError(f"expected {EXAMPLES_PER_FORM} exercises, got {len(items)}")

    return [
        _validate_exercise(item, word_form=word_form, index=index)
        for index, item in enumerate(items)
    ]


def generate_examples(record: dict[str, Any]) -> list[str]:
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": _build_prompt(record),
            "stream": False,
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
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise OllamaNotRunningError("ollama serve is not running") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OllamaError("invalid JSON response from Ollama") from exc

    response_text = str(parsed.get("response", ""))
    return _parse_examples(response_text, record=record)
