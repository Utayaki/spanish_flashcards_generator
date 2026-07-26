from __future__ import annotations

import sqlite3
from typing import Any

from fsrs import Card, Optimizer, Scheduler

from drills.inflection.fsrs_cards import (
    insert_inflection_card_snapshot,
    load_inflection_review_logs,
    load_inflection_review_logs_for_card,
    load_inflection_scheduler,
    save_inflection_scheduler,
)
from drills.fsrs.scheduler import card_snapshot, utc_now


def run_inflection_optimizer(connection: sqlite3.Connection) -> dict[str, Any]:
    review_logs = load_inflection_review_logs(connection)
    if not review_logs:
        return {
            "review_log_count": 0,
            "parameters_updated": False,
            "retention_updated": False,
            "cards_rescheduled": 0,
            "message": "No review history yet. Complete some reviews first.",
        }

    current_scheduler = load_inflection_scheduler(connection)
    optimizer = Optimizer(review_logs)
    optimal_params = optimizer.compute_optimal_parameters()

    retention_updated = False
    desired_retention = current_scheduler.desired_retention
    if len(review_logs) >= 512 and all(
        log.review_duration is not None for log in review_logs
    ):
        desired_retention = optimizer.compute_optimal_retention(optimal_params)
        retention_updated = True

    parameters_updated = list(optimal_params) != list(current_scheduler.parameters)
    new_scheduler = Scheduler(
        parameters=optimal_params,
        desired_retention=desired_retention,
        learning_steps=current_scheduler.learning_steps,
        relearning_steps=current_scheduler.relearning_steps,
        maximum_interval=current_scheduler.maximum_interval,
        enable_fuzzing=current_scheduler.enable_fuzzing,
    )
    save_inflection_scheduler(connection, new_scheduler)

    card_rows = connection.execute(
        "SELECT word_form_id, fsrs_card_json FROM inflection_fsrs_cards"
    ).fetchall()
    optimized_at = utc_now().isoformat()
    cards_rescheduled = 0
    for row in card_rows:
        word_form_id = int(row["word_form_id"])
        card = Card.from_json(str(row["fsrs_card_json"]))
        logs = load_inflection_review_logs_for_card(connection, word_form_id)
        if logs:
            rescheduled = new_scheduler.reschedule_card(card, logs)
        else:
            rescheduled = Card(card_id=word_form_id)
        snapshot = card_snapshot(rescheduled)
        cursor = connection.execute(
            """
            UPDATE inflection_fsrs_cards
            SET
                fsrs_card_json = ?,
                due_at = ?,
                fsrs_state = ?,
                step = ?,
                stability = ?,
                difficulty = ?
            WHERE word_form_id = ?
            """,
            (
                rescheduled.to_json(),
                snapshot["due_at"],
                snapshot["fsrs_state"],
                snapshot["step"],
                snapshot["stability"],
                snapshot["difficulty"],
                word_form_id,
            ),
        )
        if cursor.rowcount == 1:
            cards_rescheduled += 1
            insert_inflection_card_snapshot(
                connection,
                word_form_id=word_form_id,
                source="optimizer",
                captured_at=optimized_at,
                due_at=str(snapshot["due_at"]),
                fsrs_state=int(snapshot["fsrs_state"]),
                step=snapshot["step"],
                stability=snapshot["stability"],
                difficulty=snapshot["difficulty"],
            )

    return {
        "review_log_count": len(review_logs),
        "parameters_updated": parameters_updated,
        "retention_updated": retention_updated,
        "cards_rescheduled": cards_rescheduled,
        "message": (
            f"Updated inflection scheduler from {len(review_logs)} reviews "
            f"and rescheduled {cards_rescheduled} cards."
        ),
    }
