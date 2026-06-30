from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from controllers.verb_form_catalog import (
    VERB_FORM_CODE_BY_ID,
    VERB_FORM_ID_BY_CODE,
    persisted_verb_form_rows,
)


LEXICAL_ITEM_TYPES = {"noun", "verb", "adjective", "other"}
GENDER_AVAILABILITY = {"masculine", "feminine", "both"}
NUMBERS = ("singular", "plural")
GENDERS = ("masculine", "feminine")
OTHER_INFLECTION_TYPES = {"none", "plurality", "gender_plurality"}
ADJECTIVE_INFLECTION_TYPES = {"plurality", "gender_plurality"}
FormKey = tuple[str, str | None]

INFLECTION_FORM_TYPES = {"plurality", "gender_plurality"}
NUMBER_GENDER_FORM_TABLES = {"noun_forms", "adjective_forms", "other_forms"}
NUMBER_GENDER_COLUMNS = {"grammatical_number", "grammatical_gender"}


class DatabaseError(RuntimeError):
    """Raised when the database layer cannot complete a valid operation."""


class ValidationError(ValueError):
    """Raised when input does not match the app's data model."""


def _clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"{field_name} cannot be empty")
    return cleaned


def _clean_required_explanation(value: str) -> str:
    return _clean_required_text(value, "explanation")


def _clean_optional_form(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_required_form(value: str | None, field_name: str) -> str:
    cleaned = _clean_optional_form(value)
    if cleaned is None:
        raise ValidationError(f"{field_name} cannot be empty")
    return cleaned


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


class SpanishLexicalItemDatabase:
    """SQLite access layer for the Spanish Lexical Item DB app."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        schema_path: str | Path | None = None,
        initialize: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path) if schema_path else Path(__file__).with_name("schema.sql")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        if not self.schema_path.exists():
            raise DatabaseError(f"schema.sql not found: {self.schema_path}")

        with self.transaction() as connection:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))
            self._seed_verb_form_definitions(connection)

    def create_noun_lexical_item(
        self,
        *,
        headword: str,
        explanation: str,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> int:
        headword = _clean_required_text(headword, "headword")
        explanation = _clean_required_explanation(explanation)
        self._validate_gender_availability(gender_availability)

        with self.transaction() as connection:
            lexical_item_id = self._insert_lexical_item(
                connection, headword=headword, explanation=explanation, lexical_item_type="noun"
            )
            self._insert_detail(connection, "noun_details", "gender_availability", lexical_item_id, gender_availability)
            self._replace_noun_forms(connection, lexical_item_id, gender_availability, forms)
            return lexical_item_id

    def create_adjective_lexical_item(
        self,
        *,
        headword: str,
        explanation: str,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> int:
        headword = _clean_required_text(headword, "headword")
        explanation = _clean_required_explanation(explanation)
        self._validate_adjective_inflection_type(inflection_type)

        with self.transaction() as connection:
            lexical_item_id = self._insert_lexical_item(
                connection, headword=headword, explanation=explanation, lexical_item_type="adjective"
            )
            self._insert_detail(connection, "adjective_details", "inflection_type", lexical_item_id, inflection_type)
            self._replace_adjective_forms(connection, lexical_item_id, inflection_type, forms)
            return lexical_item_id

    def create_other_lexical_item(
        self,
        *,
        headword: str,
        explanation: str,
        inflection_type: str,
        forms: dict[FormKey, str | None] | None = None,
    ) -> int:
        headword = _clean_required_text(headword, "headword")
        explanation = _clean_required_explanation(explanation)
        self._validate_other_inflection_type(inflection_type)

        with self.transaction() as connection:
            lexical_item_id = self._insert_lexical_item(
                connection, headword=headword, explanation=explanation, lexical_item_type="other"
            )
            self._insert_detail(connection, "other_details", "inflection_type", lexical_item_id, inflection_type)
            if inflection_type in INFLECTION_FORM_TYPES:
                self._replace_other_forms(connection, lexical_item_id, inflection_type, forms or {})
            return lexical_item_id

    def create_verb_lexical_item(
        self,
        *,
        headword: str,
        explanation: str,
        forms: dict[str, dict[str, Any]],
    ) -> int:
        headword = _clean_required_text(headword, "headword")
        explanation = _clean_required_explanation(explanation)

        with self.transaction() as connection:
            lexical_item_id = self._insert_lexical_item(
                connection, headword=headword, explanation=explanation, lexical_item_type="verb"
            )
            self._write_verb_forms(connection, lexical_item_id, forms)
            return lexical_item_id

    def delete_lexical_item(self, lexical_item_id: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM lexical_items WHERE id = ?", (lexical_item_id,))
            return cursor.rowcount > 0

    def save_lexical_item_base(self, lexical_item_id: int, *, headword: str, explanation: str) -> None:
        headword = _clean_required_text(headword, "headword")
        explanation = _clean_required_explanation(explanation)
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE lexical_items
                SET headword = ?, explanation = ?
                WHERE id = ?
                """,
                (headword, explanation, lexical_item_id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError(f"lexical item not found: {lexical_item_id}")

    def save_noun_details(self, lexical_item_id: int, gender_availability: str) -> None:
        self._validate_gender_availability(gender_availability)
        with self.transaction() as connection:
            self._require_lexical_item_type(connection, lexical_item_id, {"noun"})
            self._upsert_detail(connection, "noun_details", "gender_availability", lexical_item_id, gender_availability)

    def save_noun_forms(self, lexical_item_id: int, forms: dict[FormKey, str | None]) -> None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT l.headword, nd.gender_availability
                FROM lexical_items l
                JOIN noun_details nd ON nd.lexical_item_id = l.id
                WHERE l.id = ? AND l.lexical_item_type = 'noun'
                """,
                (lexical_item_id,),
            ).fetchone()
            if row is None:
                raise DatabaseError(f"noun details missing for lexical item: {lexical_item_id}")
            self._replace_noun_forms(connection, lexical_item_id, str(row["gender_availability"]), forms)

    def save_adjective_details(self, lexical_item_id: int, inflection_type: str) -> None:
        self._validate_adjective_inflection_type(inflection_type)
        with self.transaction() as connection:
            self._require_lexical_item_type(connection, lexical_item_id, {"adjective"})
            self._upsert_detail(connection, "adjective_details", "inflection_type", lexical_item_id, inflection_type)

    def save_adjective_forms(self, lexical_item_id: int, forms: dict[FormKey, str | None]) -> None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT ad.inflection_type
                FROM lexical_items l
                JOIN adjective_details ad ON ad.lexical_item_id = l.id
                WHERE l.id = ? AND l.lexical_item_type = 'adjective'
                """,
                (lexical_item_id,),
            ).fetchone()
            if row is None:
                raise DatabaseError(f"adjective details missing for lexical item: {lexical_item_id}")
            self._replace_adjective_forms(connection, lexical_item_id, str(row["inflection_type"]), forms)

    def save_other_details(self, lexical_item_id: int, inflection_type: str) -> None:
        self._validate_other_inflection_type(inflection_type)
        with self.transaction() as connection:
            self._require_lexical_item_type(connection, lexical_item_id, {"other"})
            self._upsert_detail(connection, "other_details", "inflection_type", lexical_item_id, inflection_type)

    def save_other_inflections(
        self,
        lexical_item_id: int,
        forms: dict[FormKey, str | None],
    ) -> None:
        with self.transaction() as connection:
            self._require_lexical_item_type(connection, lexical_item_id, {"other"})
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
            if inflection_type == "none":
                connection.execute("DELETE FROM other_forms WHERE lexical_item_id = ?", (lexical_item_id,))
            elif inflection_type in INFLECTION_FORM_TYPES:
                self._replace_other_forms(connection, lexical_item_id, inflection_type, forms)
            else:
                raise ValidationError(f"invalid inflection_type: {inflection_type}")

    def save_verb_forms(self, lexical_item_id: int, forms: dict[str, dict[str, Any]]) -> None:
        with self.transaction() as connection:
            self._require_lexical_item_type(connection, lexical_item_id, {"verb"})
            self._write_verb_forms(connection, lexical_item_id, forms)

    def search_lexical_items(self, lexical_item_type: str, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        if lexical_item_type not in LEXICAL_ITEM_TYPES:
            raise ValidationError(f"invalid lexical_item_type: {lexical_item_type}")
        if limit < 1:
            raise ValidationError("limit must be positive")

        cleaned = query.strip()
        if not cleaned:
            return []

        contains_pattern = f"%{cleaned}%"
        prefix_pattern = f"{cleaned}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    headword,
                    explanation,
                    lexical_item_type,
                    CASE WHEN headword COLLATE NOCASE = ? THEN 1 ELSE 0 END AS is_exact
                FROM lexical_items
                WHERE lexical_item_type = ?
                  AND headword COLLATE NOCASE LIKE ?
                ORDER BY
                    CASE
                        WHEN headword COLLATE NOCASE = ? THEN 0
                        WHEN headword COLLATE NOCASE LIKE ? THEN 1
                        ELSE 2
                    END,
                    headword COLLATE NOCASE
                LIMIT ?
                """,
                (cleaned, lexical_item_type, contains_pattern, cleaned, prefix_pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_random_lexical_item(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, headword, explanation, lexical_item_type
                FROM lexical_items
                ORDER BY RANDOM()
                LIMIT 1
                """
            ).fetchone()
        return _row_to_dict(row)

    def get_lexical_item_summary(self, lexical_item_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, headword, explanation, lexical_item_type, created_at, updated_at
                FROM lexical_items
                WHERE id = ?
                """,
                (lexical_item_id,),
            ).fetchone()
        return _row_to_dict(row)

    def load_lexical_item(self, lexical_item_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            lexical_item = connection.execute(
                """
                SELECT id, headword, explanation, lexical_item_type, created_at, updated_at
                FROM lexical_items
                WHERE id = ?
                """,
                (lexical_item_id,),
            ).fetchone()
            if lexical_item is None:
                raise DatabaseError(f"lexical item not found: {lexical_item_id}")

            data: dict[str, Any] = dict(lexical_item)
            lexical_item_type = str(data["lexical_item_type"])
            if lexical_item_type == "noun":
                data["noun"] = self._load_noun(connection, lexical_item_id)
            elif lexical_item_type == "adjective":
                data["adjective"] = self._load_adjective(connection, lexical_item_id)
            elif lexical_item_type == "other":
                data["other"] = self._load_other(connection, lexical_item_id)
            elif lexical_item_type == "verb":
                data["verb"] = self._load_verb(connection, lexical_item_id)
            return data

    def _insert_lexical_item(
        self,
        connection: sqlite3.Connection,
        *,
        headword: str,
        explanation: str,
        lexical_item_type: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO lexical_items (headword, explanation, lexical_item_type)
            VALUES (?, ?, ?)
            """,
            (headword, explanation, lexical_item_type),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _insert_detail(
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

    @staticmethod
    def _upsert_detail(
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

    def _load_noun(self, connection: sqlite3.Connection, lexical_item_id: int) -> dict[str, Any]:
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
            "inflections": self._load_number_gender_forms(connection, "noun_forms", lexical_item_id),
        }

    def _load_adjective(self, connection: sqlite3.Connection, lexical_item_id: int) -> dict[str, Any]:
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
            "inflections": self._load_number_gender_forms(connection, "adjective_forms", lexical_item_id),
        }

    def _load_other(self, connection: sqlite3.Connection, lexical_item_id: int) -> dict[str, Any]:
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
                self._load_number_gender_forms(connection, "other_forms", lexical_item_id)
                if inflection_type in INFLECTION_FORM_TYPES
                else None
            ),
        }

    def _load_number_gender_forms(
        self,
        connection: sqlite3.Connection,
        table: str,
        lexical_item_id: int,
    ) -> dict[str, dict[str, str | None]]:
        self._validate_number_gender_table(table)
        rows = connection.execute(
            f"""
            SELECT grammatical_number, grammatical_gender, form
            FROM {table}
            WHERE lexical_item_id = ?
            ORDER BY grammatical_number, grammatical_gender
            """,
            (lexical_item_id,),
        ).fetchall()
        nested = self._empty_nested_forms(include_shared=True)
        for row in rows:
            number = str(row["grammatical_number"])
            gender = row["grammatical_gender"]
            key = "shared" if gender is None else str(gender)
            if number in nested:
                nested[number][key] = row["form"]
        return nested

    def _load_verb(self, connection: sqlite3.Connection, lexical_item_id: int) -> dict[str, Any]:
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

    def _replace_number_gender_forms(
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
        self._validate_number_gender_table(table)
        cleaned = self._clean_expected_required_forms(forms, expected_keys, label, allow_missing=allow_missing)
        connection.execute(f"DELETE FROM {table} WHERE lexical_item_id = ?", (lexical_item_id,))
        connection.executemany(
            f"""
            INSERT INTO {table} (lexical_item_id, grammatical_number, grammatical_gender, form)
            VALUES (?, ?, ?, ?)
            """,
            [(lexical_item_id, number, gender, form) for (number, gender), form in cleaned.items()],
        )

    def _replace_noun_forms(
        self,
        connection: sqlite3.Connection,
        lexical_item_id: int,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self._replace_number_gender_forms(
            connection,
            table="noun_forms",
            lexical_item_id=lexical_item_id,
            expected_keys=self._expected_noun_form_keys(gender_availability),
            forms=forms,
            label="noun form",
            allow_missing=True,
        )

    def _replace_adjective_forms(
        self,
        connection: sqlite3.Connection,
        lexical_item_id: int,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self._replace_number_gender_forms(
            connection,
            table="adjective_forms",
            lexical_item_id=lexical_item_id,
            expected_keys=self._expected_plurality_gender_form_keys(inflection_type),
            forms=forms,
            label="adjective form",
        )

    def _replace_other_forms(
        self,
        connection: sqlite3.Connection,
        lexical_item_id: int,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self._replace_number_gender_forms(
            connection,
            table="other_forms",
            lexical_item_id=lexical_item_id,
            expected_keys=self._expected_plurality_gender_form_keys(inflection_type),
            forms=forms,
            label="other form",
        )

    def _seed_verb_form_definitions(self, connection: sqlite3.Connection) -> None:
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

    def _write_verb_forms(
        self,
        connection: sqlite3.Connection,
        lexical_item_id: int,
        forms: dict[str, dict[str, Any]],
    ) -> None:
        for code, payload in forms.items():
            if code not in VERB_FORM_ID_BY_CODE:
                raise ValidationError(f"invalid verb form code: {code}")
            verb_form_id = VERB_FORM_ID_BY_CODE[code]
            form = _clean_optional_form(payload.get("form"))
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

    def _clean_expected_required_forms(
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
            self._validate_number(number)
            self._validate_gender(gender)
            if allow_missing:
                value = _clean_optional_form(forms.get(key))
                if value is not None:
                    cleaned[key] = value
            else:
                cleaned[key] = _clean_required_form(forms.get(key), f"{label} {number} {gender or 'shared'}")

        for key, raw_value in forms.items():
            value = _clean_optional_form(raw_value)
            if value is None or key in expected:
                continue
            number, gender = key
            raise ValidationError(
                f"{label} {number} {gender or 'shared'} is not allowed for this lexical item"
            )

        if allow_missing and not cleaned:
            raise ValidationError(f"at least one {label} is required")
        return cleaned

    def _expected_noun_form_keys(self, gender_availability: str) -> tuple[FormKey, ...]:
        self._validate_gender_availability(gender_availability)
        if gender_availability == "masculine":
            return tuple((number, "masculine") for number in NUMBERS)
        if gender_availability == "feminine":
            return tuple((number, "feminine") for number in NUMBERS)
        return tuple((number, gender) for number in NUMBERS for gender in GENDERS)

    def _expected_plurality_gender_form_keys(self, inflection_type: str) -> tuple[FormKey, ...]:
        if inflection_type not in INFLECTION_FORM_TYPES:
            raise ValidationError(f"invalid inflection_type: {inflection_type}")
        if inflection_type == "plurality":
            return tuple((number, None) for number in NUMBERS)
        return tuple((number, gender) for number in NUMBERS for gender in GENDERS)

    def _validate_number_gender_table(self, table: str) -> None:
        if table not in NUMBER_GENDER_FORM_TABLES:
            raise DatabaseError(f"invalid number/gender form table: {table}")

    def _require_lexical_item_type(
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

    def _validate_gender_availability(self, gender_availability: str) -> None:
        if gender_availability not in GENDER_AVAILABILITY:
            raise ValidationError(f"invalid gender_availability: {gender_availability}")

    def _validate_number(self, number: str) -> None:
        if number not in NUMBERS:
            raise ValidationError(f"invalid grammatical_number: {number}")

    def _validate_gender(self, gender: str | None) -> None:
        if gender is not None and gender not in GENDERS:
            raise ValidationError(f"invalid grammatical_gender: {gender}")

    def _validate_other_inflection_type(self, inflection_type: str) -> None:
        if inflection_type not in OTHER_INFLECTION_TYPES:
            raise ValidationError(f"invalid inflection_type: {inflection_type}")

    def _validate_adjective_inflection_type(self, inflection_type: str) -> None:
        if inflection_type not in ADJECTIVE_INFLECTION_TYPES:
            raise ValidationError(f"invalid adjective_inflection_type: {inflection_type}")

    def _empty_nested_forms(self, *, include_shared: bool) -> dict[str, dict[str, str | None]]:
        return {
            number: {
                **{gender: None for gender in GENDERS},
                **({"shared": None} if include_shared else {}),
            }
            for number in NUMBERS
        }
