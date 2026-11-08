"""Clear AkumaBank's SQLite banking records without deleting the database file."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import DB_PATH, clear_business_data, init_db


def reset_database():
    """Initialize the schema and clear banking records while preserving users."""
    init_db(seed_demo_data=False)
    clear_business_data()


def main():
    reset_database()
    print(f"Banking records cleared: {DB_PATH}")


if __name__ == "__main__":
    main()
