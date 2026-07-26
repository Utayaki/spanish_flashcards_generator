from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from word_bank.word_types.verb_forms import VERB_FORM_CODE_BY_ID

INFLECTION_TABLES = (
    "noun_details",
    "noun_forms",
    "adjective_details",
    "adjective_forms",
    "other_details",
    "other_forms",
    "verb_form_definitions",
    "verb_forms",
)


class WordFormRecord(TypedDict):
    headword: str
    explanation: str
    lexical_item_type: str
    word_form: str
    form_descriptor: str
    lexical_item_id: int


def snapshot_has_inflection_tables(snapshot_path: Path) -> bool:
    if not snapshot_path.is_file():
        return False
    with sqlite3.connect(snapshot_path) as connection:
        for table in INFLECTION_TABLES:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
            if row is None or int(row[0]) == 0:
                return False
    return True


def _number_gender_descriptor(number: str, gender: str | None) -> str:
    if gender is None:
        return number
    return f"{number}/{gender}"


def _append_number_gender_forms(
    records: list[WordFormRecord],
    *,
    lexical_item_id: int,
    headword: str,
    explanation: str,
    lexical_item_type: str,
    connection: sqlite3.Connection,
    table: str,
) -> None:
    rows = connection.execute(
        f"""
        SELECT grammatical_number, grammatical_gender, form
        FROM {table}
        WHERE lexical_item_id = ?
        ORDER BY grammatical_number, grammatical_gender
        """,
        (lexical_item_id,),
    ).fetchall()
    seen: set[tuple[int, str, str]] = set()
    for row in rows:
        form = str(row["form"]).strip()
        if not form:
            continue
        descriptor = _number_gender_descriptor(
            str(row["grammatical_number"]),
            row["grammatical_gender"],
        )
        key = (lexical_item_id, form, descriptor)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "headword": headword,
                "explanation": explanation,
                "lexical_item_type": lexical_item_type,
                "word_form": form,
                "form_descriptor": descriptor,
                "lexical_item_id": lexical_item_id,
            }
        )


def aggregate_word_forms(connection: sqlite3.Connection) -> list[WordFormRecord]:
    records: list[WordFormRecord] = []
    lexical_items = connection.execute(
        """
        SELECT id, headword, explanation, lexical_item_type
        FROM lexical_items
        ORDER BY headword COLLATE NOCASE, id
        """
    ).fetchall()

    for item in lexical_items:
        lexical_item_id = int(item["id"])
        headword = str(item["headword"])
        explanation = str(item["explanation"])
        lexical_item_type = str(item["lexical_item_type"])

        if lexical_item_type == "noun":
            _append_number_gender_forms(
                records,
                lexical_item_id=lexical_item_id,
                headword=headword,
                explanation=explanation,
                lexical_item_type=lexical_item_type,
                connection=connection,
                table="noun_forms",
            )
        elif lexical_item_type == "adjective":
            _append_number_gender_forms(
                records,
                lexical_item_id=lexical_item_id,
                headword=headword,
                explanation=explanation,
                lexical_item_type=lexical_item_type,
                connection=connection,
                table="adjective_forms",
            )
        elif lexical_item_type == "other":
            detail = connection.execute(
                """
                SELECT inflection_type
                FROM other_details
                WHERE lexical_item_id = ?
                """,
                (lexical_item_id,),
            ).fetchone()
            if detail is None:
                continue
            inflection_type = str(detail["inflection_type"])
            if inflection_type == "none":
                records.append(
                    {
                        "headword": headword,
                        "explanation": explanation,
                        "lexical_item_type": lexical_item_type,
                        "word_form": headword,
                        "form_descriptor": "headword",
                        "lexical_item_id": lexical_item_id,
                    }
                )
            else:
                _append_number_gender_forms(
                    records,
                    lexical_item_id=lexical_item_id,
                    headword=headword,
                    explanation=explanation,
                    lexical_item_type=lexical_item_type,
                    connection=connection,
                    table="other_forms",
                )
        elif lexical_item_type == "verb":
            rows = connection.execute(
                """
                SELECT verb_form_id, form
                FROM verb_forms
                WHERE lexical_item_id = ?
                ORDER BY verb_form_id
                """,
                (lexical_item_id,),
            ).fetchall()
            seen: set[tuple[int, str, str]] = set()
            for row in rows:
                form = str(row["form"]).strip()
                if not form:
                    continue
                verb_form_id = int(row["verb_form_id"])
                descriptor = VERB_FORM_CODE_BY_ID.get(verb_form_id, f"verb_form_{verb_form_id}")
                key = (lexical_item_id, form, descriptor)
                if key in seen:
                    continue
                seen.add(key)
                records.append(
                    {
                        "headword": headword,
                        "explanation": explanation,
                        "lexical_item_type": lexical_item_type,
                        "word_form": form,
                        "form_descriptor": descriptor,
                        "lexical_item_id": lexical_item_id,
                    }
                )

    return records


def aggregate_word_forms_from_path(snapshot_path: Path) -> list[WordFormRecord]:
    with sqlite3.connect(snapshot_path) as connection:
        connection.row_factory = sqlite3.Row
        return aggregate_word_forms(connection)
