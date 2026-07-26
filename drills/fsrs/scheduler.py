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
