from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path

from controllers.start_page_presenter import (
    already_added_title,
    create_button_text,
    highlight_match_html,
    primary_action_for_enter,
)
from database import SpanishWordDatabase


ROOT = Path(__file__).resolve().parent


def make_db() -> SpanishWordDatabase:
    temp_dir = tempfile.TemporaryDirectory()
    # Keep TemporaryDirectory alive by attaching it to the DB object for the test duration.
    db = SpanishWordDatabase(Path(temp_dir.name) / "test.db")
    db._temp_dir = temp_dir  # type: ignore[attr-defined]
    return db


def test_presenter_labels() -> None:
    assert already_added_title("verb") == "Already added verbs"
    assert already_added_title("other") == "Already added other words"
    assert create_button_text("verb", "doler") == "Create new verb: doler"
    assert create_button_text("verb", "dormir", exact_match_exists=True) == "Create duplicate verb: dormir"


def test_highlight_match_html_is_safe_and_bolds_match() -> None:
    assert highlight_match_html("dormir", "do") == "<b>do</b>rmir"
    assert highlight_match_html("divertirse", "tir") == "diver<b>tir</b>se"
    assert highlight_match_html("<tag>", "ta") == "&lt;<b>ta</b>g&gt;"


def test_enter_opens_exact_match_else_creates() -> None:
    results = [{"id": 10, "lemma": "dormir", "english": "to sleep", "word_type": "verb"}]
    assert primary_action_for_enter(results, "dormir").name == "open"
    assert primary_action_for_enter(results, "dormir").word_id == 10
    assert primary_action_for_enter(results, "doler").name == "create"
    assert primary_action_for_enter(results, "   ").name == "none"


def test_same_class_search_for_start_page() -> None:
    db = make_db()
    db.create_word("dormir", "verb", english="to sleep")
    db.create_word("decir", "verb", english="to say")
    db.create_word("domingo", "noun", english="Sunday")

    verb_results = db.search_words("verb", "do")
    noun_results = db.search_words("noun", "do")

    assert [row["lemma"] for row in verb_results] == ["dormir"]
    assert [row["lemma"] for row in noun_results] == ["domingo"]


def test_create_new_word_defaults_match_start_page() -> None:
    db = make_db()
    verb_id = db.create_word("doler", "verb", english="")
    verb = db.load_word(verb_id)
    assert verb["word_type"] == "verb"
    assert set(verb["verb"]["participles"]) == {"present", "past"}

    noun_id = db.create_word("casa", "noun", english="", gender_availability="both")
    noun = db.load_word(noun_id)
    assert noun["nominal"]["gender_availability"] == "both"

    other_id = db.create_word("muy", "other", english="", other_subtype="unknown")
    other = db.load_word(other_id)
    assert other["other"]["subtype"] == "unknown"


def test_python_files_compile() -> None:
    for path in ROOT.rglob("*.py"):
        if "__pycache__" not in path.parts:
            py_compile.compile(str(path), doraise=True)


def run_all() -> None:
    tests = [
        test_presenter_labels,
        test_highlight_match_html_is_safe_and_bolds_match,
        test_enter_opens_exact_match_else_creates,
        test_same_class_search_for_start_page,
        test_create_new_word_defaults_match_start_page,
        test_python_files_compile,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("All Phase 3 start-page tests passed.")


if __name__ == "__main__":
    run_all()
