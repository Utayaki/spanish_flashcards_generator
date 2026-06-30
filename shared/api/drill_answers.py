from __future__ import annotations

from typing import Any

from shared.errors import ValidationError

ANSWER_KEYS: dict[str, tuple[str, ...]] = {
    "inflection": ("user_inflection_pattern", "user_form"),
    "verb_form": ("user_form",),
    "transform": ("user_form",),
    "reverse": ("user_headword", "user_form"),
}

RECOGNITION_VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "id": "number_gender",
        "when": {"metadata_kind": "number_gender"},
        "keys": ("user_translation", "user_number", "user_gender"),
    },
    {
        "id": "verb_participle",
        "when": {"metadata_kind": "verb", "group_code": "participle"},
        "keys": ("user_translation", "user_group_code", "user_tense_code"),
    },
    {
        "id": "verb",
        "when": {"metadata_kind": "verb"},
        "keys": ("user_translation", "user_group_code", "user_tense_code", "user_person_code"),
    },
)

PARTICIPLE_GROUP_CODE = "participle"


def _matches_when(question: dict[str, Any], when: dict[str, str]) -> bool:
    return all(question.get(key) == value for key, value in when.items())


def recognition_answer_keys(question: dict[str, Any]) -> tuple[str, ...]:
    for variant in RECOGNITION_VARIANTS:
        if _matches_when(question, variant["when"]):
            return variant["keys"]
    raise ValidationError("unsupported recognition question shape")


def answer_keys_for_question(question: dict[str, Any]) -> tuple[str, ...]:
    drill_type = str(question["drill_type"])
    if drill_type == "recognition":
        return recognition_answer_keys(question)
    keys = ANSWER_KEYS.get(drill_type)
    if keys is None:
        raise ValidationError(f"unsupported drill type: {drill_type}")
    return keys


def validate_answer_keys(question: dict[str, Any], answers: dict[str, Any]) -> None:
    expected = set(answer_keys_for_question(question))
    submitted = set(answers.keys())
    missing = expected - submitted
    extra = submitted - expected
    if missing:
        raise ValidationError(f"missing answer fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValidationError(f"unexpected answer fields: {', '.join(sorted(extra))}")


def answer_schemas_for_meta() -> dict[str, Any]:
    return {
        "by_drill_type": {drill_type: list(keys) for drill_type, keys in ANSWER_KEYS.items()},
        "recognition_variants": [
            {
                "id": variant["id"],
                "when": dict(variant["when"]),
                "keys": list(variant["keys"]),
            }
            for variant in RECOGNITION_VARIANTS
        ],
        "defaults": {
            "participle_group_code": PARTICIPLE_GROUP_CODE,
        },
    }
