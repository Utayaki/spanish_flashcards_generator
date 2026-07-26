from __future__ import annotations

import sqlite3
from pathlib import Path

from drills.db.collections import CollectionsRepository
from drills.errors import DatabaseError

OLD_REGISTRY_SCHEMA_MESSAGE = (
    "This drills registry uses an old schema. Delete drills.db and create new collections."
)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
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


class DrillsDatabase(CollectionsRepository):
    """SQLite registry for drill collections."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        schema_path: str | Path | None = None,
        initialize: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.schema_path = (
            Path(schema_path)
            if schema_path
            else Path(__file__).resolve().parent.parent / "schema.sql"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            self.initialize()

    def _column_exists(self, connection, table_name: str, column_name: str) -> bool:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(str(row[1]) == column_name for row in rows)

    def _validate_registry_schema(self, connection) -> None:
        if not _table_exists(connection, "drill_collections"):
            return
        if not self._column_exists(connection, "drill_collections", "snapshot_filename"):
            raise DatabaseError(OLD_REGISTRY_SCHEMA_MESSAGE)

    def initialize(self) -> None:
        if not self.schema_path.exists():
            raise DatabaseError(f"schema.sql not found: {self.schema_path}")

        schema_sql = self.schema_path.read_text(encoding="utf-8")
        with self.transaction() as connection:
            self._validate_registry_schema(connection)
            connection.executescript(schema_sql)
