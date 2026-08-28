PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fsrs_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS spanish_to_english_cards (
    fsrs_card_id INTEGER PRIMARY KEY,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    FOREIGN KEY (fsrs_card_id) REFERENCES fsrs_cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS english_to_spanish_cards (
    fsrs_card_id INTEGER PRIMARY KEY,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    FOREIGN KEY (fsrs_card_id) REFERENCES fsrs_cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS noun_gender_cards (
    fsrs_card_id INTEGER PRIMARY KEY,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    FOREIGN KEY (fsrs_card_id) REFERENCES fsrs_cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS adjective_inflection_type_cards (
    fsrs_card_id INTEGER PRIMARY KEY,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    FOREIGN KEY (fsrs_card_id) REFERENCES fsrs_cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inflection_lexical_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    headword TEXT NOT NULL,
    explanation TEXT NOT NULL,
    lexical_item_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inflection_cards (
    fsrs_card_id INTEGER PRIMARY KEY,
    lexical_item_id INTEGER NOT NULL,
    word_form TEXT NOT NULL,
    form_descriptor TEXT NOT NULL,
    FOREIGN KEY (fsrs_card_id) REFERENCES fsrs_cards(id) ON DELETE CASCADE,
    FOREIGN KEY (lexical_item_id) REFERENCES inflection_lexical_items(id)
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

CREATE TABLE IF NOT EXISTS fsrs_schedules (
    fsrs_card_id INTEGER PRIMARY KEY,
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
    FOREIGN KEY (fsrs_card_id) REFERENCES fsrs_cards(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fsrs_schedules_due
ON fsrs_schedules(is_suspended, due_at);

CREATE INDEX IF NOT EXISTS idx_fsrs_schedules_card_due
ON fsrs_schedules(fsrs_card_id, is_suspended, due_at);

CREATE TRIGGER IF NOT EXISTS trg_fsrs_schedules_updated_at
AFTER UPDATE ON fsrs_schedules
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE fsrs_schedules
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE fsrs_card_id = NEW.fsrs_card_id;
END;

CREATE TABLE IF NOT EXISTS fsrs_review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fsrs_card_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating IN (1, 2, 3, 4)),
    rating_label TEXT NOT NULL CHECK (
        rating_label IN ('again', 'hard', 'good', 'easy')
    ),
    reviewed_at TEXT NOT NULL,
    review_duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (fsrs_card_id) REFERENCES fsrs_cards(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fsrs_review_logs_card
ON fsrs_review_logs(fsrs_card_id, reviewed_at);

CREATE INDEX IF NOT EXISTS idx_fsrs_review_logs_reviewed_at
ON fsrs_review_logs(reviewed_at);
