from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fsrs import Card, Rating, ReviewLog, Scheduler, State

FSRS_PARAMETER_COUNT = 21
PARAM_COLUMNS = [f"param_{index}" for index in range(FSRS_PARAMETER_COUNT)]

RATING_BY_LABEL = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}

RATING_LABEL_BY_INT = {
    1: "again",
    2: "hard",
    3: "good",
    4: "easy",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat()


def default_scheduler() -> Scheduler:
    return Scheduler(
        desired_retention=0.9,
        enable_fuzzing=True,
    )


def rating_from_label(label: str) -> Rating:
    normalized = label.strip().casefold()
    if normalized not in RATING_BY_LABEL:
        raise ValueError("rating must be one of: again, hard, good, easy")
    return RATING_BY_LABEL[normalized]


def rating_label_from_int(value: int) -> str:
    return RATING_LABEL_BY_INT[int(value)]


def _parse_utc_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def card_from_schedule(study_card_id: int, row: Any) -> Card:
    last_review = _parse_utc_datetime(row["last_reviewed_at"])
    due = _parse_utc_datetime(str(row["due_at"]))
    if due is None:
        raise ValueError(f"fsrs schedule missing due_at for study_card_id={study_card_id}")
    return Card(
        card_id=study_card_id,
        state=State(int(row["fsrs_state"])),
        step=row["step"],
        stability=row["stability"],
        difficulty=row["difficulty"],
        due=due,
        last_review=last_review,
    )


def review_log_from_row(study_card_id: int, row: Any) -> ReviewLog:
    reviewed_at = _parse_utc_datetime(str(row["reviewed_at"]))
    if reviewed_at is None:
        raise ValueError(f"review log missing reviewed_at for study_card_id={study_card_id}")
    return ReviewLog(
        card_id=study_card_id,
        rating=Rating(int(row["rating"])),
        review_datetime=reviewed_at,
        review_duration=row["review_duration_ms"],
    )


def card_snapshot(card: Card) -> dict[str, Any]:
    return {
        "due_at": card.due.astimezone(timezone.utc).isoformat(),
        "fsrs_state": int(card.state),
        "step": card.step,
        "stability": card.stability,
        "difficulty": card.difficulty,
        "last_reviewed_at": (
            card.last_review.astimezone(timezone.utc).isoformat()
            if card.last_review is not None
            else None
        ),
    }


def scheduler_row_values(scheduler: Scheduler) -> tuple[Any, ...]:
    return (
        scheduler.desired_retention,
        int(scheduler.enable_fuzzing),
        scheduler.maximum_interval,
        *scheduler.parameters,
    )


def learning_step_rows(scheduler: Scheduler) -> list[tuple[int, int]]:
    return [
        (index, int(step.total_seconds()))
        for index, step in enumerate(scheduler.learning_steps)
    ]


def relearning_step_rows(scheduler: Scheduler) -> list[tuple[int, int]]:
    return [
        (index, int(step.total_seconds()))
        for index, step in enumerate(scheduler.relearning_steps)
    ]


def scheduler_from_db(
    scalar_row: Any,
    learning_rows: list[Any],
    relearning_rows: list[Any],
) -> Scheduler:
    parameters = tuple(float(scalar_row[column]) for column in PARAM_COLUMNS)
    learning_steps = tuple(
        timedelta(seconds=int(row["duration_seconds"])) for row in learning_rows
    )
    relearning_steps = tuple(
        timedelta(seconds=int(row["duration_seconds"])) for row in relearning_rows
    )
    return Scheduler(
        parameters=parameters,
        desired_retention=float(scalar_row["desired_retention"]),
        learning_steps=learning_steps,
        relearning_steps=relearning_steps,
        maximum_interval=int(scalar_row["maximum_interval"]),
        enable_fuzzing=bool(scalar_row["enable_fuzzing"]),
    )
