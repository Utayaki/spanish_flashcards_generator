from __future__ import annotations

import sqlite3
from pathlib import Path

from drills.db.migrations import table_exists
from drills.errors import DatabaseError

OLD_SCHEMA_MESSAGE = (
    "This collection uses an old schema. Delete it and create a new collection."
)


def _table_has_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row[1]) == column_name for row in rows)


def validate_collection_schema(connection: sqlite3.Connection) -> None:
    if table_exists(connection, "noun_details"):
        raise DatabaseError(OLD_SCHEMA_MESSAGE)
    if not table_exists(connection, "spanish_to_english_fsrs_cards"):
        raise DatabaseError(OLD_SCHEMA_MESSAGE)
    if table_exists(connection, "fsrs_cards") and _table_has_column(
        connection,
        "fsrs_cards",
        "lexical_item_id",
    ):
        raise DatabaseError(OLD_SCHEMA_MESSAGE)


def migrate_snapshot_if_needed(snapshot_path: Path) -> None:
    if not snapshot_path.is_file():
        raise DatabaseError(f"snapshot file not found: {snapshot_path}")
    with sqlite3.connect(snapshot_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        validate_collection_schema(connection)
