from __future__ import annotations

import sqlite3
from typing import Any

from fsrs import Card, ReviewLog, Scheduler

from drills.errors import DatabaseError
from drills.fsrs.scheduler import (
    PARAM_COLUMNS,
    card_snapshot,
    default_scheduler,
    learning_step_rows,
    rating_label_from_int,
    relearning_step_rows,
    scheduler_from_db,
    scheduler_row_values,
    utc_iso,
    utc_now,
)

DIRECTION_SPANISH_TO_ENGLISH = "spanish_to_english"
DIRECTION_ENGLISH_TO_SPANISH = "english_to_spanish"
DIRECTION_NOUN_GENDER = "noun_gender"
DIRECTION_ADJECTIVE_INFLECTION_TYPE = "adjective_inflection_type"
DIRECTION_MIXED = "mixed"
CARD_DIRECTIONS = frozenset({
    DIRECTION_SPANISH_TO_ENGLISH,
    DIRECTION_ENGLISH_TO_SPANISH,
    DIRECTION_NOUN_GENDER,
    DIRECTION_ADJECTIVE_INFLECTION_TYPE,
})
CARD_TABLES = {
    DIRECTION_SPANISH_TO_ENGLISH: "spanish_to_english_fsrs_cards",
    DIRECTION_ENGLISH_TO_SPANISH: "english_to_spanish_fsrs_cards",
    DIRECTION_NOUN_GENDER: "noun_gender_fsrs_cards",
    DIRECTION_ADJECTIVE_INFLECTION_TYPE: "adjective_inflection_type_fsrs_cards",
}


def insert_card_snapshot(
    connection: sqlite3.Connection,
    *,
    direction: str,
    study_card_id: int,
    source: str,
    captured_at: str,
    due_at: str,
    fsrs_state: int,
    step: int | None,
    stability: float | None,
    difficulty: float | None,
    review_log_id: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO fsrs_card_snapshots (
            direction,
            study_card_id,
            review_log_id,
            source,
            captured_at,
            due_at,
            fsrs_state,
            step,
            stability,
            difficulty
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            direction,
            study_card_id,
            review_log_id,
            source,
            captured_at,
            due_at,
            fsrs_state,
            step,
            stability,
            difficulty,
        ),
    )


def validate_direction(direction: str) -> str:
    if direction not in CARD_DIRECTIONS:
        raise DatabaseError(
            f"invalid direction: {direction}; expected one of: {', '.join(sorted(CARD_DIRECTIONS))}"
        )
    return direction


def load_scheduler(connection: sqlite3.Connection) -> Scheduler:
    scalar_columns = ", ".join(
        [
            "desired_retention",
            "enable_fuzzing",
            "maximum_interval",
            *PARAM_COLUMNS,
        ]
    )
    row = connection.execute(
        f"SELECT {scalar_columns} FROM fsrs_scheduler WHERE id = 1"
    ).fetchone()
    if row is None:
        raise DatabaseError("fsrs scheduler not initialized")
    learning_rows = connection.execute(
        """
        SELECT step_index, duration_seconds
        FROM fsrs_scheduler_learning_steps
        ORDER BY step_index
        """
    ).fetchall()
    relearning_rows = connection.execute(
        """
        SELECT step_index, duration_seconds
        FROM fsrs_scheduler_relearning_steps
        ORDER BY step_index
        """
    ).fetchall()
    return scheduler_from_db(row, learning_rows, relearning_rows)


def _save_scheduler_steps(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    rows: list[tuple[int, int]],
) -> None:
    connection.execute(f"DELETE FROM {table_name}")
    connection.executemany(
        f"""
        INSERT INTO {table_name} (step_index, duration_seconds)
        VALUES (?, ?)
        """,
        rows,
    )


def save_scheduler(connection: sqlite3.Connection, scheduler: Scheduler) -> None:
    param_assignments = ", ".join(f"{column} = ?" for column in PARAM_COLUMNS)
    cursor = connection.execute(
        f"""
        UPDATE fsrs_scheduler
        SET
            desired_retention = ?,
            enable_fuzzing = ?,
            maximum_interval = ?,
            {param_assignments},
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = 1
        """,
        scheduler_row_values(scheduler),
    )
    if cursor.rowcount != 1:
        raise DatabaseError("fsrs scheduler not initialized")
    _save_scheduler_steps(
        connection,
        table_name="fsrs_scheduler_learning_steps",
        rows=learning_step_rows(scheduler),
    )
    _save_scheduler_steps(
        connection,
        table_name="fsrs_scheduler_relearning_steps",
        rows=relearning_step_rows(scheduler),
    )


def insert_scheduler(connection: sqlite3.Connection, scheduler: Scheduler) -> None:
    param_columns = ", ".join(PARAM_COLUMNS)
    param_placeholders = ", ".join("?" for _ in PARAM_COLUMNS)
    connection.execute(
        f"""
        INSERT INTO fsrs_scheduler (
            id,
            desired_retention,
            enable_fuzzing,
            maximum_interval,
            {param_columns}
        )
        VALUES (1, ?, ?, ?, {param_placeholders})
        """,
        scheduler_row_values(scheduler),
    )
    _save_scheduler_steps(
        connection,
        table_name="fsrs_scheduler_learning_steps",
        rows=learning_step_rows(scheduler),
    )
    _save_scheduler_steps(
        connection,
        table_name="fsrs_scheduler_relearning_steps",
        rows=relearning_step_rows(scheduler),
    )


def seed_default_scheduler(connection: sqlite3.Connection) -> None:
    row = connection.execute("SELECT id FROM fsrs_scheduler WHERE id = 1").fetchone()
    if row is not None:
        return
    insert_scheduler(connection, default_scheduler())


def get_due_counts(connection: sqlite3.Connection, direction: str) -> dict[str, int]:
    direction = validate_direction(direction)
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
        WHERE is_suspended = 0 AND direction = ?
        """,
        (now, now, direction),
    ).fetchone()
    if row is None:
        return {"total": 0, "new": 0, "due": 0, "future": 0}
    return {
        "total": int(row["total"] or 0),
        "new": int(row["new_cards"] or 0),
        "due": int(row["due"] or 0),
        "future": int(row["future"] or 0),
    }


def get_mixed_due_counts(connection: sqlite3.Connection) -> dict[str, int]:
    totals = {"total": 0, "new": 0, "due": 0, "future": 0}
    for direction in CARD_DIRECTIONS:
        counts = get_due_counts(connection, direction)
        for key in totals:
            totals[key] += counts[key]
    return totals


def get_next_due_mixed(connection: sqlite3.Connection) -> dict[str, Any] | None:
    now = utc_iso()
    union_parts = []
    for direction, card_table in CARD_TABLES.items():
        union_parts.append(
            f"""
            SELECT
                '{direction}' AS direction,
                fc.study_card_id,
                fc.due_at,
                fc.fsrs_state,
                sc.front,
                sc.back
            FROM fsrs_cards fc
            JOIN {card_table} sc ON sc.id = fc.study_card_id
            WHERE fc.is_suspended = 0
              AND fc.direction = '{direction}'
              AND fc.due_at <= ?
            """
        )
    query = f"""
        SELECT direction, study_card_id, due_at, fsrs_state, front, back
        FROM (
            {" UNION ALL ".join(union_parts)}
        )
        ORDER BY RANDOM()
        LIMIT 1
    """
    row = connection.execute(query, tuple([now] * len(CARD_DIRECTIONS))).fetchone()
    if row is None:
        return None

    direction = str(row["direction"])
    counts = get_mixed_due_counts(connection)
    return {
        "study_card_id": int(row["study_card_id"]),
        "direction": direction,
        "front": str(row["front"]),
        "back": str(row["back"]),
        "due_at": str(row["due_at"]),
        "fsrs_state": int(row["fsrs_state"]),
        "counts": counts,
    }


def get_next_due(connection: sqlite3.Connection, direction: str) -> dict[str, Any] | None:
    direction = validate_direction(direction)
    card_table = CARD_TABLES[direction]
    now = utc_iso()
    row = connection.execute(
        f"""
        SELECT
            fc.study_card_id,
            fc.due_at,
            fc.fsrs_state,
            sc.front,
            sc.back
        FROM fsrs_cards fc
        JOIN {card_table} sc ON sc.id = fc.study_card_id
        WHERE fc.is_suspended = 0
          AND fc.direction = ?
          AND fc.due_at <= ?
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (direction, now),
    ).fetchone()
    if row is None:
        return None

    counts = get_due_counts(connection, direction)
    return {
        "study_card_id": int(row["study_card_id"]),
        "direction": direction,
        "front": str(row["front"]),
        "back": str(row["back"]),
        "due_at": str(row["due_at"]),
        "fsrs_state": int(row["fsrs_state"]),
        "counts": counts,
    }


def rate_card(
    connection: sqlite3.Connection,
    *,
    direction: str,
    study_card_id: int,
    rating_label: str,
    review_duration_ms: int | None,
) -> dict[str, Any]:
    from drills.fsrs.scheduler import rating_from_label

    direction = validate_direction(direction)
    scheduler = load_scheduler(connection)
    row = connection.execute(
        """
        SELECT fsrs_card_json, first_reviewed_at
        FROM fsrs_cards
        WHERE direction = ? AND study_card_id = ? AND is_suspended = 0
        """,
        (direction, study_card_id),
    ).fetchone()
    if row is None:
        raise DatabaseError(f"fsrs card not found: {direction}/{study_card_id}")

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

    log_cursor = connection.execute(
        """
        INSERT INTO fsrs_review_logs (
            direction,
            study_card_id,
            rating,
            rating_label,
            review_log_json,
            reviewed_at,
            review_duration_ms
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            direction,
            study_card_id,
            int(rating),
            label,
            review_log.to_json(),
            reviewed_at.isoformat(),
            review_duration_ms,
        ),
    )
    update_cursor = connection.execute(
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
        WHERE direction = ? AND study_card_id = ?
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
            direction,
            study_card_id,
        ),
    )
    if update_cursor.rowcount != 1:
        raise DatabaseError(f"fsrs card update failed: {direction}/{study_card_id}")

    insert_card_snapshot(
        connection,
        direction=direction,
        study_card_id=study_card_id,
        review_log_id=int(log_cursor.lastrowid),
        source="review",
        captured_at=reviewed_at.isoformat(),
        due_at=str(snapshot["due_at"]),
        fsrs_state=int(snapshot["fsrs_state"]),
        step=snapshot["step"],
        stability=snapshot["stability"],
        difficulty=snapshot["difficulty"],
    )

    counts = get_due_counts(connection, direction)
    mixed_counts = get_mixed_due_counts(connection)
    return {
        "study_card_id": study_card_id,
        "direction": direction,
        "rating": label,
        "next_due_at": snapshot["due_at"],
        "fsrs_state": snapshot["fsrs_state"],
        "counts": counts,
        "mixed_counts": mixed_counts,
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
    *,
    direction: str,
    study_card_id: int,
) -> list[ReviewLog]:
    direction = validate_direction(direction)
    rows = connection.execute(
        """
        SELECT review_log_json
        FROM fsrs_review_logs
        WHERE direction = ? AND study_card_id = ?
        ORDER BY reviewed_at
        """,
        (direction, study_card_id),
    ).fetchall()
    return [ReviewLog.from_json(str(row["review_log_json"])) for row in rows]
