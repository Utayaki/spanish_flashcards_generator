from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "collection_schema.sql"

LEXICAL_CONTENT_TABLES = {
    "spanish_to_english": "spanish_to_english_fsrs_cards",
    "english_to_spanish": "english_to_spanish_fsrs_cards",
    "noun_gender": "noun_gender_fsrs_cards",
    "adjective_inflection_type": "adjective_inflection_type_fsrs_cards",
}

LEGACY_RENAME_MAP = {
    "fsrs_review_logs": "_legacy_fsrs_review_logs",
    "fsrs_scheduler": "_legacy_fsrs_scheduler",
    "fsrs_scheduler_learning_steps": "_legacy_fsrs_scheduler_learning_steps",
    "fsrs_scheduler_relearning_steps": "_legacy_fsrs_scheduler_relearning_steps",
}


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _is_new_schema(connection: sqlite3.Connection) -> bool:
    return _table_exists(connection, "study_cards")


def _is_legacy_schema(connection: sqlite3.Connection) -> bool:
    return _table_exists(connection, "fsrs_cards") or _table_exists(connection, "lexical_items")


def _rename_conflicting_legacy_tables(connection: sqlite3.Connection) -> None:
    for old_name, new_name in LEGACY_RENAME_MAP.items():
        if _table_exists(connection, old_name) and not _table_exists(connection, new_name):
            connection.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")


def _create_new_tables(connection: sqlite3.Connection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    connection.executescript(schema_sql)


def _migrate_scheduler(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT id FROM fsrs_scheduler WHERE id = 1").fetchone() is not None:
        return

    source = None
    if _table_exists(connection, "_legacy_fsrs_scheduler"):
        source = "_legacy_fsrs_scheduler"
    elif _table_exists(connection, "inflection_fsrs_scheduler"):
        source = "inflection_fsrs_scheduler"
    if source is None:
        return

    row = connection.execute(f"SELECT * FROM {source} WHERE id = 1").fetchone()
    if row is None:
        return

    columns = [
        "desired_retention",
        "enable_fuzzing",
        "maximum_interval",
        *[f"param_{index}" for index in range(21)],
    ]
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"""
        INSERT INTO fsrs_scheduler (id, {", ".join(columns)})
        VALUES (1, {placeholders})
        """,
        tuple(row[column] for column in columns),
    )

    step_sources = [
        ("fsrs_scheduler_learning_steps", "_legacy_fsrs_scheduler_learning_steps"),
        ("fsrs_scheduler_relearning_steps", "_legacy_fsrs_scheduler_relearning_steps"),
        ("fsrs_scheduler_learning_steps", "inflection_fsrs_scheduler_learning_steps"),
        ("fsrs_scheduler_relearning_steps", "inflection_fsrs_scheduler_relearning_steps"),
    ]
    copied: set[str] = set()
    for new_table, old_table in step_sources:
        if old_table in copied or not _table_exists(connection, old_table):
            continue
        if connection.execute(f"SELECT COUNT(*) AS c FROM {new_table}").fetchone()["c"]:
            copied.add(old_table)
            continue
        rows = connection.execute(
            f"SELECT step_index, duration_seconds FROM {old_table} ORDER BY step_index"
        ).fetchall()
        if rows:
            connection.executemany(
                f"INSERT INTO {new_table} (step_index, duration_seconds) VALUES (?, ?)",
                [(row["step_index"], row["duration_seconds"]) for row in rows],
            )
            copied.add(old_table)


def _insert_lexical_study_cards(connection: sqlite3.Connection) -> dict[tuple[str, int], int]:
    mapping: dict[tuple[str, int], int] = {}
    for card_kind, table_name in LEXICAL_CONTENT_TABLES.items():
        if not _table_exists(connection, table_name):
            continue
        rows = connection.execute(
            f"SELECT id, front, back FROM {table_name} ORDER BY id"
        ).fetchall()
        for row in rows:
            old_id = int(row["id"])
            cursor = connection.execute(
                """
                INSERT INTO study_cards (card_kind, front, back, created_at)
                VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (card_kind, row["front"], row["back"]),
            )
            mapping[(card_kind, old_id)] = int(cursor.lastrowid)
    return mapping


def _insert_inflection_study_cards(connection: sqlite3.Connection) -> dict[int, int]:
    mapping: dict[int, int] = {}
    if not _table_exists(connection, "inflection_word_forms"):
        return mapping
    rows = connection.execute(
        """
        SELECT id, headword, explanation, lexical_item_type, word_form, form_descriptor, created_at
        FROM inflection_word_forms
        ORDER BY id
        """
    ).fetchall()
    for row in rows:
        old_id = int(row["id"])
        cursor = connection.execute(
            """
            INSERT INTO study_cards (
                card_kind,
                headword,
                explanation,
                lexical_item_type,
                word_form,
                form_descriptor,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inflection",
                row["headword"],
                row["explanation"],
                row["lexical_item_type"],
                row["word_form"],
                row["form_descriptor"],
                row["created_at"],
            ),
        )
        mapping[old_id] = int(cursor.lastrowid)
    return mapping


def _migrate_fsrs_schedules(
    connection: sqlite3.Connection,
    lexical_map: dict[tuple[str, int], int],
    inflection_map: dict[int, int],
) -> None:
    if _table_exists(connection, "fsrs_cards"):
        rows = connection.execute(
            "SELECT * FROM fsrs_cards ORDER BY direction, study_card_id"
        ).fetchall()
        for row in rows:
            direction = str(row["direction"])
            old_id = int(row["study_card_id"])
            new_id = lexical_map.get((direction, old_id))
            if new_id is None:
                continue
            connection.execute(
                """
                INSERT INTO fsrs_schedules (
                    study_card_id,
                    due_at,
                    fsrs_state,
                    step,
                    stability,
                    difficulty,
                    first_reviewed_at,
                    last_reviewed_at,
                    is_suspended,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    row["due_at"],
                    row["fsrs_state"],
                    row["step"],
                    row["stability"],
                    row["difficulty"],
                    row["first_reviewed_at"],
                    row["last_reviewed_at"],
                    row["is_suspended"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )

    if _table_exists(connection, "inflection_fsrs_cards"):
        rows = connection.execute(
            "SELECT * FROM inflection_fsrs_cards ORDER BY word_form_id"
        ).fetchall()
        for row in rows:
            old_id = int(row["word_form_id"])
            new_id = inflection_map.get(old_id)
            if new_id is None:
                continue
            connection.execute(
                """
                INSERT INTO fsrs_schedules (
                    study_card_id,
                    due_at,
                    fsrs_state,
                    step,
                    stability,
                    difficulty,
                    first_reviewed_at,
                    last_reviewed_at,
                    is_suspended,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    row["due_at"],
                    row["fsrs_state"],
                    row["step"],
                    row["stability"],
                    row["difficulty"],
                    row["first_reviewed_at"],
                    row["last_reviewed_at"],
                    row["is_suspended"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )


def _migrate_review_logs(
    connection: sqlite3.Connection,
    lexical_map: dict[tuple[str, int], int],
    inflection_map: dict[int, int],
) -> None:
    if _table_exists(connection, "_legacy_fsrs_review_logs"):
        rows = connection.execute(
            """
            SELECT direction, study_card_id, rating, rating_label, reviewed_at,
                   review_duration_ms, created_at
            FROM _legacy_fsrs_review_logs
            ORDER BY id
            """
        ).fetchall()
        for row in rows:
            direction = str(row["direction"])
            old_id = int(row["study_card_id"])
            new_id = lexical_map.get((direction, old_id))
            if new_id is None:
                continue
            connection.execute(
                """
                INSERT INTO fsrs_review_logs (
                    study_card_id,
                    rating,
                    rating_label,
                    reviewed_at,
                    review_duration_ms,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    row["rating"],
                    row["rating_label"],
                    row["reviewed_at"],
                    row["review_duration_ms"],
                    row["created_at"],
                ),
            )

    if _table_exists(connection, "inflection_fsrs_review_logs"):
        rows = connection.execute(
            """
            SELECT word_form_id, rating, rating_label, reviewed_at,
                   review_duration_ms, created_at
            FROM inflection_fsrs_review_logs
            ORDER BY id
            """
        ).fetchall()
        for row in rows:
            old_id = int(row["word_form_id"])
            new_id = inflection_map.get(old_id)
            if new_id is None:
                continue
            connection.execute(
                """
                INSERT INTO fsrs_review_logs (
                    study_card_id,
                    rating,
                    rating_label,
                    reviewed_at,
                    review_duration_ms,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    row["rating"],
                    row["rating_label"],
                    row["reviewed_at"],
                    row["review_duration_ms"],
                    row["created_at"],
                ),
            )


def _drop_legacy_tables(connection: sqlite3.Connection) -> None:
    legacy_tables = [
        "_legacy_fsrs_review_logs",
        "fsrs_card_snapshots",
        "inflection_fsrs_card_snapshots",
        "fsrs_cards",
        "inflection_fsrs_cards",
        "inflection_fsrs_review_logs",
        "spanish_to_english_fsrs_cards",
        "english_to_spanish_fsrs_cards",
        "noun_gender_fsrs_cards",
        "adjective_inflection_type_fsrs_cards",
        "inflection_word_forms",
        "inflection_fsrs_scheduler_learning_steps",
        "inflection_fsrs_scheduler_relearning_steps",
        "inflection_fsrs_scheduler",
        "_legacy_fsrs_scheduler_learning_steps",
        "_legacy_fsrs_scheduler_relearning_steps",
        "_legacy_fsrs_scheduler",
        "verb_forms",
        "verb_form_definitions",
        "other_forms",
        "other_details",
        "adjective_forms",
        "adjective_details",
        "noun_forms",
        "noun_details",
        "lexical_items",
        "inflection_drill_examples",
    ]
    for table_name in legacy_tables:
        if _table_exists(connection, table_name):
            connection.execute(f"DROP TABLE {table_name}")


def migrate_legacy_collection(connection: sqlite3.Connection) -> bool:
    if _is_new_schema(connection):
        return False
    if not _is_legacy_schema(connection):
        return False

    connection.execute("PRAGMA foreign_keys = OFF")
    _rename_conflicting_legacy_tables(connection)
    _create_new_tables(connection)
    _migrate_scheduler(connection)
    lexical_map = _insert_lexical_study_cards(connection)
    inflection_map = _insert_inflection_study_cards(connection)
    _migrate_fsrs_schedules(connection, lexical_map, inflection_map)
    _migrate_review_logs(connection, lexical_map, inflection_map)
    _drop_legacy_tables(connection)
    connection.execute("PRAGMA foreign_keys = ON")
    return True


def ensure_cards_only_schema(connection: sqlite3.Connection) -> None:
    migrate_legacy_collection(connection)


# Backward-compatible alias for collection_snapshot imports
ensure_lexical_fsrs_card_types = ensure_cards_only_schema
