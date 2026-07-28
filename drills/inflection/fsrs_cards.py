from __future__ import annotations

import sqlite3
from typing import Any

from fsrs import Card, ReviewLog, Scheduler

from drills.errors import DatabaseError
from drills.inflection.word_forms import display_form_descriptor
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


class InflectionReviewNotFoundError(LookupError):
    pass


def insert_inflection_card_snapshot(
    connection: sqlite3.Connection,
    *,
    word_form_id: int,
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
        INSERT INTO inflection_fsrs_card_snapshots (
            word_form_id,
            review_log_id,
            source,
            captured_at,
            due_at,
            fsrs_state,
            step,
            stability,
            difficulty
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            word_form_id,
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


def _save_inflection_scheduler_steps(
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


def insert_inflection_scheduler(connection: sqlite3.Connection, scheduler: Scheduler) -> None:
    param_columns = ", ".join(PARAM_COLUMNS)
    param_placeholders = ", ".join("?" for _ in PARAM_COLUMNS)
    connection.execute(
        f"""
        INSERT INTO inflection_fsrs_scheduler (
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
    _save_inflection_scheduler_steps(
        connection,
        table_name="inflection_fsrs_scheduler_learning_steps",
        rows=learning_step_rows(scheduler),
    )
    _save_inflection_scheduler_steps(
        connection,
        table_name="inflection_fsrs_scheduler_relearning_steps",
        rows=relearning_step_rows(scheduler),
    )


def seed_inflection_scheduler(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT id FROM inflection_fsrs_scheduler WHERE id = 1"
    ).fetchone()
    if row is not None:
        return
    insert_inflection_scheduler(connection, default_scheduler())


def load_inflection_scheduler(connection: sqlite3.Connection) -> Scheduler:
    scalar_columns = ", ".join(
        [
            "desired_retention",
            "enable_fuzzing",
            "maximum_interval",
            *PARAM_COLUMNS,
        ]
    )
    row = connection.execute(
        f"SELECT {scalar_columns} FROM inflection_fsrs_scheduler WHERE id = 1"
    ).fetchone()
    if row is None:
        raise DatabaseError("inflection fsrs scheduler not initialized")
    learning_rows = connection.execute(
        """
        SELECT step_index, duration_seconds
        FROM inflection_fsrs_scheduler_learning_steps
        ORDER BY step_index
        """
    ).fetchall()
    relearning_rows = connection.execute(
        """
        SELECT step_index, duration_seconds
        FROM inflection_fsrs_scheduler_relearning_steps
        ORDER BY step_index
        """
    ).fetchall()
    return scheduler_from_db(row, learning_rows, relearning_rows)


def save_inflection_scheduler(connection: sqlite3.Connection, scheduler: Scheduler) -> None:
    param_assignments = ", ".join(f"{column} = ?" for column in PARAM_COLUMNS)
    cursor = connection.execute(
        f"""
        UPDATE inflection_fsrs_scheduler
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
        raise DatabaseError("inflection fsrs scheduler not initialized")
    _save_inflection_scheduler_steps(
        connection,
        table_name="inflection_fsrs_scheduler_learning_steps",
        rows=learning_step_rows(scheduler),
    )
    _save_inflection_scheduler_steps(
        connection,
        table_name="inflection_fsrs_scheduler_relearning_steps",
        rows=relearning_step_rows(scheduler),
    )


def ensure_inflection_fsrs_card(
    connection: sqlite3.Connection,
    word_form_id: int,
) -> None:
    row = connection.execute(
        "SELECT word_form_id FROM inflection_fsrs_cards WHERE word_form_id = ?",
        (word_form_id,),
    ).fetchone()
    if row is not None:
        return

    fsrs_card = Card(card_id=word_form_id)
    snapshot = card_snapshot(fsrs_card)
    connection.execute(
        """
        INSERT INTO inflection_fsrs_cards (
            word_form_id,
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
            word_form_id,
            fsrs_card.to_json(),
            snapshot["due_at"],
            snapshot["fsrs_state"],
            snapshot["step"],
            snapshot["stability"],
            snapshot["difficulty"],
        ),
    )
    insert_inflection_card_snapshot(
        connection,
        word_form_id=word_form_id,
        source="created",
        captured_at=str(snapshot["due_at"]),
        due_at=str(snapshot["due_at"]),
        fsrs_state=int(snapshot["fsrs_state"]),
        step=snapshot["step"],
        stability=snapshot["stability"],
        difficulty=snapshot["difficulty"],
    )


def get_inflection_due_counts(connection: sqlite3.Connection) -> dict[str, int]:
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
        FROM inflection_fsrs_cards
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


def get_next_inflection_review(connection: sqlite3.Connection) -> dict[str, Any] | None:
    now = utc_iso()
    row = connection.execute(
        """
        SELECT
            wf.id AS word_form_id,
            wf.lexical_item_id,
            wf.headword,
            wf.explanation,
            wf.form_descriptor,
            wf.word_form,
            fc.due_at,
            fc.fsrs_state
        FROM inflection_fsrs_cards fc
        JOIN inflection_word_forms wf ON wf.id = fc.word_form_id
        WHERE fc.is_suspended = 0
          AND fc.due_at <= ?
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (now,),
    ).fetchone()
    if row is None:
        return None

    lexical_item_id = int(row["lexical_item_id"])
    form_descriptor = display_form_descriptor(
        connection,
        lexical_item_id,
        str(row["form_descriptor"]),
    )
    counts = get_inflection_due_counts(connection)
    return {
        "word_form_id": int(row["word_form_id"]),
        "headword": str(row["headword"]),
        "explanation": str(row["explanation"]),
        "form_descriptor": form_descriptor,
        "word_form": str(row["word_form"]),
        "due_at": str(row["due_at"]),
        "fsrs_state": int(row["fsrs_state"]),
        "counts": counts,
    }


def rate_inflection_card(
    connection: sqlite3.Connection,
    *,
    word_form_id: int,
    rating_label: str,
    review_duration_ms: int | None,
) -> dict[str, Any]:
    from drills.fsrs.scheduler import rating_from_label

    scheduler = load_inflection_scheduler(connection)
    row = connection.execute(
        """
        SELECT fsrs_card_json, first_reviewed_at
        FROM inflection_fsrs_cards
        WHERE word_form_id = ? AND is_suspended = 0
        """,
        (word_form_id,),
    ).fetchone()
    if row is None:
        raise DatabaseError(f"inflection fsrs card not found: {word_form_id}")

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
        INSERT INTO inflection_fsrs_review_logs (
            word_form_id,
            rating,
            rating_label,
            review_log_json,
            reviewed_at,
            review_duration_ms
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            word_form_id,
            int(rating),
            label,
            review_log.to_json(),
            reviewed_at.isoformat(),
            review_duration_ms,
        ),
    )
    update_cursor = connection.execute(
        """
        UPDATE inflection_fsrs_cards
        SET
            fsrs_card_json = ?,
            due_at = ?,
            fsrs_state = ?,
            step = ?,
            stability = ?,
            difficulty = ?,
            first_reviewed_at = ?,
            last_reviewed_at = ?
        WHERE word_form_id = ?
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
            word_form_id,
        ),
    )
    if update_cursor.rowcount != 1:
        raise DatabaseError(f"inflection fsrs card update failed: {word_form_id}")

    insert_inflection_card_snapshot(
        connection,
        word_form_id=word_form_id,
        review_log_id=int(log_cursor.lastrowid),
        source="review",
        captured_at=reviewed_at.isoformat(),
        due_at=str(snapshot["due_at"]),
        fsrs_state=int(snapshot["fsrs_state"]),
        step=snapshot["step"],
        stability=snapshot["stability"],
        difficulty=snapshot["difficulty"],
    )

    counts = get_inflection_due_counts(connection)
    return {
        "word_form_id": word_form_id,
        "rating": label,
        "next_due_at": snapshot["due_at"],
        "fsrs_state": snapshot["fsrs_state"],
        "counts": counts,
    }


def submit_inflection_answer(
    connection: sqlite3.Connection,
    *,
    word_form_id: int,
    answer: str,
    review_duration_ms: int | None,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT word_form
        FROM inflection_word_forms
        WHERE id = ?
        """,
        (word_form_id,),
    ).fetchone()
    if row is None:
        raise InflectionReviewNotFoundError(f"word form not found: {word_form_id}")

    word_form = str(row["word_form"])
    correct = answer.strip().casefold() == word_form.strip().casefold()

    if correct:
        return {
            "correct": True,
            "needs_rating": True,
            "word_form": word_form,
            "counts": get_inflection_due_counts(connection),
        }

    result = rate_inflection_card(
        connection,
        word_form_id=word_form_id,
        rating_label="again",
        review_duration_ms=review_duration_ms,
    )
    return {
        "correct": False,
        "needs_rating": False,
        "auto_rated": True,
        "word_form": word_form,
        "rating": result["rating"],
        "counts": result["counts"],
    }


def load_inflection_review_logs(connection: sqlite3.Connection) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT review_log_json
        FROM inflection_fsrs_review_logs
        ORDER BY reviewed_at
        """
    ).fetchall()
    return [ReviewLog.from_json(str(row["review_log_json"])) for row in rows]


def load_inflection_review_logs_for_card(
    connection: sqlite3.Connection,
    word_form_id: int,
) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT review_log_json
        FROM inflection_fsrs_review_logs
        WHERE word_form_id = ?
        ORDER BY reviewed_at
        """,
        (word_form_id,),
    ).fetchall()
    return [ReviewLog.from_json(str(row["review_log_json"])) for row in rows]
