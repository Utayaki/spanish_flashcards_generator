PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS study_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_kind TEXT NOT NULL CHECK (
        card_kind IN (
            'spanish_to_english',
            'english_to_spanish',
            'noun_gender',
            'adjective_inflection_type',
            'inflection'
        )
    ),
    front TEXT,
    back TEXT,
    headword TEXT,
    explanation TEXT,
    lexical_item_type TEXT,
    word_form TEXT,
    form_descriptor TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (
        (
            card_kind = 'inflection'
            AND front IS NULL
            AND back IS NULL
            AND headword IS NOT NULL
            AND explanation IS NOT NULL
            AND lexical_item_type IS NOT NULL
            AND word_form IS NOT NULL
            AND form_descriptor IS NOT NULL
        )
        OR (
            card_kind != 'inflection'
            AND front IS NOT NULL
            AND back IS NOT NULL
            AND headword IS NULL
            AND explanation IS NULL
            AND lexical_item_type IS NULL
            AND word_form IS NULL
            AND form_descriptor IS NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_study_cards_kind
ON study_cards(card_kind);

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
    study_card_id INTEGER PRIMARY KEY,
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
    FOREIGN KEY (study_card_id) REFERENCES study_cards(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fsrs_schedules_due
ON fsrs_schedules(is_suspended, due_at);

CREATE INDEX IF NOT EXISTS idx_fsrs_schedules_kind_due
ON fsrs_schedules(study_card_id, is_suspended, due_at);

CREATE TRIGGER IF NOT EXISTS trg_fsrs_schedules_updated_at
AFTER UPDATE ON fsrs_schedules
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE fsrs_schedules
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE study_card_id = NEW.study_card_id;
END;

CREATE TABLE IF NOT EXISTS fsrs_review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    study_card_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating IN (1, 2, 3, 4)),
    rating_label TEXT NOT NULL CHECK (
        rating_label IN ('again', 'hard', 'good', 'easy')
    ),
    reviewed_at TEXT NOT NULL,
    review_duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (study_card_id) REFERENCES study_cards(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fsrs_review_logs_card
ON fsrs_review_logs(study_card_id, reviewed_at);

CREATE INDEX IF NOT EXISTS idx_fsrs_review_logs_reviewed_at
ON fsrs_review_logs(reviewed_at);
