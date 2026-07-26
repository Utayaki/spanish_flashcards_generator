from __future__ import annotations

import sqlite3
from typing import Any

from fsrs import Card, ReviewLog, Scheduler

from drills.errors import DatabaseError
from drills.fsrs.scheduler import (
    card_snapshot,
    default_scheduler,
    rating_label_from_int,
    utc_iso,
    utc_now,
)


def load_scheduler(connection: sqlite3.Connection) -> Scheduler:
    row = connection.execute(
        "SELECT scheduler_json FROM fsrs_scheduler WHERE id = 1"
    ).fetchone()
    if row is None:
        raise DatabaseError("fsrs scheduler not initialized")
    return Scheduler.from_json(str(row["scheduler_json"]))


def save_scheduler(connection: sqlite3.Connection, scheduler: Scheduler) -> None:
    cursor = connection.execute(
        """
        UPDATE fsrs_scheduler
        SET scheduler_json = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = 1
        """,
        (scheduler.to_json(),),
    )
    if cursor.rowcount != 1:
        raise DatabaseError("fsrs scheduler not initialized")


def seed_default_scheduler(connection: sqlite3.Connection) -> None:
    row = connection.execute("SELECT id FROM fsrs_scheduler WHERE id = 1").fetchone()
    if row is not None:
        return
    scheduler = default_scheduler()
    connection.execute(
        """
        INSERT INTO fsrs_scheduler (id, scheduler_json)
        VALUES (1, ?)
        """,
        (scheduler.to_json(),),
    )


def init_fsrs_cards(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        """
        SELECT li.id
        FROM lexical_items li
        LEFT JOIN fsrs_cards fc ON fc.lexical_item_id = li.id
        WHERE fc.lexical_item_id IS NULL
        ORDER BY li.id
        """
    ).fetchall()

    for row in rows:
        lexical_item_id = int(row["id"])
        card = Card(card_id=lexical_item_id)
        snapshot = card_snapshot(card)
        connection.execute(
            """
            INSERT INTO fsrs_cards (
                lexical_item_id,
                fsrs_card_json,
                due_at,
                fsrs_state,
                step,
                stability,
                difficulty
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lexical_item_id,
                card.to_json(),
                snapshot["due_at"],
                snapshot["fsrs_state"],
                snapshot["step"],
                snapshot["stability"],
                snapshot["difficulty"],
            ),
        )

    return len(rows)


def get_due_counts(connection: sqlite3.Connection) -> dict[str, int]:
    now = utc_iso()
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN first_reviewed_at IS NULL THEN 1 ELSE 0 END) AS new_cards,
            SUM(
                CASE
                    WHEN first_reviewed_at IS NOT NULL AND due_at <= ? THEN 1
                    ELSE 0
                END
            ) AS due,
            SUM(
                CASE
                    WHEN first_reviewed_at IS NOT NULL AND due_at > ? THEN 1
                    ELSE 0
                END
            ) AS future
        FROM fsrs_cards
        WHERE is_suspended = 0
        """,
        (now, now),
    ).fetchone()
    if row is None:
        return {"total": 0, "new": 0, "due": 0, "future": 0}
    return {
        "total": int(row["total"] or 0),
        "new": int(row["new_cards"] or 0),
        "due": int(row["due"] or 0),
        "future": int(row["future"] or 0),
    }


def get_next_due(connection: sqlite3.Connection) -> dict[str, Any] | None:
    now = utc_iso()
    row = connection.execute(
        """
        SELECT
            fc.lexical_item_id,
            fc.fsrs_card_json,
            fc.due_at,
            fc.fsrs_state,
            fc.first_reviewed_at,
            li.headword,
            li.explanation,
            li.lexical_item_type
        FROM fsrs_cards fc
        JOIN lexical_items li ON li.id = fc.lexical_item_id
        WHERE fc.is_suspended = 0
          AND fc.due_at <= ?
        ORDER BY
            CASE WHEN fc.first_reviewed_at IS NULL THEN 0 ELSE 1 END,
            fc.due_at ASC,
            RANDOM()
        LIMIT 1
        """,
        (now,),
    ).fetchone()
    if row is None:
        return None

    counts = get_due_counts(connection)
    return {
        "lexical_item_id": int(row["lexical_item_id"]),
        "headword": str(row["headword"]),
        "explanation": str(row["explanation"]),
        "lexical_item_type": str(row["lexical_item_type"]),
        "due_at": str(row["due_at"]),
        "fsrs_state": int(row["fsrs_state"]),
        "counts": counts,
    }


def rate_card(
    connection: sqlite3.Connection,
    *,
    lexical_item_id: int,
    rating_label: str,
    review_duration_ms: int | None,
) -> dict[str, Any]:
    from drills.fsrs.scheduler import rating_from_label

    scheduler = load_scheduler(connection)
    row = connection.execute(
        """
        SELECT fsrs_card_json, first_reviewed_at
        FROM fsrs_cards
        WHERE lexical_item_id = ? AND is_suspended = 0
        """,
        (lexical_item_id,),
    ).fetchone()
    if row is None:
        raise DatabaseError(f"fsrs card not found: {lexical_item_id}")

    card = Card.from_json(str(row["fsrs_card_json"]))
    rating = rating_from_label(rating_label)
    reviewed_at = utc_now()

    updated_card, review_log = scheduler.review_card(
        card=card,
        rating=rating,
        review_datetime=reviewed_at,
        review_duration=review_duration_ms,
    )
    snapshot = card_snapshot(updated_card)
    first_reviewed_at = row["first_reviewed_at"] or reviewed_at.isoformat()
    label = rating_label_from_int(int(rating))

    connection.execute(
        """
        INSERT INTO fsrs_review_logs (
            lexical_item_id,
            rating,
            rating_label,
            review_log_json,
            reviewed_at,
            review_duration_ms
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            lexical_item_id,
            int(rating),
            label,
            review_log.to_json(),
            reviewed_at.isoformat(),
            review_duration_ms,
        ),
    )
    connection.execute(
        """
        UPDATE fsrs_cards
        SET
            fsrs_card_json = ?,
            due_at = ?,
            fsrs_state = ?,
            step = ?,
            stability = ?,
            difficulty = ?,
            first_reviewed_at = ?,
            last_reviewed_at = ?
        WHERE lexical_item_id = ?
        """,
        (
            updated_card.to_json(),
            snapshot["due_at"],
            snapshot["fsrs_state"],
            snapshot["step"],
            snapshot["stability"],
            snapshot["difficulty"],
            first_reviewed_at,
            reviewed_at.isoformat(),
            lexical_item_id,
        ),
    )

    counts = get_due_counts(connection)
    return {
        "lexical_item_id": lexical_item_id,
        "rating": label,
        "next_due_at": snapshot["due_at"],
        "fsrs_state": snapshot["fsrs_state"],
        "counts": counts,
    }


def load_review_logs(connection: sqlite3.Connection) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT review_log_json
        FROM fsrs_review_logs
        ORDER BY reviewed_at
        """
    ).fetchall()
    return [ReviewLog.from_json(str(row["review_log_json"])) for row in rows]


def load_review_logs_for_card(
    connection: sqlite3.Connection,
    lexical_item_id: int,
) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT review_log_json
        FROM fsrs_review_logs
        WHERE lexical_item_id = ?
        ORDER BY reviewed_at
        """,
        (lexical_item_id,),
    ).fetchall()
    return [ReviewLog.from_json(str(row["review_log_json"])) for row in rows]
