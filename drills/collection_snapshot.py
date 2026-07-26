from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from drills.db.connection import connect
from drills.errors import DatabaseError
from drills.fsrs.analytics import DEFAULT_DASHBOARD_RANGE_DAYS, ensure_fsrs_snapshot_storage, get_dashboard_analytics
from drills.fsrs.cards import get_due_counts, get_next_due, rate_card
from drills.fsrs.optimizer import run_optimizer
from drills.inflection.fsrs_analytics import (
    DEFAULT_DASHBOARD_RANGE_DAYS as INFLECTION_DEFAULT_DASHBOARD_RANGE_DAYS,
    ensure_inflection_fsrs_snapshot_storage,
    get_inflection_dashboard_analytics,
)
from drills.inflection.fsrs_cards import (
    get_inflection_due_counts,
    get_next_inflection_review,
    rate_inflection_card,
    submit_inflection_answer,
)
from drills.inflection.fsrs_optimizer import run_inflection_optimizer


class CollectionSnapshot:
    def __init__(self, snapshot_path: Path) -> None:
        self.snapshot_path = snapshot_path
        with self.transaction() as connection:
            ensure_fsrs_snapshot_storage(connection)
            ensure_inflection_fsrs_snapshot_storage(connection)

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

    def get_counts(self, direction: str) -> dict[str, int]:
        with self.connect() as connection:
            return get_due_counts(connection, direction)

    def get_stats(
        self,
        direction: str,
        *,
        timezone_offset_minutes: int = 0,
        range_days: int = DEFAULT_DASHBOARD_RANGE_DAYS,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            return {
                "counts": get_due_counts(connection, direction),
                "analytics": get_dashboard_analytics(
                    connection,
                    direction=direction,
                    timezone_offset_minutes=timezone_offset_minutes,
                    range_days=range_days,
                ),
            }

    def get_next(self, direction: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            return get_next_due(connection, direction)

    def rate(
        self,
        *,
        direction: str,
        study_card_id: int,
        rating: str,
        review_duration_ms: int | None,
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            return rate_card(
                connection,
                direction=direction,
                study_card_id=study_card_id,
                rating_label=rating,
                review_duration_ms=review_duration_ms,
            )

    def optimize(self) -> dict[str, Any]:
        with self.transaction() as connection:
            return run_optimizer(connection)

    def get_inflection_counts(self) -> dict[str, int]:
        with self.connect() as connection:
            return get_inflection_due_counts(connection)

    def get_inflection_stats(
        self,
        *,
        timezone_offset_minutes: int = 0,
        range_days: int = INFLECTION_DEFAULT_DASHBOARD_RANGE_DAYS,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            return {
                "counts": get_inflection_due_counts(connection),
                "analytics": get_inflection_dashboard_analytics(
                    connection,
                    timezone_offset_minutes=timezone_offset_minutes,
                    range_days=range_days,
                ),
            }

    def get_inflection_next(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            return get_next_inflection_review(connection)

    def submit_inflection_answer(
        self,
        *,
        word_form_id: int,
        example_id: int,
        answer: str,
        review_duration_ms: int | None,
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            return submit_inflection_answer(
                connection,
                word_form_id=word_form_id,
                example_id=example_id,
                answer=answer,
                review_duration_ms=review_duration_ms,
            )

    def rate_inflection(
        self,
        *,
        word_form_id: int,
        rating: str,
        review_duration_ms: int | None,
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            return rate_inflection_card(
                connection,
                word_form_id=word_form_id,
                rating_label=rating,
                review_duration_ms=review_duration_ms,
            )

    def optimize_inflection(self) -> dict[str, Any]:
        with self.transaction() as connection:
            return run_inflection_optimizer(connection)


def open_collection_snapshot(
    collection: dict[str, Any],
    *,
    project_root: Path,
) -> CollectionSnapshot:
    snapshot_path = project_root / str(collection["snapshot_path"])
    if not snapshot_path.is_file():
        raise DatabaseError(f"snapshot file not found: {snapshot_path}")
    return CollectionSnapshot(snapshot_path)
