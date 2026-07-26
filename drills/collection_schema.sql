PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lexical_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    headword TEXT NOT NULL CHECK (length(trim(headword)) > 0),
    explanation TEXT NOT NULL CHECK (length(trim(explanation)) > 0),
    lexical_item_type TEXT NOT NULL CHECK (lexical_item_type IN ('noun', 'verb', 'adjective', 'other')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_lexical_item_type_headword
ON lexical_items(lexical_item_type, headword COLLATE NOCASE);

CREATE TRIGGER IF NOT EXISTS trg_lexical_item_updated_at
AFTER UPDATE ON lexical_items
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE lexical_items
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS spanish_to_english_fsrs_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS english_to_spanish_fsrs_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS fsrs_scheduler (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    desired_retention REAL NOT NULL,
    enable_fuzzing INTEGER NOT NULL DEFAULT 1,
    maximum_interval INTEGER NOT NULL DEFAULT 36500,
    param_0 REAL NOT NULL,
    param_1 REAL NOT NULL,
    param_2 REAL NOT NULL,
    param_3 REAL NOT NULL,
    param_4 REAL NOT NULL,
    param_5 REAL NOT NULL,
    param_6 REAL NOT NULL,
    param_7 REAL NOT NULL,
    param_8 REAL NOT NULL,
    param_9 REAL NOT NULL,
    param_10 REAL NOT NULL,
    param_11 REAL NOT NULL,
    param_12 REAL NOT NULL,
    param_13 REAL NOT NULL,
    param_14 REAL NOT NULL,
    param_15 REAL NOT NULL,
    param_16 REAL NOT NULL,
    param_17 REAL NOT NULL,
    param_18 REAL NOT NULL,
    param_19 REAL NOT NULL,
    param_20 REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS fsrs_scheduler_learning_steps (
    step_index INTEGER NOT NULL PRIMARY KEY,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0)
);

CREATE TABLE IF NOT EXISTS fsrs_scheduler_relearning_steps (
    step_index INTEGER NOT NULL PRIMARY KEY,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0)
);

CREATE TABLE IF NOT EXISTS fsrs_cards (
    direction TEXT NOT NULL CHECK (direction IN ('spanish_to_english', 'english_to_spanish')),
    study_card_id INTEGER NOT NULL,
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
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (direction, study_card_id)
);

CREATE INDEX IF NOT EXISTS idx_fsrs_cards_due
ON fsrs_cards(direction, is_suspended, due_at);

CREATE TRIGGER IF NOT EXISTS trg_fsrs_cards_updated_at
AFTER UPDATE ON fsrs_cards
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE fsrs_cards
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE direction = NEW.direction AND study_card_id = NEW.study_card_id;
END;

CREATE TABLE IF NOT EXISTS fsrs_review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL CHECK (direction IN ('spanish_to_english', 'english_to_spanish')),
    study_card_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating IN (1, 2, 3, 4)),
    rating_label TEXT NOT NULL CHECK (
        rating_label IN ('again', 'hard', 'good', 'easy')
    ),
    review_log_json TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    review_duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_fsrs_review_logs_card
ON fsrs_review_logs(direction, study_card_id, reviewed_at);
