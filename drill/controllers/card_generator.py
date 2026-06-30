from __future__ import annotations

from typing import Any

from shared.verb_form_catalog import VERB_FORM_DEFINITIONS

VERB_FORM_BY_CODE = {str(row["code"]): row for row in VERB_FORM_DEFINITIONS}


def number_gender_target_key(number: str, gender: str | None) -> str:
    gender_key = "shared" if gender is None else gender
    return f"number_gender:{number}:{gender_key}"


def verb_target_key(verb_form_code: str) -> str:
    return f"verb_form:{verb_form_code}"


def parse_number_gender_target_key(target_key: str) -> tuple[str, str | None]:
    prefix = "number_gender:"
    if not target_key.startswith(prefix):
        raise ValueError(f"invalid number_gender target_key: {target_key}")
    rest = target_key[len(prefix) :]
    number, gender_key = rest.split(":", 1)
    gender = None if gender_key == "shared" else gender_key
    return number, gender


def parse_verb_target_key(target_key: str) -> str:
    prefix = "verb_form:"
    if not target_key.startswith(prefix):
        raise ValueError(f"invalid verb_form target_key: {target_key}")
    return target_key[len(prefix) :]


def transform_number_gender_target_key(
    source_number: str,
    source_gender: str | None,
    target_number: str,
    target_gender: str | None,
) -> str:
    src_gender_key = "shared" if source_gender is None else source_gender
    tgt_gender_key = "shared" if target_gender is None else target_gender
    return (
        f"transform:number_gender:{source_number}:{src_gender_key}"
        f":{target_number}:{tgt_gender_key}"
    )


def transform_verb_target_key(source_code: str, target_code: str) -> str:
    return f"transform:verb_form:{source_code}:{target_code}"


def parse_transform_number_gender_target_key(
    target_key: str,
) -> tuple[str, str | None, str, str | None]:
    prefix = "transform:number_gender:"
    if not target_key.startswith(prefix):
        raise ValueError(f"invalid transform number_gender target_key: {target_key}")
    rest = target_key[len(prefix) :]
    source_number, rest = rest.split(":", 1)
    source_gender_key, target_number, target_gender_key = rest.split(":", 2)
    source_gender = None if source_gender_key == "shared" else source_gender_key
    target_gender = None if target_gender_key == "shared" else target_gender_key
    return source_number, source_gender, target_number, target_gender


def parse_transform_verb_target_key(target_key: str) -> tuple[str, str]:
    prefix = "transform:verb_form:"
    if not target_key.startswith(prefix):
        raise ValueError(f"invalid transform verb_form target_key: {target_key}")
    rest = target_key[len(prefix) :]
    source_code, target_code = rest.split(":", 1)
    return source_code, target_code


def _normalize_text(value: str) -> str:
    return value.strip()


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
            if form and _normalize_text(str(form)):
                gender = None if gender_key == "shared" else gender_key
                slots.append(
                    {
                        "grammatical_number": number,
                        "grammatical_gender": gender,
                    }
                )
    return slots


def _verb_skill_tags(verb_form_code: str) -> list[str]:
    definition = VERB_FORM_BY_CODE[verb_form_code]
    tags = ["verb", str(definition["group_code"])]
    if definition.get("tense_code"):
        tags.append(str(definition["tense_code"]))
    if definition.get("person_code"):
        tags.append(str(definition["person_code"]))
    return tags


def _number_gender_skill_tags(item: dict[str, Any], number: str, gender: str | None) -> list[str]:
    tags = [str(item["lexical_item_type"]), number]
    tags.append(gender if gender is not None else "shared")
    return tags


def _number_gender_card_seeds(item: dict[str, Any]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for slot in _filled_number_gender_slots(item):
        number = str(slot["grammatical_number"])
        gender = slot["grammatical_gender"]
        if gender is not None:
            gender = str(gender)
        target_key = number_gender_target_key(number, gender)
        skill_tags = _number_gender_skill_tags(item, number, gender)
        seeds.append(
            {
                "drill_type": "inflection",
                "target_kind": "number_gender",
                "target_key": target_key,
                "prompt_schema": "headword_to_inflected_form",
                "answer_schema": "pattern_and_form",
                "skill_tags": skill_tags,
            }
        )
        seeds.append(
            {
                "drill_type": "recognition",
                "target_kind": "number_gender",
                "target_key": target_key,
                "prompt_schema": "form_to_meaning_and_metadata",
                "answer_schema": "translation_and_metadata",
                "skill_tags": skill_tags,
            }
        )
        seeds.append(
            {
                "drill_type": "reverse",
                "target_kind": "number_gender",
                "target_key": target_key,
                "prompt_schema": "meaning_to_headword_and_form",
                "answer_schema": "headword_and_form",
                "skill_tags": skill_tags,
            }
        )
    return seeds


def _number_gender_transform_seeds(item: dict[str, Any]) -> list[dict[str, Any]]:
    slots = _filled_number_gender_slots(item)
    if len(slots) < 2:
        return []

    seeds: list[dict[str, Any]] = []
    for source in slots:
        src_number = str(source["grammatical_number"])
        src_gender = source["grammatical_gender"]
        if src_gender is not None:
            src_gender = str(src_gender)
        for target in slots:
            tgt_number = str(target["grammatical_number"])
            tgt_gender = target["grammatical_gender"]
            if tgt_gender is not None:
                tgt_gender = str(tgt_gender)
            if src_number == tgt_number and src_gender == tgt_gender:
                continue
            skill_tags = [
                str(item["lexical_item_type"]),
                "transform",
                src_number,
                src_gender if src_gender is not None else "shared",
                tgt_number,
                tgt_gender if tgt_gender is not None else "shared",
            ]
            seeds.append(
                {
                    "drill_type": "transform",
                    "target_kind": "number_gender",
                    "target_key": transform_number_gender_target_key(
                        src_number, src_gender, tgt_number, tgt_gender
                    ),
                    "prompt_schema": "shown_form_to_other_form",
                    "answer_schema": "single_text",
                    "skill_tags": skill_tags,
                }
            )
    return seeds


def _verb_transform_seeds(item: dict[str, Any]) -> list[dict[str, Any]]:
    filled_codes = [
        str(code)
        for code, payload in item["verb"]["forms"].items()
        if payload.get("form") and _normalize_text(str(payload["form"]))
    ]
    if len(filled_codes) < 2:
        return []

    seeds: list[dict[str, Any]] = []
    for source_code in filled_codes:
        for target_code in filled_codes:
            if source_code == target_code:
                continue
            skill_tags = ["verb", "transform", source_code, target_code]
            seeds.append(
                {
                    "drill_type": "transform",
                    "target_kind": "verb_form",
                    "target_key": transform_verb_target_key(source_code, target_code),
                    "prompt_schema": "shown_form_to_other_form",
                    "answer_schema": "single_text",
                    "skill_tags": skill_tags,
                }
            )
    return seeds


def _verb_card_seeds(item: dict[str, Any]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    forms = item["verb"]["forms"]
    for verb_form_code, payload in forms.items():
        form = payload.get("form")
        if not form or not _normalize_text(str(form)):
            continue
        code = str(verb_form_code)
        target_key = verb_target_key(code)
        skill_tags = _verb_skill_tags(code)
        seeds.append(
            {
                "drill_type": "verb_form",
                "target_kind": "verb_form",
                "target_key": target_key,
                "prompt_schema": "infinitive_to_conjugated_form",
                "answer_schema": "single_text",
                "skill_tags": skill_tags,
            }
        )
        seeds.append(
            {
                "drill_type": "recognition",
                "target_kind": "verb_form",
                "target_key": target_key,
                "prompt_schema": "form_to_meaning_and_metadata",
                "answer_schema": "translation_and_metadata",
                "skill_tags": skill_tags,
            }
        )
        seeds.append(
            {
                "drill_type": "reverse",
                "target_kind": "verb_form",
                "target_key": target_key,
                "prompt_schema": "meaning_to_headword_and_form",
                "answer_schema": "headword_and_form",
                "skill_tags": skill_tags,
            }
        )
    return seeds


def build_drill_card_seeds(item: dict[str, Any]) -> list[dict[str, Any]]:
    lexical_item_type = item["lexical_item_type"]
    seeds: list[dict[str, Any]] = []

    if lexical_item_type in {"noun", "adjective", "other"}:
        seeds.extend(_number_gender_card_seeds(item))
        seeds.extend(_number_gender_transform_seeds(item))

    if lexical_item_type == "verb":
        seeds.extend(_verb_card_seeds(item))
        seeds.extend(_verb_transform_seeds(item))

    return seeds
