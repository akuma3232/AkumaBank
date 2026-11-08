"""Create the first AkumaBank owner account interactively."""

import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from werkzeug.security import generate_password_hash

from database import get_db, init_db


def main():
    init_db(seed_demo_data=False)
    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM USERS WHERE Role='Owner' LIMIT 1").fetchone():
            raise SystemExit("An owner account already exists; refusing to create another.")

        username = input("Owner username: ").strip()
        if not username:
            raise SystemExit("Username cannot be empty.")

        email = input("Owner email: ").strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise SystemExit("Enter a valid email address.")
        if conn.execute(
            "SELECT 1 FROM USERS WHERE lower(Email)=lower(?) LIMIT 1", (email,)
        ).fetchone():
            raise SystemExit("That email address is already in use.")

        password = getpass.getpass("Owner password (minimum 12 characters): ")
        confirmation = getpass.getpass("Confirm owner password: ")
        if len(password) < 12:
            raise SystemExit("Password must be at least 12 characters.")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")

        conn.execute(
            "INSERT INTO USERS (Username, Password, Email, Role) VALUES (?, ?, ?, 'Owner')",
            (username, generate_password_hash(password), email),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Owner account '{username}' ({email}) created.")


if __name__ == "__main__":
    main()
