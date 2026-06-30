from __future__ import annotations

import sqlite3
from collections.abc import Callable


def get_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0


def set_user_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(f"PRAGMA user_version = {int(version)}")


def run_script_with_foreign_keys_disabled(
    connection: sqlite3.Connection,
    script: str,
) -> None:
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(script)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"foreign key violations after migration: {violations}")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


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


def bootstrap_legacy_version(
    connection: sqlite3.Connection,
    *,
    target_version: int,
    detect_version: Callable[[sqlite3.Connection], int],
) -> None:
    if get_user_version(connection) != 0:
        return
    detected = detect_version(connection)
    if detected > 0:
        set_user_version(connection, detected)
        if detected >= target_version:
            return
    run_pending_migrations(
        connection,
        target_version=target_version,
        migrations={},
    )
