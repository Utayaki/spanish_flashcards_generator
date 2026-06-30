from __future__ import annotations

import sqlite3

from shared.sqlite.migrations import (
    get_user_version,
    run_script_with_foreign_keys_disabled,
    set_user_version,
    table_exists,
)

SCHEMA_VERSION = 2

TRANSFORM_MIGRATION_SQL = """
CREATE TABLE drill_cards_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL,
    drill_type TEXT NOT NULL CHECK (
        drill_type IN (
            'inflection', 'verb_form', 'recognition', 'reverse', 'transform'
        )
    ),
    target_kind TEXT NOT NULL,
    target_key TEXT NOT NULL,
    prompt_schema TEXT NOT NULL,
    answer_schema TEXT NOT NULL,
    skill_tags TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (lexical_item_id, drill_type, target_kind, target_key)
);

INSERT INTO drill_cards_new (
    id,
    lexical_item_id,
    drill_type,
    target_kind,
    target_key,
    prompt_schema,
    answer_schema,
    skill_tags,
    is_active,
    created_at,
    updated_at
)
SELECT
    id,
    lexical_item_id,
    drill_type,
    target_kind,
    target_key,
    prompt_schema,
    answer_schema,
    skill_tags,
    is_active,
    created_at,
    updated_at
FROM drill_cards;

DROP TABLE drill_cards;
ALTER TABLE drill_cards_new RENAME TO drill_cards;

CREATE INDEX IF NOT EXISTS idx_drill_cards_type_active
ON drill_cards(drill_type, is_active);

CREATE INDEX IF NOT EXISTS idx_drill_cards_lexical_item
ON drill_cards(lexical_item_id);

CREATE TRIGGER IF NOT EXISTS trg_drill_cards_updated_at
AFTER UPDATE ON drill_cards
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE drill_cards
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;
"""


def drill_cards_supports_transform(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute("SAVEPOINT transform_check")
        connection.execute(
            """
            INSERT INTO drill_cards (
                lexical_item_id,
                drill_type,
                target_kind,
                target_key,
                prompt_schema,
                answer_schema,
                skill_tags,
                is_active
            )
            VALUES (-1, 'transform', 'test', 'test', 'x', 'x', '[]', 0)
            """
        )
        connection.execute("ROLLBACK TO transform_check")
        connection.execute("RELEASE transform_check")
        return True
    except sqlite3.IntegrityError:
        connection.execute("ROLLBACK TO transform_check")
        connection.execute("RELEASE transform_check")
        return False


def detect_legacy_drill_version(connection: sqlite3.Connection) -> int:
    if not table_exists(connection, "drill_cards"):
        return 0
    if drill_cards_supports_transform(connection):
        return SCHEMA_VERSION
    return 1


def build_migrations(schema_sql: str) -> dict[int, str]:
    return {
        1: schema_sql,
        2: TRANSFORM_MIGRATION_SQL,
    }


def pending_migration_versions(connection: sqlite3.Connection, target_version: int) -> list[int]:
    current = get_user_version(connection)
    if current == 0 and table_exists(connection, "drill_cards"):
        current = detect_legacy_drill_version(connection)
    return list(range(current + 1, target_version + 1))


def run_transform_migration(connection: sqlite3.Connection) -> None:
    run_script_with_foreign_keys_disabled(connection, TRANSFORM_MIGRATION_SQL)
    set_user_version(connection, 2)
    connection.commit()
