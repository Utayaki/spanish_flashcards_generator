from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from typing import Any

from fsrs import Card, ReviewLog, Scheduler

from drills.fsrs.cards import CARD_DIRECTIONS, insert_card_snapshot, load_scheduler
from drills.fsrs.scheduler import card_snapshot

DASHBOARD_RANGE_OPTIONS = (7, 30, 180)
DEFAULT_DASHBOARD_RANGE_DAYS = 30
FRAGILE_STABILITY_DAYS = 7.0
DURABLE_STABILITY_DAYS = 30.0


def validate_range_days(days: int) -> int:
    if days not in DASHBOARD_RANGE_OPTIONS:
        allowed = ", ".join(str(value) for value in DASHBOARD_RANGE_OPTIONS)
        raise ValueError(f"invalid range_days: {days}; expected one of: {allowed}")
    return days

SNAPSHOT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fsrs_card_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL CHECK (
        direction IN ('spanish_to_english', 'english_to_spanish')
    ),
    study_card_id INTEGER NOT NULL,
    review_log_id INTEGER,
    source TEXT NOT NULL CHECK (source IN ('created', 'review', 'optimizer', 'migration')),
    captured_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    fsrs_state INTEGER NOT NULL,
    step INTEGER,
    stability REAL,
    difficulty REAL,
    FOREIGN KEY (review_log_id) REFERENCES fsrs_review_logs(id) ON DELETE CASCADE,
    FOREIGN KEY (direction, study_card_id)
        REFERENCES fsrs_cards(direction, study_card_id) ON DELETE CASCADE,
    UNIQUE (direction, study_card_id, captured_at, source)
)
"""

SNAPSHOT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_fsrs_card_snapshots_history
ON fsrs_card_snapshots(direction, captured_at, study_card_id)
"""


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _local_timezone(offset_minutes: int) -> timezone:
    if not -840 <= offset_minutes <= 840:
        raise ValueError("timezone offset must be between -840 and 840 minutes")
    return timezone(timedelta(minutes=-offset_minutes))


def _scheduler_without_fuzzing(scheduler: Scheduler) -> Scheduler:
    return Scheduler(
        parameters=scheduler.parameters,
        desired_retention=scheduler.desired_retention,
        learning_steps=scheduler.learning_steps,
        relearning_steps=scheduler.relearning_steps,
        maximum_interval=scheduler.maximum_interval,
        enable_fuzzing=False,
    )


def _backfill_card(
    connection: sqlite3.Connection,
    scheduler: Scheduler,
    row: sqlite3.Row,
) -> None:
    direction = str(row["direction"])
    study_card_id = int(row["study_card_id"])
    created_at = str(row["created_at"])

    insert_card_snapshot(
        connection,
        direction=direction,
        study_card_id=study_card_id,
        source="migration",
        captured_at=created_at,
        due_at=created_at,
        fsrs_state=1,
        step=0,
        stability=None,
        difficulty=None,
    )

    log_rows = connection.execute(
        """
        SELECT id, review_log_json
        FROM fsrs_review_logs
        WHERE direction = ? AND study_card_id = ?
        ORDER BY reviewed_at, id
        """,
        (direction, study_card_id),
    ).fetchall()

    replayed_card = Card(card_id=study_card_id)
    for log_row in log_rows:
        review_log = ReviewLog.from_json(str(log_row["review_log_json"]))
        replayed_card, _ = scheduler.review_card(
            card=replayed_card,
            rating=review_log.rating,
            review_datetime=review_log.review_datetime,
            review_duration=review_log.review_duration,
        )
        snapshot = card_snapshot(replayed_card)
        insert_card_snapshot(
            connection,
            direction=direction,
            study_card_id=study_card_id,
            review_log_id=int(log_row["id"]),
            source="review",
            captured_at=review_log.review_datetime.isoformat(),
            due_at=str(snapshot["due_at"]),
            fsrs_state=int(snapshot["fsrs_state"]),
            step=snapshot["step"],
            stability=snapshot["stability"],
            difficulty=snapshot["difficulty"],
        )

    if not log_rows and row["first_reviewed_at"] is not None:
        captured_at = str(row["last_reviewed_at"] or row["updated_at"])
        insert_card_snapshot(
            connection,
            direction=direction,
            study_card_id=study_card_id,
            source="migration",
            captured_at=captured_at,
            due_at=str(row["due_at"]),
            fsrs_state=int(row["fsrs_state"]),
            step=row["step"],
            stability=row["stability"],
            difficulty=row["difficulty"],
        )


def ensure_fsrs_snapshot_storage(connection: sqlite3.Connection) -> None:
    connection.execute(SNAPSHOT_TABLE_SQL)
    connection.execute(SNAPSHOT_INDEX_SQL)
    missing_rows = connection.execute(
        """
        SELECT fc.*
        FROM fsrs_cards fc
        WHERE NOT EXISTS (
            SELECT 1
            FROM fsrs_card_snapshots snapshots
            WHERE snapshots.direction = fc.direction
              AND snapshots.study_card_id = fc.study_card_id
        )
        ORDER BY fc.direction, fc.study_card_id
        """
    ).fetchall()
    if not missing_rows:
        return

    scheduler = _scheduler_without_fuzzing(load_scheduler(connection))
    for row in missing_rows:
        _backfill_card(connection, scheduler, row)


def _memory_stage(stability: float | None) -> str:
    if stability is None:
        return "not_introduced"
    if stability < FRAGILE_STABILITY_DAYS:
        return "fragile"
    if stability < DURABLE_STABILITY_DAYS:
        return "developing"
    return "durable"


def _memory_growth(
    connection: sqlite3.Connection,
    *,
    direction: str,
    local_tz: timezone,
    today: date,
    range_days: int,
) -> dict[str, Any]:
    card_rows = connection.execute(
        """
        SELECT study_card_id
        FROM fsrs_cards
        WHERE direction = ? AND is_suspended = 0
        ORDER BY study_card_id
        """,
        (direction,),
    ).fetchall()
    card_ids = [int(row["study_card_id"]) for row in card_rows]

    snapshot_rows = connection.execute(
        """
        SELECT study_card_id, captured_at, stability
        FROM fsrs_card_snapshots
        WHERE direction = ?
        ORDER BY study_card_id, captured_at, id
        """,
        (direction,),
    ).fetchall()
    snapshots: dict[int, list[tuple[datetime, float | None]]] = defaultdict(list)
    for row in snapshot_rows:
        snapshots[int(row["study_card_id"])].append(
            (
                _parse_utc(str(row["captured_at"])),
                None if row["stability"] is None else float(row["stability"]),
            )
        )

    start_day = today - timedelta(days=range_days - 1)
    points: list[dict[str, Any]] = []
    indexes = {card_id: 0 for card_id in card_ids}
    latest: dict[int, float | None] = {card_id: None for card_id in card_ids}

    for day_offset in range(range_days):
        current_day = start_day + timedelta(days=day_offset)
        end_of_day_utc = datetime.combine(
            current_day,
            time.max,
            tzinfo=local_tz,
        ).astimezone(timezone.utc)
        counts = {
            "not_introduced": 0,
            "fragile": 0,
            "developing": 0,
            "durable": 0,
        }

        for card_id in card_ids:
            card_snapshots = snapshots.get(card_id, [])
            index = indexes[card_id]
            while index < len(card_snapshots) and card_snapshots[index][0] <= end_of_day_utc:
                latest[card_id] = card_snapshots[index][1]
                index += 1
            indexes[card_id] = index
            counts[_memory_stage(latest[card_id])] += 1

        points.append({"date": current_day.isoformat(), **counts})

    durable_change = 0
    if points:
        durable_change = int(points[-1]["durable"]) - int(points[0]["durable"])

    return {
        "days": range_days,
        "total": len(card_ids),
        "durable_change": durable_change,
        "points": points,
    }


def _review_pace(
    connection: sqlite3.Connection,
    *,
    direction: str,
    local_tz: timezone,
    today: date,
    range_days: int,
) -> int | None:
    start_day = today - timedelta(days=range_days - 1)
    start_utc = datetime.combine(start_day, time.min, tzinfo=local_tz).astimezone(
        timezone.utc
    )
    rows = connection.execute(
        """
        SELECT reviewed_at
        FROM fsrs_review_logs
        WHERE direction = ? AND reviewed_at >= ?
        ORDER BY reviewed_at
        """,
        (direction, start_utc.isoformat()),
    ).fetchall()
    daily_counts: dict[date, int] = defaultdict(int)
    for row in rows:
        local_day = _parse_utc(str(row["reviewed_at"])).astimezone(local_tz).date()
        daily_counts[local_day] += 1
    active_counts = list(daily_counts.values())
    return round(median(active_counts)) if active_counts else None


def _forecast(
    connection: sqlite3.Connection,
    *,
    direction: str,
    local_tz: timezone,
    today: date,
    range_days: int,
) -> dict[str, Any]:
    points = [
        {"date": (today + timedelta(days=offset)).isoformat(), "reviews": 0}
        for offset in range(range_days)
    ]
    counts_by_day = {date.fromisoformat(point["date"]): point for point in points}
    end_day = today + timedelta(days=range_days - 1)
    overdue = 0
    new_cards = 0

    rows = connection.execute(
        """
        SELECT due_at, first_reviewed_at
        FROM fsrs_cards
        WHERE direction = ? AND is_suspended = 0
        """,
        (direction,),
    ).fetchall()
    for row in rows:
        if row["first_reviewed_at"] is None:
            new_cards += 1
            continue
        due_day = _parse_utc(str(row["due_at"])).astimezone(local_tz).date()
        if due_day < today:
            overdue += 1
        elif due_day <= end_day:
            counts_by_day[due_day]["reviews"] += 1

    total = sum(int(point["reviews"]) for point in points)
    peak = max((int(point["reviews"]) for point in points), default=0)
    return {
        "days": range_days,
        "overdue": overdue,
        "new": new_cards,
        "scheduled_total": total,
        "peak": peak,
        "recent_daily_pace": _review_pace(
            connection,
            direction=direction,
            local_tz=local_tz,
            today=today,
            range_days=range_days,
        ),
        "points": points,
    }


def get_dashboard_analytics(
    connection: sqlite3.Connection,
    *,
    direction: str,
    timezone_offset_minutes: int = 0,
    range_days: int = DEFAULT_DASHBOARD_RANGE_DAYS,
) -> dict[str, Any]:
    if direction not in CARD_DIRECTIONS:
        raise ValueError(f"invalid direction: {direction}")
    validated_range_days = validate_range_days(range_days)
    local_tz = _local_timezone(timezone_offset_minutes)
    today = datetime.now(timezone.utc).astimezone(local_tz).date()
    return {
        "memory_growth": _memory_growth(
            connection,
            direction=direction,
            local_tz=local_tz,
            today=today,
            range_days=validated_range_days,
        ),
        "forecast": _forecast(
            connection,
            direction=direction,
            local_tz=local_tz,
            today=today,
            range_days=validated_range_days,
        ),
    }
