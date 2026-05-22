from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


WORD_TYPES = {"noun", "verb", "adjective", "determiner", "other"}
NOMINAL_WORD_TYPES = {"noun", "adjective", "determiner"}
GENDER_AVAILABILITY = {"masc", "fem", "both", "ambiguous"}
NUMBERS = {"singular", "plural"}
GENDERS = {"masc", "fem"}
OTHER_SUBTYPES = {"adverb", "preposition", "conjunction", "interjection", "unknown"}
PARTICIPLE_TYPES = {"present", "past"}


class DatabaseError(RuntimeError):
    """Raised when the database layer cannot complete a valid operation."""


class ValidationError(ValueError):
    """Raised when input does not match the app's frozen data model."""


def _clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"{field_name} cannot be empty")
    return cleaned


def _clean_optional_form(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _bool_to_int(value: bool | int) -> int:
    return 1 if bool(value) else 0


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


class SpanishWordDatabase:
    """Small SQLite access layer for the Spanish Word DB app.

    This class owns all SQL access. PyQt code should call this class instead of
    executing SQL directly.
    """

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

        with self.transaction() as connection:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))
            connection.executescript(self.seed_path.read_text(encoding="utf-8"))

    def create_word(
        self,
        lemma: str,
        word_type: str,
        *,
        english: str = "",
        gender_availability: str = "both",
        other_subtype: str = "unknown",
    ) -> int:
        lemma = _clean_required_text(lemma, "lemma")
        english = english.strip()

        if word_type not in WORD_TYPES:
            raise ValidationError(f"invalid word_type: {word_type}")

        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO words (lemma, english, word_type)
                VALUES (?, ?, ?)
                """,
                (lemma, english, word_type),
            )
            word_id = int(cursor.lastrowid)

            if word_type in NOMINAL_WORD_TYPES:
                self._validate_gender_availability(gender_availability)
                connection.execute(
                    """
                    INSERT INTO nominal_details (word_id, gender_availability)
                    VALUES (?, ?)
                    """,
                    (word_id, gender_availability),
                )
                self._ensure_nominal_inflection_rows(connection, word_id)

            elif word_type == "other":
                self._validate_other_subtype(other_subtype)
                connection.execute(
                    """
                    INSERT INTO other_details (word_id, subtype)
                    VALUES (?, ?)
                    """,
                    (word_id, other_subtype),
                )

            elif word_type == "verb":
                self._ensure_verb_participle_rows(connection, word_id)
                self._ensure_verb_form_rows(connection, word_id)

            return word_id

    def delete_word(self, word_id: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM words WHERE id = ?", (word_id,))
            return cursor.rowcount > 0

    def save_word_base(self, word_id: int, *, lemma: str, english: str) -> None:
        lemma = _clean_required_text(lemma, "lemma")
        english = english.strip()

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
                    CASE
                        WHEN lemma COLLATE NOCASE = ? THEN 1
                        ELSE 0
                    END AS is_exact
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
            word_type = data["word_type"]

            if word_type in NOMINAL_WORD_TYPES:
                data["nominal"] = self._load_nominal(connection, word_id)

            elif word_type == "other":
                data["other"] = self._load_other(connection, word_id)

            elif word_type == "verb":
                data["verb"] = self._load_verb(connection, word_id)

            return data

    def save_nominal_details(self, word_id: int, gender_availability: str) -> None:
        self._validate_gender_availability(gender_availability)

        with self.transaction() as connection:
            self._require_word_type(connection, word_id, NOMINAL_WORD_TYPES)
            connection.execute(
                """
                INSERT INTO nominal_details (word_id, gender_availability)
                VALUES (?, ?)
                ON CONFLICT(word_id) DO UPDATE SET
                    gender_availability = excluded.gender_availability
                """,
                (word_id, gender_availability),
            )
            self._ensure_nominal_inflection_rows(connection, word_id)
            self._clear_disallowed_nominal_forms(connection, word_id, gender_availability)

    def save_nominal_inflections(
        self,
        word_id: int,
        forms: dict[tuple[str, str], str | None],
    ) -> None:
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, NOMINAL_WORD_TYPES)
            details = connection.execute(
                """
                SELECT gender_availability
                FROM nominal_details
                WHERE word_id = ?
                """,
                (word_id,),
            ).fetchone()
            if details is None:
                raise DatabaseError(f"nominal details missing for word: {word_id}")

            gender_availability = str(details["gender_availability"])

            for (number, gender), form in forms.items():
                self._validate_number(number)
                self._validate_gender(gender)

                cleaned_form = _clean_optional_form(form)
                if not self._is_gender_allowed(gender_availability, gender):
                    cleaned_form = None

                connection.execute(
                    """
                    INSERT INTO nominal_inflections (word_id, number, gender, form)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(word_id, number, gender) DO UPDATE SET
                        form = excluded.form
                    """,
                    (word_id, number, gender, cleaned_form),
                )

    def save_other_details(self, word_id: int, subtype: str) -> None:
        self._validate_other_subtype(subtype)

        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"other"})
            connection.execute(
                """
                INSERT INTO other_details (word_id, subtype)
                VALUES (?, ?)
                ON CONFLICT(word_id) DO UPDATE SET
                    subtype = excluded.subtype
                """,
                (word_id, subtype),
            )

    def save_verb_participles(
        self,
        word_id: int,
        participles: dict[str, dict[str, Any]],
    ) -> None:
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"verb"})

            for participle_type, payload in participles.items():
                self._validate_participle_type(participle_type)

                form = _clean_optional_form(payload.get("form"))
                is_irregular = _bool_to_int(payload.get("is_irregular", False))

                connection.execute(
                    """
                    INSERT INTO verb_participles
                        (word_id, participle_type, form, is_irregular)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(word_id, participle_type) DO UPDATE SET
                        form = excluded.form,
                        is_irregular = excluded.is_irregular
                    """,
                    (word_id, participle_type, form, is_irregular),
                )

    def save_verb_forms(
        self,
        word_id: int,
        forms: dict[tuple[str, str], dict[str, Any]],
    ) -> None:
        with self.transaction() as connection:
            self._require_word_type(connection, word_id, {"verb"})
            tense_ids = self._get_tense_id_map(connection)
            person_ids = self._get_person_id_map(connection)

            for (tense_code, person_code), payload in forms.items():
                if tense_code not in tense_ids:
                    raise ValidationError(f"invalid tense_code: {tense_code}")
                if person_code not in person_ids:
                    raise ValidationError(f"invalid person_code: {person_code}")

                form = _clean_optional_form(payload.get("form"))
                is_irregular = _bool_to_int(payload.get("is_irregular", False))

                connection.execute(
                    """
                    INSERT INTO verb_forms
                        (word_id, tense_id, person_id, form, is_irregular)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(word_id, tense_id, person_id) DO UPDATE SET
                        form = excluded.form,
                        is_irregular = excluded.is_irregular
                    """,
                    (word_id, tense_ids[tense_code], person_ids[person_code], form, is_irregular),
                )

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

    def _load_nominal(self, connection: sqlite3.Connection, word_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT gender_availability
            FROM nominal_details
            WHERE word_id = ?
            """,
            (word_id,),
        ).fetchone()

        if details is None:
            raise DatabaseError(f"nominal details missing for word: {word_id}")

        rows = connection.execute(
            """
            SELECT number, gender, form
            FROM nominal_inflections
            WHERE word_id = ?
            ORDER BY
                CASE number
                    WHEN 'singular' THEN 1
                    WHEN 'plural' THEN 2
                END,
                CASE gender
                    WHEN 'masc' THEN 1
                    WHEN 'fem' THEN 2
                END
            """,
            (word_id,),
        ).fetchall()

        inflections: dict[str, dict[str, str | None]] = {
            "singular": {"masc": None, "fem": None},
            "plural": {"masc": None, "fem": None},
        }
        for row in rows:
            inflections[row["number"]][row["gender"]] = row["form"]

        return {
            "gender_availability": details["gender_availability"],
            "inflections": inflections,
        }

    def _load_other(self, connection: sqlite3.Connection, word_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT subtype
            FROM other_details
            WHERE word_id = ?
            """,
            (word_id,),
        ).fetchone()

        if details is None:
            raise DatabaseError(f"other details missing for word: {word_id}")

        return {"subtype": details["subtype"]}

    def _load_verb(self, connection: sqlite3.Connection, word_id: int) -> dict[str, Any]:
        self._ensure_verb_participle_rows(connection, word_id)
        self._ensure_verb_form_rows(connection, word_id)

        participle_rows = connection.execute(
            """
            SELECT participle_type, form, is_irregular
            FROM verb_participles
            WHERE word_id = ?
            ORDER BY
                CASE participle_type
                    WHEN 'present' THEN 1
                    WHEN 'past' THEN 2
                END
            """,
            (word_id,),
        ).fetchall()

        participles = {
            row["participle_type"]: {
                "form": row["form"],
                "is_irregular": bool(row["is_irregular"]),
            }
            for row in participle_rows
        }

        form_rows = connection.execute(
            """
            SELECT
                vt.group_code,
                vt.code AS tense_code,
                vt.label AS tense_label,
                vt.sort_order AS tense_sort_order,
                vp.code AS person_code,
                vp.label AS person_label,
                vp.imperative_label AS imperative_label,
                vp.sort_order AS person_sort_order,
                vf.form,
                vf.is_irregular
            FROM verb_forms vf
            JOIN verb_tenses vt ON vt.id = vf.tense_id
            JOIN verb_persons vp ON vp.id = vf.person_id
            WHERE vf.word_id = ?
            ORDER BY vt.sort_order, vp.sort_order
            """,
            (word_id,),
        ).fetchall()

        forms: dict[str, dict[str, Any]] = {}
        for row in form_rows:
            group = row["group_code"]
            tense_code = row["tense_code"]
            person_code = row["person_code"]

            forms.setdefault(group, {})
            forms[group].setdefault(
                tense_code,
                {
                    "label": row["tense_label"],
                    "sort_order": row["tense_sort_order"],
                    "persons": {},
                },
            )
            forms[group][tense_code]["persons"][person_code] = {
                "label": row["person_label"],
                "imperative_label": row["imperative_label"],
                "sort_order": row["person_sort_order"],
                "form": row["form"],
                "is_irregular": bool(row["is_irregular"]),
            }

        return {
            "participles": participles,
            "forms": forms,
        }

    def _ensure_nominal_inflection_rows(self, connection: sqlite3.Connection, word_id: int) -> None:
        for number in ("singular", "plural"):
            for gender in ("masc", "fem"):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO nominal_inflections
                        (word_id, number, gender, form)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (word_id, number, gender),
                )

    def _ensure_verb_participle_rows(self, connection: sqlite3.Connection, word_id: int) -> None:
        for participle_type in ("present", "past"):
            connection.execute(
                """
                INSERT OR IGNORE INTO verb_participles
                    (word_id, participle_type, form, is_irregular)
                VALUES (?, ?, NULL, 0)
                """,
                (word_id, participle_type),
            )

    def _ensure_verb_form_rows(self, connection: sqlite3.Connection, word_id: int) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO verb_forms
                (word_id, tense_id, person_id, form, is_irregular)
            SELECT ?, vt.id, vp.id, NULL, 0
            FROM verb_tenses vt
            CROSS JOIN verb_persons vp
            """,
            (word_id,),
        )

    def _clear_disallowed_nominal_forms(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        gender_availability: str,
    ) -> None:
        if gender_availability == "masc":
            connection.execute(
                """
                UPDATE nominal_inflections
                SET form = NULL
                WHERE word_id = ? AND gender = 'fem'
                """,
                (word_id,),
            )
        elif gender_availability == "fem":
            connection.execute(
                """
                UPDATE nominal_inflections
                SET form = NULL
                WHERE word_id = ? AND gender = 'masc'
                """,
                (word_id,),
            )

    def _require_word_type(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        allowed_types: set[str],
    ) -> str:
        row = connection.execute(
            "SELECT word_type FROM words WHERE id = ?",
            (word_id,),
        ).fetchone()

        if row is None:
            raise DatabaseError(f"word not found: {word_id}")

        word_type = str(row["word_type"])
        if word_type not in allowed_types:
            allowed = ", ".join(sorted(allowed_types))
            raise ValidationError(f"word {word_id} has type {word_type}; expected one of: {allowed}")

        return word_type

    def _get_tense_id_map(self, connection: sqlite3.Connection) -> dict[str, int]:
        rows = connection.execute("SELECT id, code FROM verb_tenses").fetchall()
        return {row["code"]: int(row["id"]) for row in rows}

    def _get_person_id_map(self, connection: sqlite3.Connection) -> dict[str, int]:
        rows = connection.execute("SELECT id, code FROM verb_persons").fetchall()
        return {row["code"]: int(row["id"]) for row in rows}

    @staticmethod
    def _validate_gender_availability(value: str) -> None:
        if value not in GENDER_AVAILABILITY:
            raise ValidationError(f"invalid gender_availability: {value}")

    @staticmethod
    def _validate_number(value: str) -> None:
        if value not in NUMBERS:
            raise ValidationError(f"invalid number: {value}")

    @staticmethod
    def _validate_gender(value: str) -> None:
        if value not in GENDERS:
            raise ValidationError(f"invalid gender: {value}")

    @staticmethod
    def _validate_other_subtype(value: str) -> None:
        if value not in OTHER_SUBTYPES:
            raise ValidationError(f"invalid other subtype: {value}")

    @staticmethod
    def _validate_participle_type(value: str) -> None:
        if value not in PARTICIPLE_TYPES:
            raise ValidationError(f"invalid participle_type: {value}")

    @staticmethod
    def _is_gender_allowed(gender_availability: str, gender: str) -> bool:
        if gender_availability in {"both", "ambiguous"}:
            return True
        return gender_availability == gender
