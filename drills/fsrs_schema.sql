PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fsrs_scheduler (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    scheduler_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS fsrs_cards (
    lexical_item_id INTEGER PRIMARY KEY
        REFERENCES lexical_items(id) ON DELETE CASCADE,
    fsrs_card_json TEXT NOT NULL,
    due_at TEXT NOT NULL,
    fsrs_state INTEGER NOT NULL,
    step INTEGER,
    stability REAL,
    difficulty REAL,
    first_reviewed_at TEXT,
    last_reviewed_at TEXT,
    is_suspended INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_fsrs_cards_due
ON fsrs_cards(is_suspended, due_at);

CREATE TRIGGER IF NOT EXISTS trg_fsrs_cards_updated_at
AFTER UPDATE ON fsrs_cards
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE fsrs_cards
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE lexical_item_id = NEW.lexical_item_id;
END;

CREATE TABLE IF NOT EXISTS fsrs_review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL
        REFERENCES lexical_items(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating IN (1, 2, 3, 4)),
    rating_label TEXT NOT NULL CHECK (
        rating_label IN ('again', 'hard', 'good', 'easy')
    ),
    review_log_json TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    review_duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_fsrs_review_logs_item
ON fsrs_review_logs(lexical_item_id, reviewed_at);
