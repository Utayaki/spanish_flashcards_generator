from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fsrs import Card, Rating, Scheduler


RATING_BY_LABEL = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
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


def new_fsrs_card(drill_card_id: int) -> Card:
    return Card(card_id=drill_card_id)


def rating_from_label(label: str) -> Rating:
    normalized = label.strip().casefold()
    if normalized not in RATING_BY_LABEL:
        raise ValueError("rating must be one of: again, hard, good, easy")
    return RATING_BY_LABEL[normalized]


def rating_label_from_int(value: int) -> str:
    return {
        1: "again",
        2: "hard",
        3: "good",
        4: "easy",
    }[value]


def fsrs_card_snapshot(card: Card) -> dict[str, Any]:
    return {
        "due_at": card.due.astimezone(timezone.utc).isoformat(),
        "fsrs_state": str(card.state),
        "stability": getattr(card, "stability", None),
        "difficulty": getattr(card, "difficulty", None),
        "elapsed_days": getattr(card, "elapsed_days", None),
        "scheduled_days": getattr(card, "scheduled_days", None),
        "reps": getattr(card, "reps", 0),
        "lapses": getattr(card, "lapses", 0),
        "last_reviewed_at": (
            card.last_review.astimezone(timezone.utc).isoformat()
            if getattr(card, "last_review", None)
            else None
        ),
    }
