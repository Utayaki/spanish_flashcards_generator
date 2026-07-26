PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS drill_collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    snapshot_path TEXT NOT NULL UNIQUE
);
