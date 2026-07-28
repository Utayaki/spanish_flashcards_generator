from __future__ import annotations

import sqlite3

from drills.inflection.storage import seed_inflection_drill_cards


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


def ensure_inflection_cards_seeded(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "inflection_word_forms"):
        return

    if _table_exists(connection, "inflection_drill_examples"):
        connection.execute("DROP TABLE inflection_drill_examples")

    seed_inflection_drill_cards(connection)
