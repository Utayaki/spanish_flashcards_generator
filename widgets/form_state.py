from __future__ import annotations


GENDER_AVAILABILITY = {"masculine", "feminine", "both"}
GENDERS = ("masculine", "feminine")
NUMBERS = ("singular", "plural")
SHARED_GENDER_KEY = "shared"


class WidgetStateError(ValueError):
    """Raised when widget helper state receives invalid data."""


def normalize_optional_form(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def validate_gender_availability(gender_availability: str) -> str:
    if gender_availability not in GENDER_AVAILABILITY:
        raise WidgetStateError(f"invalid gender availability: {gender_availability}")
    return gender_availability


def validate_gender(gender: str | None) -> str | None:
    if gender is not None and gender not in GENDERS:
        raise WidgetStateError(f"invalid gender: {gender}")
    return gender


def validate_number(number: str) -> str:
    if number not in NUMBERS:
        raise WidgetStateError(f"invalid number: {number}")
    return number


def empty_gendered_forms() -> dict[tuple[str, str | None], str | None]:
    return {(number, gender): None for number in NUMBERS for gender in GENDERS}


def empty_shared_forms() -> dict[tuple[str, str | None], str | None]:
    return {(number, None): None for number in NUMBERS}
