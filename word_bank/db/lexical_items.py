from __future__ import annotations

import sqlite3
from typing import Any

from shared.errors import DatabaseError, ValidationError
from shared.sqlite.connection import row_to_dict

from word_bank.db.constants import INFLECTION_FORM_TYPES, LEXICAL_ITEM_TYPES, FormKey
from word_bank.db.forms import WordBankFormsRepository
from word_bank.db.validation import clean_required_explanation, clean_required_text


class WordBankLexicalItemsRepository(WordBankFormsRepository):
    def insert_lexical_item(
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

    def create_noun_lexical_item(
        self,
        *,
        headword: str,
        explanation: str,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> int:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)
        self.validate_gender_availability(gender_availability)

        with self.transaction() as connection:
            lexical_item_id = self.insert_lexical_item(
                connection, headword=headword, explanation=explanation, lexical_item_type="noun"
            )
            self.insert_detail(connection, "noun_details", "gender_availability", lexical_item_id, gender_availability)
            self.replace_noun_forms(connection, lexical_item_id, gender_availability, forms)
        return lexical_item_id

    def create_adjective_lexical_item(
        self,
        *,
        headword: str,
        explanation: str,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> int:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)
        self.validate_adjective_inflection_type(inflection_type)

        with self.transaction() as connection:
            lexical_item_id = self.insert_lexical_item(
                connection, headword=headword, explanation=explanation, lexical_item_type="adjective"
            )
            self.insert_detail(connection, "adjective_details", "inflection_type", lexical_item_id, inflection_type)
            self.replace_adjective_forms(connection, lexical_item_id, inflection_type, forms)
        return lexical_item_id

    def create_other_lexical_item(
        self,
        *,
        headword: str,
        explanation: str,
        inflection_type: str,
        forms: dict[FormKey, str | None] | None = None,
    ) -> int:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)
        self.validate_other_inflection_type(inflection_type)

        with self.transaction() as connection:
            lexical_item_id = self.insert_lexical_item(
                connection, headword=headword, explanation=explanation, lexical_item_type="other"
            )
            self.insert_detail(connection, "other_details", "inflection_type", lexical_item_id, inflection_type)
            if inflection_type in INFLECTION_FORM_TYPES:
                self.replace_other_forms(connection, lexical_item_id, inflection_type, forms or {})
        return lexical_item_id

    def create_verb_lexical_item(
        self,
        *,
        headword: str,
        explanation: str,
        forms: dict[str, dict[str, Any]],
    ) -> int:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)

        with self.transaction() as connection:
            lexical_item_id = self.insert_lexical_item(
                connection, headword=headword, explanation=explanation, lexical_item_type="verb"
            )
            self.write_verb_forms(connection, lexical_item_id, forms)
        return lexical_item_id

    def update_noun_lexical_item(
        self,
        lexical_item_id: int,
        *,
        headword: str,
        explanation: str,
        gender_availability: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)
        self.validate_gender_availability(gender_availability)

        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"noun"})
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

            self.upsert_detail(
                connection,
                "noun_details",
                "gender_availability",
                lexical_item_id,
                gender_availability,
            )
            self.replace_noun_forms(connection, lexical_item_id, gender_availability, forms)

    def update_adjective_lexical_item(
        self,
        lexical_item_id: int,
        *,
        headword: str,
        explanation: str,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)
        self.validate_adjective_inflection_type(inflection_type)

        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"adjective"})
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

            self.upsert_detail(
                connection,
                "adjective_details",
                "inflection_type",
                lexical_item_id,
                inflection_type,
            )
            self.replace_adjective_forms(connection, lexical_item_id, inflection_type, forms)

    def update_other_lexical_item(
        self,
        lexical_item_id: int,
        *,
        headword: str,
        explanation: str,
        inflection_type: str,
        forms: dict[FormKey, str | None],
    ) -> None:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)
        self.validate_other_inflection_type(inflection_type)

        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"other"})
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

            self.upsert_detail(
                connection,
                "other_details",
                "inflection_type",
                lexical_item_id,
                inflection_type,
            )
            if inflection_type == "none":
                connection.execute("DELETE FROM other_forms WHERE lexical_item_id = ?", (lexical_item_id,))
            elif inflection_type in INFLECTION_FORM_TYPES:
                self.replace_other_forms(connection, lexical_item_id, inflection_type, forms)
            else:
                raise ValidationError(f"invalid inflection_type: {inflection_type}")

    def update_verb_lexical_item(
        self,
        lexical_item_id: int,
        *,
        headword: str,
        explanation: str,
        forms: dict[str, dict[str, Any]],
    ) -> None:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)

        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"verb"})
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

            self.write_verb_forms(connection, lexical_item_id, forms)

    def delete_lexical_item(self, lexical_item_id: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM lexical_items WHERE id = ?", (lexical_item_id,))
            return cursor.rowcount > 0

    def save_lexical_item_base(self, lexical_item_id: int, *, headword: str, explanation: str) -> None:
        headword = clean_required_text(headword, "headword")
        explanation = clean_required_explanation(explanation)
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
        self.validate_gender_availability(gender_availability)
        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"noun"})
            self.upsert_detail(connection, "noun_details", "gender_availability", lexical_item_id, gender_availability)

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
            self.replace_noun_forms(connection, lexical_item_id, str(row["gender_availability"]), forms)

    def save_adjective_details(self, lexical_item_id: int, inflection_type: str) -> None:
        self.validate_adjective_inflection_type(inflection_type)
        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"adjective"})
            self.upsert_detail(connection, "adjective_details", "inflection_type", lexical_item_id, inflection_type)

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
            self.replace_adjective_forms(connection, lexical_item_id, str(row["inflection_type"]), forms)

    def save_other_details(self, lexical_item_id: int, inflection_type: str) -> None:
        self.validate_other_inflection_type(inflection_type)
        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"other"})
            self.upsert_detail(connection, "other_details", "inflection_type", lexical_item_id, inflection_type)

    def save_other_inflections(
        self,
        lexical_item_id: int,
        forms: dict[FormKey, str | None],
    ) -> None:
        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"other"})
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
                self.replace_other_forms(connection, lexical_item_id, inflection_type, forms)
            else:
                raise ValidationError(f"invalid inflection_type: {inflection_type}")

    def save_verb_forms(self, lexical_item_id: int, forms: dict[str, dict[str, Any]]) -> None:
        with self.transaction() as connection:
            self.require_lexical_item_type(connection, lexical_item_id, {"verb"})
            self.write_verb_forms(connection, lexical_item_id, forms)

    def list_lexical_item_ids(self) -> list[int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM lexical_items
                ORDER BY id
                """
            ).fetchall()
        return [int(row["id"]) for row in rows]

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
                  AND (
                    headword COLLATE NOCASE LIKE ?
                    OR explanation COLLATE NOCASE LIKE ?
                  )
                ORDER BY
                    CASE
                        WHEN headword COLLATE NOCASE = ? THEN 0
                        WHEN headword COLLATE NOCASE LIKE ? THEN 1
                        WHEN headword COLLATE NOCASE LIKE ? THEN 2
                        WHEN explanation COLLATE NOCASE = ? THEN 3
                        WHEN explanation COLLATE NOCASE LIKE ? THEN 4
                        WHEN explanation COLLATE NOCASE LIKE ? THEN 5
                        ELSE 6
                    END,
                    headword COLLATE NOCASE
                LIMIT ?
                """,
                (
                    cleaned,
                    lexical_item_type,
                    contains_pattern,
                    contains_pattern,
                    cleaned,
                    prefix_pattern,
                    contains_pattern,
                    cleaned,
                    prefix_pattern,
                    contains_pattern,
                    limit,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_explanations_for_headword(self, headword: str, lexical_item_type: str) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT explanation
                FROM lexical_items
                WHERE headword = ? COLLATE NOCASE AND lexical_item_type = ?
                ORDER BY id
                """,
                (headword, lexical_item_type),
            ).fetchall()
        return [str(row["explanation"]) for row in rows]

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
        return row_to_dict(row)

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
                data["noun"] = self.load_noun(connection, lexical_item_id)
            elif lexical_item_type == "adjective":
                data["adjective"] = self.load_adjective(connection, lexical_item_id)
            elif lexical_item_type == "other":
                data["other"] = self.load_other(connection, lexical_item_id)
            elif lexical_item_type == "verb":
                data["verb"] = self.load_verb(connection, lexical_item_id)
            return data
