from __future__ import annotations

import random
from typing import Any

from controllers.verb_form_catalog import GROUP_LABELS, VERB_FORM_DEFINITIONS
from database import SpanishLexicalItemDatabase

DRILL_TYPES = ("inflection", "verb_form", "recognition", "reverse")

NUMBER_LABELS = {"singular": "singular", "plural": "plural"}
GENDER_LABELS = {"masculine": "masculine", "feminine": "feminine", "shared": "shared"}

NOUN_PATTERN_OPTIONS = [
    {"value": "masculine", "label": "Masculine only"},
    {"value": "feminine", "label": "Feminine only"},
    {"value": "both", "label": "Both genders"},
]

ADJ_OTHER_PATTERN_OPTIONS = [
    {"value": "plurality", "label": "Plurality only"},
    {"value": "gender_plurality", "label": "Plurality + gender"},
]

OTHER_ONLY_NONE_OPTION = {"value": "none", "label": "No inflections"}

VERB_FORM_BY_CODE = {str(row["code"]): row for row in VERB_FORM_DEFINITIONS}

DRILL_TYPE_META = {
    "inflection": {"button": "Inflection", "description": "Noun, adjective, or other inflection pattern and forms"},
    "verb_form": {"button": "Verb conjugation", "description": "Type 1–5 verb forms for the same infinitive"},
    "recognition": {"button": "Form → meaning", "description": "Identify translation and grammar from an inflected form"},
    "reverse": {"button": "Meaning → form", "description": "Recall headword and inflected form from a translation"},
}


class DrillPoolEmptyError(LookupError):
    """Raised when no lexical items match the drill pool."""


def normalize_text(value: str) -> str:
    return value.strip()


def text_matches(user_value: str, expected: str) -> bool:
    return normalize_text(user_value).casefold() == normalize_text(expected).casefold()


def translation_matches(user_value: str, explanations: list[str]) -> bool:
    cleaned = normalize_text(user_value).casefold()
    if not cleaned:
        return False
    return any(cleaned == normalize_text(explanation).casefold() for explanation in explanations)


def slot_label(number: str, gender: str | None) -> str:
    if gender is None:
        return f"{NUMBER_LABELS[number]} {GENDER_LABELS['shared']}"
    return f"{NUMBER_LABELS[number]} {GENDER_LABELS[gender]}"


def verb_context_label(row: dict[str, Any]) -> str:
    parts = [str(row["group_label"])]
    if row.get("tense_label"):
        parts.append(str(row["tense_label"]))
    if row.get("person_label"):
        parts.append(str(row["person_label"]))
    return " · ".join(parts)


def verb_form_labels(verb_form_code: str) -> dict[str, Any]:
    definition = VERB_FORM_BY_CODE[verb_form_code]
    group_code = str(definition["group_code"])
    return {
        "verb_form_code": verb_form_code,
        "group_code": group_code,
        "group_label": GROUP_LABELS.get(group_code, group_code),
        "tense_code": definition.get("tense_code"),
        "tense_label": definition.get("tense_label"),
        "person_code": definition.get("person_code"),
        "person_label": definition.get("person_label"),
    }


def _filled_number_gender_slots(item: dict[str, Any]) -> list[dict[str, Any]]:
    lexical_item_type = str(item["lexical_item_type"])
    if lexical_item_type == "noun":
        inflections = item["noun"]["inflections"]
    elif lexical_item_type == "adjective":
        inflections = item["adjective"]["inflections"]
    elif lexical_item_type == "other":
        other = item["other"]
        if other["inflection_type"] == "none" or other["inflections"] is None:
            return []
        inflections = other["inflections"]
    else:
        return []

    slots: list[dict[str, Any]] = []
    for number, gender_map in inflections.items():
        for gender_key, form in gender_map.items():
            if form and normalize_text(form):
                gender = None if gender_key == "shared" else gender_key
                slots.append(
                    {
                        "grammatical_number": number,
                        "grammatical_gender": gender,
                        "form": form,
                        "slot_label": slot_label(number, gender),
                    }
                )
    return slots


def _inflection_pattern(item: dict[str, Any]) -> tuple[str, str]:
    lexical_item_type = str(item["lexical_item_type"])
    if lexical_item_type == "noun":
        value = str(item["noun"]["gender_availability"])
        label = next(option["label"] for option in NOUN_PATTERN_OPTIONS if option["value"] == value)
        return value, label
    if lexical_item_type == "adjective":
        value = str(item["adjective"]["adjective_inflection_type"])
        label = next(option["label"] for option in ADJ_OTHER_PATTERN_OPTIONS if option["value"] == value)
        return value, label
    value = str(item["other"]["inflection_type"])
    options = ADJ_OTHER_PATTERN_OPTIONS + [OTHER_ONLY_NONE_OPTION]
    label = next(option["label"] for option in options if option["value"] == value)
    return value, label


def _pattern_options(item: dict[str, Any]) -> list[dict[str, str]]:
    lexical_item_type = str(item["lexical_item_type"])
    if lexical_item_type == "noun":
        return list(NOUN_PATTERN_OPTIONS)
    if lexical_item_type == "other":
        return list(ADJ_OTHER_PATTERN_OPTIONS) + [OTHER_ONLY_NONE_OPTION]
    return list(ADJ_OTHER_PATTERN_OPTIONS)


def _form_for_slot(item: dict[str, Any], number: str, gender: str | None) -> str:
    lexical_item_type = str(item["lexical_item_type"])
    if lexical_item_type == "noun":
        inflections = item["noun"]["inflections"]
    elif lexical_item_type == "adjective":
        inflections = item["adjective"]["inflections"]
    else:
        inflections = item["other"]["inflections"]
    gender_key = "shared" if gender is None else gender
    form = inflections[number][gender_key]
    if not form:
        raise LookupError(f"form missing for {number}/{gender_key}")
    return str(form)


def build_random_question(database: SpanishLexicalItemDatabase, drill_type: str) -> dict[str, Any]:
    if drill_type not in DRILL_TYPES:
        raise ValueError(f"invalid drill type: {drill_type}")
    builders = {
        "inflection": _build_inflection_question,
        "verb_form": _build_verb_form_question,
        "recognition": _build_recognition_question,
        "reverse": _build_reverse_question,
    }
    return builders[drill_type](database)


def check_answer(database: SpanishLexicalItemDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    drill_type = str(payload.get("drill_type", ""))
    if drill_type not in DRILL_TYPES:
        raise ValueError(f"invalid drill type: {drill_type}")
    checkers = {
        "inflection": _check_inflection_answer,
        "verb_form": _check_verb_form_answer,
        "recognition": _check_recognition_answer,
        "reverse": _check_reverse_answer,
    }
    return checkers[drill_type](database, payload)


def _build_inflection_question(database: SpanishLexicalItemDatabase) -> dict[str, Any]:
    lexical_item_id = database.get_random_inflection_drill_lexical_item_id()
    if lexical_item_id is None:
        raise DrillPoolEmptyError("No nouns, adjectives, or inflected other items in the word bank")

    item = database.load_lexical_item(lexical_item_id)
    slots = _filled_number_gender_slots(item)
    if not slots:
        raise DrillPoolEmptyError("No filled inflection forms available for drill")

    slot = random.choice(slots)
    return {
        "drill_type": "inflection",
        "lexical_item_id": lexical_item_id,
        "headword": item["headword"],
        "lexical_item_type": item["lexical_item_type"],
        "pattern_options": _pattern_options(item),
        "target_number": slot["grammatical_number"],
        "target_gender": slot["grammatical_gender"],
        "slot_label": slot["slot_label"],
    }


def _check_inflection_answer(database: SpanishLexicalItemDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    lexical_item_id = int(payload["lexical_item_id"])
    target_number = str(payload["target_number"])
    target_gender = payload.get("target_gender")
    if target_gender is not None:
        target_gender = str(target_gender)

    item = database.load_lexical_item(lexical_item_id)
    expected_pattern, expected_pattern_label = _inflection_pattern(item)
    expected_form = _form_for_slot(item, target_number, target_gender)

    user_pattern = str(payload.get("user_inflection_pattern", ""))
    user_form = str(payload.get("user_form", ""))

    pattern_correct = user_pattern == expected_pattern
    form_correct = text_matches(user_form, expected_form)
    correct = pattern_correct and form_correct

    return {
        "correct": correct,
        "results": {
            "inflection_pattern": {
                "correct": pattern_correct,
                "expected": expected_pattern_label,
            },
            "form": {
                "correct": form_correct,
                "expected": expected_form,
            },
        },
        "reveal": {
            "headword": item["headword"],
            "lexical_item_type": item["lexical_item_type"],
            "slot_label": slot_label(target_number, target_gender),
            "inflection_pattern": expected_pattern_label,
            "form": expected_form,
        },
    }


def _verb_form_slot(form_row: dict[str, Any]) -> dict[str, Any]:
    verb_form_code = str(form_row["verb_form_code"])
    labels = verb_form_labels(verb_form_code)
    return {
        "verb_form_code": verb_form_code,
        "context_label": verb_context_label(labels),
        "group_code": labels["group_code"],
        "tense_code": labels["tense_code"],
        "person_code": labels["person_code"],
    }


def _build_verb_form_question(database: SpanishLexicalItemDatabase) -> dict[str, Any]:
    verb_data = database.get_random_verb_with_filled_forms()
    if verb_data is None:
        raise DrillPoolEmptyError("No filled verb forms in the word bank")

    filled_forms = verb_data["filled_forms"]
    form_count = random.randint(1, min(5, len(filled_forms)))
    sampled_forms = random.sample(filled_forms, form_count)
    slots = [_verb_form_slot(form_row) for form_row in sampled_forms]

    return {
        "drill_type": "verb_form",
        "lexical_item_id": int(verb_data["lexical_item_id"]),
        "headword": verb_data["headword"],
        "form_count": form_count,
        "slots": slots,
    }


def _check_verb_form_answer(database: SpanishLexicalItemDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    lexical_item_id = int(payload["lexical_item_id"])
    slots = payload.get("slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("slots are required for verb_form drill")

    user_forms = payload.get("user_forms")
    if not isinstance(user_forms, dict):
        raise ValueError("user_forms must be an object")

    item = database.load_lexical_item(lexical_item_id)
    results: dict[str, Any] = {}
    reveal_forms: list[dict[str, str]] = []
    all_correct = True

    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("each slot must be an object")
        verb_form_code = str(slot["verb_form_code"])
        context_label = str(slot.get("context_label", verb_form_code))
        expected_form = str(item["verb"]["forms"][verb_form_code]["form"])
        user_form = str(user_forms.get(verb_form_code, ""))
        form_correct = text_matches(user_form, expected_form)
        all_correct = all_correct and form_correct
        results[context_label] = {
            "correct": form_correct,
            "expected": expected_form,
        }
        reveal_forms.append({"context_label": context_label, "form": expected_form})

    return {
        "correct": all_correct,
        "results": results,
        "reveal": {
            "headword": item["headword"],
            "forms": reveal_forms,
        },
    }


def _pick_random_recognition_source(database: SpanishLexicalItemDatabase) -> tuple[str, dict[str, Any]]:
    sources: list[tuple[str, dict[str, Any] | None]] = [
        ("number_gender", database.get_random_filled_noun_adjective_other_form()),
        ("verb", database.get_random_filled_verb_form()),
    ]
    available = [(kind, row) for kind, row in sources if row is not None]
    if not available:
        raise DrillPoolEmptyError("No inflected forms available for recognition drill")
    return random.choice(available)


def _build_recognition_question(database: SpanishLexicalItemDatabase) -> dict[str, Any]:
    metadata_kind, row = _pick_random_recognition_source(database)
    if metadata_kind == "number_gender":
        gender = row["grammatical_gender"]
        return {
            "drill_type": "recognition",
            "metadata_kind": "number_gender",
            "lexical_item_id": int(row["lexical_item_id"]),
            "shown_form": row["form"],
            "lexical_item_type": row["lexical_item_type"],
            "target_number": row["grammatical_number"],
            "target_gender": gender,
            "has_gender": gender is not None,
        }

    verb_form_code = str(row["verb_form_code"])
    labels = verb_form_labels(verb_form_code)
    return {
        "drill_type": "recognition",
        "metadata_kind": "verb",
        "lexical_item_id": int(row["lexical_item_id"]),
        "shown_form": row["form"],
        "lexical_item_type": "verb",
        "verb_form_code": verb_form_code,
        "has_person": labels["person_code"] is not None,
        **labels,
    }


def _check_recognition_answer(database: SpanishLexicalItemDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    lexical_item_id = int(payload["lexical_item_id"])
    item = database.load_lexical_item(lexical_item_id)
    headword = str(item["headword"])
    lexical_item_type = str(item["lexical_item_type"])
    explanations = database.get_explanations_for_headword(headword, lexical_item_type)

    user_translation = str(payload.get("user_translation", ""))
    translation_correct = translation_matches(user_translation, explanations)

    metadata_kind = str(payload["metadata_kind"])
    metadata_results: dict[str, Any] = {}

    if metadata_kind == "number_gender":
        target_number = str(payload["target_number"])
        target_gender = payload.get("target_gender")
        if target_gender is not None:
            target_gender = str(target_gender)
        user_number = str(payload.get("user_number", ""))
        user_gender = str(payload.get("user_gender", ""))

        number_correct = user_number == target_number
        metadata_results["number"] = {"correct": number_correct, "expected": NUMBER_LABELS[target_number]}

        if target_gender is None:
            gender_correct = user_gender == "shared"
            metadata_results["gender"] = {"correct": gender_correct, "expected": GENDER_LABELS["shared"]}
        else:
            gender_correct = user_gender == target_gender
            metadata_results["gender"] = {"correct": gender_correct, "expected": GENDER_LABELS[target_gender]}

        metadata_correct = all(field["correct"] for field in metadata_results.values())
        slot_label_text = slot_label(target_number, target_gender)
    else:
        verb_form_code = str(payload["verb_form_code"])
        labels = verb_form_labels(verb_form_code)
        user_group = str(payload.get("user_group_code", ""))
        user_tense = str(payload.get("user_tense_code", ""))
        user_person = str(payload.get("user_person_code", ""))

        group_correct = user_group == str(labels["group_code"])
        tense_correct = user_tense == str(labels["tense_code"])
        person_expected = labels["person_code"]
        person_correct = person_expected is None or user_person == str(person_expected)

        metadata_results["group"] = {"correct": group_correct, "expected": labels["group_label"]}
        metadata_results["tense"] = {"correct": tense_correct, "expected": labels["tense_label"]}
        if person_expected is not None:
            metadata_results["person"] = {"correct": person_correct, "expected": labels["person_label"]}

        metadata_correct = all(field["correct"] for field in metadata_results.values())
        slot_label_text = verb_context_label(labels)

    correct = translation_correct and metadata_correct
    return {
        "correct": correct,
        "results": {
            "translation": {
                "correct": translation_correct,
                "expected": explanations,
            },
            **metadata_results,
        },
        "reveal": {
            "headword": headword,
            "lexical_item_type": lexical_item_type,
            "explanations": explanations,
            "slot_label": slot_label_text,
        },
    }


def _pick_random_reverse_source(database: SpanishLexicalItemDatabase) -> tuple[str, dict[str, Any]]:
    return _pick_random_recognition_source(database)


def _build_reverse_question(database: SpanishLexicalItemDatabase) -> dict[str, Any]:
    metadata_kind, row = _pick_random_reverse_source(database)
    if metadata_kind == "number_gender":
        gender = row["grammatical_gender"]
        return {
            "drill_type": "reverse",
            "metadata_kind": "number_gender",
            "lexical_item_id": int(row["lexical_item_id"]),
            "explanation": row["explanation"],
            "lexical_item_type": row["lexical_item_type"],
            "target_number": row["grammatical_number"],
            "target_gender": gender,
            "slot_label": slot_label(str(row["grammatical_number"]), gender),
        }

    verb_form_code = str(row["verb_form_code"])
    labels = verb_form_labels(verb_form_code)
    return {
        "drill_type": "reverse",
        "metadata_kind": "verb",
        "lexical_item_id": int(row["lexical_item_id"]),
        "explanation": row["explanation"],
        "lexical_item_type": "verb",
        "verb_form_code": verb_form_code,
        "slot_label": verb_context_label(labels),
        **labels,
    }


def _check_reverse_answer(database: SpanishLexicalItemDatabase, payload: dict[str, Any]) -> dict[str, Any]:
    lexical_item_id = int(payload["lexical_item_id"])
    item = database.load_lexical_item(lexical_item_id)
    headword = str(item["headword"])

    user_headword = str(payload.get("user_headword", ""))
    user_form = str(payload.get("user_form", ""))
    headword_correct = text_matches(user_headword, headword)

    metadata_kind = str(payload["metadata_kind"])
    if metadata_kind == "number_gender":
        target_number = str(payload["target_number"])
        target_gender = payload.get("target_gender")
        if target_gender is not None:
            target_gender = str(target_gender)
        expected_form = _form_for_slot(item, target_number, target_gender)
        slot_label_text = slot_label(target_number, target_gender)
    else:
        verb_form_code = str(payload["verb_form_code"])
        expected_form = str(item["verb"]["forms"][verb_form_code]["form"])
        slot_label_text = verb_context_label(verb_form_labels(verb_form_code))

    form_correct = text_matches(user_form, expected_form)
    correct = headword_correct and form_correct

    return {
        "correct": correct,
        "results": {
            "headword": {
                "correct": headword_correct,
                "expected": headword,
            },
            "form": {
                "correct": form_correct,
                "expected": expected_form,
            },
        },
        "reveal": {
            "headword": headword,
            "lexical_item_type": item["lexical_item_type"],
            "explanation": item["explanation"],
            "slot_label": slot_label_text,
            "form": expected_form,
        },
    }
