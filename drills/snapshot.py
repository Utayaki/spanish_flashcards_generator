from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from drills.db.collections import count_lexical_items
from drills.db.database import DrillsDatabase
from drills.errors import DatabaseError

COLLECTIONS_DIR_NAME = "drill_collections"


def snapshot_relative_path(collection_id: int) -> str:
    return f"{COLLECTIONS_DIR_NAME}/{collection_id}.db"


def backup_word_bank(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        destination_path.unlink()

    with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as source:
        with sqlite3.connect(destination_path) as destination:
            source.backup(destination)


def create_collection_from_word_bank(
    word_bank_path: Path,
    drill_db: DrillsDatabase,
    *,
    project_root: Path,
) -> dict[str, Any]:
    if not word_bank_path.is_file():
        raise DatabaseError(f"word bank database not found: {word_bank_path}")

    collections_dir = project_root / COLLECTIONS_DIR_NAME
    collections_dir.mkdir(parents=True, exist_ok=True)

    collection_id: int | None = None
    snapshot_path: Path | None = None

    try:
        with drill_db.transaction() as connection:
            name = drill_db.next_collection_name(connection)
            placeholder_path = f"__pending__{name}"
            collection_id = drill_db.insert_collection(
                connection,
                name=name,
                snapshot_path=placeholder_path,
            )
            snapshot_rel = snapshot_relative_path(collection_id)
            drill_db.update_snapshot_path(connection, collection_id, snapshot_rel)

        snapshot_path = project_root / snapshot_rel
        backup_word_bank(word_bank_path, snapshot_path)

        item_count = count_lexical_items(snapshot_path)
        collection = drill_db.get_collection(collection_id)
        if collection is None:
            raise DatabaseError(f"collection not found after create: {collection_id}")

        return {
            "id": collection_id,
            "name": collection["name"],
            "created_at": collection["created_at"],
            "item_count": item_count,
        }
    except Exception:
        if snapshot_path is not None and snapshot_path.exists():
            snapshot_path.unlink()
        if collection_id is not None:
            drill_db.delete_collection(collection_id)
        raise


def collection_with_item_count(
    collection: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    snapshot_path = project_root / str(collection["snapshot_path"])
    item_count = count_lexical_items(snapshot_path)
    return {
        "id": int(collection["id"]),
        "name": str(collection["name"]),
        "created_at": str(collection["created_at"]),
        "item_count": item_count,
    }
