from __future__ import annotations

from word_bank.errors import ValidationError

from word_bank.db.constants import GENDERS, NUMBERS


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"{field_name} cannot be empty")
    return cleaned


def clean_required_explanation(value: str) -> str:
    return clean_required_text(value, "explanation")


def clean_optional_form(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def clean_required_form(value: str | None, field_name: str) -> str:
    cleaned = clean_optional_form(value)
    if cleaned is None:
        raise ValidationError(f"{field_name} cannot be empty")
    return cleaned


def empty_nested_forms(*, include_shared: bool) -> dict[str, dict[str, str | None]]:
    return {
        number: {
            **{gender: None for gender in GENDERS},
            **({"shared": None} if include_shared else {}),
        }
        for number in NUMBERS
    }
