from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB_PATH = Path("word_bank.db")
DEFAULT_OUTPUT_DIR = Path("verbs_export")
DEFAULT_BATCH_SIZE = 100

VERBS_QUERY = """
SELECT li.id, li.headword, li.explanation,
       vfd.sort_order,
       CASE
         WHEN vfd.person_code IS NULL THEN vfd.group_code || '_' || vfd.tense_code
         ELSE vfd.group_code || '_' || vfd.tense_code || '_' || vfd.person_code
       END AS form_code,
       vf.form
FROM lexical_items li
LEFT JOIN verb_forms vf ON vf.lexical_item_id = li.id
LEFT JOIN verb_form_definitions vfd ON vfd.id = vf.verb_form_id
WHERE li.lexical_item_type = 'verb'
ORDER BY li.headword COLLATE NOCASE, vfd.sort_order
"""

GroupedVerb = tuple[str, str, list[tuple[str, str]]]


def format_line(headword: str, explanation: str, forms: list[tuple[str, str]]) -> str:
    prefix = f"verb | {headword} | {explanation}"
    if not forms:
        return prefix
    forms_text = ", ".join(f"{code} {form}" for code, form in forms)
    return f"{prefix}: {forms_text}"


def fetch_verb_lines(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(VERBS_QUERY).fetchall()
    grouped: dict[int, GroupedVerb] = {}

    for lexical_item_id, headword, explanation, _sort_order, form_code, form in rows:
        item_id = int(lexical_item_id)
        if item_id not in grouped:
            grouped[item_id] = (str(headword), str(explanation), [])

        if form_code is None or form is None:
            continue

        headword_str, explanation_str, forms = grouped[item_id]
        forms.append((str(form_code), str(form)))
        grouped[item_id] = (headword_str, explanation_str, forms)

    return [
        format_line(headword, explanation, forms)
        for headword, explanation, forms in sorted(
            grouped.values(), key=lambda item: item[0].casefold()
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


def export_verbs(
    db_path: str | Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    with sqlite3.connect(db_path) as connection:
        lines = fetch_verb_lines(connection)

    batch_count = write_exports(lines, output_dir, batch_size=batch_size)
    print(f"Exported {len(lines)} lines to {output_dir}/all.txt")
    if batch_count:
        print(f"Wrote {batch_count} batch file(s) ({batch_size} lines each, last may be shorter)")
    print("Done.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export verbs from word_bank.db to text files.")
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

    export_verbs(
        db_path=db_path,
        output_dir=Path(args.output_dir),
        batch_size=args.batch_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
