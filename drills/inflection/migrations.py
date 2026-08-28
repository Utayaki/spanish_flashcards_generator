from __future__ import annotations

import sqlite3


def ensure_inflection_cards_seeded(connection: sqlite3.Connection) -> None:
    """No-op: inflection cards are created during collection generation or migration."""
