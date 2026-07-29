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


GENDER_DESCRIPTOR_SUFFIXES = frozenset({"masculine", "feminine"})


def strip_gender_from_descriptor(descriptor: str) -> str:
    if "/" not in descriptor:
        return descriptor
    number, suffix = descriptor.split("/", 1)
    if suffix in GENDER_DESCRIPTOR_SUFFIXES:
        return number
    return descriptor


def lexical_item_shows_gender_in_descriptor(
    connection: sqlite3.Connection,
    lexical_item_id: int,
) -> bool:
    row = connection.execute(
        "SELECT lexical_item_type FROM lexical_items WHERE id = ?",
        (lexical_item_id,),
    ).fetchone()
    if row is None:
        return True

    lexical_item_type = str(row["lexical_item_type"])
    if lexical_item_type == "noun":
        detail = connection.execute(
            """
            SELECT gender_availability
            FROM noun_details
            WHERE lexical_item_id = ?
            """,
            (lexical_item_id,),
        ).fetchone()
        if detail is None:
            return True
        return str(detail["gender_availability"]) == "both"

    if lexical_item_type == "adjective":
        detail = connection.execute(
            """
            SELECT inflection_type
            FROM adjective_details
            WHERE lexical_item_id = ?
            """,
            (lexical_item_id,),
        ).fetchone()
        if detail is None:
            return True
        return str(detail["inflection_type"]) == "gender_plurality"

    if lexical_item_type == "other":
        detail = connection.execute(
            """
            SELECT inflection_type
            FROM other_details
            WHERE lexical_item_id = ?
            """,
            (lexical_item_id,),
        ).fetchone()
        if detail is None:
            return False
        return str(detail["inflection_type"]) == "gender_plurality"

    return True


def display_form_descriptor(
    connection: sqlite3.Connection,
    lexical_item_id: int,
    form_descriptor: str,
) -> str:
    if lexical_item_shows_gender_in_descriptor(connection, lexical_item_id):
        return form_descriptor
    return strip_gender_from_descriptor(form_descriptor)


def _number_gender_descriptor(
    number: str,
    gender: str | None,
    *,
    include_gender: bool,
) -> str:
    if gender is None or not include_gender:
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
    include_gender: bool,
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
            include_gender=include_gender,
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
            noun_detail = connection.execute(
                """
                SELECT gender_availability
                FROM noun_details
                WHERE lexical_item_id = ?
                """,
                (lexical_item_id,),
            ).fetchone()
            include_gender = (
                noun_detail is not None
                and str(noun_detail["gender_availability"]) == "both"
            )
            _append_number_gender_forms(
                records,
                lexical_item_id=lexical_item_id,
                headword=headword,
                explanation=explanation,
                lexical_item_type=lexical_item_type,
                connection=connection,
                table="noun_forms",
                include_gender=include_gender,
            )
        elif lexical_item_type == "adjective":
            adjective_detail = connection.execute(
                """
                SELECT inflection_type
                FROM adjective_details
                WHERE lexical_item_id = ?
                """,
                (lexical_item_id,),
            ).fetchone()
            include_gender = (
                adjective_detail is not None
                and str(adjective_detail["inflection_type"]) == "gender_plurality"
            )
            _append_number_gender_forms(
                records,
                lexical_item_id=lexical_item_id,
                headword=headword,
                explanation=explanation,
                lexical_item_type=lexical_item_type,
                connection=connection,
                table="adjective_forms",
                include_gender=include_gender,
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
                continue
            include_gender = inflection_type == "gender_plurality"
            _append_number_gender_forms(
                records,
                lexical_item_id=lexical_item_id,
                headword=headword,
                explanation=explanation,
                lexical_item_type=lexical_item_type,
                connection=connection,
                table="other_forms",
                include_gender=include_gender,
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
