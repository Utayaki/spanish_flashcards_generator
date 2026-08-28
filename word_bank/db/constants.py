from __future__ import annotations

LEXICAL_ITEM_TYPES = {"noun", "verb", "adjective", "other"}
GENDER_AVAILABILITY = {"masculine", "feminine", "both"}
NUMBERS = ("singular", "plural")
GENDERS = ("masculine", "feminine")
OTHER_INFLECTION_TYPES = {"none", "plurality", "gender_plurality"}
ADJECTIVE_INFLECTION_TYPES = {"plurality", "gender_plurality"}
FormKey = tuple[str, str | None]

INFLECTION_FORM_TYPES = {"plurality", "gender_plurality"}
NUMBER_GENDER_FORM_TABLES = {"noun_forms", "adjective_forms", "other_forms"}
