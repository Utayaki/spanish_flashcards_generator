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

CREATE TABLE IF NOT EXISTS noun_gender_fsrs_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS adjective_inflection_type_fsrs_cards (
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
    direction TEXT NOT NULL CHECK (
        direction IN (
            'spanish_to_english',
            'english_to_spanish',
            'noun_gender',
            'adjective_inflection_type'
        )
    ),
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
    direction TEXT NOT NULL CHECK (
        direction IN (
            'spanish_to_english',
            'english_to_spanish',
            'noun_gender',
            'adjective_inflection_type'
        )
    ),
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

CREATE TABLE IF NOT EXISTS fsrs_card_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL CHECK (
        direction IN (
            'spanish_to_english',
            'english_to_spanish',
            'noun_gender',
            'adjective_inflection_type'
        )
    ),
    study_card_id INTEGER NOT NULL,
    review_log_id INTEGER,
    source TEXT NOT NULL CHECK (source IN ('created', 'review', 'optimizer', 'migration')),
    captured_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    fsrs_state INTEGER NOT NULL,
    step INTEGER,
    stability REAL,
    difficulty REAL,
    FOREIGN KEY (review_log_id) REFERENCES fsrs_review_logs(id) ON DELETE CASCADE,
    FOREIGN KEY (direction, study_card_id)
        REFERENCES fsrs_cards(direction, study_card_id) ON DELETE CASCADE,
    UNIQUE (direction, study_card_id, captured_at, source)
);

CREATE INDEX IF NOT EXISTS idx_fsrs_card_snapshots_history
ON fsrs_card_snapshots(direction, captured_at, study_card_id);

CREATE TABLE IF NOT EXISTS noun_details (
    lexical_item_id INTEGER PRIMARY KEY,
    gender_availability TEXT NOT NULL CHECK (gender_availability IN ('masculine', 'feminine', 'both')),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS noun_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_items(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_noun_forms_unique
ON noun_forms(lexical_item_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_noun_forms_lexical_item
ON noun_forms(lexical_item_id);

CREATE TABLE IF NOT EXISTS adjective_details (
    lexical_item_id INTEGER PRIMARY KEY,
    inflection_type TEXT NOT NULL CHECK (inflection_type IN ('plurality', 'gender_plurality')),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS adjective_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_items(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_adjective_forms_unique
ON adjective_forms(lexical_item_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_adjective_forms_lexical_item
ON adjective_forms(lexical_item_id);

CREATE TABLE IF NOT EXISTS other_details (
    lexical_item_id INTEGER PRIMARY KEY,
    inflection_type TEXT NOT NULL DEFAULT 'none'
        CHECK (inflection_type IN ('none', 'plurality', 'gender_plurality')),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS other_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_items(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_other_forms_unique
ON other_forms(lexical_item_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_other_forms_lexical_item
ON other_forms(lexical_item_id);

CREATE TABLE IF NOT EXISTS verb_form_definitions (
    id INTEGER PRIMARY KEY,
    group_code TEXT NOT NULL,
    tense_code TEXT NOT NULL,
    person_code TEXT,
    sort_order INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS verb_forms (
    lexical_item_id INTEGER NOT NULL,
    verb_form_id INTEGER NOT NULL,
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    PRIMARY KEY (lexical_item_id, verb_form_id),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_items(id) ON DELETE CASCADE,
    FOREIGN KEY (verb_form_id) REFERENCES verb_form_definitions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verb_forms_lexical_item
ON verb_forms(lexical_item_id);

CREATE INDEX IF NOT EXISTS idx_verb_forms_definition
ON verb_forms(verb_form_id);

CREATE TRIGGER IF NOT EXISTS trg_noun_details_lexical_item_type_insert
BEFORE INSERT ON noun_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_details can only be used for noun lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_details_lexical_item_type_update
BEFORE UPDATE ON noun_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_details can only be used for noun lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_forms_lexical_item_type_insert
BEFORE INSERT ON noun_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_forms can only be used for noun lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_forms_lexical_item_type_update
BEFORE UPDATE ON noun_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_forms can only be used for noun lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_details_lexical_item_type_insert
BEFORE INSERT ON adjective_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_details can only be used for adjective lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_details_lexical_item_type_update
BEFORE UPDATE ON adjective_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_details can only be used for adjective lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_forms_lexical_item_type_insert
BEFORE INSERT ON adjective_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_forms can only be used for adjective lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_forms_lexical_item_type_update
BEFORE UPDATE ON adjective_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_forms can only be used for adjective lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_lexical_item_type_insert
BEFORE INSERT ON other_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_details can only be used for other lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_lexical_item_type_update
BEFORE UPDATE ON other_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_details can only be used for other lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_lexical_item_type_insert
BEFORE INSERT ON other_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_forms can only be used for other lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_lexical_item_type_update
BEFORE UPDATE ON other_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_forms can only be used for other lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_forms_lexical_item_type_insert
BEFORE INSERT ON verb_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_forms can only be used for verb lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_forms_lexical_item_type_update
BEFORE UPDATE ON verb_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_items WHERE id = NEW.lexical_item_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_forms can only be used for verb lexical items');
END;

CREATE TABLE IF NOT EXISTS inflection_word_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL,
    headword TEXT NOT NULL,
    explanation TEXT NOT NULL,
    lexical_item_type TEXT NOT NULL,
    word_form TEXT NOT NULL,
    form_descriptor TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_items(id) ON DELETE CASCADE,
    UNIQUE (lexical_item_id, word_form, form_descriptor)
);

CREATE INDEX IF NOT EXISTS idx_inflection_word_forms_lexical_item
ON inflection_word_forms(lexical_item_id);

CREATE TABLE IF NOT EXISTS inflection_fsrs_scheduler (
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

CREATE TABLE IF NOT EXISTS inflection_fsrs_scheduler_learning_steps (
    step_index INTEGER NOT NULL PRIMARY KEY,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0)
);

CREATE TABLE IF NOT EXISTS inflection_fsrs_scheduler_relearning_steps (
    step_index INTEGER NOT NULL PRIMARY KEY,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0)
);

CREATE TABLE IF NOT EXISTS inflection_fsrs_cards (
    word_form_id INTEGER PRIMARY KEY,
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
    FOREIGN KEY (word_form_id) REFERENCES inflection_word_forms(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_inflection_fsrs_cards_due
ON inflection_fsrs_cards(is_suspended, due_at);

CREATE TRIGGER IF NOT EXISTS trg_inflection_fsrs_cards_updated_at
AFTER UPDATE ON inflection_fsrs_cards
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE inflection_fsrs_cards
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE word_form_id = NEW.word_form_id;
END;

CREATE TABLE IF NOT EXISTS inflection_fsrs_review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_form_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating IN (1, 2, 3, 4)),
    rating_label TEXT NOT NULL CHECK (
        rating_label IN ('again', 'hard', 'good', 'easy')
    ),
    review_log_json TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    review_duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (word_form_id) REFERENCES inflection_word_forms(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_inflection_fsrs_review_logs_card
ON inflection_fsrs_review_logs(word_form_id, reviewed_at);

CREATE TABLE IF NOT EXISTS inflection_fsrs_card_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_form_id INTEGER NOT NULL,
    review_log_id INTEGER,
    source TEXT NOT NULL CHECK (source IN ('created', 'review', 'optimizer', 'migration')),
    captured_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    fsrs_state INTEGER NOT NULL,
    step INTEGER,
    stability REAL,
    difficulty REAL,
    FOREIGN KEY (review_log_id) REFERENCES inflection_fsrs_review_logs(id) ON DELETE CASCADE,
    FOREIGN KEY (word_form_id) REFERENCES inflection_fsrs_cards(word_form_id) ON DELETE CASCADE,
    UNIQUE (word_form_id, captured_at, source)
);

CREATE INDEX IF NOT EXISTS idx_inflection_fsrs_card_snapshots_history
ON inflection_fsrs_card_snapshots(captured_at, word_form_id);
