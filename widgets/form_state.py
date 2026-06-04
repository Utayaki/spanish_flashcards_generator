from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GENDER_AVAILABILITY = {"masc", "fem", "both", "ambiguous"}
GENDERS = ("masc", "fem")
NUMBERS = ("singular", "plural")


class WidgetStateError(ValueError):
    """Raised when widget helper state receives invalid data."""


def normalize_optional_form(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


@dataclass(frozen=True)
class NullableTextValue:
    """A normalized value for a widget that can be set to None."""

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


@dataclass(frozen=True)
class IrregularTextValue:
    """A normalized value for a verb cell with an irregular flag."""

    form: str | None
    is_irregular: bool = False

    @classmethod
    def from_widget_state(
        cls,
        text: str,
        none_checked: bool,
        irregular_checked: bool,
    ) -> "IrregularTextValue":
        form = NullableTextValue.from_widget_state(text, none_checked).form
        return cls(form=form, is_irregular=bool(irregular_checked) if form is not None else False)

    @property
    def is_none(self) -> bool:
        return self.form is None

    def as_database_payload(self) -> dict[str, Any]:
        return {"form": self.form, "is_irregular": self.is_irregular}


def validate_gender_availability(gender_availability: str) -> str:
    if gender_availability not in GENDER_AVAILABILITY:
        raise WidgetStateError(f"invalid gender availability: {gender_availability}")
    return gender_availability


def validate_gender(gender: str) -> str:
    if gender not in GENDERS:
        raise WidgetStateError(f"invalid gender: {gender}")
    return gender


def validate_number(number: str) -> str:
    if number not in NUMBERS:
        raise WidgetStateError(f"invalid number: {number}")
    return number


def allowed_genders(gender_availability: str) -> tuple[str, ...]:
    validate_gender_availability(gender_availability)
    if gender_availability == "masc":
        return ("masc",)
    if gender_availability == "fem":
        return ("fem",)
    return GENDERS


def is_gender_enabled(gender_availability: str, gender: str) -> bool:
    validate_gender(gender)
    return gender in allowed_genders(gender_availability)


def empty_nominal_forms() -> dict[tuple[str, str], str | None]:
    return {(number, gender): None for number in NUMBERS for gender in GENDERS}


def apply_gender_availability_to_forms(
    forms: dict[tuple[str, str], str | None],
    gender_availability: str,
) -> dict[tuple[str, str], str | None]:
    validate_gender_availability(gender_availability)
    cleaned = empty_nominal_forms()
    for (number, gender), value in forms.items():
        validate_number(number)
        validate_gender(gender)
        cleaned[(number, gender)] = normalize_optional_form(value) if is_gender_enabled(gender_availability, gender) else None
    return cleaned
