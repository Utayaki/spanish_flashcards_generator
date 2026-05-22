from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from database import SpanishWordDatabase, ValidationError


ROOT = Path(__file__).resolve().parent


def make_db() -> SpanishWordDatabase:
    temp_dir = tempfile.TemporaryDirectory()
    # Keep the temp directory alive by attaching it to the db object.
    db = SpanishWordDatabase(
        Path(temp_dir.name) / "test_spanish_words.db",
        schema_path=ROOT / "schema.sql",
        seed_path=ROOT / "seed.sql",
    )
    db._temp_dir = temp_dir  # type: ignore[attr-defined]
    return db


def test_seed_counts() -> None:
    db = make_db()

    persons = db.list_verb_persons()
    tenses = db.list_verb_tenses()

    assert len(persons) == 7
    assert len(tenses) == 24
    assert persons[2]["code"] == "vos"
    assert persons[5]["code"] == "vosotros"


def test_search_words_stays_inside_class() -> None:
    db = make_db()

    db.create_word("dormir", "verb", english="to sleep")
    db.create_word("dolor", "noun", english="pain", gender_availability="masc")

    verb_results = db.search_words("verb", "do")
    noun_results = db.search_words("noun", "do")

    assert [row["lemma"] for row in verb_results] == ["dormir"]
    assert [row["lemma"] for row in noun_results] == ["dolor"]


def test_nominal_gender_availability_clears_disallowed_forms() -> None:
    db = make_db()

    word_id = db.create_word("casa", "noun", english="house", gender_availability="fem")
    db.save_nominal_inflections(
        word_id,
        {
            ("singular", "masc"): "caso",
            ("singular", "fem"): "casa",
            ("plural", "masc"): "casos",
            ("plural", "fem"): "casas",
        },
    )

    loaded = db.load_word(word_id)
    inflections = loaded["nominal"]["inflections"]

    assert inflections["singular"]["masc"] is None
    assert inflections["plural"]["masc"] is None
    assert inflections["singular"]["fem"] == "casa"
    assert inflections["plural"]["fem"] == "casas"

    db.save_nominal_details(word_id, "both")
    db.save_nominal_inflections(
        word_id,
        {
            ("singular", "masc"): "caso",
            ("plural", "masc"): "casos",
        },
    )

    loaded = db.load_word(word_id)
    inflections = loaded["nominal"]["inflections"]

    assert inflections["singular"]["masc"] == "caso"
    assert inflections["plural"]["masc"] == "casos"


def test_other_subtype_rejects_particle() -> None:
    db = make_db()
    word_id = db.create_word("muy", "other", english="very", other_subtype="adverb")

    try:
        db.save_other_details(word_id, "particle")
    except ValidationError:
        pass
    else:
        raise AssertionError("particle should be rejected")


def test_verb_save_and_load_forms() -> None:
    db = make_db()

    word_id = db.create_word("haber", "verb", english="to have")
    db.save_verb_participles(
        word_id,
        {
            "present": {"form": "habiendo", "is_irregular": False},
            "past": {"form": "habido", "is_irregular": False},
        },
    )
    db.save_verb_forms(
        word_id,
        {
            ("indicative_present", "yo"): {"form": "he", "is_irregular": True},
            ("subjunctive_imperfect", "yo"): {
                "form": "hubiera, hubiese",
                "is_irregular": True,
            },
            ("imperative_affirmative", "yo"): {"form": None, "is_irregular": False},
        },
    )

    loaded = db.load_word(word_id)
    verb = loaded["verb"]

    assert verb["participles"]["present"]["form"] == "habiendo"
    assert verb["participles"]["past"]["form"] == "habido"

    assert verb["forms"]["indicative"]["indicative_present"]["persons"]["yo"]["form"] == "he"
    assert verb["forms"]["indicative"]["indicative_present"]["persons"]["yo"]["is_irregular"] is True

    assert (
        verb["forms"]["subjunctive"]["subjunctive_imperfect"]["persons"]["yo"]["form"]
        == "hubiera, hubiese"
    )

    assert (
        verb["forms"]["imperative"]["imperative_affirmative"]["persons"]["yo"]["form"]
        is None
    )


def test_schema_triggers_reject_wrong_detail_tables() -> None:
    db = make_db()
    word_id = db.create_word("casa", "noun", english="house", gender_availability="fem")

    try:
        with db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO verb_participles
                    (word_id, participle_type, form, is_irregular)
                VALUES (?, 'present', 'casando', 0)
                """,
                (word_id,),
            )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("verb participle insert should be rejected for nouns")


def run_all_tests() -> None:
    tests = [
        test_seed_counts,
        test_search_words_stays_inside_class,
        test_nominal_gender_availability_clears_disallowed_forms,
        test_other_subtype_rejects_particle,
        test_verb_save_and_load_forms,
        test_schema_triggers_reject_wrong_detail_tables,
    ]

    for test in tests:
        test()
        print(f"PASS {test.__name__}")

    print("All Phase 2 database-layer tests passed.")


if __name__ == "__main__":
    run_all_tests()
