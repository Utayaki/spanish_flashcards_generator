from __future__ import annotations

import os
from pathlib import Path

from shared.errors import DatabaseError
from shared.sqlite.migrations import set_user_version

from drill.db.cards import DrillCardsRepository
from drill.db.connection import DrillConnectionMixin
from drill.db.migrations import (
    SCHEMA_VERSION,
    build_migrations,
    detect_legacy_drill_version,
    pending_migration_versions,
    run_transform_migration,
)
from drill.db.schedules import DrillSchedulesRepository
from drill.db.sessions import DrillSessionsRepository

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DRILL_DB_PATH = PROJECT_ROOT / "drill.db"


def default_drill_db_path() -> Path:
    return Path(os.environ.get("SPANISH_DRILL_DB", DEFAULT_DRILL_DB_PATH))


class DrillDatabase(
    DrillConnectionMixin,
    DrillCardsRepository,
    DrillSessionsRepository,
    DrillSchedulesRepository,
):
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
            Path(schema_path) if schema_path else Path(__file__).resolve().parent.parent / "drill_schema.sql"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            self.initialize()

    def initialize(self) -> None:
        if not self.schema_path.exists():
            raise DatabaseError(f"drill_schema.sql not found: {self.schema_path}")

        schema_sql = self.schema_path.read_text(encoding="utf-8")
        migrations = build_migrations(schema_sql)

        with self.transaction() as connection:
            versions = pending_migration_versions(connection, SCHEMA_VERSION)
            for version in versions:
                if version == 2:
                    run_transform_migration(connection)
                else:
                    connection.executescript(migrations[version])
                    set_user_version(connection, version)


def open_default_drill_database(*, initialize: bool = True) -> DrillDatabase:
    return DrillDatabase(initialize=initialize)


__all__ = [
    "DEFAULT_DRILL_DB_PATH",
    "DrillDatabase",
    "default_drill_db_path",
    "detect_legacy_drill_version",
    "open_default_drill_database",
]
