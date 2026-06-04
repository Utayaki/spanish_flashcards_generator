from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


WORD_TYPES = {"noun", "verb", "adjective", "other"}
NOMINAL_WORD_TYPES = {"noun", "adjective"}
INFLECTABLE_WORD_TYPES = {"noun", "adjective", "other"}
GENDER_AVAILABILITY = {"masc", "fem", "both", "ambiguous"}
NUMBERS = {"singular", "plural"}
GENDERS = {"masc", "fem"}
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


class DatabaseError(RuntimeError):
    """Raised when the database layer cannot complete a valid operation."""


class ValidationError(ValueError):
    """Raised when input does not match the app's frozen data model."""


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


def _bool_to_int(value: bool | int) -> int:
    return 1 if bool(value) else 0


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

        # This project intentionally has no migrations. If an older incompatible
        # development database is present, recreate it cleanly instead of
        # letting the GUI fail later with half-old, half-new tables.
        if self.db_path.exists() and self._has_incompatible_schema():
            self.db_path.unlink()

        with self.transaction() as connection:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))
            connection.executescript(self.seed_path.read_text(encoding="utf-8"))

    def _has_incompatible_schema(self) -> bool:
        try:
            connection = sqlite3.connect(self.db_path)
            try:
                words_sql = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'words'"
                ).fetchone()
                if words_sql is None:
                    return False
                if "determiner" in str(words_sql[0]):
                    return True

                nominal_columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(nominal_details)").fetchall()
                }
                if nominal_columns and "adjective_inflection_type" not in nominal_columns:
                    return True

                other_columns = {
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(other_details)").fetchall()
                }
                if other_columns and "inflection_type" not in other_columns:
                    return True
                if "has_inflections" in other_columns or "subtype" in other_columns:
                    return True

                if len(connection.execute("PRAGMA table_info(verb_participles)").fetchall()) not in {0, 4}:
                    return True
                if len(connection.execute("PRAGMA table_info(verb_forms)").fetchall()) not in {0, 5}:
                    return True
                return False
            finally:
                connection.close()
        except sqlite3.DatabaseError:
            return True

    def create_nominal_word(
        self,
        *,
        lemma: str,
        word_type: str,
        english: str,
        gender_availability: str,
        forms: dict[tuple[str, str], str | None],
        adjective_inflection_type: str = "gender_plurality",
    ) -> int:
        lemma = _clean_required_text(lemma, "lemma")
        english = _clean_required_english(english)
        if word_type not in NOMINAL_WORD_TYPES:
            allowed = ", ".join(sorted(NOMINAL_WORD_TYPES))
            raise ValidationError(f"invalid nominal word_type: {word_type}; expected one of: {allowed}")
        self._validate_gender_availability(gender_availability)
        adjective_inflection_type = self._clean_adjective_inflection_type(word_type, adjective_inflection_type)
        forms = self._with_locked_noun_default(word_type, lemma, gender_availability, forms)

        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO words (lemma, english, word_type)
                VALUES (?, ?, ?)
                """,
                (lemma, english, word_type),
            )
            word_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO nominal_details (word_id, gender_availability, adjective_inflection_type)
                VALUES (?, ?, ?)
                """,
                (word_id, gender_availability, adjective_inflection_type),
            )
            self._ensure_inflection_rows(connection, word_id)
            self._write_nominal_inflections(connection, word_id, gender_availability, forms)
            return word_id

    def create_other_word(
        self,
        *,
        lemma: str,
        english: str,
        inflection_type: str,
        forms: dict[tuple[str, str], str | None] | None = None,
        person_forms: dict[tuple[str, str], str | None] | None = None,
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
                self._ensure_inflection_rows(connection, word_id)
                self._write_unrestricted_inflections(connection, word_id, forms or {})
            elif inflection_type == "person_gender_plurality":
                self._ensure_other_person_rows(connection, word_id)
                self._write_other_person_inflections(connection, word_id, person_forms or {})
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
            if word_type in NOMINAL_WORD_TYPES:
                data["nominal"] = self._load_nominal(connection, word_id)
            elif word_type == "other":
                data["other"] = self._load_other(connection, word_id)
            elif word_type == "verb":
                data["verb"] = self._load_verb(connection, word_id)
            return data

    def save_nominal_details(
        self,
        word_id: int,
        gender_availability: str,
        adjective_inflection_type: str = "gender_plurality",
    ) -> None:
        self._validate_gender_availability(gender_availability)
        with self.transaction() as connection:
            word_type = self._require_word_type(connection, word_id, NOMINAL_WORD_TYPES)
            adjective_inflection_type = self._clean_adjective_inflection_type(word_type, adjective_inflection_type)
            connection.execute(
                """
                INSERT INTO nominal_details (word_id, gender_availability, adjective_inflection_type)
                VALUES (?, ?, ?)
                ON CONFLICT(word_id) DO UPDATE SET
                    gender_availability = excluded.gender_availability,
                    adjective_inflection_type = excluded.adjective_inflection_type
                """,
                (word_id, gender_availability, adjective_inflection_type),
            )
            self._ensure_inflection_rows(connection, word_id)
            self._clear_disallowed_nominal_forms(connection, word_id, gender_availability)
            if word_type == "noun" and gender_availability in {"masc", "fem"}:
                lemma = connection.execute("SELECT lemma FROM words WHERE id = ?", (word_id,)).fetchone()["lemma"]
                self._upsert_locked_noun_default(connection, word_id, str(lemma), gender_availability)

    def save_nominal_inflections(self, word_id: int, forms: dict[tuple[str, str], str | None]) -> None:
        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT w.lemma, w.word_type, nd.gender_availability
                FROM words w
                LEFT JOIN nominal_details nd ON nd.word_id = w.id
                WHERE w.id = ?
                """,
                (word_id,),
            ).fetchone()
            if row is None:
                raise DatabaseError(f"word not found: {word_id}")
            word_type = str(row["word_type"])
            if word_type not in NOMINAL_WORD_TYPES:
                allowed = ", ".join(sorted(NOMINAL_WORD_TYPES))
                raise ValidationError(f"word {word_id} has type {word_type}, expected one of: {allowed}")
            gender_availability = row["gender_availability"]
            if gender_availability is None:
                raise DatabaseError(f"nominal details missing for word: {word_id}")
            forms = self._with_locked_noun_default(word_type, str(row["lemma"]), str(gender_availability), forms)
            self._write_nominal_inflections(connection, word_id, str(gender_availability), forms)

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
            if inflection_type == "gender_plurality":
                self._ensure_inflection_rows(connection, word_id)
            elif inflection_type == "person_gender_plurality":
                self._ensure_other_person_rows(connection, word_id)

    def save_other_inflections(
        self,
        word_id: int,
        forms: dict[tuple[str, str], str | None],
        person_forms: dict[tuple[str, str], str | None],
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
                connection.execute("DELETE FROM nominal_inflections WHERE word_id = ?", (word_id,))
                connection.execute("DELETE FROM other_person_inflections WHERE word_id = ?", (word_id,))
            elif inflection_type == "gender_plurality":
                self._ensure_inflection_rows(connection, word_id)
                self._write_unrestricted_inflections(connection, word_id, forms)
                connection.execute("DELETE FROM other_person_inflections WHERE word_id = ?", (word_id,))
            elif inflection_type == "person_gender_plurality":
                self._ensure_other_person_rows(connection, word_id)
                self._write_other_person_inflections(connection, word_id, person_forms)
                connection.execute("DELETE FROM nominal_inflections WHERE word_id = ?", (word_id,))
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

    def _load_nominal(self, connection: sqlite3.Connection, word_id: int) -> dict[str, Any]:
        details = connection.execute(
            """
            SELECT gender_availability, adjective_inflection_type
            FROM nominal_details
            WHERE word_id = ?
            """,
            (word_id,),
        ).fetchone()
        if details is None:
            raise DatabaseError(f"nominal details missing for word: {word_id}")
        return {
            "gender_availability": details["gender_availability"],
            "adjective_inflection_type": details["adjective_inflection_type"],
            "inflections": self._load_inflections(connection, word_id),
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
            "inflections": self._load_inflections(connection, word_id) if inflection_type == "gender_plurality" else None,
            "person_inflections": self._load_other_person_inflections(connection, word_id)
            if inflection_type == "person_gender_plurality" else None,
        }

    def _load_inflections(self, connection: sqlite3.Connection, word_id: int) -> dict[str, dict[str, str | None]]:
        self._ensure_inflection_rows(connection, word_id)
        rows = connection.execute(
            """
            SELECT number, gender, form
            FROM nominal_inflections
            WHERE word_id = ?
            ORDER BY number, gender
            """,
            (word_id,),
        ).fetchall()
        nested: dict[str, dict[str, str | None]] = {
            "singular": {"masc": None, "fem": None},
            "plural": {"masc": None, "fem": None},
        }
        for row in rows:
            nested[str(row["number"])][str(row["gender"])] = row["form"]
        return nested

    def _load_other_person_inflections(
        self,
        connection: sqlite3.Connection,
        word_id: int,
    ) -> dict[str, dict[str, str | None]]:
        self._ensure_other_person_rows(connection, word_id)
        rows = connection.execute(
            """
            SELECT person_code, gender, form
            FROM other_person_inflections
            WHERE word_id = ?
            ORDER BY id
            """,
            (word_id,),
        ).fetchall()
        nested: dict[str, dict[str, str | None]] = {
            person: {"masc": None, "fem": None}
            for person in OTHER_PERSONS
        }
        for row in rows:
            nested[str(row["person_code"])][str(row["gender"])] = row["form"]
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

    def _ensure_inflection_rows(self, connection: sqlite3.Connection, word_id: int) -> None:
        for number in ("singular", "plural"):
            for gender in ("masc", "fem"):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO nominal_inflections (word_id, number, gender, form)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (word_id, number, gender),
                )

    def _ensure_other_person_rows(self, connection: sqlite3.Connection, word_id: int) -> None:
        for person in OTHER_PERSONS:
            for gender in ("masc", "fem"):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO other_person_inflections
                        (word_id, person_code, gender, form)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (word_id, person, gender),
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

    def _with_locked_noun_default(
        self,
        word_type: str,
        lemma: str,
        gender_availability: str,
        forms: dict[tuple[str, str], str | None],
    ) -> dict[tuple[str, str], str | None]:
        locked_forms = dict(forms)
        if word_type == "noun" and gender_availability == "masc":
            locked_forms[("singular", "masc")] = lemma
        elif word_type == "noun" and gender_availability == "fem":
            locked_forms[("singular", "fem")] = lemma
        return locked_forms

    def _upsert_locked_noun_default(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        lemma: str,
        gender_availability: str,
    ) -> None:
        if gender_availability == "masc":
            self._upsert_inflection(connection, word_id, "singular", "masc", lemma)
        elif gender_availability == "fem":
            self._upsert_inflection(connection, word_id, "singular", "fem", lemma)

    def _write_nominal_inflections(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        gender_availability: str,
        forms: dict[tuple[str, str], str | None],
    ) -> None:
        self._validate_gender_availability(gender_availability)
        for (number, gender), form in forms.items():
            self._validate_number(number)
            self._validate_gender(gender)
            cleaned_form = _clean_optional_form(form)
            if not self._is_gender_allowed(gender_availability, gender):
                cleaned_form = None
            self._upsert_inflection(connection, word_id, number, gender, cleaned_form)

    def _write_unrestricted_inflections(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        forms: dict[tuple[str, str], str | None],
    ) -> None:
        for (number, gender), form in forms.items():
            self._validate_number(number)
            self._validate_gender(gender)
            self._upsert_inflection(connection, word_id, number, gender, _clean_optional_form(form))

    def _write_other_person_inflections(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        forms: dict[tuple[str, str], str | None],
    ) -> None:
        for (person, gender), form in forms.items():
            self._validate_other_person(person)
            self._validate_gender(gender)
            connection.execute(
                """
                INSERT INTO other_person_inflections
                    (word_id, person_code, gender, form)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(word_id, person_code, gender) DO UPDATE SET
                    form = excluded.form
                """,
                (word_id, person, gender, _clean_optional_form(form)),
            )

    def _upsert_inflection(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        number: str,
        gender: str,
        form: str | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO nominal_inflections (word_id, number, gender, form)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(word_id, number, gender) DO UPDATE SET
                form = excluded.form
            """,
            (word_id, number, gender, form),
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

    def _clear_disallowed_nominal_forms(
        self,
        connection: sqlite3.Connection,
        word_id: int,
        gender_availability: str,
    ) -> None:
        self._validate_gender_availability(gender_availability)
        for gender in GENDERS:
            if not self._is_gender_allowed(gender_availability, gender):
                connection.execute(
                    """
                    UPDATE nominal_inflections
                    SET form = NULL
                    WHERE word_id = ? AND gender = ?
                    """,
                    (word_id, gender),
                )

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
            raise ValidationError(f"invalid number: {number}")

    def _validate_gender(self, gender: str) -> None:
        if gender not in GENDERS:
            raise ValidationError(f"invalid gender: {gender}")

    def _validate_participle_type(self, participle_type: str) -> None:
        if participle_type not in PARTICIPLE_TYPES:
            raise ValidationError(f"invalid participle_type: {participle_type}")

    def _validate_other_inflection_type(self, inflection_type: str) -> None:
        if inflection_type not in OTHER_INFLECTION_TYPES:
            raise ValidationError(f"invalid inflection_type: {inflection_type}")

    def _clean_adjective_inflection_type(self, word_type: str, value: str) -> str:
        if word_type != "adjective":
            return "gender_plurality"
        if value not in ADJECTIVE_INFLECTION_TYPES:
            raise ValidationError(f"invalid adjective_inflection_type: {value}")
        return value

    def _validate_other_person(self, person: str) -> None:
        if person not in OTHER_PERSONS:
            raise ValidationError(f"invalid person: {person}")

    def _is_gender_allowed(self, gender_availability: str, gender: str) -> bool:
        self._validate_gender_availability(gender_availability)
        self._validate_gender(gender)
        if gender_availability == "masc":
            return gender == "masc"
        if gender_availability == "fem":
            return gender == "fem"
        return True
