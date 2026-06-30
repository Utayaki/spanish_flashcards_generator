from __future__ import annotations

from typing import Any

from drill.controllers.card_generator import (
    parse_number_gender_target_key,
    parse_transform_number_gender_target_key,
    parse_transform_verb_target_key,
    parse_verb_target_key,
)
from drill.database import DrillDatabase
from shared.verb_form_catalog import GROUP_LABELS, VERB_FORM_DEFINITIONS
from word_bank.database import WordBankDatabase

DRILL_TYPES = ("inflection", "verb_form", "recognition", "reverse", "transform")

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
    "verb_form": {"button": "Verb conjugation", "description": "Type one conjugated form for the infinitive"},
    "recognition": {"button": "Form → meaning", "description": "Identify translation and grammar from an inflected form"},
    "reverse": {"button": "Meaning → form", "description": "Recall headword and inflected form from a translation"},
    "transform": {
        "button": "Change inflection",
        "description": "Given one inflected form, type the same word in a different slot",
    },
}


class DrillPoolEmptyError(LookupError):
    """Raised when no drill cards match the drill pool."""


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


def build_random_question(
    word_bank: WordBankDatabase,
    drill_db: DrillDatabase,
    drill_type: str,
) -> dict[str, Any]:
    if drill_type not in DRILL_TYPES:
        raise ValueError(f"invalid drill type: {drill_type}")

    card = drill_db.get_random_drill_card(drill_type)
    if card is None:
        raise DrillPoolEmptyError(f"No active drill cards for drill type: {drill_type}")

    question = build_question_from_card(word_bank, card)
    question["drill_card_id"] = int(card["id"])
    return question


def build_question_from_card(word_bank: WordBankDatabase, card: dict[str, Any]) -> dict[str, Any]:
    item = word_bank.load_lexical_item(int(card["lexical_item_id"]))
    drill_type = str(card["drill_type"])

    if drill_type == "inflection":
        return _build_inflection_question_from_card(card, item)
    if drill_type == "verb_form":
        return _build_verb_form_question_from_card(card, item)
    if drill_type == "recognition":
        return _build_recognition_question_from_card(card, item)
    if drill_type == "reverse":
        return _build_reverse_question_from_card(card, item)
    if drill_type == "transform":
        return _build_transform_question_from_card(card, item)
    raise ValueError(f"invalid drill type: {drill_type}")


def check_answer_for_question(
    word_bank: WordBankDatabase,
    question: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    drill_type = str(question.get("drill_type", ""))
    if drill_type not in DRILL_TYPES:
        raise ValueError(f"invalid drill type: {drill_type}")
    checkers = {
        "inflection": _check_inflection_answer,
        "verb_form": _check_verb_form_answer,
        "recognition": _check_recognition_answer,
        "reverse": _check_reverse_answer,
        "transform": _check_transform_answer,
    }
    return checkers[drill_type](word_bank, question, answers)


def _build_inflection_question_from_card(card: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    target_number, target_gender = parse_number_gender_target_key(str(card["target_key"]))
    return {
        "drill_type": "inflection",
        "lexical_item_id": int(item["id"]),
        "headword": item["headword"],
        "lexical_item_type": item["lexical_item_type"],
        "pattern_options": _pattern_options(item),
        "target_number": target_number,
        "target_gender": target_gender,
        "slot_label": slot_label(target_number, target_gender),
    }


def _build_verb_form_question_from_card(card: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    verb_form_code = parse_verb_target_key(str(card["target_key"]))
    labels = verb_form_labels(verb_form_code)
    return {
        "drill_type": "verb_form",
        "lexical_item_id": int(item["id"]),
        "headword": item["headword"],
        "verb_form_code": verb_form_code,
        "context_label": verb_context_label(labels),
        "group_code": labels["group_code"],
        "tense_code": labels["tense_code"],
        "person_code": labels["person_code"],
    }


def _build_recognition_question_from_card(card: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    target_kind = str(card["target_kind"])
    if target_kind == "number_gender":
        target_number, target_gender = parse_number_gender_target_key(str(card["target_key"]))
        return {
            "drill_type": "recognition",
            "metadata_kind": "number_gender",
            "lexical_item_id": int(item["id"]),
            "shown_form": _form_for_slot(item, target_number, target_gender),
            "lexical_item_type": item["lexical_item_type"],
            "target_number": target_number,
            "target_gender": target_gender,
            "has_gender": target_gender is not None,
        }

    verb_form_code = parse_verb_target_key(str(card["target_key"]))
    labels = verb_form_labels(verb_form_code)
    return {
        "drill_type": "recognition",
        "metadata_kind": "verb",
        "lexical_item_id": int(item["id"]),
        "shown_form": str(item["verb"]["forms"][verb_form_code]["form"]),
        "lexical_item_type": "verb",
        "verb_form_code": verb_form_code,
        "has_person": labels["person_code"] is not None,
        **labels,
    }


def _build_reverse_question_from_card(card: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    target_kind = str(card["target_kind"])
    if target_kind == "number_gender":
        target_number, target_gender = parse_number_gender_target_key(str(card["target_key"]))
        return {
            "drill_type": "reverse",
            "metadata_kind": "number_gender",
            "lexical_item_id": int(item["id"]),
            "explanation": item["explanation"],
            "lexical_item_type": item["lexical_item_type"],
            "target_number": target_number,
            "target_gender": target_gender,
            "slot_label": slot_label(target_number, target_gender),
        }

    verb_form_code = parse_verb_target_key(str(card["target_key"]))
    labels = verb_form_labels(verb_form_code)
    return {
        "drill_type": "reverse",
        "metadata_kind": "verb",
        "lexical_item_id": int(item["id"]),
        "explanation": item["explanation"],
        "lexical_item_type": "verb",
        "verb_form_code": verb_form_code,
        "slot_label": verb_context_label(labels),
        **labels,
    }


def _build_transform_question_from_card(card: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    target_kind = str(card["target_kind"])
    if target_kind == "number_gender":
        source_number, source_gender, target_number, target_gender = parse_transform_number_gender_target_key(
            str(card["target_key"])
        )
        return {
            "drill_type": "transform",
            "metadata_kind": "number_gender",
            "lexical_item_id": int(item["id"]),
            "headword": item["headword"],
            "lexical_item_type": item["lexical_item_type"],
            "shown_form": _form_for_slot(item, source_number, source_gender),
            "source_slot_label": slot_label(source_number, source_gender),
            "target_slot_label": slot_label(target_number, target_gender),
            "source_number": source_number,
            "source_gender": source_gender,
            "target_number": target_number,
            "target_gender": target_gender,
        }

    source_code, target_code = parse_transform_verb_target_key(str(card["target_key"]))
    source_labels = verb_form_labels(source_code)
    target_labels = verb_form_labels(target_code)
    return {
        "drill_type": "transform",
        "metadata_kind": "verb",
        "lexical_item_id": int(item["id"]),
        "headword": item["headword"],
        "lexical_item_type": "verb",
        "shown_form": str(item["verb"]["forms"][source_code]["form"]),
        "source_slot_label": verb_context_label(source_labels),
        "target_slot_label": verb_context_label(target_labels),
        "source_verb_form_code": source_code,
        "target_verb_form_code": target_code,
    }


def _check_inflection_answer(
    word_bank: WordBankDatabase,
    question: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    lexical_item_id = int(question["lexical_item_id"])
    target_number = str(question["target_number"])
    target_gender = question.get("target_gender")
    if target_gender is not None:
        target_gender = str(target_gender)

    item = word_bank.load_lexical_item(lexical_item_id)
    expected_pattern, expected_pattern_label = _inflection_pattern(item)
    expected_form = _form_for_slot(item, target_number, target_gender)

    user_pattern = str(answers.get("user_inflection_pattern", ""))
    user_form = str(answers.get("user_form", ""))

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
        "expected_answer": {
            "pattern": expected_pattern,
            "form": expected_form,
        },
        "submitted_answer": {
            "pattern": user_pattern,
            "form": user_form,
        },
    }


def _check_verb_form_answer(
    word_bank: WordBankDatabase,
    question: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    lexical_item_id = int(question["lexical_item_id"])
    verb_form_code = str(question["verb_form_code"])
    user_form = str(answers.get("user_form", ""))

    item = word_bank.load_lexical_item(lexical_item_id)
    context_label = str(question.get("context_label", verb_form_code))
    expected_form = str(item["verb"]["forms"][verb_form_code]["form"])
    form_correct = text_matches(user_form, expected_form)

    return {
        "correct": form_correct,
        "results": {
            context_label: {
                "correct": form_correct,
                "expected": expected_form,
            },
        },
        "reveal": {
            "headword": item["headword"],
            "context_label": context_label,
            "form": expected_form,
        },
        "expected_answer": {
            "form": expected_form,
        },
        "submitted_answer": {
            "form": user_form,
        },
    }


def _check_recognition_answer(
    word_bank: WordBankDatabase,
    question: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    lexical_item_id = int(question["lexical_item_id"])
    item = word_bank.load_lexical_item(lexical_item_id)
    headword = str(item["headword"])
    lexical_item_type = str(item["lexical_item_type"])
    explanations = word_bank.get_explanations_for_headword(headword, lexical_item_type)

    user_translation = str(answers.get("user_translation", ""))
    translation_correct = translation_matches(user_translation, explanations)

    metadata_kind = str(question["metadata_kind"])
    metadata_results: dict[str, Any] = {}
    submitted_metadata: dict[str, str] = {}

    if metadata_kind == "number_gender":
        target_number = str(question["target_number"])
        target_gender = question.get("target_gender")
        if target_gender is not None:
            target_gender = str(target_gender)
        user_number = str(answers.get("user_number", ""))
        user_gender = str(answers.get("user_gender", ""))

        number_correct = user_number == target_number
        metadata_results["number"] = {"correct": number_correct, "expected": NUMBER_LABELS[target_number]}

        if target_gender is None:
            gender_correct = user_gender == "shared"
            metadata_results["gender"] = {"correct": gender_correct, "expected": GENDER_LABELS["shared"]}
            expected_gender = "shared"
        else:
            gender_correct = user_gender == target_gender
            metadata_results["gender"] = {"correct": gender_correct, "expected": GENDER_LABELS[target_gender]}
            expected_gender = target_gender

        metadata_correct = all(field["correct"] for field in metadata_results.values())
        slot_label_text = slot_label(target_number, target_gender)
        submitted_metadata = {"number": user_number, "gender": user_gender}
        expected_metadata = {"number": target_number, "gender": expected_gender}
    else:
        verb_form_code = str(question["verb_form_code"])
        labels = verb_form_labels(verb_form_code)
        user_group = str(answers.get("user_group_code", ""))
        user_tense = str(answers.get("user_tense_code", ""))
        user_person = str(answers.get("user_person_code", ""))

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
        submitted_metadata = {
            "group_code": user_group,
            "tense_code": user_tense,
            "person_code": user_person,
        }
        expected_metadata = {
            "group_code": str(labels["group_code"]),
            "tense_code": str(labels["tense_code"]),
            "person_code": str(person_expected) if person_expected is not None else None,
        }

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
        "expected_answer": {
            "translation": explanations[0] if explanations else "",
            "metadata": expected_metadata,
        },
        "submitted_answer": {
            "translation": user_translation,
            "metadata": submitted_metadata,
        },
    }


def _check_reverse_answer(
    word_bank: WordBankDatabase,
    question: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    lexical_item_id = int(question["lexical_item_id"])
    item = word_bank.load_lexical_item(lexical_item_id)
    headword = str(item["headword"])

    user_headword = str(answers.get("user_headword", ""))
    user_form = str(answers.get("user_form", ""))
    headword_correct = text_matches(user_headword, headword)

    metadata_kind = str(question["metadata_kind"])
    if metadata_kind == "number_gender":
        target_number = str(question["target_number"])
        target_gender = question.get("target_gender")
        if target_gender is not None:
            target_gender = str(target_gender)
        expected_form = _form_for_slot(item, target_number, target_gender)
        slot_label_text = slot_label(target_number, target_gender)
    else:
        verb_form_code = str(question["verb_form_code"])
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
        "expected_answer": {
            "headword": headword,
            "form": expected_form,
        },
        "submitted_answer": {
            "headword": user_headword,
            "form": user_form,
        },
    }


def _check_transform_answer(
    word_bank: WordBankDatabase,
    question: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    lexical_item_id = int(question["lexical_item_id"])
    item = word_bank.load_lexical_item(lexical_item_id)
    user_form = str(answers.get("user_form", ""))

    metadata_kind = str(question["metadata_kind"])
    if metadata_kind == "number_gender":
        target_number = str(question["target_number"])
        target_gender = question.get("target_gender")
        if target_gender is not None:
            target_gender = str(target_gender)
        source_number = str(question["source_number"])
        source_gender = question.get("source_gender")
        if source_gender is not None:
            source_gender = str(source_gender)
        expected_form = _form_for_slot(item, target_number, target_gender)
        source_slot_label = slot_label(source_number, source_gender)
        target_slot_label = slot_label(target_number, target_gender)
    else:
        target_code = str(question["target_verb_form_code"])
        source_code = str(question["source_verb_form_code"])
        expected_form = str(item["verb"]["forms"][target_code]["form"])
        source_slot_label = verb_context_label(verb_form_labels(source_code))
        target_slot_label = verb_context_label(verb_form_labels(target_code))

    form_correct = text_matches(user_form, expected_form)

    return {
        "correct": form_correct,
        "results": {
            "form": {
                "correct": form_correct,
                "expected": expected_form,
            },
        },
        "reveal": {
            "headword": item["headword"],
            "lexical_item_type": item["lexical_item_type"],
            "source_slot_label": source_slot_label,
            "target_slot_label": target_slot_label,
            "form": expected_form,
        },
        "expected_answer": {
            "form": expected_form,
        },
        "submitted_answer": {
            "form": user_form,
        },
    }
