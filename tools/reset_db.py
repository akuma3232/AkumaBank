"""Reset AkumaBank's SQLite database without deleting the database file.

Drops every business record (customers, accounts, transactions, loans, requests),
all login accounts, and the profile badges and custom roles owned by them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import DB_PATH, clear_business_data, get_db, init_db


def _row_counts():
    """Return the row count of every table that reset_database() empties."""
    conn = get_db()
    try:
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
    finally:
        conn.close()


def reset_database():
    """Initialize the schema and clear banking records, users, badges and roles."""
    init_db(seed_demo_data=False)
    clear_business_data(include_users=True)


def main():
    before = _row_counts()
    reset_database()
    after = _row_counts()

    print(f"Database reset: {DB_PATH}")
    remaining = {table: count for table, count in after.items() if count}
    if remaining:
        print("Tables still holding rows:")
        for table, count in remaining.items():
            print(f"  {table}: {count}")
    else:
        print("All tables are empty (banking records, users, badges and roles cleared).")
    print(f"Rows removed: {sum(before.values())}")


if __name__ == "__main__":
    main()
