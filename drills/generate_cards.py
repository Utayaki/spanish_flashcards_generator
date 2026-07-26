from __future__ import annotations

import sqlite3
from pathlib import Path

from fsrs import Card

from drills.errors import DatabaseError
from drills.fsrs.cards import DIRECTION_ENGLISH_TO_SPANISH, DIRECTION_SPANISH_TO_ENGLISH
from drills.fsrs.scheduler import card_snapshot, default_scheduler

COLLECTION_SCHEMA_PATH = Path(__file__).resolve().parent / "collection_schema.sql"

TYPE_LABELS = {
    "noun": "Noun",
    "verb": "Verb",
    "adjective": "Adjective",
    "other": "Other",
}


def _format_typed_explanation(lexical_type: str, explanation: str) -> str:
    label = TYPE_LABELS.get(lexical_type, lexical_type.title())
    return f"{label}: {explanation}"


def _format_back(items: list[sqlite3.Row]) -> str:
    blocks: list[str] = []
    for item in items:
        lexical_type = str(item["lexical_item_type"])
        blocks.append(_format_typed_explanation(lexical_type, str(item["explanation"])))
    return "\n\n".join(blocks)


def _insert_fsrs_card(
    connection: sqlite3.Connection,
    *,
    direction: str,
    study_card_id: int,
) -> None:
    fsrs_card = Card(card_id=study_card_id)
    snapshot = card_snapshot(fsrs_card)
    connection.execute(
        """
        INSERT INTO fsrs_cards (
            direction,
            study_card_id,
            fsrs_card_json,
            due_at,
            fsrs_state,
            step,
            stability,
            difficulty
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            direction,
            study_card_id,
            fsrs_card.to_json(),
            snapshot["due_at"],
            snapshot["fsrs_state"],
            snapshot["step"],
            snapshot["stability"],
            snapshot["difficulty"],
        ),
    )


def deep_copy_lexical_items(
    source_connection: sqlite3.Connection,
    destination_connection: sqlite3.Connection,
) -> int:
    rows = source_connection.execute(
        """
        SELECT headword, explanation, lexical_item_type, created_at, updated_at
        FROM lexical_items
        ORDER BY headword COLLATE NOCASE, id
        """
    ).fetchall()

    for row in rows:
        destination_connection.execute(
            """
            INSERT INTO lexical_items (
                headword,
                explanation,
                lexical_item_type,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["headword"],
                row["explanation"],
                row["lexical_item_type"],
                row["created_at"],
                row["updated_at"],
            ),
        )

    return len(rows)


def generate_spanish_to_english_fsrs_cards(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        """
        SELECT headword, explanation, lexical_item_type
        FROM lexical_items
        ORDER BY headword COLLATE NOCASE, id
        """
    ).fetchall()

    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        key = str(row["headword"]).casefold()
        groups.setdefault(key, []).append(row)

    created = 0
    for items in groups.values():
        front = str(items[0]["headword"])
        back = _format_back(items)
        cursor = connection.execute(
            """
            INSERT INTO spanish_to_english_fsrs_cards (front, back)
            VALUES (?, ?)
            """,
            (front, back),
        )
        study_card_id = int(cursor.lastrowid)
        _insert_fsrs_card(
            connection,
            direction=DIRECTION_SPANISH_TO_ENGLISH,
            study_card_id=study_card_id,
        )
        created += 1

    return created


def generate_english_to_spanish_fsrs_cards(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        """
        SELECT headword, explanation, lexical_item_type
        FROM lexical_items
        ORDER BY id
        """
    ).fetchall()

    created = 0
    for row in rows:
        front = _format_typed_explanation(
            str(row["lexical_item_type"]),
            str(row["explanation"]),
        )
        back = str(row["headword"])
        cursor = connection.execute(
            """
            INSERT INTO english_to_spanish_fsrs_cards (front, back)
            VALUES (?, ?)
            """,
            (front, back),
        )
        study_card_id = int(cursor.lastrowid)
        _insert_fsrs_card(
            connection,
            direction=DIRECTION_ENGLISH_TO_SPANISH,
            study_card_id=study_card_id,
        )
        created += 1

    return created


def seed_scheduler(connection: sqlite3.Connection) -> None:
    scheduler = default_scheduler()
    connection.execute(
        """
        INSERT INTO fsrs_scheduler (id, scheduler_json)
        VALUES (1, ?)
        """,
        (scheduler.to_json(),),
    )


def generate_collection_db(word_bank_path: Path, snapshot_path: Path) -> dict[str, int]:
    if not word_bank_path.is_file():
        raise DatabaseError(f"word bank database not found: {word_bank_path}")
    if not COLLECTION_SCHEMA_PATH.is_file():
        raise DatabaseError(f"collection schema not found: {COLLECTION_SCHEMA_PATH}")

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_path.exists():
        snapshot_path.unlink()

    schema_sql = COLLECTION_SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(f"file:{word_bank_path}?mode=ro", uri=True) as source:
        source.row_factory = sqlite3.Row
        with sqlite3.connect(snapshot_path) as destination:
            destination.row_factory = sqlite3.Row
            destination.execute("PRAGMA foreign_keys = ON")
            destination.executescript(schema_sql)
            lexical_item_count = deep_copy_lexical_items(source, destination)
            seed_scheduler(destination)
            spanish_to_english_card_count = generate_spanish_to_english_fsrs_cards(
                destination
            )
            english_to_spanish_card_count = generate_english_to_spanish_fsrs_cards(
                destination
            )
            destination.commit()

    return {
        "lexical_item_count": lexical_item_count,
        "spanish_to_english_card_count": spanish_to_english_card_count,
        "english_to_spanish_card_count": english_to_spanish_card_count,
    }
