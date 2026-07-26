from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from drills.inflection.word_forms import snapshot_has_inflection_tables


def count_inflection_drill_word_forms(snapshot_path: Path) -> int:
    if not snapshot_path.is_file():
        return 0
    with sqlite3.connect(snapshot_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM sqlite_master
            WHERE type = 'table' AND name = 'inflection_drill_word_forms'
            """
        ).fetchone()
        if row is None or int(row[0]) == 0:
            return 0
        count_row = connection.execute(
            "SELECT COUNT(*) FROM inflection_drill_word_forms"
        ).fetchone()
        return int(count_row[0]) if count_row is not None else 0


def count_inflection_drill_examples(snapshot_path: Path) -> int:
    if not snapshot_path.is_file():
        return 0
    with sqlite3.connect(snapshot_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM sqlite_master
            WHERE type = 'table' AND name = 'inflection_drill_examples'
            """
        ).fetchone()
        if row is None or int(row[0]) == 0:
            return 0
        count_row = connection.execute(
            "SELECT COUNT(*) FROM inflection_drill_examples"
        ).fetchone()
        return int(count_row[0]) if count_row is not None else 0


def get_inflection_drill_status(snapshot_path: Path) -> dict[str, Any]:
    if not snapshot_has_inflection_tables(snapshot_path):
        return {
            "has_inflection_data": False,
            "has_drills": False,
            "word_form_count": 0,
            "example_count": 0,
            "generated_at": None,
            "model_name": None,
        }

    with sqlite3.connect(snapshot_path) as connection:
        connection.row_factory = sqlite3.Row
        meta_row = connection.execute(
            """
            SELECT generated_at, total_word_forms, model_name
            FROM inflection_drill_meta
            WHERE id = 1
            """
        ).fetchone()
        word_form_count = connection.execute(
            "SELECT COUNT(*) FROM inflection_drill_word_forms"
        ).fetchone()
        example_count = connection.execute(
            "SELECT COUNT(*) FROM inflection_drill_examples"
        ).fetchone()

    word_forms = int(word_form_count[0]) if word_form_count is not None else 0
    examples = int(example_count[0]) if example_count is not None else 0
    return {
        "has_inflection_data": True,
        "has_drills": word_forms > 0 and examples > 0,
        "word_form_count": word_forms,
        "example_count": examples,
        "generated_at": meta_row["generated_at"] if meta_row else None,
        "model_name": meta_row["model_name"] if meta_row else None,
    }


def clear_inflection_drills(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM inflection_drill_examples")
    connection.execute("DELETE FROM inflection_drill_word_forms")
    connection.execute("DELETE FROM inflection_drill_meta")
    connection.execute(
        """
        INSERT INTO inflection_drill_meta (id, generated_at, total_word_forms, model_name)
        VALUES (1, NULL, 0, NULL)
        ON CONFLICT(id) DO UPDATE SET
            generated_at = NULL,
            total_word_forms = 0,
            model_name = NULL
        """
    )


def save_word_form_with_examples(
    connection: sqlite3.Connection,
    *,
    record: dict[str, Any],
    examples: list[str],
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO inflection_drill_word_forms (
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
    word_form_id = int(cursor.lastrowid)
    for index, example in enumerate(examples[:5], start=1):
        connection.execute(
            """
            INSERT INTO inflection_drill_examples (
                word_form_id,
                example_index,
                example_text
            )
            VALUES (?, ?, ?)
            """,
            (word_form_id, index, example),
        )
    return word_form_id


def finalize_inflection_drills(
    connection: sqlite3.Connection,
    *,
    total_word_forms: int,
    model_name: str,
) -> None:
    connection.execute(
        """
        INSERT INTO inflection_drill_meta (id, generated_at, total_word_forms, model_name)
        VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            generated_at = excluded.generated_at,
            total_word_forms = excluded.total_word_forms,
            model_name = excluded.model_name
        """,
        (total_word_forms, model_name),
    )
