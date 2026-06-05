import sqlite3
import csv
import os
import sys

if len(sys.argv) < 2:
    print("Usage: python export_sqlite_to_csv.py your_database.db")
    sys.exit(1)

db_path = sys.argv[1]
output_dir = "csv_exports"

os.makedirs(output_dir, exist_ok=True)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all user tables
cursor.execute("""
    SELECT name 
    FROM sqlite_master 
    WHERE type='table' 
    AND name NOT LIKE 'sqlite_%'
""")

tables = [row[0] for row in cursor.fetchall()]

for table in tables:
    cursor.execute(f'SELECT * FROM "{table}"')
    rows = cursor.fetchall()

    column_names = [description[0] for description in cursor.description]

    csv_path = os.path.join(output_dir, f"{table}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(column_names)
        writer.writerows(rows)

    print(f"Exported {table} -> {csv_path}")

conn.close()
print("Done.")
