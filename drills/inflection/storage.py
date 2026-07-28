from __future__ import annotations

import sqlite3
from typing import Any

from drills.inflection.fsrs_cards import ensure_inflection_fsrs_card
from drills.inflection.word_forms import aggregate_word_forms

WordFormKey = tuple[int, str, str]


def word_form_key(record: dict[str, Any]) -> WordFormKey:
    return (
        int(record["lexical_item_id"]),
        str(record["word_form"]),
        str(record["form_descriptor"]),
    )


def _has_word_forms_table(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM sqlite_master
        WHERE type = 'table' AND name = 'inflection_word_forms'
        """
    ).fetchone()
    return row is not None and int(row[0]) > 0


def upsert_word_form(connection: sqlite3.Connection, record: dict[str, Any]) -> int:
    key = word_form_key(record)
    existing = connection.execute(
        """
        SELECT id
        FROM inflection_word_forms
        WHERE lexical_item_id = ? AND word_form = ? AND form_descriptor = ?
        """,
        key,
    ).fetchone()
    if existing is not None:
        return int(existing["id"])

    cursor = connection.execute(
        """
        INSERT INTO inflection_word_forms (
            lexical_item_id,
            headword,
            explanation,
            lexical_item_type,
            word_form,
            form_descriptor
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            record["lexical_item_id"],
            record["headword"],
            record["explanation"],
            record["lexical_item_type"],
            record["word_form"],
            record["form_descriptor"],
        ),
    )
    return int(cursor.lastrowid)


def seed_inflection_drill_cards(connection: sqlite3.Connection) -> int:
    created = 0
    for record in aggregate_word_forms(connection):
        word_form_id = upsert_word_form(connection, record)
        existing = connection.execute(
            "SELECT word_form_id FROM inflection_fsrs_cards WHERE word_form_id = ?",
            (word_form_id,),
        ).fetchone()
        if existing is None:
            ensure_inflection_fsrs_card(connection, word_form_id)
            created += 1
    return created


def count_word_forms(connection: sqlite3.Connection) -> int:
    if not _has_word_forms_table(connection):
        return 0
    row = connection.execute("SELECT COUNT(*) AS count FROM inflection_word_forms").fetchone()
    return int(row["count"]) if row is not None else 0
