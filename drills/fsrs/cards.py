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

LEXICAL_CARD_TABLES: dict[str, str] = {
    CARD_KIND_SPANISH_TO_ENGLISH: "spanish_to_english_cards",
    CARD_KIND_ENGLISH_TO_SPANISH: "english_to_spanish_cards",
    CARD_KIND_NOUN_GENDER: "noun_gender_cards",
    CARD_KIND_ADJECTIVE_INFLECTION_TYPE: "adjective_inflection_type_cards",
}


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


def _lexical_table(card_kind: str) -> str:
    validate_lexical_card_kind(card_kind)
    return LEXICAL_CARD_TABLES[card_kind]


def _new_card_kind_order_sql() -> str:
    when_clauses = "\n".join(
        f"    WHEN due_cards.card_kind = '{card_kind}' THEN {index}"
        for index, card_kind in enumerate(DRILL_KIND_ORDER)
    )
    fallback = len(DRILL_KIND_ORDER)
    return f"""CASE
    WHEN due_cards.first_reviewed_at IS NOT NULL THEN 0
{when_clauses}
    ELSE {fallback}
END"""


def _mixed_due_cards_subquery() -> str:
    unions = []
    for card_kind in DRILL_KIND_ORDER:
        table = LEXICAL_CARD_TABLES[card_kind]
        unions.append(
            f"""
            SELECT
                c.fsrs_card_id,
                '{card_kind}' AS card_kind,
                c.front,
                c.back,
                fs.due_at,
                fs.fsrs_state,
                fs.first_reviewed_at
            FROM fsrs_schedules fs
            JOIN {table} c ON c.fsrs_card_id = fs.fsrs_card_id
            WHERE fs.is_suspended = 0 AND fs.due_at <= ?
            """
        )
    return "\nUNION ALL\n".join(unions)


def insert_fsrs_card(connection: sqlite3.Connection) -> int:
    cursor = connection.execute("INSERT INTO fsrs_cards DEFAULT VALUES")
    return int(cursor.lastrowid)


def insert_spanish_to_english_card(
    connection: sqlite3.Connection,
    *,
    front: str,
    back: str,
) -> int:
    fsrs_card_id = insert_fsrs_card(connection)
    connection.execute(
        """
        INSERT INTO spanish_to_english_cards (fsrs_card_id, front, back)
        VALUES (?, ?, ?)
        """,
        (fsrs_card_id, front, back),
    )
    seed_fsrs_schedule(connection, fsrs_card_id)
    return fsrs_card_id


def insert_english_to_spanish_card(
    connection: sqlite3.Connection,
    *,
    front: str,
    back: str,
) -> int:
    fsrs_card_id = insert_fsrs_card(connection)
    connection.execute(
        """
        INSERT INTO english_to_spanish_cards (fsrs_card_id, front, back)
        VALUES (?, ?, ?)
        """,
        (fsrs_card_id, front, back),
    )
    seed_fsrs_schedule(connection, fsrs_card_id)
    return fsrs_card_id


def insert_noun_gender_card(
    connection: sqlite3.Connection,
    *,
    front: str,
    back: str,
) -> int:
    fsrs_card_id = insert_fsrs_card(connection)
    connection.execute(
        """
        INSERT INTO noun_gender_cards (fsrs_card_id, front, back)
        VALUES (?, ?, ?)
        """,
        (fsrs_card_id, front, back),
    )
    seed_fsrs_schedule(connection, fsrs_card_id)
    return fsrs_card_id


def insert_adjective_inflection_type_card(
    connection: sqlite3.Connection,
    *,
    front: str,
    back: str,
) -> int:
    fsrs_card_id = insert_fsrs_card(connection)
    connection.execute(
        """
        INSERT INTO adjective_inflection_type_cards (fsrs_card_id, front, back)
        VALUES (?, ?, ?)
        """,
        (fsrs_card_id, front, back),
    )
    seed_fsrs_schedule(connection, fsrs_card_id)
    return fsrs_card_id


def insert_inflection_lexical_item(
    connection: sqlite3.Connection,
    *,
    headword: str,
    explanation: str,
    lexical_item_type: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO inflection_lexical_items (headword, explanation, lexical_item_type)
        VALUES (?, ?, ?)
        """,
        (headword, explanation, lexical_item_type),
    )
    return int(cursor.lastrowid)


def insert_inflection_card(
    connection: sqlite3.Connection,
    *,
    lexical_item_id: int,
    word_form: str,
    form_descriptor: str,
) -> int:
    fsrs_card_id = insert_fsrs_card(connection)
    connection.execute(
        """
        INSERT INTO inflection_cards (
            fsrs_card_id,
            lexical_item_id,
            word_form,
            form_descriptor
        )
        VALUES (?, ?, ?, ?)
        """,
        (fsrs_card_id, lexical_item_id, word_form, form_descriptor),
    )
    seed_fsrs_schedule(connection, fsrs_card_id)
    return fsrs_card_id


def seed_fsrs_schedule(connection: sqlite3.Connection, fsrs_card_id: int) -> None:
    fsrs_card = Card(card_id=fsrs_card_id)
    snapshot = card_snapshot(fsrs_card)
    connection.execute(
        """
        INSERT INTO fsrs_schedules (
            fsrs_card_id,
            due_at,
            fsrs_state,
            step,
            stability,
            difficulty
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            fsrs_card_id,
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
    params: list[Any] = [now, now]
    if card_kind is None:
        table_joins = "\nUNION ALL\n".join(
            f"""
            SELECT fs.total, fs.new_cards, fs.due, fs.future
            FROM (
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN fs2.first_reviewed_at IS NULL THEN 1 ELSE 0 END) AS new_cards,
                    SUM(
                        CASE
                            WHEN fs2.first_reviewed_at IS NOT NULL AND fs2.due_at <= ? THEN 1
                            ELSE 0
                        END
                    ) AS due,
                    SUM(
                        CASE
                            WHEN fs2.first_reviewed_at IS NOT NULL AND fs2.due_at > ? THEN 1
                            ELSE 0
                        END
                    ) AS future
                FROM fsrs_schedules fs2
                JOIN {table} c ON c.fsrs_card_id = fs2.fsrs_card_id
                WHERE fs2.is_suspended = 0
            ) fs
            """
            for table in LEXICAL_CARD_TABLES.values()
        )
        query = f"""
            SELECT
                SUM(total) AS total,
                SUM(new_cards) AS new_cards,
                SUM(due) AS due,
                SUM(future) AS future
            FROM (
                {table_joins}
            )
        """
        return query, tuple([now, now] * len(LEXICAL_CARD_TABLES))

    table = _lexical_table(card_kind)
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
        JOIN {table} c ON c.fsrs_card_id = fs.fsrs_card_id
        WHERE fs.is_suspended = 0
    """
    return query, tuple(params)


def _inflection_schedule_count_query() -> tuple[str, tuple[Any, ...]]:
    now = utc_iso()
    query = """
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
        JOIN inflection_cards ic ON ic.fsrs_card_id = fs.fsrs_card_id
        WHERE fs.is_suspended = 0
    """
    return query, (now, now)


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
    query, params = _schedule_count_query(card_kind=None)
    row = connection.execute(query, params).fetchone()
    return _counts_from_row(row)


def get_inflection_due_counts(connection: sqlite3.Connection) -> dict[str, int]:
    query, params = _inflection_schedule_count_query()
    row = connection.execute(query, params).fetchone()
    return _counts_from_row(row)


def _lexical_card_payload(row: sqlite3.Row, *, card_kind: str) -> dict[str, Any]:
    fsrs_card_id = int(row["fsrs_card_id"])
    return {
        "study_card_id": fsrs_card_id,
        "direction": card_kind,
        "card_kind": card_kind,
        "front": str(row["front"]),
        "back": str(row["back"]),
        "due_at": str(row["due_at"]),
        "fsrs_state": int(row["fsrs_state"]),
    }


def get_next_due(connection: sqlite3.Connection, card_kind: str) -> dict[str, Any] | None:
    card_kind = validate_lexical_card_kind(card_kind)
    table = _lexical_table(card_kind)
    now = utc_iso()
    row = connection.execute(
        f"""
        SELECT
            c.fsrs_card_id,
            c.front,
            c.back,
            fs.due_at,
            fs.fsrs_state
        FROM fsrs_schedules fs
        JOIN {table} c ON c.fsrs_card_id = fs.fsrs_card_id
        WHERE fs.is_suspended = 0
          AND fs.due_at <= ?
        ORDER BY
          CASE WHEN fs.first_reviewed_at IS NULL THEN 1 ELSE 0 END,
          RANDOM()
        LIMIT 1
        """,
        (now,),
    ).fetchone()
    if row is None:
        return None

    counts = get_due_counts(connection, card_kind)
    return {**_lexical_card_payload(row, card_kind=card_kind), "counts": counts}


def get_next_due_mixed(connection: sqlite3.Connection) -> dict[str, Any] | None:
    now = utc_iso()
    kind_order_sql = _new_card_kind_order_sql()
    row = connection.execute(
        f"""
        SELECT
            due_cards.fsrs_card_id,
            due_cards.card_kind,
            due_cards.front,
            due_cards.back,
            due_cards.due_at,
            due_cards.fsrs_state
        FROM (
            {_mixed_due_cards_subquery()}
        ) due_cards
        ORDER BY
          CASE WHEN due_cards.first_reviewed_at IS NULL THEN 1 ELSE 0 END,
          {kind_order_sql},
          RANDOM()
        LIMIT 1
        """,
        (now, now, now, now),
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
            ic.fsrs_card_id,
            li.headword,
            li.explanation,
            ic.form_descriptor,
            ic.word_form,
            fs.due_at,
            fs.fsrs_state
        FROM fsrs_schedules fs
        JOIN inflection_cards ic ON ic.fsrs_card_id = fs.fsrs_card_id
        JOIN inflection_lexical_items li ON li.id = ic.lexical_item_id
        WHERE fs.is_suspended = 0
          AND fs.due_at <= ?
        ORDER BY
          CASE WHEN fs.first_reviewed_at IS NULL THEN 1 ELSE 0 END,
          RANDOM()
        LIMIT 1
        """,
        (now,),
    ).fetchone()
    if row is None:
        return None

    fsrs_card_id = int(row["fsrs_card_id"])
    counts = get_inflection_due_counts(connection)
    return {
        "study_card_id": fsrs_card_id,
        "word_form_id": fsrs_card_id,
        "headword": str(row["headword"]),
        "explanation": str(row["explanation"]),
        "form_descriptor": str(row["form_descriptor"]),
        "word_form": str(row["word_form"]),
        "due_at": str(row["due_at"]),
        "fsrs_state": int(row["fsrs_state"]),
        "counts": counts,
    }


def _resolve_card_kind(connection: sqlite3.Connection, fsrs_card_id: int) -> str:
    for card_kind, table in LEXICAL_CARD_TABLES.items():
        row = connection.execute(
            f"SELECT fsrs_card_id FROM {table} WHERE fsrs_card_id = ?",
            (fsrs_card_id,),
        ).fetchone()
        if row is not None:
            return card_kind
    row = connection.execute(
        "SELECT fsrs_card_id FROM inflection_cards WHERE fsrs_card_id = ?",
        (fsrs_card_id,),
    ).fetchone()
    if row is not None:
        return CARD_KIND_INFLECTION
    raise DatabaseError(f"fsrs card not found: {fsrs_card_id}")


def _apply_review(
    connection: sqlite3.Connection,
    *,
    fsrs_card_id: int,
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
        WHERE fsrs_card_id = ? AND is_suspended = 0
        """,
        (fsrs_card_id,),
    ).fetchone()
    if row is None:
        raise DatabaseError(f"fsrs schedule not found: {fsrs_card_id}")

    card = card_from_schedule(fsrs_card_id, row)
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
            fsrs_card_id,
            rating,
            rating_label,
            reviewed_at,
            review_duration_ms
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            fsrs_card_id,
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
        WHERE fsrs_card_id = ?
        """,
        (
            snapshot["due_at"],
            snapshot["fsrs_state"],
            snapshot["step"],
            snapshot["stability"],
            snapshot["difficulty"],
            first_reviewed_at,
            reviewed_at.isoformat(),
            fsrs_card_id,
        ),
    )
    if update_cursor.rowcount != 1:
        raise DatabaseError(f"fsrs schedule update failed: {fsrs_card_id}")

    card_kind = _resolve_card_kind(connection, fsrs_card_id)

    result: dict[str, Any] = {
        "study_card_id": fsrs_card_id,
        "word_form_id": fsrs_card_id,
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
    card_kind = _resolve_card_kind(connection, study_card_id)
    if card_kind != direction:
        raise DatabaseError(
            f"study card kind mismatch: expected {direction}, got {card_kind}"
        )
    return _apply_review(
        connection,
        fsrs_card_id=study_card_id,
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
    card_kind = _resolve_card_kind(connection, word_form_id)
    if card_kind != CARD_KIND_INFLECTION:
        raise DatabaseError(f"study card is not inflection: {word_form_id}")
    return _apply_review(
        connection,
        fsrs_card_id=word_form_id,
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
        FROM inflection_cards
        WHERE fsrs_card_id = ?
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


def load_review_logs(connection: sqlite3.Connection) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT fsrs_card_id, rating, reviewed_at, review_duration_ms
        FROM fsrs_review_logs
        ORDER BY reviewed_at, id
        """
    ).fetchall()
    return [
        review_log_from_row(int(row["fsrs_card_id"]), row)
        for row in rows
    ]


def load_review_logs_for_card(
    connection: sqlite3.Connection,
    *,
    study_card_id: int,
) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT fsrs_card_id, rating, reviewed_at, review_duration_ms
        FROM fsrs_review_logs
        WHERE fsrs_card_id = ?
        ORDER BY reviewed_at, id
        """,
        (study_card_id,),
    ).fetchall()
    return [
        review_log_from_row(int(row["fsrs_card_id"]), row)
        for row in rows
    ]


def load_inflection_review_logs(connection: sqlite3.Connection) -> list[ReviewLog]:
    rows = connection.execute(
        """
        SELECT rl.fsrs_card_id, rl.rating, rl.reviewed_at, rl.review_duration_ms
        FROM fsrs_review_logs rl
        JOIN inflection_cards ic ON ic.fsrs_card_id = rl.fsrs_card_id
        ORDER BY rl.reviewed_at, rl.id
        """
    ).fetchall()
    return [
        review_log_from_row(int(row["fsrs_card_id"]), row)
        for row in rows
    ]


def load_inflection_review_logs_for_card(
    connection: sqlite3.Connection,
    word_form_id: int,
) -> list[ReviewLog]:
    return load_review_logs_for_card(connection, study_card_id=word_form_id)


def count_fsrs_cards_by_kind(connection: sqlite3.Connection, card_kind: str) -> int:
    validate_card_kind(card_kind)
    if card_kind == CARD_KIND_INFLECTION:
        row = connection.execute("SELECT COUNT(*) AS count FROM inflection_cards").fetchone()
    else:
        table = _lexical_table(card_kind)
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"]) if row is not None else 0
