from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterator

from controllers.verb_form_catalog import VERB_FORM_COUNT, build_verb_form_definitions


LEMMA_TYPES = {"noun", "verb", "adjective", "other"}
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


def _clean_required_english(value: str) -> str:
    return _clean_required_text(value, "english definition")


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


class SpanishLemmaDatabase:
    """SQLite access layer for the Spanish Lemma DB app."""

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
        # No migrations: an incompatible development database is recreated cleanly.
        if self.db_path.exists() and self._has_incompatible_schema():
            self.db_path.unlink()

        with self.transaction() as connection:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))
            self._seed_verb_form_definitions(connection)

    def _has_incompatible_schema(self) -> bool:
        try:
            with closing(sqlite3.connect(self.db_path)) as connection:
                return not self._schema_is_compatible(connection)
        except sqlite3.DatabaseError:
            return True

    def _schema_is_compatible(self, connection: sqlite3.Connection) -> bool:
        required_tables = {
            "lemma",
            "noun_details",
            "noun_forms",
            "adjective_details",
            "adjective_forms",
            "other_details",
            "other_forms",
            "verb_form_definitions",
            "verb_forms",
        }
        if not required_tables.issubset(self._table_names(connection)):
            return False

        noun_columns = self._table_columns(connection, "noun_forms")
        adjective_columns = self._table_columns(connection, "adjective_forms")
        other_columns = self._table_columns(connection, "other_forms")
        lemma_columns = self._table_columns(connection, "lemma")
        verb_form_info = self._table_info_by_column(connection, "verb_forms")
        verb_form_columns = set(verb_form_info)
        definition_columns = self._table_columns(connection, "verb_form_definitions")
        lemma_sql = self._table_sql(connection, "lemma")
        definition_count = self._table_row_count(connection, "verb_form_definitions")
        form_is_required = "form" in verb_form_info and int(verb_form_info["form"][3]) == 1

        return (
            "lemma_type" in lemma_columns
            and "DEFAULT ''" not in lemma_sql
            and NUMBER_GENDER_COLUMNS.issubset(noun_columns)
            and NUMBER_GENDER_COLUMNS.issubset(adjective_columns)
            and NUMBER_GENDER_COLUMNS.issubset(other_columns)
            and "person_code" not in other_columns
            and {"lemma_id", "verb_form_id", "form"}.issubset(verb_form_columns)
            and form_is_required
            and "tense_id" not in verb_form_columns
            and {"code", "variant_code", "sort_order"}.issubset(definition_columns)
            and "variant_label" not in definition_columns
            and definition_count == VERB_FORM_COUNT
        )

    @staticmethod
    def _table_names(connection: sqlite3.Connection) -> set[str]:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        return {str(row[0]) for row in rows}

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _table_info_by_column(connection: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row | tuple[Any, ...]]:
        return {str(row[1]): row for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _table_sql(connection: sqlite3.Connection, table: str) -> str:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return "" if row is None else str(row[0])

    @staticmethod
    def _table_row_count(connection: sqlite3.Connection, table: str) -> int:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def create_noun_lemma(
        self,
        *,
        lemma: str,
        english: str,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> int:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)
        self._validate_gender_availability(gender_availability)
        forms = self._with_locked_noun_default(lemma, gender_availability, forms)

        with self.transaction() as connection:
            lemma_id = self._insert_lemma(connection, lemma=lemma, english=english, lemma_type="noun")
            self._insert_detail(connection, "noun_details", "gender_availability", lemma_id, gender_availability)
            self._replace_noun_forms(connection, lemma_id, gender_availability, forms)
            return lemma_id

    def create_adjective_lemma(
        self,
        *,
        lemma: str,
        english: str,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> int:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)
        self._validate_adjective_inflection_type(inflection_type)

        with self.transaction() as connection:
            lemma_id = self._insert_lemma(connection, lemma=lemma, english=english, lemma_type="adjective")
            self._insert_detail(connection, "adjective_details", "inflection_type", lemma_id, inflection_type)
            self._replace_adjective_forms(connection, lemma_id, inflection_type, forms)
            return lemma_id

    def create_other_lemma(
        self,
        *,
        lemma: str,
        english: str,
        inflection_type: str,
        forms: dict[FormKey, str | None] | None = None,
    ) -> int:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)
        self._validate_other_inflection_type(inflection_type)

        with self.transaction() as connection:
            lemma_id = self._insert_lemma(connection, lemma=lemma, english=english, lemma_type="other")
            self._insert_detail(connection, "other_details", "inflection_type", lemma_id, inflection_type)
            if inflection_type in INFLECTION_FORM_TYPES:
                self._replace_other_forms(connection, lemma_id, inflection_type, forms or {})
            return lemma_id

    def create_verb_lemma(
        self,
        *,
        lemma: str,
        english: str,
        forms: dict[str, dict[str, Any]],
    ) -> int:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)

        with self.transaction() as connection:
            lemma_id = self._insert_lemma(connection, lemma=lemma, english=english, lemma_type="verb")
            self._write_verb_forms(connection, lemma_id, forms)
            return lemma_id

    def delete_lemma(self, lemma_id: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM lemma WHERE id = ?", (lemma_id,))
            return cursor.rowcount > 0

    def save_lemma_base(self, lemma_id: int, *, lemma: str, english: str) -> None:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE lemma
                SET lemma = ?, english = ?
                WHERE id = ?
                """,
                (lemma, english, lemma_id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError(f"lemma not found: {lemma_id}")

    def save_noun_details(self, lemma_id: int, gender_availability: str) -> None:
        self._validate_gender_availability(gender_availability)
        with self.transaction() as connection:
            self._require_lemma_type(connection, lemma_id, {"noun"})
            self._upsert_detail(connection, "noun_details", "gender_availability", lemma_id, gender_availability)

    def save_noun_forms(self, lemma_id: int, forms: dict[FormKey, str | None]) -> None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT l.lemma, nd.gender_availability
                FROM lemma l
                JOIN noun_details nd ON nd.lemma_id = l.id
                WHERE l.id = ? AND l.lemma_type = 'noun'
                """,
                (lemma_id,),
            ).fetchone()
            if row is None:
                raise DatabaseError(f"noun details missing for lemma: {lemma_id}")
            forms = self._with_locked_noun_default(str(row["lemma"]), str(row["gender_availability"]), forms)
            self._replace_noun_forms(connection, lemma_id, str(row["gender_availability"]), forms)

    def save_adjective_details(self, lemma_id: int, inflection_type: str) -> None:
        self._validate_adjective_inflection_type(inflection_type)
        with self.transaction() as connection:
            self._require_lemma_type(connection, lemma_id, {"adjective"})
            self._upsert_detail(connection, "adjective_details", "inflection_type", lemma_id, inflection_type)

    def save_adjective_forms(self, lemma_id: int, forms: dict[FormKey, str | None]) -> None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT ad.inflection_type
                FROM lemma l
                JOIN adjective_details ad ON ad.lemma_id = l.id
                WHERE l.id = ? AND l.lemma_type = 'adjective'
                """,
                (lemma_id,),
            ).fetchone()
            if row is None:
                raise DatabaseError(f"adjective details missing for lemma: {lemma_id}")
            self._replace_adjective_forms(connection, lemma_id, str(row["inflection_type"]), forms)

    def save_other_details(self, lemma_id: int, inflection_type: str) -> None:
        self._validate_other_inflection_type(inflection_type)
        with self.transaction() as connection:
            self._require_lemma_type(connection, lemma_id, {"other"})
            self._upsert_detail(connection, "other_details", "inflection_type", lemma_id, inflection_type)

    def save_other_inflections(
        self,
        lemma_id: int,
        forms: dict[FormKey, str | None],
    ) -> None:
        with self.transaction() as connection:
            self._require_lemma_type(connection, lemma_id, {"other"})
            details = connection.execute(
                """
                SELECT inflection_type
                FROM other_details
                WHERE lemma_id = ?
                """,
                (lemma_id,),
            ).fetchone()
            if details is None:
                raise DatabaseError(f"other details missing for lemma: {lemma_id}")

            inflection_type = str(details["inflection_type"])
            if inflection_type == "none":
                connection.execute("DELETE FROM other_forms WHERE lemma_id = ?", (lemma_id,))
            elif inflection_type in INFLECTION_FORM_TYPES:
                self._replace_other_forms(connection, lemma_id, inflection_type, forms)
            else:
                raise ValidationError(f"invalid inflection_type: {inflection_type}")

    def save_verb_forms(self, lemma_id: int, forms: dict[str, dict[str, Any]]) -> None:
        with self.transaction() as connection:
            self._require_lemma_type(connection, lemma_id, {"verb"})
            self._write_verb_forms(connection, lemma_id, forms)

    def search_lemmas(self, lemma_type: str, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        if lemma_type not in LEMMA_TYPES:
            raise ValidationError(f"invalid lemma_type: {lemma_type}")
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
                    lemma,
                    english,
                    lemma_type,
                    CASE WHEN lemma COLLATE NOCASE = ? THEN 1 ELSE 0 END AS is_exact
                FROM lemma
                WHERE lemma_type = ?
                  AND lemma COLLATE NOCASE LIKE ?
                ORDER BY
                    CASE
                        WHEN lemma COLLATE NOCASE = ? THEN 0
                        WHEN lemma COLLATE NOCASE LIKE ? THEN 1
                        ELSE 2
                    END,
                    lemma COLLATE NOCASE
                LIMIT ?
                """,
                (cleaned, lemma_type, contains_pattern, cleaned, prefix_pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_lemma_summary(self, lemma_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, lemma, english, lemma_type, created_at, updated_at
                FROM lemma
                WHERE id = ?
                """,
                (lemma_id,),
            ).fetchone()
        return _row_to_dict(row)

    def load_lemma(self, lemma_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            lemma = connection.execute(
                """
                SELECT id, lemma, english, lemma_type, created_at, updated_at
                FROM lemma
                WHERE id = ?
                """,
                (lemma_id,),
            ).fetchone()
            if lemma is None:
                raise DatabaseError(f"lemma not found: {lemma_id}")

            data: dict[str, Any] = dict(lemma)
            lemma_type = str(data["lemma_type"])
            if lemma_type == "noun":
                data["noun"] = self._load_noun(connection, lemma_id)
            elif lemma_type == "adjective":
                data["adjective"] = self._load_adjective(connection, lemma_id)
            elif lemma_type == "other":
                data["other"] = self._load_other(connection, lemma_id)
            elif lemma_type == "verb":
                data["verb"] = self._load_verb(connection, lemma_id)
            return data

    def list_verb_form_definitions(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    code,
                    group_code,
                    group_label,
                    tense_code,
                    tense_label,
                    variant_code,
                    person_code,
                    person_label,
                    sort_order
                FROM verb_form_definitions
                ORDER BY sort_order
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _insert_lemma(
        self,
        connection: sqlite3.Connection,
        *,
        lemma: str,
        english: str,
        lemma_type: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO lemma (lemma, english, lemma_type)
            VALUES (?, ?, ?)
            """,
            (lemma, english, lemma_type),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _insert_detail(
        connection: sqlite3.Connection,
        table: str,
        value_column: str,
        lemma_id: int,
        value: str,
    ) -> None:
        connection.execute(
            f"INSERT INTO {table} (lemma_id, {value_column}) VALUES (?, ?)",
            (lemma_id, value),
        )

    @staticmethod
    def _upsert_detail(
        connection: sqlite3.Connection,
        table: str,
        value_column: str,
        lemma_id: int,
        value: str,
    ) -> None:
        connection.execute(
            f"""
            INSERT INTO {table} (lemma_id, {value_column})
            VALUES (?, ?)
            ON CONFLICT(lemma_id) DO UPDATE SET
                {value_column} = excluded.{value_column}
            """,
            (lemma_id, value),
        )

    def _load_noun(self, connection: sqlite3.Connection, lemma_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT gender_availability
            FROM noun_details
            WHERE lemma_id = ?
            """,
            (lemma_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"noun details missing for lemma: {lemma_id}")
        return {
            "gender_availability": details["gender_availability"],
            "inflections": self._load_number_gender_forms(connection, "noun_forms", lemma_id),
        }

    def _load_adjective(self, connection: sqlite3.Connection, lemma_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT inflection_type
            FROM adjective_details
            WHERE lemma_id = ?
            """,
            (lemma_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"adjective details missing for lemma: {lemma_id}")
        return {
            "adjective_inflection_type": details["inflection_type"],
            "inflections": self._load_number_gender_forms(connection, "adjective_forms", lemma_id),
        }

    def _load_other(self, connection: sqlite3.Connection, lemma_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT inflection_type
            FROM other_details
            WHERE lemma_id = ?
            """,
            (lemma_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"other details missing for lemma: {lemma_id}")

        inflection_type = str(details["inflection_type"])
        return {
            "inflection_type": inflection_type,
            "inflections": (
                self._load_number_gender_forms(connection, "other_forms", lemma_id)
                if inflection_type in INFLECTION_FORM_TYPES
                else None
            ),
        }

    def _load_number_gender_forms(
        self,
        connection: sqlite3.Connection,
        table: str,
        lemma_id: int,
    ) -> dict[str, dict[str, str | None]]:
        self._validate_number_gender_table(table)
        rows = connection.execute(
            f"""
            SELECT grammatical_number, grammatical_gender, form
            FROM {table}
            WHERE lemma_id = ?
            ORDER BY grammatical_number, grammatical_gender
            """,
            (lemma_id,),
        ).fetchall()
        nested = self._empty_nested_forms(include_shared=True)
        for row in rows:
            number = str(row["grammatical_number"])
            gender = row["grammatical_gender"]
            key = "shared" if gender is None else str(gender)
            if number in nested:
                nested[number][key] = row["form"]
        return nested

    def _load_verb(self, connection: sqlite3.Connection, lemma_id: int) -> dict[str, Any]:
        rows = connection.execute(
            """
            SELECT
                vfd.code,
                vf.form
            FROM verb_form_definitions vfd
            LEFT JOIN verb_forms vf
                ON vf.verb_form_id = vfd.id
               AND vf.lemma_id = ?
            ORDER BY vfd.sort_order
            """,
            (lemma_id,),
        ).fetchall()
        return {
            "forms": {str(row["code"]): {"form": row["form"]} for row in rows}
        }

    def _replace_number_gender_forms(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        lemma_id: int,
        expected_keys: tuple[FormKey, ...],
        forms: dict[FormKey, str | None],
        label: str,
    ) -> None:
        self._validate_number_gender_table(table)
        cleaned = self._clean_expected_required_forms(forms, expected_keys, label)
        connection.execute(f"DELETE FROM {table} WHERE lemma_id = ?", (lemma_id,))
        connection.executemany(
            f"""
            INSERT INTO {table} (lemma_id, grammatical_number, grammatical_gender, form)
            VALUES (?, ?, ?, ?)
            """,
            [(lemma_id, number, gender, form) for (number, gender), form in cleaned.items()],
        )

    def _replace_noun_forms(
        self,
        connection: sqlite3.Connection,
        lemma_id: int,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self._replace_number_gender_forms(
            connection,
            table="noun_forms",
            lemma_id=lemma_id,
            expected_keys=self._expected_noun_form_keys(gender_availability),
            forms=forms,
            label="noun form",
        )

    def _replace_adjective_forms(
        self,
        connection: sqlite3.Connection,
        lemma_id: int,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self._replace_number_gender_forms(
            connection,
            table="adjective_forms",
            lemma_id=lemma_id,
            expected_keys=self._expected_plurality_gender_form_keys(inflection_type),
            forms=forms,
            label="adjective form",
        )

    def _replace_other_forms(
        self,
        connection: sqlite3.Connection,
        lemma_id: int,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        self._replace_number_gender_forms(
            connection,
            table="other_forms",
            lemma_id=lemma_id,
            expected_keys=self._expected_plurality_gender_form_keys(inflection_type),
            forms=forms,
            label="other form",
        )

    def _seed_verb_form_definitions(self, connection: sqlite3.Connection) -> None:
        rows = build_verb_form_definitions()
        connection.executemany(
            """
            INSERT INTO verb_form_definitions (
                id,
                code,
                group_code,
                group_label,
                tense_code,
                tense_label,
                variant_code,
                person_code,
                person_label,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                code = excluded.code,
                group_code = excluded.group_code,
                group_label = excluded.group_label,
                tense_code = excluded.tense_code,
                tense_label = excluded.tense_label,
                variant_code = excluded.variant_code,
                person_code = excluded.person_code,
                person_label = excluded.person_label,
                sort_order = excluded.sort_order
            """,
            [
                (
                    row["id"],
                    row["code"],
                    row["group_code"],
                    row["group_label"],
                    row["tense_code"],
                    row["tense_label"],
                    row["variant_code"],
                    row["person_code"],
                    row["person_label"],
                    row["sort_order"],
                )
                for row in rows
            ],
        )

    def _write_verb_forms(
        self,
        connection: sqlite3.Connection,
        lemma_id: int,
        forms: dict[str, dict[str, Any]],
    ) -> None:
        definition_ids = self._get_verb_form_definition_id_map(connection)
        for code, payload in forms.items():
            if code not in definition_ids:
                raise ValidationError(f"invalid verb form code: {code}")
            verb_form_id = definition_ids[code]
            form = _clean_optional_form(payload.get("form"))
            if form is None:
                connection.execute(
                    "DELETE FROM verb_forms WHERE lemma_id = ? AND verb_form_id = ?",
                    (lemma_id, verb_form_id),
                )
                continue
            connection.execute(
                """
                INSERT INTO verb_forms (lemma_id, verb_form_id, form)
                VALUES (?, ?, ?)
                ON CONFLICT(lemma_id, verb_form_id) DO UPDATE SET
                    form = excluded.form
                """,
                (lemma_id, verb_form_id, form),
            )

    def _with_locked_noun_default(
        self,
        lemma: str,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> dict[FormKey, str | None]:
        locked_forms = dict(forms)
        if gender_availability == "masculine":
            locked_forms[("singular", "masculine")] = lemma
        elif gender_availability == "feminine":
            locked_forms[("singular", "feminine")] = lemma
        return locked_forms

    def _clean_expected_required_forms(
        self,
        forms: dict[FormKey, str | None],
        expected_keys: tuple[FormKey, ...],
        label: str,
    ) -> dict[FormKey, str]:
        expected = set(expected_keys)
        cleaned: dict[FormKey, str] = {}

        for key in expected_keys:
            number, gender = key
            self._validate_number(number)
            self._validate_gender(gender)
            cleaned[key] = _clean_required_form(forms.get(key), f"{label} {number} {gender or 'shared'}")

        for key, raw_value in forms.items():
            value = _clean_optional_form(raw_value)
            if value is None or key in expected:
                continue
            number, gender = key
            raise ValidationError(
                f"{label} {number} {gender or 'shared'} is not allowed for this lemma"
            )
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

    def _get_verb_form_definition_id_map(self, connection: sqlite3.Connection) -> dict[str, int]:
        rows = connection.execute("SELECT id, code FROM verb_form_definitions").fetchall()
        return {str(row["code"]): int(row["id"]) for row in rows}

    def _require_lemma_type(self, connection: sqlite3.Connection, lemma_id: int, allowed_types: set[str]) -> str:
        row = connection.execute("SELECT lemma_type FROM lemma WHERE id = ?", (lemma_id,)).fetchone()
        if row is None:
            raise DatabaseError(f"lemma not found: {lemma_id}")
        lemma_type = str(row["lemma_type"])
        if lemma_type not in allowed_types:
            allowed = ", ".join(sorted(allowed_types))
            raise ValidationError(f"lemma {lemma_id} has type {lemma_type}, expected one of: {allowed}")
        return lemma_type

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
