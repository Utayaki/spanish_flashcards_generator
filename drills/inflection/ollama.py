from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma4:e2b"
OLLAMA_TIMEOUT_SECONDS = 300


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
    return (
        "You are helping a Spanish learner practice inflected word forms.\n"
        "Generate exactly 5 different example sentences in Spanish that naturally use "
        "the target word form.\n"
        "Each sentence must use the exact word form provided, not a different inflection.\n"
        "Return only a JSON array of 5 strings, with no markdown or extra text.\n\n"
        f"Lexical item (lemma): {record['headword']}\n"
        f"English meaning: {record['explanation']}\n"
        f"Word type: {record['lexical_item_type']}\n"
        f"Target word form: {record['word_form']}\n"
        f"Form descriptor: {record['form_descriptor']}\n"
    )


def _parse_examples(raw_response: str) -> list[str]:
    text = raw_response.strip()
    if not text:
        raise OllamaError("empty response from Ollama")

    candidates: list[str] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            candidates = [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass

    if not candidates:
        array_match = re.search(r"\[[\s\S]*\]", text)
        if array_match:
            try:
                parsed = json.loads(array_match.group(0))
                if isinstance(parsed, list):
                    candidates = [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass

    if not candidates:
        candidates = [
            line.strip(" \"-\t")
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("[") and not line.strip().startswith("]")
        ]

    examples = [example for example in candidates if example]
    if len(examples) < 5:
        raise OllamaError(f"expected 5 examples, got {len(examples)}")
    return examples[:5]


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
    return _parse_examples(response_text)
