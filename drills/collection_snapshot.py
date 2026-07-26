from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from drills.db.connection import connect
from drills.errors import DatabaseError
from drills.fsrs.cards import get_due_counts, get_next_due, rate_card
from drills.fsrs.migrate_snapshot import migrate_snapshot_if_needed
from drills.fsrs.optimizer import run_optimizer


class CollectionSnapshot:
    def __init__(self, snapshot_path: Path) -> None:
        self.snapshot_path = snapshot_path
        migrate_snapshot_if_needed(snapshot_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = connect(self.snapshot_path)
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = connect(self.snapshot_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_stats(self) -> dict[str, int]:
        with self.connect() as connection:
            return get_due_counts(connection)

    def get_next(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            return get_next_due(connection)

    def rate(
        self,
        *,
        lexical_item_id: int,
        rating: str,
        review_duration_ms: int | None,
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            return rate_card(
                connection,
                lexical_item_id=lexical_item_id,
                rating_label=rating,
                review_duration_ms=review_duration_ms,
            )

    def optimize(self) -> dict[str, Any]:
        with self.transaction() as connection:
            return run_optimizer(connection)


def open_collection_snapshot(
    collection: dict[str, Any],
    *,
    project_root: Path,
) -> CollectionSnapshot:
    snapshot_path = project_root / str(collection["snapshot_path"])
    if not snapshot_path.is_file():
        raise DatabaseError(f"snapshot file not found: {snapshot_path}")
    return CollectionSnapshot(snapshot_path)
