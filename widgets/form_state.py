from __future__ import annotations

from dataclasses import dataclass

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


def normalize_required_form(value: str | None, field_name: str) -> str:
    cleaned = normalize_optional_form(value)
    if cleaned is None:
        raise WidgetStateError(f"{field_name} cannot be empty")
    return cleaned


@dataclass(frozen=True)
class NullableTextValue:
    """A normalized value for a text field that can be explicitly set to None."""

    form: str | None

    @classmethod
    def from_widget_state(cls, text: str, none_checked: bool) -> "NullableTextValue":
        if none_checked:
            return cls(None)
        return cls(normalize_optional_form(text))

    @property
    def is_none(self) -> bool:
        return self.form is None

    def as_database_value(self) -> str | None:
        return self.form


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


def allowed_genders(gender_availability: str) -> tuple[str, ...]:
    validate_gender_availability(gender_availability)
    if gender_availability == "masculine":
        return ("masculine",)
    if gender_availability == "feminine":
        return ("feminine",)
    return GENDERS


def is_gender_enabled(gender_availability: str, gender: str) -> bool:
    validate_gender(gender)
    return gender in allowed_genders(gender_availability)


def empty_gendered_forms() -> dict[tuple[str, str | None], str | None]:
    return {(number, gender): None for number in NUMBERS for gender in GENDERS}


def empty_shared_forms() -> dict[tuple[str, str | None], str | None]:
    return {(number, None): None for number in NUMBERS}


def apply_gender_availability_to_forms(
    forms: dict[tuple[str, str | None], str | None],
    gender_availability: str,
) -> dict[tuple[str, str | None], str | None]:
    validate_gender_availability(gender_availability)
    cleaned: dict[tuple[str, str | None], str | None] = {}
    allowed = set(allowed_genders(gender_availability))
    for (number, gender), value in forms.items():
        validate_number(number)
        validate_gender(gender)
        if gender in allowed:
            cleaned[(number, gender)] = normalize_optional_form(value)
    return cleaned
