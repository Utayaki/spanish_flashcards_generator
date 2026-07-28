from __future__ import annotations

import sqlite3

from drills.generate_cards import (
    generate_adjective_inflection_type_fsrs_cards,
    generate_noun_gender_fsrs_cards,
)

_DIRECTION_CHECK = """(
    'spanish_to_english',
    'english_to_spanish',
    'noun_gender',
    'adjective_inflection_type'
)"""

_NEW_CARD_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS noun_gender_fsrs_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS adjective_inflection_type_fsrs_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


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


def _direction_check_supports_new_types(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'fsrs_cards'
        """
    ).fetchone()
    if row is None:
        return True
    return "noun_gender" in str(row["sql"] or "")


def _rebuild_fsrs_direction_tables(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = OFF")

    connection.execute("DROP TABLE IF EXISTS _migration_fsrs_review_logs_backup")
    connection.execute("DROP TABLE IF EXISTS _migration_fsrs_card_snapshots_backup")
    connection.execute(
        """
        CREATE TABLE _migration_fsrs_review_logs_backup AS
        SELECT * FROM fsrs_review_logs
        """
    )
    connection.execute(
        """
        CREATE TABLE _migration_fsrs_card_snapshots_backup AS
        SELECT direction, study_card_id, review_log_id, source, captured_at, due_at,
               fsrs_state, step, stability, difficulty
        FROM fsrs_card_snapshots
        """
    )

    connection.execute("DROP TABLE IF EXISTS fsrs_card_snapshots")
    connection.execute("DROP TABLE IF EXISTS fsrs_review_logs")

    connection.execute(
        f"""
        CREATE TABLE fsrs_cards_new (
            direction TEXT NOT NULL CHECK (direction IN {_DIRECTION_CHECK}),
            study_card_id INTEGER NOT NULL,
            fsrs_card_json TEXT NOT NULL,
            due_at TEXT NOT NULL,
            fsrs_state INTEGER NOT NULL,
            step INTEGER,
            stability REAL,
            difficulty REAL,
            first_reviewed_at TEXT,
            last_reviewed_at TEXT,
            is_suspended INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            PRIMARY KEY (direction, study_card_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO fsrs_cards_new
        SELECT * FROM fsrs_cards
        """
    )
    connection.execute("DROP TABLE fsrs_cards")
    connection.execute("ALTER TABLE fsrs_cards_new RENAME TO fsrs_cards")

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fsrs_cards_due
        ON fsrs_cards(direction, is_suspended, due_at)
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_fsrs_cards_updated_at
        AFTER UPDATE ON fsrs_cards
        FOR EACH ROW
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE fsrs_cards
            SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE direction = NEW.direction AND study_card_id = NEW.study_card_id;
        END
        """
    )

    connection.execute(
        f"""
        CREATE TABLE fsrs_review_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL CHECK (direction IN {_DIRECTION_CHECK}),
            study_card_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK (rating IN (1, 2, 3, 4)),
            rating_label TEXT NOT NULL CHECK (
                rating_label IN ('again', 'hard', 'good', 'easy')
            ),
            review_log_json TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            review_duration_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    connection.execute(
        """
        INSERT INTO fsrs_review_logs (
            id, direction, study_card_id, rating, rating_label,
            review_log_json, reviewed_at, review_duration_ms, created_at
        )
        SELECT
            id, direction, study_card_id, rating, rating_label,
            review_log_json, reviewed_at, review_duration_ms, created_at
        FROM _migration_fsrs_review_logs_backup
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fsrs_review_logs_card
        ON fsrs_review_logs(direction, study_card_id, reviewed_at)
        """
    )

    connection.execute(
        f"""
        CREATE TABLE fsrs_card_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL CHECK (direction IN {_DIRECTION_CHECK}),
            study_card_id INTEGER NOT NULL,
            review_log_id INTEGER,
            source TEXT NOT NULL CHECK (source IN ('created', 'review', 'optimizer', 'migration')),
            captured_at TEXT NOT NULL,
            due_at TEXT NOT NULL,
            fsrs_state INTEGER NOT NULL,
            step INTEGER,
            stability REAL,
            difficulty REAL,
            FOREIGN KEY (review_log_id) REFERENCES fsrs_review_logs(id) ON DELETE CASCADE,
            FOREIGN KEY (direction, study_card_id)
                REFERENCES fsrs_cards(direction, study_card_id) ON DELETE CASCADE,
            UNIQUE (direction, study_card_id, captured_at, source)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO fsrs_card_snapshots (
            direction, study_card_id, review_log_id, source, captured_at,
            due_at, fsrs_state, step, stability, difficulty
        )
        SELECT
            direction, study_card_id, review_log_id, source, captured_at,
            due_at, fsrs_state, step, stability, difficulty
        FROM _migration_fsrs_card_snapshots_backup
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fsrs_card_snapshots_history
        ON fsrs_card_snapshots(direction, captured_at, study_card_id)
        """
    )

    connection.execute("DROP TABLE IF EXISTS _migration_fsrs_review_logs_backup")
    connection.execute("DROP TABLE IF EXISTS _migration_fsrs_card_snapshots_backup")
    connection.execute("PRAGMA foreign_keys = ON")


def ensure_lexical_fsrs_card_types(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "fsrs_cards"):
        return

    connection.executescript(_NEW_CARD_TABLES_SQL)

    if not _direction_check_supports_new_types(connection):
        _rebuild_fsrs_direction_tables(connection)

    noun_count_row = connection.execute(
        "SELECT COUNT(*) AS count FROM noun_gender_fsrs_cards"
    ).fetchone()
    if noun_count_row is not None and int(noun_count_row["count"]) == 0:
        generate_noun_gender_fsrs_cards(connection)

    adjective_count_row = connection.execute(
        "SELECT COUNT(*) AS count FROM adjective_inflection_type_fsrs_cards"
    ).fetchone()
    if adjective_count_row is not None and int(adjective_count_row["count"]) == 0:
        generate_adjective_inflection_type_fsrs_cards(connection)
