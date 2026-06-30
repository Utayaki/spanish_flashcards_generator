from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import sqlite3

from shared.sqlite.connection import connect


class DrillConnectionMixin:
    db_path: Path

    def connect(self) -> sqlite3.Connection:
        return connect(self.db_path)

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
