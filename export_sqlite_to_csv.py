from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

OUTPUT_DIR = Path("csv_exports")
USAGE = "Usage: python export_sqlite_to_csv.py your_database.db"


def user_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def quoted_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def export_table(connection: sqlite3.Connection, table: str, output_dir: Path) -> Path:
    cursor = connection.execute(f"SELECT * FROM {quoted_identifier(table)}")
    rows = cursor.fetchall()
    column_names = [description[0] for description in cursor.description]
    csv_path = output_dir / f"{table}.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(column_names)
        writer.writerows(rows)

    return csv_path


def export_database(db_path: str | Path, output_dir: Path = OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        for table in user_tables(connection):
            csv_path = export_table(connection, table, output_dir)
            print(f"Exported {table} -> {csv_path}")
    print("Done.")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(USAGE)
        return 1
    export_database(args[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
