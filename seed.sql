PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO verb_persons
    (id, code, label, imperative_label, sort_order)
VALUES
    (1, 'yo', 'yo', 'yo', 1),
    (2, 'tu', 'tú', 'tú', 2),
    (3, 'vos', 'vos', 'vos', 3),
    (4, 'el_ella_usted', 'él/ella/Ud.', 'Ud.', 4),
    (5, 'nosotros', 'nosotros', 'nosotros', 5),
    (6, 'vosotros', 'vosotros', 'vosotros', 6),
    (7, 'ellos_ellas_ustedes', 'ellos/ellas/Uds.', 'Uds.', 7);

INSERT OR IGNORE INTO verb_tenses
    (id, code, label, group_code, sort_order)
VALUES
    (1, 'indicative_present', 'Present', 'indicative', 1),
    (2, 'indicative_preterite', 'Preterite', 'indicative', 2),
    (3, 'indicative_imperfect', 'Imperfect', 'indicative', 3),
    (4, 'indicative_conditional', 'Conditional', 'indicative', 4),
    (5, 'indicative_future', 'Future', 'indicative', 5),

    (6, 'subjunctive_present', 'Present', 'subjunctive', 6),
    (7, 'subjunctive_imperfect', 'Imperfect', 'subjunctive', 7),
    (8, 'subjunctive_future', 'Future', 'subjunctive', 8),

    (9, 'imperative_affirmative', 'Affirmative', 'imperative', 9),
    (10, 'imperative_negative', 'Negative', 'imperative', 10),

    (11, 'progressive_present', 'Present', 'progressive', 11),
    (12, 'progressive_preterite', 'Preterite', 'progressive', 12),
    (13, 'progressive_imperfect', 'Imperfect', 'progressive', 13),
    (14, 'progressive_conditional', 'Conditional', 'progressive', 14),
    (15, 'progressive_future', 'Future', 'progressive', 15),

    (16, 'perfect_present', 'Present', 'perfect', 16),
    (17, 'perfect_preterite', 'Preterite', 'perfect', 17),
    (18, 'perfect_past', 'Past', 'perfect', 18),
    (19, 'perfect_conditional', 'Conditional', 'perfect', 19),
    (20, 'perfect_future', 'Future', 'perfect', 20),

    (21, 'perfect_subjunctive_present', 'Present', 'perfect_subjunctive', 21),
    (22, 'perfect_subjunctive_past', 'Past', 'perfect_subjunctive', 22),
    (23, 'perfect_subjunctive_future', 'Future', 'perfect_subjunctive', 23),

    (24, 'informal_future', 'Informal Future', 'informal_future', 24);
