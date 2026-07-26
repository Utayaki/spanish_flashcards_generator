from __future__ import annotations

import sqlite3
from pathlib import Path

from fsrs import Card

from drills.db.migrations import table_exists
from drills.errors import DatabaseError
from drills.fsrs.cards import init_fsrs_cards, seed_default_scheduler
from drills.fsrs.scheduler import card_snapshot, default_scheduler

FSRS_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "fsrs_schema.sql"


def ensure_fsrs_schema(connection: sqlite3.Connection) -> None:
    if not FSRS_SCHEMA_PATH.is_file():
        raise DatabaseError(f"fsrs schema not found: {FSRS_SCHEMA_PATH}")
    if table_exists(connection, "fsrs_scheduler"):
        return
    connection.executescript(FSRS_SCHEMA_PATH.read_text(encoding="utf-8"))


def initialize_fsrs_snapshot(connection: sqlite3.Connection) -> int:
    ensure_fsrs_schema(connection)
    seed_default_scheduler(connection)
    return init_fsrs_cards(connection)


def migrate_snapshot_if_needed(snapshot_path: Path) -> None:
    if not snapshot_path.is_file():
        raise DatabaseError(f"snapshot file not found: {snapshot_path}")
    with sqlite3.connect(snapshot_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if table_exists(connection, "fsrs_scheduler"):
            return
        connection.executescript(FSRS_SCHEMA_PATH.read_text(encoding="utf-8"))
        seed_default_scheduler(connection)
        init_fsrs_cards(connection)
        connection.commit()
