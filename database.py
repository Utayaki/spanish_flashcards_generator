from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


WORD_TYPES = {"noun", "verb", "adjective", "other"}
GENDER_AVAILABILITY = {"masculine", "feminine", "both", "ambiguous"}
NUMBERS = ("singular", "plural")
GENDERS = ("masculine", "feminine")
PARTICIPLE_TYPES = {"present", "past"}
OTHER_INFLECTION_TYPES = {"none", "gender_plurality", "person_gender_plurality"}
ADJECTIVE_INFLECTION_TYPES = {"plurality", "gender_plurality"}
OTHER_PERSONS = (
    "yo",
    "tu",
    "vos",
    "el_ella_usted",
    "nosotros",
    "vosotros",
    "ellos_ellas_ustedes",
)

FormKey = tuple[str, str | None]
PersonFormKey = tuple[str, str]


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


class SpanishWordDatabase:
    """SQLite access layer for the Spanish Word DB app."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        schema_path: str | Path | None = None,
        seed_path: str | Path | None = None,
        initialize: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path) if schema_path else Path(__file__).with_name("schema.sql")
        self.seed_path = Path(seed_path) if seed_path else Path(__file__).with_name("seed.sql")
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
        if not self.seed_path.exists():
            raise DatabaseError(f"seed.sql not found: {self.seed_path}")

        # No migrations: an incompatible development database is recreated cleanly.
        if self.db_path.exists() and self._has_incompatible_schema():
            self.db_path.unlink()

        with self.transaction() as connection:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))
            connection.executescript(self.seed_path.read_text(encoding="utf-8"))

    def _has_incompatible_schema(self) -> bool:
        try:
            connection = sqlite3.connect(self.db_path)
            try:
                required_tables = {
                    "words",
                    "noun_details",
                    "noun_forms",
                    "adjective_details",
                    "adjective_forms",
                    "other_details",
                    "other_forms",
                    "other_person_inflections",
                    "verb_participles",
                    "verb_tenses",
                    "verb_persons",
                    "verb_forms",
                }
                existing_tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                if not required_tables.issubset(existing_tables):
                    return True

                noun_columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(noun_forms)").fetchall()
                }
                adjective_columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(adjective_forms)").fetchall()
                }
                other_person_columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(other_person_inflections)").fetchall()
                }
                return not (
                    {"grammatical_number", "grammatical_gender"}.issubset(noun_columns)
                    and {"grammatical_number", "grammatical_gender"}.issubset(adjective_columns)
                    and "grammatical_gender" in other_person_columns
                )
            finally:
                connection.close()
        except sqlite3.DatabaseError:
            return True

    def create_noun_word(
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
            cursor = connection.execute(
                """
                INSERT INTO words (lemma, english, word_type)
                VALUES (?, ?, 'noun')
                """,
                (lemma, english),
            )
            word_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO noun_details (word_id, gender_availability)
                VALUES (?, ?)
                """,
                (word_id, gender_availability),
            )
            self._replace_noun_forms(connection, word_id, gender_availability, forms)
            return word_id

    def create_adjective_word(
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
            cursor = connection.execute(
                """
                INSERT INTO words (lemma, english, word_type)
                VALUES (?, ?, 'adjective')
                """,
                (lemma, english),
            )
            word_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO adjective_details (word_id, inflection_type)
                VALUES (?, ?)
                """,
                (word_id, inflection_type),
            )
            self._replace_adjective_forms(connection, word_id, inflection_type, forms)
            return word_id

    def create_other_word(
        self,
        *,
        lemma: str,
        english: str,
        inflection_type: str,
        forms: dict[FormKey, str | None] | None = None,
        person_forms: dict[PersonFormKey, str | None] | None = None,
    ) -> int:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)
        self._validate_other_inflection_type(inflection_type)

        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO words (lemma, english, word_type)
                VALUES (?, ?, 'other')
                """,
                (lemma, english),
            )
            word_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO other_details (word_id, inflection_type)
                VALUES (?, ?)
                """,
                (word_id, inflection_type),
            )
            if inflection_type == "gender_plurality":
                self._replace_other_forms(connection, word_id, forms or {})
            elif inflection_type == "person_gender_plurality":
                self._replace_other_person_inflections(connection, word_id, person_forms or {})
            return word_id

    def create_verb_word(
        self,
        *,
        lemma: str,
        english: str,
        participles: dict[str, dict[str, Any]],
        forms: dict[tuple[str, str], dict[str, Any]],
    ) -> int:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)

        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO words (lemma, english, word_type)
                VALUES (?, ?, 'verb')
                """,
                (lemma, english),
            )
            word_id = int(cursor.lastrowid)
            self._ensure_verb_participle_rows(connection, word_id)
            self._ensure_verb_form_rows(connection, word_id)
            self._write_verb_participles(connection, word_id, participles)
            self._write_verb_forms(connection, word_id, forms)
            return word_id

    def delete_word(self, word_id: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM words WHERE id = ?", (word_id,))
            return cursor.rowcount > 0

    def save_word_base(self, word_id: int, *, lemma: str, english: str) -> None:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE words
                SET lemma = ?, english = ?
                WHERE id = ?
                """,
                (lemma, english, word_id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError(f"word not found: {word_id}")

    def save_noun_details(self, word_id: int, gender_availability: str) -> None:
        self._validate_gender_availability(gender_availability)
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"noun"})
            connection.execute(
                """
                INSERT INTO noun_details (word_id, gender_availability)
                VALUES (?, ?)
                ON CONFLICT(word_id) DO UPDATE SET
                    gender_availability = excluded.gender_availability
                """,
                (word_id, gender_availability),
            )

    def save_noun_forms(self, word_id: int, forms: dict[FormKey, str | None]) -> None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT w.lemma, nd.gender_availability
                FROM words w
                JOIN noun_details nd ON nd.word_id = w.id
                WHERE w.id = ? AND w.word_type = 'noun'
                """,
                (word_id,),
            ).fetchone()
            if row is None:
                raise DatabaseError(f"noun details missing for word: {word_id}")
            forms = self._with_locked_noun_default(str(row["lemma"]), str(row["gender_availability"]), forms)
            self._replace_noun_forms(connection, word_id, str(row["gender_availability"]), forms)

    def save_adjective_details(self, word_id: int, inflection_type: str) -> None:
        self._validate_adjective_inflection_type(inflection_type)
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"adjective"})
            connection.execute(
                """
                INSERT INTO adjective_details (word_id, inflection_type)
                VALUES (?, ?)
                ON CONFLICT(word_id) DO UPDATE SET
                    inflection_type = excluded.inflection_type
                """,
                (word_id, inflection_type),
            )

    def save_adjective_forms(self, word_id: int, forms: dict[FormKey, str | None]) -> None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT ad.inflection_type
                FROM words w
                JOIN adjective_details ad ON ad.word_id = w.id
                WHERE w.id = ? AND w.word_type = 'adjective'
                """,
                (word_id,),
            ).fetchone()
            if row is None:
                raise DatabaseError(f"adjective details missing for word: {word_id}")
            self._replace_adjective_forms(connection, word_id, str(row["inflection_type"]), forms)

    def save_other_details(self, word_id: int, inflection_type: str) -> None:
        self._validate_other_inflection_type(inflection_type)
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"other"})
            connection.execute(
                """
                INSERT INTO other_details (word_id, inflection_type)
                VALUES (?, ?)
                ON CONFLICT(word_id) DO UPDATE SET
                    inflection_type = excluded.inflection_type
                """,
                (word_id, inflection_type),
            )

    def save_other_inflections(
        self,
        word_id: int,
        forms: dict[FormKey, str | None],
        person_forms: dict[PersonFormKey, str | None],
    ) -> None:
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"other"})
            details = connection.execute(
                """
                SELECT inflection_type
                FROM other_details
                WHERE word_id = ?
                """,
                (word_id,),
            ).fetchone()
            if details is None:
                raise DatabaseError(f"other details missing for word: {word_id}")

            inflection_type = str(details["inflection_type"])
            if inflection_type == "none":
                connection.execute("DELETE FROM other_forms WHERE word_id = ?", (word_id,))
                connection.execute("DELETE FROM other_person_inflections WHERE word_id = ?", (word_id,))
            elif inflection_type == "gender_plurality":
                self._replace_other_forms(connection, word_id, forms)
                connection.execute("DELETE FROM other_person_inflections WHERE word_id = ?", (word_id,))
            elif inflection_type == "person_gender_plurality":
                self._replace_other_person_inflections(connection, word_id, person_forms)
                connection.execute("DELETE FROM other_forms WHERE word_id = ?", (word_id,))
            else:
                raise ValidationError(f"invalid inflection_type: {inflection_type}")

    def save_verb_participles(self, word_id: int, participles: dict[str, dict[str, Any]]) -> None:
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"verb"})
            self._write_verb_participles(connection, word_id, participles)

    def save_verb_forms(self, word_id: int, forms: dict[tuple[str, str], dict[str, Any]]) -> None:
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"verb"})
            self._write_verb_forms(connection, word_id, forms)

    def search_words(self, word_type: str, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        if word_type not in WORD_TYPES:
            raise ValidationError(f"invalid word_type: {word_type}")
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
                    word_type,
                    CASE WHEN lemma COLLATE NOCASE = ? THEN 1 ELSE 0 END AS is_exact
                FROM words
                WHERE word_type = ?
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
                (cleaned, word_type, contains_pattern, cleaned, prefix_pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_word_summary(self, word_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, lemma, english, word_type, created_at, updated_at
                FROM words
                WHERE id = ?
                """,
                (word_id,),
            ).fetchone()
        return _row_to_dict(row)

    def load_word(self, word_id: int) -> dict[str, Any]:
        with self.connect() as connection:
            word = connection.execute(
                """
                SELECT id, lemma, english, word_type, created_at, updated_at
                FROM words
                WHERE id = ?
                """,
                (word_id,),
            ).fetchone()
            if word is None:
                raise DatabaseError(f"word not found: {word_id}")

            data: dict[str, Any] = dict(word)
            word_type = str(data["word_type"])
            if word_type == "noun":
                data["nominal"] = self._load_noun(connection, word_id)
            elif word_type == "adjective":
                data["nominal"] = self._load_adjective(connection, word_id)
            elif word_type == "other":
                data["other"] = self._load_other(connection, word_id)
            elif word_type == "verb":
                data["verb"] = self._load_verb(connection, word_id)
            return data

    def list_verb_tenses(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, code, label, group_code, sort_order
                FROM verb_tenses
                ORDER BY sort_order
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_verb_persons(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, code, label, imperative_label, sort_order
                FROM verb_persons
                ORDER BY sort_order
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _load_noun(self, connection: sqlite3.Connection, word_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT gender_availability
            FROM noun_details
            WHERE word_id = ?
            """,
            (word_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"noun details missing for word: {word_id}")
        return {
            "gender_availability": details["gender_availability"],
            "inflections": self._load_number_gender_forms(connection, "noun_forms", word_id),
        }

    def _load_adjective(self, connection: sqlite3.Connection, word_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT inflection_type
            FROM adjective_details
            WHERE word_id = ?
            """,
            (word_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"adjective details missing for word: {word_id}")
        return {
            "adjective_inflection_type": details["inflection_type"],
            "inflections": self._load_number_gender_forms(connection, "adjective_forms", word_id),
        }

    def _load_other(self, connection: sqlite3.Connection, word_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT inflection_type
            FROM other_details
            WHERE word_id = ?
            """,
            (word_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"other details missing for word: {word_id}")

        inflection_type = str(details["inflection_type"])
        return {
            "inflection_type": inflection_type,
            "inflections": self._load_other_forms(connection, word_id) if inflection_type == "gender_plurality" else None,
            "person_inflections": self._load_other_person_inflections(connection, word_id)
            if inflection_type == "person_gender_plurality" else None,
        }

    def _load_number_gender_forms(
        self,
        connection: sqlite3.Connection,
        table: str,
        word_id: int,
    ) -> dict[str, dict[str, str | None]]:
        rows = connection.execute(
            f"""
            SELECT grammatical_number, grammatical_gender, form
            FROM {table}
            WHERE word_id = ?
            ORDER BY grammatical_number, grammatical_gender
            """,
            (word_id,),
        ).fetchall()
        nested = self._empty_nested_forms(include_shared=True)
        for row in rows:
            number = str(row["grammatical_number"])
            gender = row["grammatical_gender"]
            key = "shared" if gender is None else str(gender)
            if number in nested:
                nested[number][key] = row["form"]
        return nested

    def _load_other_forms(self, connection: sqlite3.Connection, word_id: int) -> dict[str, dict[str, str | None]]:
        rows = connection.execute(
            """
            SELECT grammatical_number, grammatical_gender, form
            FROM other_forms
            WHERE word_id = ?
            ORDER BY grammatical_number, grammatical_gender
            """,
            (word_id,),
        ).fetchall()
        nested = self._empty_nested_forms(include_shared=False)
        for row in rows:
            nested[str(row["grammatical_number"])][str(row["grammatical_gender"])] = row["form"]
        return nested

    def _load_other_person_inflections(
        self,
        connection: sqlite3.Connection,
        word_id: int,
    ) -> dict[str, dict[str, str | None]]:
        rows = connection.execute(
            """
            SELECT person_code, grammatical_gender, form
            FROM other_person_inflections
            WHERE word_id = ?
            ORDER BY id
            """,
            (word_id,),
        ).fetchall()
        nested: dict[str, dict[str, str | None]] = {
            person: {gender: None for gender in GENDERS}
            for person in OTHER_PERSONS
        }
        for row in rows:
            nested[str(row["person_code"])][str(row["grammatical_gender"])] = row["form"]
        return nested

    def _load_verb(self, connection: sqlite3.Connection, word_id: int) -> dict[str, Any]:
        self._ensure_verb_participle_rows(connection, word_id)
        self._ensure_verb_form_rows(connection, word_id)

        participle_rows = connection.execute(
            """
            SELECT participle_type, form
            FROM verb_participles
            WHERE word_id = ?
            ORDER BY participle_type
            """,
            (word_id,),
        ).fetchall()
        participles = {
            str(row["participle_type"]): {"form": row["form"]}
            for row in participle_rows
        }

        form_rows = connection.execute(
            """
            SELECT
                vt.group_code,
                vt.code AS tense_code,
                vt.label AS tense_label,
                vp.code AS person_code,
                vp.label AS person_label,
                vf.form
            FROM verb_forms vf
            JOIN verb_tenses vt ON vt.id = vf.tense_id
            JOIN verb_persons vp ON vp.id = vf.person_id
            WHERE vf.word_id = ?
            ORDER BY vt.sort_order, vp.sort_order
            """,
            (word_id,),
        ).fetchall()

        groups: dict[str, dict[str, Any]] = {}
        for row in form_rows:
            group_code = str(row["group_code"])
            tense_code = str(row["tense_code"])
            person_code = str(row["person_code"])
            group = groups.setdefault(group_code, {})
            tense = group.setdefault(
                tense_code,
                {
                    "label": row["tense_label"],
                    "persons": {},
                },
            )
            tense["persons"][person_code] = {
                "label": row["person_label"],
                "form": row["form"],
            }

        return {
            "participles": participles,
            "forms": groups,
        }

    def _replace_noun_forms(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        expected_keys = self._expected_noun_form_keys(gender_availability)
        cleaned = self._clean_expected_required_forms(forms, expected_keys, "noun form")
        connection.execute("DELETE FROM noun_forms WHERE word_id = ?", (word_id,))
        for (number, gender), form in cleaned.items():
            connection.execute(
                """
                INSERT INTO noun_forms (word_id, grammatical_number, grammatical_gender, form)
                VALUES (?, ?, ?, ?)
                """,
                (word_id, number, gender, form),
            )

    def _replace_adjective_forms(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        expected_keys = self._expected_adjective_form_keys(inflection_type)
        cleaned = self._clean_expected_required_forms(forms, expected_keys, "adjective form")
        connection.execute("DELETE FROM adjective_forms WHERE word_id = ?", (word_id,))
        for (number, gender), form in cleaned.items():
            connection.execute(
                """
                INSERT INTO adjective_forms (word_id, grammatical_number, grammatical_gender, form)
                VALUES (?, ?, ?, ?)
                """,
                (word_id, number, gender, form),
            )

    def _replace_other_forms(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        forms: dict[FormKey, str | None],
    ) -> None:
        connection.execute("DELETE FROM other_forms WHERE word_id = ?", (word_id,))
        for number in NUMBERS:
            for gender in GENDERS:
                form = _clean_optional_form(forms.get((number, gender)))
                connection.execute(
                    """
                    INSERT INTO other_forms (word_id, grammatical_number, grammatical_gender, form)
                    VALUES (?, ?, ?, ?)
                    """,
                    (word_id, number, gender, form),
                )

    def _replace_other_person_inflections(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        forms: dict[PersonFormKey, str | None],
    ) -> None:
        connection.execute("DELETE FROM other_person_inflections WHERE word_id = ?", (word_id,))
        for person in OTHER_PERSONS:
            for gender in GENDERS:
                form = _clean_optional_form(forms.get((person, gender)))
                connection.execute(
                    """
                    INSERT INTO other_person_inflections
                        (word_id, person_code, grammatical_gender, form)
                    VALUES (?, ?, ?, ?)
                    """,
                    (word_id, person, gender, form),
                )

    def _ensure_verb_participle_rows(self, connection: sqlite3.Connection, word_id: int) -> None:
        for participle_type in ("present", "past"):
            connection.execute(
                """
                INSERT OR IGNORE INTO verb_participles
                    (word_id, participle_type, form)
                VALUES (?, ?, NULL)
                """,
                (word_id, participle_type),
            )

    def _ensure_verb_form_rows(self, connection: sqlite3.Connection, word_id: int) -> None:
        tense_ids = self._get_tense_id_map(connection)
        person_ids = self._get_person_id_map(connection)
        for tense_id in tense_ids.values():
            for person_id in person_ids.values():
                connection.execute(
                    """
                    INSERT OR IGNORE INTO verb_forms
                        (word_id, tense_id, person_id, form)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (word_id, tense_id, person_id),
                )

    def _write_verb_participles(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        participles: dict[str, dict[str, Any]],
    ) -> None:
        for participle_type, payload in participles.items():
            self._validate_participle_type(participle_type)
            form = _clean_optional_form(payload.get("form"))
            connection.execute(
                """
                INSERT INTO verb_participles
                    (word_id, participle_type, form)
                VALUES (?, ?, ?)
                ON CONFLICT(word_id, participle_type) DO UPDATE SET
                    form = excluded.form
                """,
                (word_id, participle_type, form),
            )

    def _write_verb_forms(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        forms: dict[tuple[str, str], dict[str, Any]],
    ) -> None:
        tense_ids = self._get_tense_id_map(connection)
        person_ids = self._get_person_id_map(connection)
        for (tense_code, person_code), payload in forms.items():
            if tense_code not in tense_ids:
                raise ValidationError(f"invalid tense_code: {tense_code}")
            if person_code not in person_ids:
                raise ValidationError(f"invalid person_code: {person_code}")
            form = _clean_optional_form(payload.get("form"))
            connection.execute(
                """
                INSERT INTO verb_forms
                    (word_id, tense_id, person_id, form)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(word_id, tense_id, person_id) DO UPDATE SET
                    form = excluded.form
                """,
                (word_id, tense_ids[tense_code], person_ids[person_code], form),
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
                f"{label} {number} {gender or 'shared'} is not allowed for this word"
            )
        return cleaned

    def _expected_noun_form_keys(self, gender_availability: str) -> tuple[FormKey, ...]:
        self._validate_gender_availability(gender_availability)
        if gender_availability == "masculine":
            return tuple((number, "masculine") for number in NUMBERS)
        if gender_availability == "feminine":
            return tuple((number, "feminine") for number in NUMBERS)
        return tuple((number, gender) for number in NUMBERS for gender in GENDERS)

    def _expected_adjective_form_keys(self, inflection_type: str) -> tuple[FormKey, ...]:
        self._validate_adjective_inflection_type(inflection_type)
        if inflection_type == "plurality":
            return tuple((number, None) for number in NUMBERS)
        return tuple((number, gender) for number in NUMBERS for gender in GENDERS)

    def _get_tense_id_map(self, connection: sqlite3.Connection) -> dict[str, int]:
        rows = connection.execute("SELECT id, code FROM verb_tenses").fetchall()
        return {str(row["code"]): int(row["id"]) for row in rows}

    def _get_person_id_map(self, connection: sqlite3.Connection) -> dict[str, int]:
        rows = connection.execute("SELECT id, code FROM verb_persons").fetchall()
        return {str(row["code"]): int(row["id"]) for row in rows}

    def _require_word_type(self, connection: sqlite3.Connection, word_id: int, allowed_types: set[str]) -> str:
        row = connection.execute("SELECT word_type FROM words WHERE id = ?", (word_id,)).fetchone()
        if row is None:
            raise DatabaseError(f"word not found: {word_id}")
        word_type = str(row["word_type"])
        if word_type not in allowed_types:
            allowed = ", ".join(sorted(allowed_types))
            raise ValidationError(f"word {word_id} has type {word_type}, expected one of: {allowed}")
        return word_type

    def _validate_gender_availability(self, gender_availability: str) -> None:
        if gender_availability not in GENDER_AVAILABILITY:
            raise ValidationError(f"invalid gender_availability: {gender_availability}")

    def _validate_number(self, number: str) -> None:
        if number not in NUMBERS:
            raise ValidationError(f"invalid grammatical_number: {number}")

    def _validate_gender(self, gender: str | None) -> None:
        if gender is not None and gender not in GENDERS:
            raise ValidationError(f"invalid grammatical_gender: {gender}")

    def _validate_participle_type(self, participle_type: str) -> None:
        if participle_type not in PARTICIPLE_TYPES:
            raise ValidationError(f"invalid participle_type: {participle_type}")

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
