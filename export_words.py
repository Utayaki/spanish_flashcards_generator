from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB_PATH = Path("word_bank.db")
DEFAULT_OUTPUT_DIR = Path("words_export")
DEFAULT_BATCH_SIZE = 100

GENDER_FORM_SLOTS = (
    ("singular", "masculine", "m/one"),
    ("singular", "feminine", "f/one"),
    ("plural", "masculine", "m/many"),
    ("plural", "feminine", "f/many"),
)

PLURALITY_FORM_SLOTS = (
    ("singular", "one"),
    ("plural", "many"),
)

WORDS_QUERY = """
SELECT li.id, li.lexical_item_type, li.headword, li.explanation,
       nd.gender_availability AS meta,
       nf.grammatical_number, nf.grammatical_gender, nf.form
FROM lexical_items li
JOIN noun_details nd ON nd.lexical_item_id = li.id
JOIN noun_forms nf ON nf.lexical_item_id = li.id

UNION ALL

SELECT li.id, li.lexical_item_type, li.headword, li.explanation,
       'both' AS meta,
       af.grammatical_number, af.grammatical_gender, af.form
FROM lexical_items li
JOIN adjective_details ad ON ad.lexical_item_id = li.id
JOIN adjective_forms af ON af.lexical_item_id = li.id
WHERE ad.inflection_type = 'gender_plurality'

UNION ALL

SELECT li.id, li.lexical_item_type, li.headword, li.explanation,
       'both' AS meta,
       of.grammatical_number, of.grammatical_gender, of.form
FROM lexical_items li
JOIN other_details od ON od.lexical_item_id = li.id
JOIN other_forms of ON of.lexical_item_id = li.id
WHERE od.inflection_type = 'gender_plurality'

UNION ALL

SELECT li.id, li.lexical_item_type, li.headword, li.explanation,
       'plurality' AS meta,
       of.grammatical_number, of.grammatical_gender, of.form
FROM lexical_items li
JOIN other_details od ON od.lexical_item_id = li.id
JOIN other_forms of ON of.lexical_item_id = li.id
WHERE od.inflection_type = 'plurality'

UNION ALL

SELECT li.id, li.lexical_item_type, li.headword, li.explanation,
       'none' AS meta,
       NULL, NULL, NULL
FROM lexical_items li
JOIN other_details od ON od.lexical_item_id = li.id
WHERE od.inflection_type = 'none';
"""

GenderForms = dict[tuple[str, str], str]
PluralityForms = dict[str, str]
GroupedItem = tuple[str, str, str, str, GenderForms | PluralityForms | None]


def format_gender_forms(forms: GenderForms) -> str:
    parts = [
        f"{label} {forms[(number, gender)]}"
        for number, gender, label in GENDER_FORM_SLOTS
        if (number, gender) in forms
    ]
    return ", ".join(parts)


def format_plurality_forms(forms: PluralityForms) -> str:
    parts = [
        f"{label} {forms[number]}"
        for number, label in PLURALITY_FORM_SLOTS
        if number in forms
    ]
    return ", ".join(parts)


def format_forms(meta: str, forms: GenderForms | PluralityForms | None) -> str:
    if forms is None:
        return ""
    if meta == "plurality":
        return format_plurality_forms(forms)  # type: ignore[arg-type]
    return format_gender_forms(forms)  # type: ignore[arg-type]


def format_line(
    item_type: str,
    headword: str,
    meta: str,
    explanation: str,
    forms: GenderForms | PluralityForms | None,
) -> str:
    prefix = f"{item_type} | {headword} ({meta}) | {explanation}"
    if meta == "none":
        return prefix
    return f"{prefix}: {format_forms(meta, forms)}"


def fetch_word_lines(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(WORDS_QUERY).fetchall()
    grouped: dict[int, GroupedItem] = {}

    for (
        lexical_item_id,
        item_type,
        headword,
        explanation,
        meta,
        number,
        grammatical_gender,
        form,
    ) in rows:
        item_id = int(lexical_item_id)
        if item_id not in grouped:
            grouped[item_id] = (str(item_type), str(headword), str(meta), str(explanation), None)

        if meta == "none":
            continue

        item_type, headword, meta, explanation, existing_forms = grouped[item_id]
        if meta == "plurality":
            forms: GenderForms | PluralityForms = dict(existing_forms) if existing_forms else {}
            forms[str(number)] = str(form)
            grouped[item_id] = (item_type, headword, meta, explanation, forms)
        else:
            gender_forms: GenderForms = dict(existing_forms) if existing_forms else {}
            gender_forms[(str(number), str(grammatical_gender))] = str(form)
            grouped[item_id] = (item_type, headword, meta, explanation, gender_forms)

    return [
        format_line(item_type, headword, meta, explanation, forms)
        for item_type, headword, meta, explanation, forms in sorted(
            grouped.values(), key=lambda item: item[1].casefold()
        )
    ]


def write_exports(lines: list[str], output_dir: Path, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "all.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    batch_count = 0
    for batch_index, start in enumerate(range(0, len(lines), batch_size), start=1):
        chunk = lines[start : start + batch_size]
        (output_dir / f"batch_{batch_index:03d}.txt").write_text(
            "\n".join(chunk) + ("\n" if chunk else ""),
            encoding="utf-8",
        )
        batch_count += 1

    return batch_count


def export_words(
    db_path: str | Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    with sqlite3.connect(db_path) as connection:
        lines = fetch_word_lines(connection)

    batch_count = write_exports(lines, output_dir, batch_size=batch_size)
    print(f"Exported {len(lines)} lines to {output_dir}/all.txt")
    if batch_count:
        print(f"Wrote {batch_count} batch file(s) ({batch_size} lines each, last may be shorter)")
    print("Done.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export words from word_bank.db to text files.")
    parser.add_argument(
        "db_path",
        nargs="?",
        default=str(DEFAULT_DB_PATH),
        help=f"path to word bank database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"output folder (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"lines per batch file (default: {DEFAULT_BATCH_SIZE})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.batch_size < 1:
        print("batch-size must be at least 1", file=sys.stderr)
        return 1

    db_path = Path(args.db_path)
    if not db_path.is_file():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1

    export_words(
        db_path=db_path,
        output_dir=Path(args.output_dir),
        batch_size=args.batch_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
