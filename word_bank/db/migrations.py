from __future__ import annotations

import sqlite3


def get_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0


def set_user_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(f"PRAGMA user_version = {int(version)}")


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def run_pending_migrations(
    connection: sqlite3.Connection,
    *,
    target_version: int,
    migrations: dict[int, str],
) -> None:
    current = get_user_version(connection)
    if current >= target_version:
        return

    for version in range(current + 1, target_version + 1):
        script = migrations.get(version)
        if script is None:
            raise RuntimeError(f"missing migration for schema version {version}")
        connection.executescript(script)
        set_user_version(connection, version)


