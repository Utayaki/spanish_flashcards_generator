from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from typing import Any

from fsrs import Card, Scheduler

from drills.fsrs.cards import (
    CARD_KIND_INFLECTION,
    CARD_KIND_TABLES,
    LEXICAL_CARD_KINDS,
    LEXICAL_CARD_TABLES,
    load_scheduler,
)
from drills.fsrs.scheduler import card_snapshot, parse_utc_datetime, review_log_from_row

DASHBOARD_RANGE_OPTIONS = (7, 30, 180)
DEFAULT_DASHBOARD_RANGE_DAYS = 30
FRAGILE_STABILITY_DAYS = 7.0
DURABLE_STABILITY_DAYS = 30.0


DASHBOARD_CARD_KINDS = frozenset(CARD_KIND_TABLES)


def validate_range_days(days: int) -> int:
    if days not in DASHBOARD_RANGE_OPTIONS:
        allowed = ", ".join(str(value) for value in DASHBOARD_RANGE_OPTIONS)
        raise ValueError(f"invalid range_days: {days}; expected one of: {allowed}")
    return days


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


def _memory_stage(stability: float | None) -> str:
    if stability is None:
        return "not_introduced"
    if stability < FRAGILE_STABILITY_DAYS:
        return "fragile"
    if stability < DURABLE_STABILITY_DAYS:
        return "developing"
    return "durable"


def _card_kind_join(card_kind: str) -> tuple[str, tuple[Any, ...]]:
    if card_kind == CARD_KIND_INFLECTION:
        return (
            "JOIN inflection_cards ic ON ic.fsrs_card_id = fs.fsrs_card_id",
            (),
        )
    if card_kind in LEXICAL_CARD_KINDS:
        table = LEXICAL_CARD_TABLES[card_kind]
        return (
            f"JOIN {table} c ON c.fsrs_card_id = fs.fsrs_card_id",
            (),
        )
    raise ValueError(f"invalid card_kind: {card_kind}")


def _build_replayed_snapshots(
    connection: sqlite3.Connection,
    *,
    scheduler: Scheduler,
    card_kind: str,
) -> dict[int, list[tuple[datetime, float | None]]]:
    join_clause, _ = _card_kind_join(card_kind)
    schedule_rows = connection.execute(
        f"""
        SELECT fs.fsrs_card_id, fs.created_at, fs.due_at, fs.fsrs_state, fs.step,
               fs.stability, fs.difficulty, fs.last_reviewed_at, fs.first_reviewed_at,
               fs.updated_at
        FROM fsrs_schedules fs
        {join_clause}
        WHERE fs.is_suspended = 0
        ORDER BY fs.fsrs_card_id
        """
    ).fetchall()

    snapshots: dict[int, list[tuple[datetime, float | None]]] = defaultdict(list)
    for schedule_row in schedule_rows:
        fsrs_card_id = int(schedule_row["fsrs_card_id"])
        created_at = parse_utc_datetime(str(schedule_row["created_at"]))
        snapshots[fsrs_card_id].append((created_at, None))

        log_rows = connection.execute(
            """
            SELECT fsrs_card_id, rating, reviewed_at, review_duration_ms
            FROM fsrs_review_logs
            WHERE fsrs_card_id = ?
            ORDER BY reviewed_at, id
            """,
            (fsrs_card_id,),
        ).fetchall()

        replayed_card = Card(card_id=fsrs_card_id)
        for log_row in log_rows:
            review_log = review_log_from_row(fsrs_card_id, log_row)
            replayed_card, _ = scheduler.review_card(
                card=replayed_card,
                rating=review_log.rating,
                review_datetime=review_log.review_datetime,
                review_duration=review_log.review_duration,
            )
            snapshot = card_snapshot(replayed_card)
            snapshots[fsrs_card_id].append(
                (
                    review_log.review_datetime.astimezone(timezone.utc),
                    snapshot["stability"],
                )
            )

        if not log_rows and schedule_row["first_reviewed_at"] is not None:
            captured_at = parse_utc_datetime(
                str(schedule_row["last_reviewed_at"] or schedule_row["updated_at"])
            )
            snapshots[fsrs_card_id].append(
                (
                    captured_at,
                    None if schedule_row["stability"] is None else float(schedule_row["stability"]),
                )
            )

    for fsrs_card_id in snapshots:
        snapshots[fsrs_card_id].sort(key=lambda item: item[0])
    return snapshots


def _memory_growth(
    connection: sqlite3.Connection,
    *,
    card_kind: str,
    local_tz: timezone,
    today: date,
    range_days: int,
) -> dict[str, Any]:
    join_clause, _ = _card_kind_join(card_kind)
    card_rows = connection.execute(
        f"""
        SELECT fs.fsrs_card_id
        FROM fsrs_schedules fs
        {join_clause}
        WHERE fs.is_suspended = 0
        ORDER BY fs.fsrs_card_id
        """
    ).fetchall()
    card_ids = [int(row["fsrs_card_id"]) for row in card_rows]

    scheduler = _scheduler_without_fuzzing(load_scheduler(connection))
    snapshots = _build_replayed_snapshots(
        connection,
        scheduler=scheduler,
        card_kind=card_kind,
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
    card_kind: str,
    local_tz: timezone,
    today: date,
    range_days: int,
) -> int | None:
    join_clause, _ = _card_kind_join(card_kind)
    join_clause = join_clause.replace("fs.fsrs_card_id", "rl.fsrs_card_id")

    start_day = today - timedelta(days=range_days - 1)
    start_utc = datetime.combine(start_day, time.min, tzinfo=local_tz).astimezone(
        timezone.utc
    )
    rows = connection.execute(
        f"""
        SELECT rl.reviewed_at
        FROM fsrs_review_logs rl
        {join_clause}
        WHERE rl.reviewed_at >= ?
        ORDER BY rl.reviewed_at
        """,
        (start_utc.isoformat(),),
    ).fetchall()
    daily_counts: dict[date, int] = defaultdict(int)
    for row in rows:
        local_day = parse_utc_datetime(str(row["reviewed_at"])).astimezone(local_tz).date()
        daily_counts[local_day] += 1
    active_counts = list(daily_counts.values())
    return round(median(active_counts)) if active_counts else None


def _forecast(
    connection: sqlite3.Connection,
    *,
    card_kind: str,
    local_tz: timezone,
    today: date,
    range_days: int,
) -> dict[str, Any]:
    join_clause, _ = _card_kind_join(card_kind)
    points = [
        {"date": (today + timedelta(days=offset)).isoformat(), "reviews": 0}
        for offset in range(range_days)
    ]
    counts_by_day = {date.fromisoformat(point["date"]): point for point in points}
    end_day = today + timedelta(days=range_days - 1)
    overdue = 0
    new_cards = 0

    rows = connection.execute(
        f"""
        SELECT fs.due_at, fs.first_reviewed_at
        FROM fsrs_schedules fs
        {join_clause}
        WHERE fs.is_suspended = 0
        """
    ).fetchall()
    for row in rows:
        if row["first_reviewed_at"] is None:
            new_cards += 1
            continue
        due_day = parse_utc_datetime(str(row["due_at"])).astimezone(local_tz).date()
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
            card_kind=card_kind,
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
    if direction not in DASHBOARD_CARD_KINDS:
        raise ValueError(f"invalid direction: {direction}")
    validated_range_days = validate_range_days(range_days)
    local_tz = _local_timezone(timezone_offset_minutes)
    today = datetime.now(timezone.utc).astimezone(local_tz).date()
    return {
        "memory_growth": _memory_growth(
            connection,
            card_kind=direction,
            local_tz=local_tz,
            today=today,
            range_days=validated_range_days,
        ),
        "forecast": _forecast(
            connection,
            card_kind=direction,
            local_tz=local_tz,
            today=today,
            range_days=validated_range_days,
        ),
    }


def get_inflection_dashboard_analytics(
    connection: sqlite3.Connection,
    *,
    timezone_offset_minutes: int = 0,
    range_days: int = DEFAULT_DASHBOARD_RANGE_DAYS,
) -> dict[str, Any]:
    return get_dashboard_analytics(
        connection,
        direction=CARD_KIND_INFLECTION,
        timezone_offset_minutes=timezone_offset_minutes,
        range_days=range_days,
    )
