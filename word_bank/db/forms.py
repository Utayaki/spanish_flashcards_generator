from __future__ import annotations

import sqlite3
from typing import Any

from shared.errors import DatabaseError, ValidationError
from shared.verb_form_catalog import (
    VERB_FORM_CODE_BY_ID,
    VERB_FORM_ID_BY_CODE,
    persisted_verb_form_rows,
)

from word_bank.db.connection import WordBankConnectionMixin
from word_bank.db.constants import (
    ADJECTIVE_INFLECTION_TYPES,
    GENDER_AVAILABILITY,
    GENDERS,
    INFLECTION_FORM_TYPES,
    NUMBERS,
    OTHER_INFLECTION_TYPES,
    NUMBER_GENDER_FORM_TABLES,
    FormKey,
)
from word_bank.db.validation import (
    clean_optional_form,
    clean_required_form,
    empty_nested_forms,
)


class WordBankFormsRepository(WordBankConnectionMixin):
    def seed_verb_form_definitions(self, connection: sqlite3.Connection) -> None:
        rows = persisted_verb_form_rows()
        connection.executemany(
            """
            INSERT INTO verb_form_definitions (
                id,
                group_code,
                tense_code,
                person_code,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                group_code = excluded.group_code,
                tense_code = excluded.tense_code,
                person_code = excluded.person_code,
                sort_order = excluded.sort_order
            """,
            [
                (
                    row["id"],
                    row["group_code"],
                    row["tense_code"],
                    row["person_code"],
                    row["sort_order"],
                )
                for row in rows
            ],
        )

    def insert_detail(
        self,
        connection: sqlite3.Connection,
        table: str,
        value_column: str,
        lexical_item_id: int,
        value: str,
    ) -> None:
        connection.execute(
            f"INSERT INTO {table} (lexical_item_id, {value_column}) VALUES (?, ?)",
            (lexical_item_id, value),
        )

    def upsert_detail(
        self,
        connection: sqlite3.Connection,
        table: str,
        value_column: str,
        lexical_item_id: int,
        value: str,
    ) -> None:
        connection.execute(
            f"""
            INSERT INTO {table} (lexical_item_id, {value_column})
            VALUES (?, ?)
            ON CONFLICT(lexical_item_id) DO UPDATE SET
                {value_column} = excluded.{value_column}
            """,
            (lexical_item_id, value),
        )

    def load_noun(self, connection: sqlite3.Connection, lexical_item_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT gender_availability
            FROM noun_details
            WHERE lexical_item_id = ?
            """,
            (lexical_item_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"noun details missing for lexical item: {lexical_item_id}")
        return {
            "gender_availability": details["gender_availability"],
            "inflections": self.load_number_gender_forms(connection, "noun_forms", lexical_item_id),
        }

    def load_adjective(self, connection: sqlite3.Connection, lexical_item_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT inflection_type
            FROM adjective_details
            WHERE lexical_item_id = ?
            """,
            (lexical_item_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"adjective details missing for lexical item: {lexical_item_id}")
        return {
            "adjective_inflection_type": details["inflection_type"],
            "inflections": self.load_number_gender_forms(connection, "adjective_forms", lexical_item_id),
        }

    def load_other(self, connection: sqlite3.Connection, lexical_item_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT inflection_type
            FROM other_details
            WHERE lexical_item_id = ?
            """,
            (lexical_item_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"other details missing for lexical item: {lexical_item_id}")

        inflection_type = str(details["inflection_type"])
        return {
            "inflection_type": inflection_type,
            "inflections": (
                self.load_number_gender_forms(connection, "other_forms", lexical_item_id)
                if inflection_type in INFLECTION_FORM_TYPES
                else None
            ),
        }

    def load_number_gender_forms(
        self,
        connection: sqlite3.Connection,
        table: str,
        lexical_item_id: int,
    ) -> dict[str, dict[str, str | None]]:
        self.validate_number_gender_table(table)
        rows = connection.execute(
            f"""
            SELECT grammatical_number, grammatical_gender, form
            FROM {table}
            WHERE lexical_item_id = ?
            ORDER BY grammatical_number, grammatical_gender
            """,
            (lexical_item_id,),
        ).fetchall()
        nested = empty_nested_forms(include_shared=True)
        for row in rows:
            number = str(row["grammatical_number"])
            gender = row["grammatical_gender"]
            key = "shared" if gender is None else str(gender)
            if number in nested:
                nested[number][key] = row["form"]
        return nested

    def load_verb(self, connection: sqlite3.Connection, lexical_item_id: int) -> dict[str, Any]:
        rows = connection.execute(
            """
            SELECT
                vfd.id,
                vf.form
            FROM verb_form_definitions vfd
            LEFT JOIN verb_forms vf
                ON vf.verb_form_id = vfd.id
               AND vf.lexical_item_id = ?
            ORDER BY vfd.sort_order
            """,
            (lexical_item_id,),
        ).fetchall()
        return {
            "forms": {
                VERB_FORM_CODE_BY_ID[int(row["id"])]: {"form": row["form"]}
                for row in rows
                if int(row["id"]) in VERB_FORM_CODE_BY_ID
            }
        }

    def replace_noun_forms(
        self,
        connection: sqlite3.Connection,
        lexical_item_id: int,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self.replace_number_gender_forms(
            connection,
            table="noun_forms",
            lexical_item_id=lexical_item_id,
            expected_keys=self.expected_noun_form_keys(gender_availability),
            forms=forms,
            label="noun form",
            allow_missing=True,
        )

    def replace_adjective_forms(
        self,
        connection: sqlite3.Connection,
        lexical_item_id: int,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self.replace_number_gender_forms(
            connection,
            table="adjective_forms",
            lexical_item_id=lexical_item_id,
            expected_keys=self.expected_plurality_gender_form_keys(inflection_type),
            forms=forms,
            label="adjective form",
        )

    def replace_other_forms(
        self,
        connection: sqlite3.Connection,
        lexical_item_id: int,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self.replace_number_gender_forms(
            connection,
            table="other_forms",
            lexical_item_id=lexical_item_id,
            expected_keys=self.expected_plurality_gender_form_keys(inflection_type),
            forms=forms,
            label="other form",
        )

    def write_verb_forms(
        self,
        connection: sqlite3.Connection,
        lexical_item_id: int,
        forms: dict[str, dict[str, Any]],
    ) -> None:
        for code, payload in forms.items():
            if code not in VERB_FORM_ID_BY_CODE:
                raise ValidationError(f"invalid verb form code: {code}")
            verb_form_id = VERB_FORM_ID_BY_CODE[code]
            form = clean_optional_form(payload.get("form"))
            if form is None:
                connection.execute(
                    "DELETE FROM verb_forms WHERE lexical_item_id = ? AND verb_form_id = ?",
                    (lexical_item_id, verb_form_id),
                )
                continue
            connection.execute(
                """
                INSERT INTO verb_forms (lexical_item_id, verb_form_id, form)
                VALUES (?, ?, ?)
                ON CONFLICT(lexical_item_id, verb_form_id) DO UPDATE SET
                    form = excluded.form
                """,
                (lexical_item_id, verb_form_id, form),
            )

    def replace_number_gender_forms(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        lexical_item_id: int,
        expected_keys: tuple[FormKey, ...],
        forms: dict[FormKey, str | None],
        label: str,
        allow_missing: bool = False,
    ) -> None:
        self.validate_number_gender_table(table)
        cleaned = self.clean_expected_required_forms(forms, expected_keys, label, allow_missing=allow_missing)
        connection.execute(f"DELETE FROM {table} WHERE lexical_item_id = ?", (lexical_item_id,))
        connection.executemany(
            f"""
            INSERT INTO {table} (lexical_item_id, grammatical_number, grammatical_gender, form)
            VALUES (?, ?, ?, ?)
            """,
            [(lexical_item_id, number, gender, form) for (number, gender), form in cleaned.items()],
        )

    def clean_expected_required_forms(
        self,
        forms: dict[FormKey, str | None],
        expected_keys: tuple[FormKey, ...],
        label: str,
        *,
        allow_missing: bool = False,
    ) -> dict[FormKey, str]:
        expected = set(expected_keys)
        cleaned: dict[FormKey, str] = {}

        for key in expected_keys:
            number, gender = key
            self.validate_number(number)
            self.validate_gender(gender)
            if allow_missing:
                value = clean_optional_form(forms.get(key))
                if value is not None:
                    cleaned[key] = value
            else:
                cleaned[key] = clean_required_form(forms.get(key), f"{label} {number} {gender or 'shared'}")

        for key, raw_value in forms.items():
            value = clean_optional_form(raw_value)
            if value is None or key in expected:
                continue
            number, gender = key
            raise ValidationError(
                f"{label} {number} {gender or 'shared'} is not allowed for this lexical item"
            )

        if allow_missing and not cleaned:
            raise ValidationError(f"at least one {label} is required")
        return cleaned

    def expected_noun_form_keys(self, gender_availability: str) -> tuple[FormKey, ...]:
        self.validate_gender_availability(gender_availability)
        if gender_availability == "masculine":
            return tuple((number, "masculine") for number in NUMBERS)
        if gender_availability == "feminine":
            return tuple((number, "feminine") for number in NUMBERS)
        return tuple((number, gender) for number in NUMBERS for gender in GENDERS)

    def expected_plurality_gender_form_keys(self, inflection_type: str) -> tuple[FormKey, ...]:
        if inflection_type not in INFLECTION_FORM_TYPES:
            raise ValidationError(f"invalid inflection_type: {inflection_type}")
        if inflection_type == "plurality":
            return tuple((number, None) for number in NUMBERS)
        return tuple((number, gender) for number in NUMBERS for gender in GENDERS)

    def validate_number_gender_table(self, table: str) -> None:
        if table not in NUMBER_GENDER_FORM_TABLES:
            raise DatabaseError(f"invalid number/gender form table: {table}")

    def require_lexical_item_type(
        self, connection: sqlite3.Connection, lexical_item_id: int, allowed_types: set[str]
    ) -> str:
        row = connection.execute(
            "SELECT lexical_item_type FROM lexical_items WHERE id = ?", (lexical_item_id,)
        ).fetchone()
        if row is None:
            raise DatabaseError(f"lexical item not found: {lexical_item_id}")
        lexical_item_type = str(row["lexical_item_type"])
        if lexical_item_type not in allowed_types:
            allowed = ", ".join(sorted(allowed_types))
            raise ValidationError(
                f"lexical item {lexical_item_id} has type {lexical_item_type}, expected one of: {allowed}"
            )
        return lexical_item_type

    def validate_gender_availability(self, gender_availability: str) -> None:
        if gender_availability not in GENDER_AVAILABILITY:
            raise ValidationError(f"invalid gender_availability: {gender_availability}")

    def validate_number(self, number: str) -> None:
        if number not in NUMBERS:
            raise ValidationError(f"invalid grammatical_number: {number}")

    def validate_gender(self, gender: str | None) -> None:
        if gender is not None and gender not in GENDERS:
            raise ValidationError(f"invalid grammatical_gender: {gender}")

    def validate_other_inflection_type(self, inflection_type: str) -> None:
        if inflection_type not in OTHER_INFLECTION_TYPES:
            raise ValidationError(f"invalid inflection_type: {inflection_type}")

    def validate_adjective_inflection_type(self, inflection_type: str) -> None:
        if inflection_type not in ADJECTIVE_INFLECTION_TYPES:
            raise ValidationError(f"invalid adjective_inflection_type: {inflection_type}")
