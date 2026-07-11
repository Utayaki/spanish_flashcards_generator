from __future__ import annotations

from pathlib import Path

from word_bank.errors import DatabaseError
from word_bank.db.migrations import (
    get_user_version,
    run_pending_migrations,
    set_user_version,
    table_exists,
)
from word_bank.db.constants import SCHEMA_VERSION
from word_bank.db.lexical_items import WordBankLexicalItemsRepository


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
        migrations = {1: schema_sql}

        with self.transaction() as connection:
            current = get_user_version(connection)
            if current == 0 and table_exists(connection, "lexical_items"):
                set_user_version(connection, SCHEMA_VERSION)
            elif current < SCHEMA_VERSION:
                run_pending_migrations(
                    connection,
                    target_version=SCHEMA_VERSION,
                    migrations=migrations,
                )
            self.seed_verb_form_definitions(connection)
