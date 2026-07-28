from __future__ import annotations

from pathlib import Path
from typing import Any

from drills.db.collections import (
    collection_sequence_label,
    count_adjective_inflection_type_cards,
    count_english_to_spanish_cards,
    count_inflection_drill_word_forms,
    count_lexical_items,
    count_noun_gender_cards,
    count_spanish_to_english_cards,
    format_collection_subtitle,
)
from drills.db.database import DrillsDatabase
from drills.errors import DatabaseError
from drills.generate_cards import generate_collection_db

COLLECTIONS_DIR_NAME = "drill_collections"


def snapshot_relative_path(snapshot_filename: str) -> str:
    return f"{COLLECTIONS_DIR_NAME}/{snapshot_filename}.db"


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
            snapshot_filename = drill_db.next_snapshot_filename(connection)
            snapshot_rel = snapshot_relative_path(snapshot_filename)
            collection_id = drill_db.insert_collection(
                connection,
                snapshot_filename=snapshot_filename,
                display_name=snapshot_filename,
                snapshot_path=snapshot_rel,
            )

        snapshot_path = project_root / snapshot_rel
        counts = generate_collection_db(word_bank_path, snapshot_path)

        collection = drill_db.get_collection(collection_id)
        if collection is None:
            raise DatabaseError(f"collection not found after create: {collection_id}")

        return collection_with_item_count(collection, project_root=project_root)
    except Exception:
        if snapshot_path is not None and snapshot_path.exists():
            snapshot_path.unlink()
        if collection_id is not None:
            drill_db.delete_collection(collection_id)
        raise


def rename_collection(
    collection_id: int,
    display_name: str,
    drill_db: DrillsDatabase,
    *,
    project_root: Path,
) -> dict[str, Any]:
    with drill_db.transaction() as connection:
        drill_db.update_collection_display_name(connection, collection_id, display_name)
    collection = drill_db.get_collection(collection_id)
    if collection is None:
        raise DatabaseError(f"collection not found: {collection_id}")
    return collection_with_item_count(collection, project_root=project_root)


def collection_with_item_count(
    collection: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    snapshot_path = project_root / str(collection["snapshot_path"])
    collection_id = int(collection["id"])
    snapshot_filename = str(collection["snapshot_filename"])
    display_name = str(collection["display_name"])
    sequence_label = collection_sequence_label(
        snapshot_filename,
        collection_id=collection_id,
        snapshot_path=str(collection["snapshot_path"]),
    )
    created_at = str(collection["created_at"])
    return {
        "id": collection_id,
        "snapshot_filename": snapshot_filename,
        "display_name": display_name,
        "name": display_name,
        "created_at": created_at,
        "sequence_label": sequence_label,
        "subtitle": format_collection_subtitle(sequence_label, created_at),
        "item_count": count_lexical_items(snapshot_path),
        "spanish_to_english_card_count": count_spanish_to_english_cards(snapshot_path),
        "english_to_spanish_card_count": count_english_to_spanish_cards(snapshot_path),
        "noun_gender_card_count": count_noun_gender_cards(snapshot_path),
        "adjective_inflection_type_card_count": count_adjective_inflection_type_cards(
            snapshot_path
        ),
        "inflection_drill_count": count_inflection_drill_word_forms(snapshot_path),
    }
