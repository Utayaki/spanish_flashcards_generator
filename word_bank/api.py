from __future__ import annotations

from collections.abc import Callable

from word_bank.http import ApiError
from word_bank.db.constants import GENDERS, NUMBERS
from word_bank.word_types import Adjective, Noun, Other, Verb

SHARED_GENDER_KEY = "shared"

LexicalItemSavePayload = Noun | Adjective | Other | Verb


def require_str(obj: dict[str, object], key: str) -> str:
    value = obj.get(key)
    if value is None:
        raise ApiError(f"missing field: {key}")
    if not isinstance(value, str):
        raise ApiError(f"field must be a string: {key}")
    return value


def empty_gendered_forms() -> dict[tuple[str, str | None], str | None]:
    return {(number, gender): None for number in NUMBERS for gender in GENDERS}


def empty_shared_forms() -> dict[tuple[str, str | None], str | None]:
    return {(number, None): None for number in NUMBERS}


def parse_lexical_item_save(lexical_item_type: str, payload: dict[str, object]) -> LexicalItemSavePayload:
    parser = _PAYLOAD_PARSERS.get(lexical_item_type)
    if parser is None:
        raise ApiError(f"unsupported lexical item type: {lexical_item_type}")
    return parser(payload)


def _parse_noun_payload(payload: dict[str, object]) -> Noun:
    return Noun(
        headword=require_str(payload, "headword"),
        explanation=require_str(payload, "explanation"),
        gender_availability=require_str(payload, "gender_availability"),
        forms=_forms_from_payload(payload.get("forms"), include_shared=False),
    )


def _parse_adjective_payload(payload: dict[str, object]) -> Adjective:
    return Adjective(
        headword=require_str(payload, "headword"),
        explanation=require_str(payload, "explanation"),
        inflection_type=_adjective_type_from_payload(payload),
        forms=_forms_from_payload(payload.get("forms"), include_shared=True),
    )


def _parse_other_payload(payload: dict[str, object]) -> Other:
    return Other(
        headword=require_str(payload, "headword"),
        explanation=require_str(payload, "explanation"),
        inflection_type=require_str(payload, "inflection_type"),
        forms=_forms_from_payload(payload.get("forms"), include_shared=True),
    )


def _parse_verb_payload(payload: dict[str, object]) -> Verb:
    return Verb(
        headword=require_str(payload, "headword"),
        explanation=require_str(payload, "explanation"),
        forms=_verb_forms_from_payload(payload.get("forms")),
    )


_PAYLOAD_PARSERS: dict[str, Callable[[dict[str, object]], LexicalItemSavePayload]] = {
    "noun": _parse_noun_payload,
    "adjective": _parse_adjective_payload,
    "other": _parse_other_payload,
    "verb": _parse_verb_payload,
}


def _adjective_type_from_payload(payload: dict[str, object]) -> str:
    value = payload.get("adjective_inflection_type", "gender_plurality")
    if not isinstance(value, str):
        raise ApiError("adjective_inflection_type must be a string")
    return value


def _forms_from_payload(raw: object, *, include_shared: bool) -> dict[tuple[str, str | None], str | None]:
    forms = empty_gendered_forms()
    if include_shared:
        forms.update(empty_shared_forms())
    if raw is None:
        return forms
    if not isinstance(raw, dict):
        raise ApiError("forms must be an object")
    for number in NUMBERS:
        number_map = raw.get(number, {})
        if number_map is None:
            continue
        if not isinstance(number_map, dict):
            raise ApiError(f"forms.{number} must be an object")
        for gender in GENDERS:
            value = number_map.get(gender)
            if value is not None and not isinstance(value, str):
                raise ApiError(f"forms.{number}.{gender} must be a string or null")
            forms[(number, gender)] = value
        if include_shared:
            value = number_map.get(SHARED_GENDER_KEY)
            if value is not None and not isinstance(value, str):
                raise ApiError(f"forms.{number}.{SHARED_GENDER_KEY} must be a string or null")
            forms[(number, None)] = value
    return forms


def _verb_forms_from_payload(raw: object) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    if raw is None:
        return result
    if not isinstance(raw, dict):
        raise ApiError("forms must be an object")
    for code, form_payload in raw.items():
        if not isinstance(code, str):
            raise ApiError("verb form keys must be strings")
        result[code] = _form_payload(form_payload, f"forms.{code}")
    return result


def _form_payload(raw: object, field: str) -> dict[str, object]:
    if raw is None:
        return {"form": None}
    if isinstance(raw, str):
        return {"form": raw}
    if isinstance(raw, dict):
        form = raw.get("form")
        if form is not None and not isinstance(form, str):
            raise ApiError(f"{field}.form must be a string or null")
        return {"form": form}
    raise ApiError(f"{field} must be a string, null, or object")
