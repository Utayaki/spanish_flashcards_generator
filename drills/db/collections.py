from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from drills.db.connection import DrillsConnectionMixin, row_to_dict
from drills.errors import DatabaseError

_COLLECTION_NAME_RE = re.compile(r"^Collection (\d+)$")


class CollectionsRepository(DrillsConnectionMixin):
    def list_collections(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, created_at, snapshot_path
                FROM drill_collections
                ORDER BY id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_collection(self, collection_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, created_at, snapshot_path
                FROM drill_collections
                WHERE id = ?
                """,
                (collection_id,),
            ).fetchone()
        return row_to_dict(row)

    def next_collection_name(self, connection: sqlite3.Connection) -> str:
        rows = connection.execute("SELECT name FROM drill_collections").fetchall()
        max_number = 0
        for row in rows:
            match = _COLLECTION_NAME_RE.match(str(row["name"]))
            if match:
                max_number = max(max_number, int(match.group(1)))
        return f"Collection {max_number + 1}"

    def insert_collection(
        self,
        connection: sqlite3.Connection,
        *,
        name: str,
        snapshot_path: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO drill_collections (name, snapshot_path)
            VALUES (?, ?)
            """,
            (name, snapshot_path),
        )
        return int(cursor.lastrowid)

    def update_snapshot_path(
        self,
        connection: sqlite3.Connection,
        collection_id: int,
        snapshot_path: str,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE drill_collections
            SET snapshot_path = ?
            WHERE id = ?
            """,
            (snapshot_path, collection_id),
        )
        if cursor.rowcount != 1:
            raise DatabaseError(f"collection not found: {collection_id}")

    def delete_collection(self, collection_id: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM drill_collections WHERE id = ?",
                (collection_id,),
            )
            return cursor.rowcount == 1


def count_lexical_items(snapshot_path: Path) -> int:
    if not snapshot_path.is_file():
        raise DatabaseError(f"snapshot file not found: {snapshot_path}")
    with sqlite3.connect(snapshot_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM sqlite_master
            WHERE type = 'table' AND name = 'lexical_items'
            """
        ).fetchone()
        if row is None or int(row[0]) == 0:
            return 0
        count_row = connection.execute("SELECT COUNT(*) FROM lexical_items").fetchone()
        return int(count_row[0]) if count_row is not None else 0
