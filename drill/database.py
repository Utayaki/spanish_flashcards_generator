from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class DatabaseError(RuntimeError):
    """Raised when the drill database layer cannot complete a valid operation."""


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DRILL_DB_PATH = PROJECT_ROOT / "drill.db"


def default_drill_db_path() -> Path:
    return Path(os.environ.get("SPANISH_DRILL_DB", DEFAULT_DRILL_DB_PATH))


class DrillDatabase:
    """SQLite access layer for drill cards, sessions, and attempts."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        schema_path: str | Path | None = None,
        initialize: bool = True,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_drill_db_path()
        self.schema_path = (
            Path(schema_path) if schema_path else Path(__file__).with_name("drill_schema.sql")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        if not self.schema_path.exists():
            raise DatabaseError(f"drill_schema.sql not found: {self.schema_path}")
        with self.transaction() as connection:
            connection.executescript(self.schema_path.read_text(encoding="utf-8"))
            self._migrate_drill_cards_for_transform(connection)

    @staticmethod
    def _drill_cards_supports_transform(connection: sqlite3.Connection) -> bool:
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

    @staticmethod
    def _migrate_drill_cards_for_transform(connection: sqlite3.Connection) -> None:
        if DrillDatabase._drill_cards_supports_transform(connection):
            return

        connection.executescript(
            """
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
        )

    def get_random_drill_card(self, drill_type: str | None = None) -> dict[str, Any] | None:
        params: list[Any] = []
        where = ["is_active = 1"]
        if drill_type:
            where.append("drill_type = ?")
            params.append(drill_type)
        sql = f"""
            SELECT *
            FROM drill_cards
            WHERE {" AND ".join(where)}
            ORDER BY RANDOM()
            LIMIT 1
        """
        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
        return _row_to_dict(row)

    def deactivate_cards_for_lexical_item(self, lexical_item_id: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE drill_cards
                SET is_active = 0
                WHERE lexical_item_id = ?
                """,
                (lexical_item_id,),
            )

    def deactivate_cards_not_in(self, lexical_item_ids: set[int]) -> None:
        with self.transaction() as connection:
            if not lexical_item_ids:
                connection.execute("UPDATE drill_cards SET is_active = 0")
                return
            placeholders = ", ".join("?" for _ in lexical_item_ids)
            connection.execute(
                f"""
                UPDATE drill_cards
                SET is_active = 0
                WHERE lexical_item_id NOT IN ({placeholders})
                """,
                tuple(lexical_item_ids),
            )

    def upsert_drill_card(
        self,
        *,
        lexical_item_id: int,
        drill_type: str,
        target_kind: str,
        target_key: str,
        prompt_schema: str,
        answer_schema: str,
        skill_tags: list[str],
    ) -> None:
        with self.transaction() as connection:
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
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT (
                    lexical_item_id,
                    drill_type,
                    target_kind,
                    target_key
                )
                DO UPDATE SET
                    prompt_schema = excluded.prompt_schema,
                    answer_schema = excluded.answer_schema,
                    skill_tags = excluded.skill_tags,
                    is_active = 1
                """,
                (
                    lexical_item_id,
                    drill_type,
                    target_kind,
                    target_key,
                    prompt_schema,
                    answer_schema,
                    json.dumps(skill_tags, ensure_ascii=False),
                ),
            )

    def sync_card_seeds_for_lexical_item(
        self,
        lexical_item_id: int,
        seeds: list[dict[str, Any]],
    ) -> int:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE drill_cards
                SET is_active = 0
                WHERE lexical_item_id = ?
                """,
                (lexical_item_id,),
            )
            for seed in seeds:
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT (
                        lexical_item_id,
                        drill_type,
                        target_kind,
                        target_key
                    )
                    DO UPDATE SET
                        prompt_schema = excluded.prompt_schema,
                        answer_schema = excluded.answer_schema,
                        skill_tags = excluded.skill_tags,
                        is_active = 1
                    """,
                    (
                        lexical_item_id,
                        seed["drill_type"],
                        seed["target_kind"],
                        seed["target_key"],
                        seed["prompt_schema"],
                        seed["answer_schema"],
                        json.dumps(seed.get("skill_tags", []), ensure_ascii=False),
                    ),
                )
        return len(seeds)

    def mark_cards_inactive_for_lexical_item(self, lexical_item_id: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE drill_cards
                SET is_active = 0
                WHERE lexical_item_id = ?
                """,
                (lexical_item_id,),
            )

    def record_drill_attempt(
        self,
        *,
        drill_card_id: int,
        session_id: int | None,
        submitted_answer: dict[str, Any],
        expected_answer: dict[str, Any],
        result: dict[str, Any],
        is_correct: bool,
        response_ms: int | None = None,
    ) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO drill_attempts (
                    drill_card_id,
                    session_id,
                    submitted_answer_json,
                    expected_answer_json,
                    result_json,
                    is_correct,
                    response_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drill_card_id,
                    session_id,
                    json.dumps(submitted_answer, ensure_ascii=False),
                    json.dumps(expected_answer, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    1 if is_correct else 0,
                    response_ms,
                ),
            )
            if session_id is not None:
                connection.execute(
                    """
                    UPDATE drill_sessions
                    SET
                        total_attempts = total_attempts + 1,
                        correct_attempts = correct_attempts + ?
                    WHERE id = ?
                    """,
                    (1 if is_correct else 0, session_id),
                )
            return int(cursor.lastrowid)

    def create_drill_session(self, *, mode: str = "random", drill_type: str | None = None) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO drill_sessions (mode, drill_type)
                VALUES (?, ?)
                """,
                (mode, drill_type),
            )
            return int(cursor.lastrowid)

    def finish_drill_session(self, session_id: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE drill_sessions
                SET finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (session_id,),
            )

    def get_drill_stats_summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            overall = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_attempts,
                    SUM(is_correct) AS correct_attempts
                FROM drill_attempts
                """
            ).fetchone()
            by_type = connection.execute(
                """
                SELECT
                    dc.drill_type,
                    COUNT(*) AS total_attempts,
                    SUM(da.is_correct) AS correct_attempts
                FROM drill_attempts da
                JOIN drill_cards dc ON dc.id = da.drill_card_id
                GROUP BY dc.drill_type
                ORDER BY dc.drill_type
                """
            ).fetchall()

        total = int(overall["total_attempts"] or 0)
        correct = int(overall["correct_attempts"] or 0)
        by_type_rows = []
        for row in by_type:
            row_total = int(row["total_attempts"] or 0)
            row_correct = int(row["correct_attempts"] or 0)
            by_type_rows.append(
                {
                    "drill_type": row["drill_type"],
                    "total_attempts": row_total,
                    "correct_attempts": row_correct,
                    "accuracy": row_correct / row_total if row_total else None,
                }
            )
        return {
            "overall": {
                "total_attempts": total,
                "correct_attempts": correct,
                "accuracy": correct / total if total else None,
            },
            "by_type": by_type_rows,
        }


def open_default_drill_database(*, initialize: bool = True) -> DrillDatabase:
    return DrillDatabase(initialize=initialize)
