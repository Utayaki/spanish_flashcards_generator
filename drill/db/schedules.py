from __future__ import annotations

from typing import Any

from fsrs import Card

from drill.controllers.drill_scheduler import (
    default_scheduler,
    fsrs_card_snapshot,
    new_fsrs_card,
    rating_from_label,
    utc_iso,
    utc_now,
)
from shared.errors import DatabaseError


class DrillSchedulesRepository:
    def ensure_drill_schedule(self, drill_card_id: int) -> None:
        card = new_fsrs_card(drill_card_id)
        snapshot = fsrs_card_snapshot(card)

        with self.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO drill_schedules (
                    drill_card_id,
                    fsrs_card_json,
                    due_at,
                    fsrs_state,
                    stability,
                    difficulty,
                    elapsed_days,
                    scheduled_days,
                    reps,
                    lapses
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drill_card_id,
                    card.to_json(),
                    snapshot["due_at"],
                    snapshot["fsrs_state"],
                    snapshot["stability"],
                    snapshot["difficulty"],
                    snapshot["elapsed_days"],
                    snapshot["scheduled_days"],
                    snapshot["reps"],
                    snapshot["lapses"],
                ),
            )

    def ensure_all_drill_schedules(self) -> int:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT dc.id
                FROM drill_cards dc
                LEFT JOIN drill_schedules ds ON ds.drill_card_id = dc.id
                WHERE dc.is_active = 1
                  AND ds.drill_card_id IS NULL
                ORDER BY dc.id
                """
            ).fetchall()

        for row in rows:
            self.ensure_drill_schedule(int(row["id"]))

        return len(rows)

    def get_due_drill_card(
        self,
        *,
        drill_type: str | None = None,
        include_new: bool = True,
    ) -> dict[str, Any] | None:
        now = utc_iso()

        params: list[Any] = [now]
        where = [
            "dc.is_active = 1",
            "ds.is_suspended = 0",
            "ds.due_at <= ?",
        ]

        if not include_new:
            where.append("ds.first_reviewed_at IS NOT NULL")

        if drill_type:
            where.append("dc.drill_type = ?")
            params.append(drill_type)

        sql = f"""
            SELECT dc.*
            FROM drill_cards dc
            JOIN drill_schedules ds ON ds.drill_card_id = dc.id
            WHERE {" AND ".join(where)}
            ORDER BY
                CASE
                    WHEN ds.first_reviewed_at IS NULL THEN 1
                    ELSE 0
                END,
                ds.due_at ASC,
                RANDOM()
            LIMIT 1
        """

        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()

        return None if row is None else dict(row)

    def get_due_counts(self) -> dict[str, Any]:
        now = utc_iso()

        with self.connect() as connection:
            due_review = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM drill_cards dc
                JOIN drill_schedules ds ON ds.drill_card_id = dc.id
                WHERE dc.is_active = 1
                  AND ds.is_suspended = 0
                  AND ds.first_reviewed_at IS NOT NULL
                  AND ds.due_at <= ?
                """,
                (now,),
            ).fetchone()

            new_cards = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM drill_cards dc
                JOIN drill_schedules ds ON ds.drill_card_id = dc.id
                WHERE dc.is_active = 1
                  AND ds.is_suspended = 0
                  AND ds.first_reviewed_at IS NULL
                """
            ).fetchone()

            due_by_type = connection.execute(
                """
                SELECT
                    dc.drill_type,
                    COUNT(*) AS count
                FROM drill_cards dc
                JOIN drill_schedules ds ON ds.drill_card_id = dc.id
                WHERE dc.is_active = 1
                  AND ds.is_suspended = 0
                  AND ds.first_reviewed_at IS NOT NULL
                  AND ds.due_at <= ?
                GROUP BY dc.drill_type
                ORDER BY dc.drill_type
                """,
                (now,),
            ).fetchall()

        return {
            "due_review_count": int(due_review["count"] or 0),
            "new_card_count": int(new_cards["count"] or 0),
            "due_by_type": [dict(row) for row in due_by_type],
        }

    def rate_drill_card(
        self,
        *,
        drill_card_id: int,
        drill_attempt_id: int | None,
        rating_label: str,
        review_duration_ms: int | None = None,
    ) -> dict[str, Any]:
        scheduler = default_scheduler()
        rating = rating_from_label(rating_label)
        reviewed_at = utc_now()

        with self.transaction() as connection:
            row = connection.execute(
                """
                SELECT fsrs_card_json, first_reviewed_at
                FROM drill_schedules
                WHERE drill_card_id = ?
                """,
                (drill_card_id,),
            ).fetchone()

            if row is None:
                raise DatabaseError(f"missing drill schedule for card {drill_card_id}")

            card = Card.from_json(str(row["fsrs_card_json"]))

            updated_card, review_log = scheduler.review_card(
                card=card,
                rating=rating,
                review_datetime=reviewed_at,
                review_duration=review_duration_ms,
            )

            snapshot = fsrs_card_snapshot(updated_card)

            first_reviewed_at = row["first_reviewed_at"] or reviewed_at.isoformat()

            cursor = connection.execute(
                """
                INSERT INTO fsrs_review_logs (
                    drill_card_id,
                    drill_attempt_id,
                    rating,
                    rating_label,
                    review_log_json,
                    reviewed_at,
                    review_duration_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drill_card_id,
                    drill_attempt_id,
                    int(rating),
                    rating_label,
                    review_log.to_json(),
                    reviewed_at.isoformat(),
                    review_duration_ms,
                ),
            )

            connection.execute(
                """
                UPDATE drill_schedules
                SET
                    fsrs_card_json = ?,
                    due_at = ?,
                    fsrs_state = ?,
                    stability = ?,
                    difficulty = ?,
                    elapsed_days = ?,
                    scheduled_days = ?,
                    reps = ?,
                    lapses = ?,
                    first_reviewed_at = ?,
                    last_reviewed_at = ?
                WHERE drill_card_id = ?
                """,
                (
                    updated_card.to_json(),
                    snapshot["due_at"],
                    snapshot["fsrs_state"],
                    snapshot["stability"],
                    snapshot["difficulty"],
                    snapshot["elapsed_days"],
                    snapshot["scheduled_days"],
                    snapshot["reps"],
                    snapshot["lapses"],
                    first_reviewed_at,
                    reviewed_at.isoformat(),
                    drill_card_id,
                ),
            )

            return {
                "review_log_id": int(cursor.lastrowid),
                "drill_card_id": drill_card_id,
                "rating": rating_label,
                "next_due_at": snapshot["due_at"],
                "fsrs_state": snapshot["fsrs_state"],
                "stability": snapshot["stability"],
                "difficulty": snapshot["difficulty"],
                "scheduled_days": snapshot["scheduled_days"],
                "reps": snapshot["reps"],
                "lapses": snapshot["lapses"],
            }

    def get_schedule_summary(self) -> dict[str, Any]:
        now = utc_iso()

        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_scheduled,
                    SUM(CASE WHEN first_reviewed_at IS NULL THEN 1 ELSE 0 END) AS new_cards,
                    SUM(CASE WHEN first_reviewed_at IS NOT NULL AND due_at <= ? THEN 1 ELSE 0 END) AS due_reviews,
                    SUM(CASE WHEN first_reviewed_at IS NOT NULL AND due_at > ? THEN 1 ELSE 0 END) AS future_reviews
                FROM drill_schedules ds
                JOIN drill_cards dc ON dc.id = ds.drill_card_id
                WHERE dc.is_active = 1
                  AND ds.is_suspended = 0
                """,
                (now, now),
            ).fetchone()

        return {
            "total_scheduled": int(row["total_scheduled"] or 0),
            "new_cards": int(row["new_cards"] or 0),
            "due_reviews": int(row["due_reviews"] or 0),
            "future_reviews": int(row["future_reviews"] or 0),
        }
