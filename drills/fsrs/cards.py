from __future__ import annotations

import sqlite3
from typing import Any

from fsrs import Card, ReviewLog, Scheduler

from drills.errors import DatabaseError
from drills.fsrs.scheduler import (
    PARAM_COLUMNS,
    card_from_schedule,
    card_snapshot,
    default_scheduler,
    learning_step_rows,
    rating_label_from_int,
    relearning_step_rows,
    review_log_from_row,
    scheduler_from_db,
    scheduler_row_values,
    utc_iso,
    utc_now,
)

CARD_KIND_SPANISH_TO_ENGLISH = "spanish_to_english"
CARD_KIND_ENGLISH_TO_SPANISH = "english_to_spanish"
CARD_KIND_NOUN_GENDER = "noun_gender"
CARD_KIND_ADJECTIVE_INFLECTION_TYPE = "adjective_inflection_type"
CARD_KIND_INFLECTION = "inflection"
CARD_KIND_MIXED = "mixed"

# API compatibility aliases
DIRECTION_SPANISH_TO_ENGLISH = CARD_KIND_SPANISH_TO_ENGLISH
DIRECTION_ENGLISH_TO_SPANISH = CARD_KIND_ENGLISH_TO_SPANISH
DIRECTION_NOUN_GENDER = CARD_KIND_NOUN_GENDER
DIRECTION_ADJECTIVE_INFLECTION_TYPE = CARD_KIND_ADJECTIVE_INFLECTION_TYPE
DIRECTION_MIXED = CARD_KIND_MIXED

LEXICAL_CARD_KINDS = frozenset({
    CARD_KIND_SPANISH_TO_ENGLISH,
    CARD_KIND_ENGLISH_TO_SPANISH,
    CARD_KIND_NOUN_GENDER,
    CARD_KIND_ADJECTIVE_INFLECTION_TYPE,
})

CARD_KINDS = LEXICAL_CARD_KINDS | {CARD_KIND_INFLECTION}

# Backward-compatible alias used by analytics and GUI
CARD_DIRECTIONS = LEXICAL_CARD_KINDS

DRILL_KIND_ORDER = (
    CARD_KIND_ENGLISH_TO_SPANISH,
    CARD_KIND_NOUN_GENDER,
    CARD_KIND_ADJECTIVE_INFLECTION_TYPE,
    CARD_KIND_SPANISH_TO_ENGLISH,
)


class InflectionReviewNotFoundError(LookupError):
    pass


def validate_card_kind(card_kind: str) -> str:
    if card_kind not in CARD_KINDS:
        raise DatabaseError(
            f"invalid card_kind: {card_kind}; expected one of: {', '.join(sorted(CARD_KINDS))}"
        )
    return card_kind


def validate_lexical_card_kind(card_kind: str) -> str:
    if card_kind not in LEXICAL_CARD_KINDS:
        raise DatabaseError(
            f"invalid card_kind: {card_kind}; expected one of: {', '.join(sorted(LEXICAL_CARD_KINDS))}"
        )
    return card_kind


def _new_card_kind_order_sql() -> str:
    when_clauses = "\n".join(
        f"    WHEN sc.card_kind = '{card_kind}' THEN {index}"
        for index, card_kind in enumerate(DRILL_KIND_ORDER)
    )
    fallback = len(DRILL_KIND_ORDER)
    return f"""CASE
    WHEN fs.first_reviewed_at IS NOT NULL THEN 0
{when_clauses}
    ELSE {fallback}
END"""


def insert_study_card(
    connection: sqlite3.Connection,
    *,
    card_kind: str,
    front: str | None = None,
    back: str | None = None,
    headword: str | None = None,
    explanation: str | None = None,
    lexical_item_type: str | None = None,
    word_form: str | None = None,
    form_descriptor: str | None = None,
) -> int:
    validate_card_kind(card_kind)
    if card_kind == CARD_KIND_INFLECTION:
        cursor = connection.execute(
            """
            INSERT INTO study_cards (
                card_kind,
                headword,
                explanation,
                lexical_item_type,
                word_form,
                form_descriptor
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (card_kind, headword, explanation, lexical_item_type, word_form, form_descriptor),
        )
    else:
        cursor = connection.execute(
            """
            INSERT INTO study_cards (card_kind, front, back)
            VALUES (?, ?, ?)
            """,
            (card_kind, front, back),
        )
    return int(cursor.lastrowid)


def seed_fsrs_schedule(connection: sqlite3.Connection, study_card_id: int) -> None:
    fsrs_card = Card(card_id=study_card_id)
    snapshot = card_snapshot(fsrs_card)
    connection.execute(
        """
        INSERT INTO fsrs_schedules (
            study_card_id,
            due_at,
            fsrs_state,
            step,
            stability,
            difficulty
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            study_card_id,
            snapshot["due_at"],
            snapshot["fsrs_state"],
            snapshot["step"],
            snapshot["stability"],
            snapshot["difficulty"],
        ),
    )


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


def seed_scheduler(connection: sqlite3.Connection, scheduler: Scheduler) -> None:
    row = connection.execute("SELECT id FROM fsrs_scheduler WHERE id = 1").fetchone()
    if row is not None:
        return
    insert_scheduler(connection, scheduler)


def seed_default_scheduler(connection: sqlite3.Connection) -> None:
    seed_scheduler(connection, default_scheduler())


def _schedule_count_query(*, card_kind: str | None = None) -> tuple[str, tuple[Any, ...]]:
    now = utc_iso()
    filters = ["fs.is_suspended = 0"]
    params: list[Any] = [now, now]
    if card_kind is not None:
        filters.append("sc.card_kind = ?")
        params.append(card_kind)
    where_clause = " AND ".join(filters)
    query = f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN fs.first_reviewed_at IS NULL THEN 1 ELSE 0 END) AS new_cards,
            SUM(
                CASE
                    WHEN fs.first_reviewed_at IS NOT NULL AND fs.due_at <= ? THEN 1
                    ELSE 0
                END
            ) AS due,
            SUM(
                CASE
                    WHEN fs.first_reviewed_at IS NOT NULL AND fs.due_at > ? THEN 1
                    ELSE 0
                END
            ) AS future
        FROM fsrs_schedules fs
        JOIN study_cards sc ON sc.id = fs.study_card_id
        WHERE {where_clause}
    """
    return query, tuple(params)


def _counts_from_row(row: sqlite3.Row | None) -> dict[str, int]:
    if row is None:
        return {"total": 0, "new": 0, "due": 0, "future": 0}
    return {
        "total": int(row["total"] or 0),
        "new": int(row["new_cards"] or 0),
        "due": int(row["due"] or 0),
        "future": int(row["future"] or 0),
    }


def get_due_counts(connection: sqlite3.Connection, card_kind: str) -> dict[str, int]:
    card_kind = validate_lexical_card_kind(card_kind)
    query, params = _schedule_count_query(card_kind=card_kind)
    row = connection.execute(query, params).fetchone()
    return _counts_from_row(row)


def get_mixed_due_counts(connection: sqlite3.Connection) -> dict[str, int]:
    query, params = _schedule_count_query(
        card_kind=None,
    )
    # mixed mode excludes inflection
    query = query.replace(
        "WHERE fs.is_suspended = 0",
        "WHERE fs.is_suspended = 0 AND sc.card_kind != ?",
        1,
    )
    params = (params[0], params[1], CARD_KIND_INFLECTION, *params[2:])
    row = connection.execute(query, params).fetchone()
    return _counts_from_row(row)


def get_inflection_due_counts(connection: sqlite3.Connection) -> dict[str, int]:
    query, params = _schedule_count_query(card_kind=CARD_KIND_INFLECTION)
    row = connection.execute(query, params).fetchone()
    return _counts_from_row(row)


def _lexical_card_payload(row: sqlite3.Row, *, card_kind: str) -> dict[str, Any]:
    return {
        "study_card_id": int(row["study_card_id"]),
        "direction": card_kind,
        "card_kind": card_kind,
        "front": str(row["front"]),
        "back": str(row["back"]),
        "due_at": str(row["due_at"]),
        "fsrs_state": int(row["fsrs_state"]),
    }


def get_next_due(connection: sqlite3.Connection, card_kind: str) -> dict[str, Any] | None:
    card_kind = validate_lexical_card_kind(card_kind)
    now = utc_iso()
    row = connection.execute(
        """
        SELECT
            sc.id AS study_card_id,
            sc.front,
            sc.back,
            fs.due_at,
            fs.fsrs_state
        FROM fsrs_schedules fs
        JOIN study_cards sc ON sc.id = fs.study_card_id
        WHERE fs.is_suspended = 0
          AND sc.card_kind = ?
          AND fs.due_at <= ?
        ORDER BY
          CASE WHEN fs.first_reviewed_at IS NULL THEN 1 ELSE 0 END,
          RANDOM()
        LIMIT 1
        """,
        (card_kind, now),
    ).fetchone()
    if row is None:
        return None

    counts = get_due_counts(connection, card_kind)
    return {**_lexical_card_payload(row, card_kind=card_kind), "counts": counts}


def get_next_due_mixed(connection: sqlite3.Connection) -> dict[str, Any] | None:
    now = utc_iso()
    kind_placeholders = ", ".join("?" for _ in DRILL_KIND_ORDER)
    kind_order_sql = _new_card_kind_order_sql()
    row = connection.execute(
        f"""
        SELECT
            sc.id AS study_card_id,
            sc.card_kind,
            sc.front,
            sc.back,
            fs.due_at,
            fs.fsrs_state,
            fs.first_reviewed_at
        FROM fsrs_schedules fs
        JOIN study_cards sc ON sc.id = fs.study_card_id
        WHERE fs.is_suspended = 0
          AND sc.card_kind IN ({kind_placeholders})
          AND fs.due_at <= ?
        ORDER BY
          CASE WHEN fs.first_reviewed_at IS NULL THEN 1 ELSE 0 END,
          {kind_order_sql},
          RANDOM()
        LIMIT 1
        """,
        (*DRILL_KIND_ORDER, now),
    ).fetchone()
    if row is None:
        return None

    card_kind = str(row["card_kind"])
    counts = get_mixed_due_counts(connection)
    return {**_lexical_card_payload(row, card_kind=card_kind), "counts": counts}


def get_next_inflection_review(connection: sqlite3.Connection) -> dict[str, Any] | None:
    now = utc_iso()
    row = connection.execute(
        """
        SELECT
            sc.id AS study_card_id,
            sc.headword,
            sc.explanation,
            sc.form_descriptor,
            sc.word_form,
            fs.due_at,
            fs.fsrs_state
        FROM fsrs_schedules fs
        JOIN study_cards sc ON sc.id = fs.study_card_id
        WHERE fs.is_suspended = 0
          AND sc.card_kind = ?
          AND fs.due_at <= ?
        ORDER BY
          CASE WHEN fs.first_reviewed_at IS NULL THEN 1 ELSE 0 END,
          RANDOM()
        LIMIT 1
        """,
        (CARD_KIND_INFLECTION, now),
    ).fetchone()
    if row is None:
        return None

    study_card_id = int(row["study_card_id"])
    counts = get_inflection_due_counts(connection)
    return {
        "study_card_id": study_card_id,
        "word_form_id": study_card_id,
        "headword": str(row["headword"]),
        "explanation": str(row["explanation"]),
        "form_descriptor": str(row["form_descriptor"]),
        "word_form": str(row["word_form"]),
        "due_at": str(row["due_at"]),
        "fsrs_state": int(row["fsrs_state"]),
        "counts": counts,
    }


def _apply_review(
    connection: sqlite3.Connection,
    *,
    study_card_id: int,
    rating_label: str,
    review_duration_ms: int | None,
) -> dict[str, Any]:
    from drills.fsrs.scheduler import rating_from_label

    scheduler = load_scheduler(connection)
    row = connection.execute(
        """
        SELECT fsrs_state, step, stability, difficulty, due_at, last_reviewed_at,
               first_reviewed_at
        FROM fsrs_schedules
        WHERE study_card_id = ? AND is_suspended = 0
        """,
        (study_card_id,),
    ).fetchone()
    if row is None:
        raise DatabaseError(f"fsrs schedule not found: {study_card_id}")

    card = card_from_schedule(study_card_id, row)
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
            study_card_id,
            rating,
            rating_label,
            reviewed_at,
            review_duration_ms
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            study_card_id,
            int(rating),
            label,
            reviewed_at.isoformat(),
            review_duration_ms,
        ),
    )
    update_cursor = connection.execute(
        """
        UPDATE fsrs_schedules
        SET
            due_at = ?,
            fsrs_state = ?,
            step = ?,
            stability = ?,
            difficulty = ?,
            first_reviewed_at = ?,
            last_reviewed_at = ?
        WHERE study_card_id = ?
        """,
        (
            snapshot["due_at"],
            snapshot["fsrs_state"],
            snapshot["step"],
            snapshot["stability"],
            snapshot["difficulty"],
            first_reviewed_at,
            reviewed_at.isoformat(),
            study_card_id,
        ),
    )
    if update_cursor.rowcount != 1:
        raise DatabaseError(f"fsrs schedule update failed: {study_card_id}")

    card_kind_row = connection.execute(
        "SELECT card_kind FROM study_cards WHERE id = ?",
        (study_card_id,),
    ).fetchone()
    card_kind = str(card_kind_row["card_kind"]) if card_kind_row else CARD_KIND_INFLECTION

    result: dict[str, Any] = {
        "study_card_id": study_card_id,
        "word_form_id": study_card_id,
        "direction": card_kind if card_kind in LEXICAL_CARD_KINDS else None,
        "card_kind": card_kind,
        "rating": label,
        "next_due_at": snapshot["due_at"],
        "fsrs_state": snapshot["fsrs_state"],
    }
    if card_kind == CARD_KIND_INFLECTION:
        result["counts"] = get_inflection_due_counts(connection)
    elif card_kind in LEXICAL_CARD_KINDS:
        result["counts"] = get_due_counts(connection, card_kind)
        result["mixed_counts"] = get_mixed_due_counts(connection)
    return result


def rate_card(
    connection: sqlite3.Connection,
    *,
    direction: str,
    study_card_id: int,
    rating_label: str,
    review_duration_ms: int | None,
) -> dict[str, Any]:
    validate_lexical_card_kind(direction)
    card_row = connection.execute(
        "SELECT card_kind FROM study_cards WHERE id = ?",
        (study_card_id,),
    ).fetchone()
    if card_row is None:
        raise DatabaseError(f"study card not found: {study_card_id}")
    if str(card_row["card_kind"]) != direction:
        raise DatabaseError(
            f"study card kind mismatch: expected {direction}, got {card_row['card_kind']}"
        )
    return _apply_review(
        connection,
        study_card_id=study_card_id,
        rating_label=rating_label,
        review_duration_ms=review_duration_ms,
    )


def rate_inflection_card(
    connection: sqlite3.Connection,
    *,
    word_form_id: int,
    rating_label: str,
    review_duration_ms: int | None,
) -> dict[str, Any]:
    card_row = connection.execute(
        "SELECT card_kind FROM study_cards WHERE id = ?",
        (word_form_id,),
    ).fetchone()
    if card_row is None:
        raise DatabaseError(f"inflection study card not found: {word_form_id}")
    if str(card_row["card_kind"]) != CARD_KIND_INFLECTION:
        raise DatabaseError(f"study card is not inflection: {word_form_id}")
    return _apply_review(
        connection,
        study_card_id=word_form_id,
        rating_label=rating_label,
        review_duration_ms=review_duration_ms,
    )


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
        FROM study_cards
        WHERE id = ? AND card_kind = ?
        """,
        (word_form_id, CARD_KIND_INFLECTION),
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


def load_review_logs(connection: sqlite3.Connection) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT study_card_id, rating, reviewed_at, review_duration_ms
        FROM fsrs_review_logs
        ORDER BY reviewed_at, id
        """
    ).fetchall()
    return [
        review_log_from_row(int(row["study_card_id"]), row)
        for row in rows
    ]


def load_review_logs_for_card(
    connection: sqlite3.Connection,
    *,
    study_card_id: int,
) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT study_card_id, rating, reviewed_at, review_duration_ms
        FROM fsrs_review_logs
        WHERE study_card_id = ?
        ORDER BY reviewed_at, id
        """,
        (study_card_id,),
    ).fetchall()
    return [
        review_log_from_row(int(row["study_card_id"]), row)
        for row in rows
    ]


def load_inflection_review_logs(connection: sqlite3.Connection) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT rl.study_card_id, rl.rating, rl.reviewed_at, rl.review_duration_ms
        FROM fsrs_review_logs rl
        JOIN study_cards sc ON sc.id = rl.study_card_id
        WHERE sc.card_kind = ?
        ORDER BY rl.reviewed_at, rl.id
        """,
        (CARD_KIND_INFLECTION,),
    ).fetchall()
    return [
        review_log_from_row(int(row["study_card_id"]), row)
        for row in rows
    ]


def load_inflection_review_logs_for_card(
    connection: sqlite3.Connection,
    word_form_id: int,
) -> list[ReviewLog]:
    return load_review_logs_for_card(connection, study_card_id=word_form_id)


def count_study_cards_by_kind(connection: sqlite3.Connection, card_kind: str) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS count FROM study_cards WHERE card_kind = ?",
        (card_kind,),
    ).fetchone()
    return int(row["count"]) if row is not None else 0
