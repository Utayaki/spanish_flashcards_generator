PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS drill_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    lexical_item_id INTEGER NOT NULL,

    drill_type TEXT NOT NULL CHECK (
        drill_type IN ('inflection', 'verb_form', 'recognition', 'reverse', 'transform')
    ),

    target_kind TEXT NOT NULL,
    target_key TEXT NOT NULL,

    prompt_schema TEXT NOT NULL,
    answer_schema TEXT NOT NULL,

    skill_tags TEXT NOT NULL DEFAULT '[]',

    is_active INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    UNIQUE (lexical_item_id, drill_type, target_kind, target_key)
);

CREATE INDEX IF NOT EXISTS idx_drill_cards_type_active
ON drill_cards(drill_type, is_active);

CREATE INDEX IF NOT EXISTS idx_drill_cards_lexical_item
ON drill_cards(lexical_item_id);

CREATE TRIGGER IF NOT EXISTS trg_drill_cards_updated_at
AFTER UPDATE ON drill_cards
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE drill_cards
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS drill_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    mode TEXT NOT NULL DEFAULT 'random',
    drill_type TEXT,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,

    total_attempts INTEGER NOT NULL DEFAULT 0,
    correct_attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_drill_sessions_started_at
ON drill_sessions(started_at);

CREATE TABLE IF NOT EXISTS drill_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    drill_card_id INTEGER NOT NULL,
    session_id INTEGER,

    submitted_answer_json TEXT NOT NULL,
    expected_answer_json TEXT NOT NULL,
    result_json TEXT NOT NULL,

    is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1)),

    response_ms INTEGER,

    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    FOREIGN KEY (drill_card_id) REFERENCES drill_cards(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES drill_sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_drill_attempts_card_created
ON drill_attempts(drill_card_id, created_at);

CREATE INDEX IF NOT EXISTS idx_drill_attempts_session
ON drill_attempts(session_id);
