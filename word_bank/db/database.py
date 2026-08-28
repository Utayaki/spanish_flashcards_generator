from __future__ import annotations

import sqlite3
from pathlib import Path

from word_bank.errors import DatabaseError
from word_bank.db.lexical_items import WordBankLexicalItemsRepository


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


class WordBankDatabase(WordBankLexicalItemsRepository):
    """SQLite access layer for the Spanish word bank."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        schema_path: str | Path | None = None,
        initialize: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.schema_path = (
            Path(schema_path)
            if schema_path
            else Path(__file__).resolve().parent.parent / "schema.sql"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            self.initialize()

    def initialize(self) -> None:
        if not self.schema_path.exists():
            raise DatabaseError(f"schema.sql not found: {self.schema_path}")

        schema_sql = self.schema_path.read_text(encoding="utf-8")

        with self.transaction() as connection:
            if not _table_exists(connection, "lexical_items"):
                connection.executescript(schema_sql)
            self.seed_verb_form_definitions(connection)
