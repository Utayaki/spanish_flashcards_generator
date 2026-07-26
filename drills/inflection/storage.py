from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from drills.inflection.word_forms import (
    WordFormRecord,
    aggregate_word_forms,
    snapshot_has_inflection_tables,
)

EXAMPLES_PER_FORM = 5
WordFormKey = tuple[int, str, str]


def word_form_key(record: dict[str, Any]) -> WordFormKey:
    return (
        int(record["lexical_item_id"]),
        str(record["word_form"]),
        str(record["form_descriptor"]),
    )


def _has_examples_table(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM sqlite_master
        WHERE type = 'table' AND name = 'inflection_drill_examples'
        """
    ).fetchone()
    return row is not None and int(row[0]) > 0


def list_complete_form_keys(connection: sqlite3.Connection) -> set[WordFormKey]:
    if not _has_examples_table(connection):
        return set()
    rows = connection.execute(
        """
        SELECT lexical_item_id, word_form, form_descriptor, COUNT(*) AS example_count
        FROM inflection_drill_examples
        GROUP BY lexical_item_id, word_form, form_descriptor
        HAVING example_count >= ?
        """,
        (EXAMPLES_PER_FORM,),
    ).fetchall()
    return {
        (int(row["lexical_item_id"]), str(row["word_form"]), str(row["form_descriptor"]))
        for row in rows
    }


def is_form_complete(connection: sqlite3.Connection, record: dict[str, Any]) -> bool:
    return word_form_key(record) in list_complete_form_keys(connection)


def pending_word_forms(connection: sqlite3.Connection) -> list[WordFormRecord]:
    complete_keys = list_complete_form_keys(connection)
    return [
        record
        for record in aggregate_word_forms(connection)
        if word_form_key(record) not in complete_keys
    ]


def clear_form_examples(connection: sqlite3.Connection, record: dict[str, Any]) -> None:
    key = word_form_key(record)
    connection.execute(
        """
        DELETE FROM inflection_drill_examples
        WHERE lexical_item_id = ? AND word_form = ? AND form_descriptor = ?
        """,
        key,
    )


def save_examples(
    connection: sqlite3.Connection,
    *,
    record: dict[str, Any],
    examples: list[str],
) -> None:
    for example in examples[:EXAMPLES_PER_FORM]:
        connection.execute(
            """
            INSERT INTO inflection_drill_examples (
                lexical_item_id,
                headword,
                explanation,
                lexical_item_type,
                word_form,
                form_descriptor,
                example_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["lexical_item_id"],
                record["headword"],
                record["explanation"],
                record["lexical_item_type"],
                record["word_form"],
                record["form_descriptor"],
                example,
            ),
        )


def _count_examples(connection: sqlite3.Connection) -> int:
    if not _has_examples_table(connection):
        return 0
    row = connection.execute("SELECT COUNT(*) FROM inflection_drill_examples").fetchone()
    return int(row[0]) if row is not None else 0


def _count_complete_forms(connection: sqlite3.Connection) -> int:
    if not _has_examples_table(connection):
        return 0
    row = connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT 1
            FROM inflection_drill_examples
            GROUP BY lexical_item_id, word_form, form_descriptor
            HAVING COUNT(*) >= ?
        )
        """,
        (EXAMPLES_PER_FORM,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _count_pending_forms(connection: sqlite3.Connection) -> int:
    return len(pending_word_forms(connection))


def get_inflection_drill_status(snapshot_path: Path) -> dict[str, Any]:
    if not snapshot_has_inflection_tables(snapshot_path):
        return {
            "has_inflection_data": False,
            "has_drills": False,
            "word_form_count": 0,
            "example_count": 0,
            "pending_word_form_count": 0,
            "is_complete": False,
        }

    with sqlite3.connect(snapshot_path) as connection:
        connection.row_factory = sqlite3.Row
        example_count = _count_examples(connection)
        word_form_count = _count_complete_forms(connection)
        pending_count = _count_pending_forms(connection)

    return {
        "has_inflection_data": True,
        "has_drills": example_count > 0,
        "word_form_count": word_form_count,
        "example_count": example_count,
        "pending_word_form_count": pending_count,
        "is_complete": pending_count == 0,
    }


def count_complete_inflection_forms(snapshot_path: Path) -> int:
    if not snapshot_path.is_file():
        return 0
    with sqlite3.connect(snapshot_path) as connection:
        connection.row_factory = sqlite3.Row
        return _count_complete_forms(connection)
