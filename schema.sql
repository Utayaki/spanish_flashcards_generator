PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lexical_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    headword TEXT NOT NULL CHECK (length(trim(headword)) > 0),
    explanation TEXT NOT NULL CHECK (length(trim(explanation)) > 0),
    lexical_item_type TEXT NOT NULL CHECK (lexical_item_type IN ('noun', 'verb', 'adjective', 'other')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_lexical_item_type_headword
ON lexical_item(lexical_item_type, headword COLLATE NOCASE);

CREATE TRIGGER IF NOT EXISTS trg_lexical_item_updated_at
AFTER UPDATE ON lexical_item
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE lexical_item
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS noun_details (
    lexical_item_id INTEGER PRIMARY KEY,
    gender_availability TEXT NOT NULL CHECK (gender_availability IN ('masculine', 'feminine', 'both')),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_item(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS noun_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_item(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_noun_forms_unique
ON noun_forms(lexical_item_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_noun_forms_lexical_item
ON noun_forms(lexical_item_id);

CREATE TABLE IF NOT EXISTS adjective_details (
    lexical_item_id INTEGER PRIMARY KEY,
    inflection_type TEXT NOT NULL CHECK (inflection_type IN ('plurality', 'gender_plurality')),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_item(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS adjective_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_item(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_adjective_forms_unique
ON adjective_forms(lexical_item_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_adjective_forms_lexical_item
ON adjective_forms(lexical_item_id);

CREATE TABLE IF NOT EXISTS other_details (
    lexical_item_id INTEGER PRIMARY KEY,
    inflection_type TEXT NOT NULL DEFAULT 'none'
        CHECK (inflection_type IN ('none', 'plurality', 'gender_plurality')),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_item(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS other_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lexical_item_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_item(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_other_forms_unique
ON other_forms(lexical_item_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_other_forms_lexical_item
ON other_forms(lexical_item_id);

CREATE TABLE IF NOT EXISTS verb_form_definitions (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    group_code TEXT NOT NULL,
    group_label TEXT NOT NULL,
    tense_code TEXT,
    tense_label TEXT,
    variant_code TEXT,
    person_code TEXT,
    person_label TEXT,
    sort_order INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS verb_forms (
    lexical_item_id INTEGER NOT NULL,
    verb_form_id INTEGER NOT NULL,
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    PRIMARY KEY (lexical_item_id, verb_form_id),
    FOREIGN KEY (lexical_item_id) REFERENCES lexical_item(id) ON DELETE CASCADE,
    FOREIGN KEY (verb_form_id) REFERENCES verb_form_definitions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verb_forms_lexical_item
ON verb_forms(lexical_item_id);

CREATE INDEX IF NOT EXISTS idx_verb_forms_definition
ON verb_forms(verb_form_id);

CREATE TRIGGER IF NOT EXISTS trg_noun_details_lexical_item_type_insert
BEFORE INSERT ON noun_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_details can only be used for noun lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_details_lexical_item_type_update
BEFORE UPDATE ON noun_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_details can only be used for noun lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_forms_lexical_item_type_insert
BEFORE INSERT ON noun_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_forms can only be used for noun lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_forms_lexical_item_type_update
BEFORE UPDATE ON noun_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_forms can only be used for noun lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_details_lexical_item_type_insert
BEFORE INSERT ON adjective_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_details can only be used for adjective lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_details_lexical_item_type_update
BEFORE UPDATE ON adjective_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_details can only be used for adjective lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_forms_lexical_item_type_insert
BEFORE INSERT ON adjective_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_forms can only be used for adjective lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_forms_lexical_item_type_update
BEFORE UPDATE ON adjective_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_forms can only be used for adjective lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_lexical_item_type_insert
BEFORE INSERT ON other_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_details can only be used for other lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_lexical_item_type_update
BEFORE UPDATE ON other_details
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_details can only be used for other lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_lexical_item_type_insert
BEFORE INSERT ON other_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_forms can only be used for other lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_lexical_item_type_update
BEFORE UPDATE ON other_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_forms can only be used for other lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_forms_lexical_item_type_insert
BEFORE INSERT ON verb_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_forms can only be used for verb lexical items');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_forms_lexical_item_type_update
BEFORE UPDATE ON verb_forms
FOR EACH ROW
WHEN (SELECT lexical_item_type FROM lexical_item WHERE id = NEW.lexical_item_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_forms can only be used for verb lexical items');
END;
