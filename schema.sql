PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lemma (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma TEXT NOT NULL CHECK (length(trim(lemma)) > 0),
    english TEXT NOT NULL DEFAULT '' CHECK (english = '' OR length(trim(english)) > 0),
    lemma_type TEXT NOT NULL CHECK (lemma_type IN ('noun', 'verb', 'adjective', 'other')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_lemma_type_lemma
ON lemma(lemma_type, lemma COLLATE NOCASE);

CREATE TRIGGER IF NOT EXISTS trg_lemma_updated_at
AFTER UPDATE ON lemma
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE lemma
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS noun_details (
    lemma_id INTEGER PRIMARY KEY,
    gender_availability TEXT NOT NULL CHECK (gender_availability IN ('masculine', 'feminine', 'both')),
    FOREIGN KEY (lemma_id) REFERENCES lemma(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS noun_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lemma_id) REFERENCES lemma(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_noun_forms_unique
ON noun_forms(lemma_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_noun_forms_lemma
ON noun_forms(lemma_id);

CREATE TABLE IF NOT EXISTS adjective_details (
    lemma_id INTEGER PRIMARY KEY,
    inflection_type TEXT NOT NULL CHECK (inflection_type IN ('plurality', 'gender_plurality')),
    FOREIGN KEY (lemma_id) REFERENCES lemma(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS adjective_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lemma_id) REFERENCES lemma(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_adjective_forms_unique
ON adjective_forms(lemma_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_adjective_forms_lemma
ON adjective_forms(lemma_id);

CREATE TABLE IF NOT EXISTS other_details (
    lemma_id INTEGER PRIMARY KEY,
    inflection_type TEXT NOT NULL DEFAULT 'none'
        CHECK (inflection_type IN ('none', 'plurality', 'gender_plurality')),
    FOREIGN KEY (lemma_id) REFERENCES lemma(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS other_forms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id INTEGER NOT NULL,
    grammatical_number TEXT NOT NULL CHECK (grammatical_number IN ('singular', 'plural')),
    grammatical_gender TEXT CHECK (grammatical_gender IN ('masculine', 'feminine') OR grammatical_gender IS NULL),
    form TEXT NOT NULL CHECK (length(trim(form)) > 0),
    FOREIGN KEY (lemma_id) REFERENCES lemma(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_other_forms_unique
ON other_forms(lemma_id, grammatical_number, COALESCE(grammatical_gender, 'shared'));

CREATE INDEX IF NOT EXISTS idx_other_forms_lemma
ON other_forms(lemma_id);

CREATE TABLE IF NOT EXISTS verb_participles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id INTEGER NOT NULL,
    participle_type TEXT NOT NULL CHECK (participle_type IN ('present', 'past')),
    form TEXT CHECK (form IS NULL OR length(trim(form)) > 0),
    UNIQUE (lemma_id, participle_type),
    FOREIGN KEY (lemma_id) REFERENCES lemma(id) ON DELETE CASCADE
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
    lemma_id INTEGER NOT NULL,
    tense_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    form TEXT CHECK (form IS NULL OR length(trim(form)) > 0),
    UNIQUE (lemma_id, tense_id, person_id),
    FOREIGN KEY (lemma_id) REFERENCES lemma(id) ON DELETE CASCADE,
    FOREIGN KEY (tense_id) REFERENCES verb_tenses(id) ON DELETE CASCADE,
    FOREIGN KEY (person_id) REFERENCES verb_persons(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verb_forms_lemma_tense
ON verb_forms(lemma_id, tense_id);

CREATE TRIGGER IF NOT EXISTS trg_noun_details_lemma_type_insert
BEFORE INSERT ON noun_details
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_details can only be used for noun lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_details_lemma_type_update
BEFORE UPDATE ON noun_details
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_details can only be used for noun lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_forms_lemma_type_insert
BEFORE INSERT ON noun_forms
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_forms can only be used for noun lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_noun_forms_lemma_type_update
BEFORE UPDATE ON noun_forms
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'noun'
BEGIN
    SELECT RAISE(ABORT, 'noun_forms can only be used for noun lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_details_lemma_type_insert
BEFORE INSERT ON adjective_details
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_details can only be used for adjective lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_details_lemma_type_update
BEFORE UPDATE ON adjective_details
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_details can only be used for adjective lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_forms_lemma_type_insert
BEFORE INSERT ON adjective_forms
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_forms can only be used for adjective lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_adjective_forms_lemma_type_update
BEFORE UPDATE ON adjective_forms
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'adjective'
BEGIN
    SELECT RAISE(ABORT, 'adjective_forms can only be used for adjective lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_lemma_type_insert
BEFORE INSERT ON other_details
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_details can only be used for other lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_details_lemma_type_update
BEFORE UPDATE ON other_details
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_details can only be used for other lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_lemma_type_insert
BEFORE INSERT ON other_forms
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_forms can only be used for other lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_other_forms_lemma_type_update
BEFORE UPDATE ON other_forms
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'other'
BEGIN
    SELECT RAISE(ABORT, 'other_forms can only be used for other lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_participles_lemma_type_insert
BEFORE INSERT ON verb_participles
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_participles can only be used for verb lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_participles_lemma_type_update
BEFORE UPDATE ON verb_participles
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_participles can only be used for verb lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_forms_lemma_type_insert
BEFORE INSERT ON verb_forms
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_forms can only be used for verb lemmas');
END;

CREATE TRIGGER IF NOT EXISTS trg_verb_forms_lemma_type_update
BEFORE UPDATE ON verb_forms
FOR EACH ROW
WHEN (SELECT lemma_type FROM lemma WHERE id = NEW.lemma_id) != 'verb'
BEGIN
    SELECT RAISE(ABORT, 'verb_forms can only be used for verb lemmas');
END;
