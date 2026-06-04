PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL CHECK (length(trim(lemma)) > 0),
    english TEXT NOT NULL DEFAULT '' CHECK (english = '' OR length(trim(english)) > 0),
    word_type TEXT NOT NULL CHECK (word_type IN ('noun', 'verb', 'adjective', 'other')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_words_type_lemma
ON words(word_type, lemma COLLATE NOCASE);

CREATE TRIGGER IF NOT EXISTS trg_words_updated_at
AFTER UPDATE ON words
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE words
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS nominal_details (
    word_id INTEGER PRIMARY KEY,
    gender_availability TEXT NOT NULL CHECK (gender_availability IN ('masc', 'fem', 'both', 'ambiguous')),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS other_details (
    word_id INTEGER PRIMARY KEY,
    has_inflections INTEGER NOT NULL DEFAULT 0 CHECK (has_inflections IN (0, 1)),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS nominal_inflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL,
    number TEXT NOT NULL CHECK (number IN ('singular', 'plural')),
    gender TEXT NOT NULL CHECK (gender IN ('masc', 'fem')),
    form TEXT CHECK (form IS NULL OR length(trim(form)) > 0),
    UNIQUE (word_id, number, gender),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_nominal_inflections_word
ON nominal_inflections(word_id);

CREATE TABLE IF NOT EXISTS verb_participles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL,
    participle_type TEXT NOT NULL CHECK (participle_type IN ('present', 'past')),
    form TEXT CHECK (form IS NULL OR length(trim(form)) > 0),
    is_irregular INTEGER NOT NULL DEFAULT 0 CHECK (is_irregular IN (0, 1)),
    UNIQUE (word_id, participle_type),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verb_tenses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    group_code TEXT NOT NULL CHECK (
        group_code IN (
            'indicative',
            'subjunctive',
            'imperative',
            'progressive',
            'perfect',
            'perfect_subjunctive',
            'informal_future'
        )
    ),
    sort_order INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS verb_persons (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    imperative_label TEXT NOT NULL,
    sort_order INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS verb_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL,
    tense_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    form TEXT CHECK (form IS NULL OR length(trim(form)) > 0),
    is_irregular INTEGER NOT NULL DEFAULT 0 CHECK (is_irregular IN (0, 1)),
    UNIQUE (word_id, tense_id, person_id),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE,
    FOREIGN KEY (tense_id) REFERENCES verb_tenses(id) ON DELETE CASCADE,
    FOREIGN KEY (person_id) REFERENCES verb_persons(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verb_forms_word_tense
ON verb_forms(word_id, tense_id);

CREATE TRIGGER IF NOT EXISTS trg_nominal_details_word_type_insert
BEFORE INSERT ON nominal_details
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) NOT IN ('noun', 'adjective')
BEGIN
    SELECT RAISE(ABORT, 'nominal_details can only be used for noun or adjective words');
END;

CREATE TRIGGER IF NOT EXISTS trg_nominal_details_word_type_update
BEFORE UPDATE ON nominal_details
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) NOT IN ('noun', 'adjective')
BEGIN
    SELECT RAISE(ABORT, 'nominal_details can only be used for noun or adjective words');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_word_type_insert
BEFORE INSERT ON other_details
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_details can only be used for other words');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_word_type_update
BEFORE UPDATE ON other_details
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_details can only be used for other words');
END;

CREATE TRIGGER IF NOT EXISTS trg_nominal_inflections_word_type_insert
BEFORE INSERT ON nominal_inflections
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) NOT IN ('noun', 'adjective', 'other')
BEGIN
    SELECT RAISE(ABORT, 'nominal_inflections can only be used for noun, adjective, or inflective other words');
END;

CREATE TRIGGER IF NOT EXISTS trg_nominal_inflections_word_type_update
BEFORE UPDATE ON nominal_inflections
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) NOT IN ('noun', 'adjective', 'other')
BEGIN
    SELECT RAISE(ABORT, 'nominal_inflections can only be used for noun, adjective, or inflective other words');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_inflections_enabled_insert
BEFORE INSERT ON nominal_inflections
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) = 'other'
 AND COALESCE((SELECT has_inflections FROM other_details WHERE word_id = NEW.word_id), 0) != 1
BEGIN
    SELECT RAISE(ABORT, 'other word inflections require has_inflections = 1');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_inflections_enabled_update
BEFORE UPDATE ON nominal_inflections
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) = 'other'
 AND COALESCE((SELECT has_inflections FROM other_details WHERE word_id = NEW.word_id), 0) != 1
BEGIN
    SELECT RAISE(ABORT, 'other word inflections require has_inflections = 1');
END;

CREATE TRIGGER IF NOT EXISTS trg_nominal_inflections_gender_availability_insert
BEFORE INSERT ON nominal_inflections
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) IN ('noun', 'adjective')
 AND NEW.form IS NOT NULL
 AND (
    ((SELECT gender_availability FROM nominal_details WHERE word_id = NEW.word_id) = 'masc' AND NEW.gender = 'fem')
    OR
    ((SELECT gender_availability FROM nominal_details WHERE word_id = NEW.word_id) = 'fem' AND NEW.gender = 'masc')
 )
BEGIN
    SELECT RAISE(ABORT, 'form is not allowed for this gender availability');
END;

CREATE TRIGGER IF NOT EXISTS trg_nominal_inflections_gender_availability_update
BEFORE UPDATE ON nominal_inflections
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) IN ('noun', 'adjective')
 AND NEW.form IS NOT NULL
 AND (
    ((SELECT gender_availability FROM nominal_details WHERE word_id = NEW.word_id) = 'masc' AND NEW.gender = 'fem')
    OR
    ((SELECT gender_availability FROM nominal_details WHERE word_id = NEW.word_id) = 'fem' AND NEW.gender = 'masc')
 )
BEGIN
    SELECT RAISE(ABORT, 'form is not allowed for this gender availability');
END;

CREATE TRIGGER IF NOT EXISTS trg_nominal_details_clear_disallowed_forms_insert
AFTER INSERT ON nominal_details
FOR EACH ROW
BEGIN
    UPDATE nominal_inflections
    SET form = NULL
    WHERE word_id = NEW.word_id
      AND (
        (NEW.gender_availability = 'masc' AND gender = 'fem')
        OR
        (NEW.gender_availability = 'fem' AND gender = 'masc')
      );
END;

CREATE TRIGGER IF NOT EXISTS trg_nominal_details_clear_disallowed_forms_update
AFTER UPDATE OF gender_availability ON nominal_details
FOR EACH ROW
BEGIN
    UPDATE nominal_inflections
    SET form = NULL
    WHERE word_id = NEW.word_id
      AND (
        (NEW.gender_availability = 'masc' AND gender = 'fem')
        OR
        (NEW.gender_availability = 'fem' AND gender = 'masc')
      );
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_clear_inflections_when_disabled
AFTER UPDATE OF has_inflections ON other_details
FOR EACH ROW
WHEN NEW.has_inflections = 0
BEGIN
    DELETE FROM nominal_inflections WHERE word_id = NEW.word_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_participles_word_type_insert
BEFORE INSERT ON verb_participles
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_participles can only be used for verb words');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_participles_word_type_update
BEFORE UPDATE ON verb_participles
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_participles can only be used for verb words');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_forms_word_type_insert
BEFORE INSERT ON verb_forms
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_forms can only be used for verb words');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_forms_word_type_update
BEFORE UPDATE ON verb_forms
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_forms can only be used for verb words');
END;
