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

CREATE TABLE IF NOT EXISTS noun_details (
    word_id INTEGER PRIMARY KEY,
    gender_availability TEXT NOT NULL CHECK (gender_availability IN ('masculine', 'feminine', 'both', 'ambiguous')),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS noun_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_noun_forms_unique
ON noun_forms(word_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_noun_forms_word
ON noun_forms(word_id);

CREATE TABLE IF NOT EXISTS adjective_details (
    word_id INTEGER PRIMARY KEY,
    inflection_type TEXT NOT NULL CHECK (inflection_type IN ('plurality', 'gender_plurality')),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS adjective_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_adjective_forms_unique
ON adjective_forms(word_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_adjective_forms_word
ON adjective_forms(word_id);

CREATE TABLE IF NOT EXISTS other_details (
    word_id INTEGER PRIMARY KEY,
    inflection_type TEXT NOT NULL DEFAULT 'none'
        CHECK (inflection_type IN ('none', 'plurality', 'gender_plurality', 'person_gender_plurality')),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS other_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL,
    person_code TEXT CHECK (person_code IN (
        'yo', 'tu', 'vos', 'el_ella_usted', 'nosotros', 'vosotros', 'ellos_ellas_ustedes'
    ) OR person_code IS NULL),
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT CHECK (form IS NULL OR length(trim(form)) > 0),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_other_forms_unique
ON other_forms(
    word_id,
    COALESCE(person_code, 'none'),
    grammatical_number,
    COALESCE(grammatical_gender, 'shared')
);

CREATE INDEX IF NOT EXISTS idx_other_forms_word
ON other_forms(word_id);

CREATE TABLE IF NOT EXISTS verb_participles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER NOT NULL,
    participle_type TEXT NOT NULL CHECK (participle_type IN ('present', 'past')),
    form TEXT CHECK (form IS NULL OR length(trim(form)) > 0),
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
    UNIQUE (word_id, tense_id, person_id),
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE,
    FOREIGN KEY (tense_id) REFERENCES verb_tenses(id) ON DELETE CASCADE,
    FOREIGN KEY (person_id) REFERENCES verb_persons(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verb_forms_word_tense
ON verb_forms(word_id, tense_id);

CREATE TRIGGER IF NOT EXISTS trg_noun_details_word_type_insert
BEFORE INSERT ON noun_details
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_details can only be used for noun words');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_details_word_type_update
BEFORE UPDATE ON noun_details
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_details can only be used for noun words');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_forms_word_type_insert
BEFORE INSERT ON noun_forms
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_forms can only be used for noun words');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_forms_word_type_update
BEFORE UPDATE ON noun_forms
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_forms can only be used for noun words');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_details_word_type_insert
BEFORE INSERT ON adjective_details
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_details can only be used for adjective words');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_details_word_type_update
BEFORE UPDATE ON adjective_details
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_details can only be used for adjective words');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_forms_word_type_insert
BEFORE INSERT ON adjective_forms
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_forms can only be used for adjective words');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_forms_word_type_update
BEFORE UPDATE ON adjective_forms
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_forms can only be used for adjective words');
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

CREATE TRIGGER IF NOT EXISTS trg_other_forms_word_type_insert
BEFORE INSERT ON other_forms
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_forms can only be used for other words');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_word_type_update
BEFORE UPDATE ON other_forms
FOR EACH ROW
WHEN (SELECT word_type FROM words WHERE id = NEW.word_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_forms can only be used for other words');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_type_insert
BEFORE INSERT ON other_forms
FOR EACH ROW
WHEN COALESCE((SELECT inflection_type FROM other_details WHERE word_id = NEW.word_id), 'none') NOT IN ('plurality', 'gender_plurality', 'person_gender_plurality')
BEGIN
    SELECT RAISE(ABORT, 'other_forms require an inflected other word');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_type_update
BEFORE UPDATE ON other_forms
FOR EACH ROW
WHEN COALESCE((SELECT inflection_type FROM other_details WHERE word_id = NEW.word_id), 'none') NOT IN ('plurality', 'gender_plurality', 'person_gender_plurality')
BEGIN
    SELECT RAISE(ABORT, 'other_forms require an inflected other word');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_clear_forms_when_none
AFTER UPDATE OF inflection_type ON other_details
FOR EACH ROW
WHEN NEW.inflection_type = 'none'
BEGIN
    DELETE FROM other_forms WHERE word_id = NEW.word_id;
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
