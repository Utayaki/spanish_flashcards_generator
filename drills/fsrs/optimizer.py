from __future__ import annotations

import sqlite3
from typing import Any

from fsrs import Card, Optimizer, Scheduler

from drills.fsrs.cards import (
    load_review_logs,
    load_review_logs_for_card,
    load_scheduler,
    save_scheduler,
)
from drills.fsrs.scheduler import card_snapshot


def run_optimizer(connection: sqlite3.Connection) -> dict[str, Any]:
    review_logs = load_review_logs(connection)
    if not review_logs:
        return {
            "review_log_count": 0,
            "parameters_updated": False,
            "retention_updated": False,
            "cards_rescheduled": 0,
            "message": "No review history yet. Complete some reviews first.",
        }

    current_scheduler = load_scheduler(connection)
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
    save_scheduler(connection, new_scheduler)

    card_rows = connection.execute(
        "SELECT direction, study_card_id, fsrs_card_json FROM fsrs_cards"
    ).fetchall()
    cards_rescheduled = 0
    for row in card_rows:
        direction = str(row["direction"])
        study_card_id = int(row["study_card_id"])
        card = Card.from_json(str(row["fsrs_card_json"]))
        logs = load_review_logs_for_card(
            connection,
            direction=direction,
            study_card_id=study_card_id,
        )
        if logs:
            rescheduled = new_scheduler.reschedule_card(card, logs)
        else:
            rescheduled = Card(card_id=study_card_id)
        snapshot = card_snapshot(rescheduled)
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
                last_reviewed_at = ?
            WHERE direction = ? AND study_card_id = ?
            """,
            (
                rescheduled.to_json(),
                snapshot["due_at"],
                snapshot["fsrs_state"],
                snapshot["step"],
                snapshot["stability"],
                snapshot["difficulty"],
                snapshot["last_reviewed_at"],
                direction,
                study_card_id,
            ),
        )
        cards_rescheduled += 1

    message = "Optimizer finished."
    if len(review_logs) < 512:
        message = (
            "Parameters updated from available history. "
            "Retention optimization requires at least 512 reviews with durations."
        )

    return {
        "review_log_count": len(review_logs),
        "parameters_updated": parameters_updated or True,
        "retention_updated": retention_updated,
        "cards_rescheduled": cards_rescheduled,
        "desired_retention": desired_retention,
        "message": message,
    }
