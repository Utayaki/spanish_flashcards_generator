from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from drills.inflection.fsrs_cards import ensure_inflection_fsrs_card
from drills.inflection.cloze import EXAMPLES_PER_FORM
from drills.fsrs.scheduler import utc_iso
from drills.inflection.word_forms import (
    WordFormRecord,
    aggregate_word_forms,
    snapshot_has_inflection_tables,
)

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


def _has_examples_table(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM sqlite_master
        WHERE type = 'table' AND name = 'inflection_drill_examples'
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


def count_examples_for_record(connection: sqlite3.Connection, record: dict[str, Any]) -> int:
    if not _has_word_forms_table(connection) or not _has_examples_table(connection):
        return 0
    key = word_form_key(record)
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM inflection_drill_examples e
        JOIN inflection_word_forms wf ON wf.id = e.word_form_id
        WHERE wf.lexical_item_id = ? AND wf.word_form = ? AND wf.form_descriptor = ?
        """,
        key,
    ).fetchone()
    return int(row["count"]) if row is not None else 0


def list_complete_form_keys(connection: sqlite3.Connection) -> set[WordFormKey]:
    if not _has_word_forms_table(connection) or not _has_examples_table(connection):
        return set()
    rows = connection.execute(
        """
        SELECT wf.lexical_item_id, wf.word_form, wf.form_descriptor, COUNT(*) AS example_count
        FROM inflection_drill_examples e
        JOIN inflection_word_forms wf ON wf.id = e.word_form_id
        GROUP BY wf.lexical_item_id, wf.word_form, wf.form_descriptor
        HAVING example_count >= ?
        """,
        (EXAMPLES_PER_FORM,),
    ).fetchall()
    return {
        (int(row["lexical_item_id"]), str(row["word_form"]), str(row["form_descriptor"]))
        for row in rows
    }


def is_form_complete(connection: sqlite3.Connection, record: dict[str, Any]) -> bool:
    return count_examples_for_record(connection, record) >= EXAMPLES_PER_FORM


def pending_word_forms(connection: sqlite3.Connection) -> list[WordFormRecord]:
    return [
        record
        for record in aggregate_word_forms(connection)
        if count_examples_for_record(connection, record) < EXAMPLES_PER_FORM
    ]


def _example_table_columns(connection: sqlite3.Connection) -> set[str]:
    if not _has_examples_table(connection):
        return set()
    return {
        row[1]
        for row in connection.execute("PRAGMA table_info(inflection_drill_examples)")
    }


def ensure_source_sentence_column(connection: sqlite3.Connection) -> None:
    if not _has_examples_table(connection):
        return
    columns = _example_table_columns(connection)
    if "source_sentence" not in columns:
        connection.execute(
            "ALTER TABLE inflection_drill_examples ADD COLUMN source_sentence TEXT"
        )


def ensure_last_shown_at_column(connection: sqlite3.Connection) -> None:
    if not _has_examples_table(connection):
        return
    columns = _example_table_columns(connection)
    if "last_shown_at" not in columns:
        connection.execute(
            "ALTER TABLE inflection_drill_examples ADD COLUMN last_shown_at TEXT"
        )


def ensure_example_columns(connection: sqlite3.Connection) -> None:
    ensure_source_sentence_column(connection)
    ensure_last_shown_at_column(connection)


def list_used_source_sentences(connection: sqlite3.Connection) -> set[str]:
    if not _has_examples_table(connection):
        return set()
    ensure_source_sentence_column(connection)
    rows = connection.execute(
        """
        SELECT DISTINCT source_sentence
        FROM inflection_drill_examples
        WHERE source_sentence IS NOT NULL
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def select_and_mark_example(
    connection: sqlite3.Connection,
    word_form_id: int,
) -> tuple[int, str] | None:
    ensure_last_shown_at_column(connection)
    row = connection.execute(
        """
        SELECT id, example_text
        FROM inflection_drill_examples
        WHERE word_form_id = ?
        ORDER BY (last_shown_at IS NULL) DESC, last_shown_at ASC, RANDOM()
        LIMIT 1
        """,
        (word_form_id,),
    ).fetchone()
    if row is None:
        return None

    example_id = int(row[0])
    example_text = str(row[1])
    shown_at = utc_iso()
    connection.execute(
        """
        UPDATE inflection_drill_examples
        SET last_shown_at = ?
        WHERE id = ?
        """,
        (shown_at, example_id),
    )
    return example_id, example_text


def append_examples(
    connection: sqlite3.Connection,
    *,
    record: dict[str, Any],
    examples: list[tuple[str, str]],
) -> tuple[int, list[str]]:
    word_form_id = upsert_word_form(connection, record)
    ensure_example_columns(connection)
    current_count = connection.execute(
        "SELECT COUNT(*) AS count FROM inflection_drill_examples WHERE word_form_id = ?",
        (word_form_id,),
    ).fetchone()
    existing = int(current_count["count"]) if current_count is not None else 0
    slots = max(0, EXAMPLES_PER_FORM - existing)
    existing_clozes = {
        str(row[0])
        for row in connection.execute(
            """
            SELECT example_text
            FROM inflection_drill_examples
            WHERE word_form_id = ?
            """,
            (word_form_id,),
        ).fetchall()
    }
    used_sentences = list_used_source_sentences(connection)
    inserted = 0
    saved_sentences: list[str] = []
    for cloze, source_sentence in examples:
        if inserted >= slots:
            break
        if source_sentence in used_sentences:
            continue
        if cloze in existing_clozes:
            continue
        connection.execute(
            """
            INSERT INTO inflection_drill_examples (word_form_id, example_text, source_sentence)
            VALUES (?, ?, ?)
            """,
            (word_form_id, cloze, source_sentence),
        )
        existing_clozes.add(cloze)
        used_sentences.add(source_sentence)
        saved_sentences.append(source_sentence)
        inserted += 1

    final_count = existing + inserted
    if final_count >= EXAMPLES_PER_FORM:
        ensure_inflection_fsrs_card(connection, word_form_id)
    return inserted, saved_sentences


def _count_examples(connection: sqlite3.Connection) -> int:
    if not _has_examples_table(connection):
        return 0
    row = connection.execute("SELECT COUNT(*) FROM inflection_drill_examples").fetchone()
    return int(row[0]) if row is not None else 0


def _count_complete_forms(connection: sqlite3.Connection) -> int:
    return len(list_complete_form_keys(connection))


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
        if not _has_word_forms_table(connection):
            return {
                "has_inflection_data": False,
                "has_drills": False,
                "word_form_count": 0,
                "example_count": 0,
                "pending_word_form_count": 0,
                "is_complete": False,
            }
        example_count = _count_examples(connection)
        word_form_count = _count_complete_forms(connection)
        pending_count = _count_pending_forms(connection)

    return {
        "has_inflection_data": True,
        "has_drills": word_form_count > 0,
        "example_count": example_count,
        "word_form_count": word_form_count,
        "pending_word_form_count": pending_count,
        "is_complete": pending_count == 0,
    }


def count_complete_inflection_forms(snapshot_path: Path) -> int:
    if not snapshot_path.is_file():
        return 0
    with sqlite3.connect(snapshot_path) as connection:
        connection.row_factory = sqlite3.Row
        return _count_complete_forms(connection)
