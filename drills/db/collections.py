from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from drills.db.connection import DrillsConnectionMixin, connect, row_to_dict
from drills.errors import DatabaseError
from drills.fsrs.cards import (
    CARD_KIND_ADJECTIVE_INFLECTION_TYPE,
    CARD_KIND_ENGLISH_TO_SPANISH,
    CARD_KIND_INFLECTION,
    CARD_KIND_NOUN_GENDER,
    CARD_KIND_SPANISH_TO_ENGLISH,
)

_COLLECTION_FILENAME_RE = re.compile(r"^(\d{3})_\d{4}_\d{2}_\d{2}$")
_SNAPSHOT_SEQ_RE = re.compile(r"^(\d{3})_")


def collection_sequence_label(
    snapshot_filename: str,
    *,
    collection_id: int,
    snapshot_path: str | None = None,
) -> str:
    match = _SNAPSHOT_SEQ_RE.match(snapshot_filename)
    if match:
        return match.group(1)
    if snapshot_path is not None:
        stem = Path(snapshot_path).stem
        match = _SNAPSHOT_SEQ_RE.match(stem)
        if match:
            return match.group(1)
    return f"{collection_id:03d}"


def format_collection_subtitle(sequence_label: str, created_at: str) -> str:
    try:
        if created_at.endswith("Z"):
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(created_at)
    except ValueError:
        return sequence_label
    formatted_date = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    return f"{sequence_label} - {formatted_date}"


class CollectionsRepository(DrillsConnectionMixin):
    def list_collections(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, snapshot_filename, display_name, created_at, snapshot_path
                FROM drill_collections
                ORDER BY id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_collection(self, collection_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, snapshot_filename, display_name, created_at, snapshot_path
                FROM drill_collections
                WHERE id = ?
                """,
                (collection_id,),
            ).fetchone()
        return row_to_dict(row)

    def next_snapshot_filename(self, connection: sqlite3.Connection) -> str:
        rows = connection.execute(
            """
            SELECT snapshot_filename, snapshot_path
            FROM drill_collections
            """
        ).fetchall()
        max_number = 0
        for row in rows:
            filename = row["snapshot_filename"]
            if filename:
                stem = str(filename)
            else:
                stem = Path(str(row["snapshot_path"])).stem
            match = _COLLECTION_FILENAME_RE.match(stem)
            if match:
                max_number = max(max_number, int(match.group(1)))
        utc_date = datetime.now(timezone.utc).strftime("%Y_%m_%d")
        return f"{max_number + 1:03d}_{utc_date}"

    def insert_collection(
        self,
        connection: sqlite3.Connection,
        *,
        snapshot_filename: str,
        display_name: str,
        snapshot_path: str,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO drill_collections (
                snapshot_filename,
                display_name,
                snapshot_path
            )
            VALUES (?, ?, ?)
            """,
            (snapshot_filename, display_name, snapshot_path),
        )
        return int(cursor.lastrowid)

    def update_snapshot_path(
        self,
        connection: sqlite3.Connection,
        collection_id: int,
        snapshot_path: str,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE drill_collections
            SET snapshot_path = ?
            WHERE id = ?
            """,
            (snapshot_path, collection_id),
        )
        if cursor.rowcount != 1:
            raise DatabaseError(f"collection not found: {collection_id}")

    def update_collection_display_name(
        self,
        connection: sqlite3.Connection,
        collection_id: int,
        display_name: str,
    ) -> None:
        cleaned = display_name.strip()
        if not cleaned:
            raise DatabaseError("collection display name cannot be empty")
        try:
            cursor = connection.execute(
                """
                UPDATE drill_collections
                SET display_name = ?
                WHERE id = ?
                """,
                (cleaned, collection_id),
            )
        except sqlite3.IntegrityError as exc:
            raise DatabaseError("collection display name already exists") from exc
        if cursor.rowcount != 1:
            raise DatabaseError(f"collection not found: {collection_id}")

    def delete_collection(self, collection_id: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM drill_collections WHERE id = ?",
                (collection_id,),
            )
            return cursor.rowcount == 1


def _has_study_cards_table(snapshot_path: Path) -> bool:
    if not snapshot_path.is_file():
        return False
    with sqlite3.connect(snapshot_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM sqlite_master
            WHERE type = 'table' AND name = 'study_cards'
            """
        ).fetchone()
        return row is not None and int(row[0]) > 0


def _legacy_table_for_kind(card_kind: str) -> str | None:
    return {
        CARD_KIND_SPANISH_TO_ENGLISH: "spanish_to_english_fsrs_cards",
        CARD_KIND_ENGLISH_TO_SPANISH: "english_to_spanish_fsrs_cards",
        CARD_KIND_NOUN_GENDER: "noun_gender_fsrs_cards",
        CARD_KIND_ADJECTIVE_INFLECTION_TYPE: "adjective_inflection_type_fsrs_cards",
        CARD_KIND_INFLECTION: "inflection_word_forms",
    }.get(card_kind)


def _count_legacy_table(snapshot_path: Path, card_kind: str) -> int:
    table_name = _legacy_table_for_kind(card_kind)
    if table_name is None:
        return 0
    with sqlite3.connect(snapshot_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        if row is None or int(row[0]) == 0:
            return 0
        count_row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(count_row[0]) if count_row is not None else 0


def count_cards_by_kind(snapshot_path: Path, card_kind: str) -> int:
    if not snapshot_path.is_file():
        raise DatabaseError(f"snapshot file not found: {snapshot_path}")
    if not _has_study_cards_table(snapshot_path):
        return _count_legacy_table(snapshot_path, card_kind)
    with connect(snapshot_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM study_cards WHERE card_kind = ?",
            (card_kind,),
        ).fetchone()
        return int(row["count"]) if row is not None else 0


def count_lexical_items(snapshot_path: Path) -> int:
    return count_cards_by_kind(snapshot_path, CARD_KIND_ENGLISH_TO_SPANISH)


def count_spanish_to_english_cards(snapshot_path: Path) -> int:
    return count_cards_by_kind(snapshot_path, CARD_KIND_SPANISH_TO_ENGLISH)


def count_english_to_spanish_cards(snapshot_path: Path) -> int:
    return count_cards_by_kind(snapshot_path, CARD_KIND_ENGLISH_TO_SPANISH)


def count_noun_gender_cards(snapshot_path: Path) -> int:
    return count_cards_by_kind(snapshot_path, CARD_KIND_NOUN_GENDER)


def count_adjective_inflection_type_cards(snapshot_path: Path) -> int:
    return count_cards_by_kind(snapshot_path, CARD_KIND_ADJECTIVE_INFLECTION_TYPE)


def count_inflection_drill_word_forms(snapshot_path: Path) -> int:
    return count_cards_by_kind(snapshot_path, CARD_KIND_INFLECTION)
