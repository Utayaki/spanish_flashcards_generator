from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from drills.errors import DatabaseError
from drills.fsrs.cards import (
    insert_adjective_inflection_type_card,
    insert_english_to_spanish_card,
    insert_inflection_card,
    insert_inflection_lexical_item,
    insert_noun_gender_card,
    insert_spanish_to_english_card,
    seed_scheduler,
)
from drills.fsrs.scheduler import default_scheduler
from drills.inflection.word_forms import aggregate_word_forms, display_form_descriptor

COLLECTION_SCHEMA_PATH = Path(__file__).resolve().parent / "collection_schema.sql"

TYPE_LABELS = {
    "noun": "Noun",
    "verb": "Verb",
    "adjective": "Adjective",
    "other": "Other",
}

GENDER_LABELS = {
    "masculine": "Always masculine",
    "feminine": "Always feminine",
    "both": "Masculine and feminine",
}

ADJECTIVE_INFLECTION_LABELS = {
    "plurality": "Plurality",
    "gender_plurality": "Plurality + gender",
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


def generate_spanish_to_english_cards(connection: sqlite3.Connection, source: sqlite3.Connection) -> int:
    rows = source.execute(
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
        insert_spanish_to_english_card(connection, front=front, back=back)
        created += 1

    return created


def generate_english_to_spanish_cards(connection: sqlite3.Connection, source: sqlite3.Connection) -> int:
    rows = source.execute(
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
        insert_english_to_spanish_card(connection, front=front, back=back)
        created += 1

    return created


def generate_noun_gender_cards(connection: sqlite3.Connection, source: sqlite3.Connection) -> int:
    rows = source.execute(
        """
        SELECT li.headword, nd.gender_availability
        FROM lexical_items li
        JOIN noun_details nd ON nd.lexical_item_id = li.id
        WHERE li.lexical_item_type = 'noun'
        ORDER BY li.headword COLLATE NOCASE, li.id
        """
    ).fetchall()

    created = 0
    for row in rows:
        gender = str(row["gender_availability"])
        back = GENDER_LABELS.get(gender)
        if back is None:
            continue
        insert_noun_gender_card(
            connection,
            front=str(row["headword"]),
            back=back,
        )
        created += 1

    return created


def generate_adjective_inflection_type_cards(
    connection: sqlite3.Connection,
    source: sqlite3.Connection,
) -> int:
    rows = source.execute(
        """
        SELECT li.headword, ad.inflection_type
        FROM lexical_items li
        JOIN adjective_details ad ON ad.lexical_item_id = li.id
        WHERE li.lexical_item_type = 'adjective'
        ORDER BY li.headword COLLATE NOCASE, li.id
        """
    ).fetchall()

    created = 0
    for row in rows:
        inflection_type = str(row["inflection_type"])
        back = ADJECTIVE_INFLECTION_LABELS.get(inflection_type)
        if back is None:
            continue
        insert_adjective_inflection_type_card(
            connection,
            front=str(row["headword"]),
            back=back,
        )
        created += 1

    return created


def generate_inflection_cards(connection: sqlite3.Connection, source: sqlite3.Connection) -> int:
    grouped: dict[int, list] = defaultdict(list)
    for record in aggregate_word_forms(source):
        grouped[int(record["lexical_item_id"])].append(record)

    created = 0
    for lexical_item_id, records in grouped.items():
        first = records[0]
        lexical_item_row_id = insert_inflection_lexical_item(
            connection,
            headword=str(first["headword"]),
            explanation=str(first["explanation"]),
            lexical_item_type=str(first["lexical_item_type"]),
        )
        for record in records:
            form_descriptor = display_form_descriptor(
                source,
                lexical_item_id,
                str(record["form_descriptor"]),
            )
            insert_inflection_card(
                connection,
                lexical_item_id=lexical_item_row_id,
                word_form=str(record["word_form"]),
                form_descriptor=form_descriptor,
            )
            created += 1

    return created


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
            seed_scheduler(destination, default_scheduler())
            spanish_to_english_card_count = generate_spanish_to_english_cards(
                destination, source
            )
            english_to_spanish_card_count = generate_english_to_spanish_cards(
                destination, source
            )
            noun_gender_card_count = generate_noun_gender_cards(destination, source)
            adjective_inflection_type_card_count = generate_adjective_inflection_type_cards(
                destination, source
            )
            inflection_card_count = generate_inflection_cards(destination, source)
            destination.commit()

    english_to_spanish_count = english_to_spanish_card_count
    return {
        "lexical_item_count": english_to_spanish_count,
        "spanish_to_english_card_count": spanish_to_english_card_count,
        "english_to_spanish_card_count": english_to_spanish_card_count,
        "noun_gender_card_count": noun_gender_card_count,
        "adjective_inflection_type_card_count": adjective_inflection_type_card_count,
        "inflection_word_form_count": inflection_card_count,
    }
