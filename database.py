"""AkumaBank database connection and initialization using SQLite."""

import sqlite3
import os
from decimal import Decimal, InvalidOperation

from morocco_banking import generate_moroccan_rib, generate_card_number

DATABASE_DIR = os.path.join(os.path.dirname(__file__), "database")
DB_PATH = os.path.join(DATABASE_DIR, "banking_system.db")
TRANSFER_FEE = Decimal("10.00")   # deducted from received amount (not sender)
DEPOSIT_FEE  = Decimal("1.00")    # deducted from each deposit


def get_db():
    """Get a database connection with row factory for dict-like access."""
    os.makedirs(DATABASE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(seed_demo_data=False):
    """Initialize the database and optionally seed Moroccan demo records."""
    conn = get_db()
    cur = conn.cursor()

    # ─────────────────────────────────────────────
    # TABLE: BRANCH
    # ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS BRANCH (
            BranchID   INTEGER PRIMARY KEY AUTOINCREMENT,
            BranchName TEXT    NOT NULL,
            BranchCode TEXT    NOT NULL UNIQUE,
            Address    TEXT    NOT NULL,
            City       TEXT    NOT NULL,
            Phone      TEXT    NOT NULL
        )
    """)

    # ─────────────────────────────────────────────
    # TABLE: CUSTOMER
    # ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS CUSTOMER (
            CustomerID   INTEGER PRIMARY KEY AUTOINCREMENT,
            Name         TEXT    NOT NULL,
            DateOfBirth  TEXT    NOT NULL,
            Email        TEXT    NOT NULL UNIQUE,
            Phone        TEXT    NOT NULL,
            Address      TEXT    NOT NULL,
            NationalID   TEXT    NOT NULL UNIQUE,
            CreatedAt    TEXT    DEFAULT (datetime('now'))
        )
    """)

    # ─────────────────────────────────────────────
    # TABLE: ACCOUNT
    # ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ACCOUNT (
            AccountID     INTEGER PRIMARY KEY AUTOINCREMENT,
            CustomerID    INTEGER NOT NULL,
            AccountNumber TEXT    NOT NULL UNIQUE,
            CardNumber    TEXT,
            AccountType   TEXT    NOT NULL CHECK(AccountType IN ('Savings','Current','Fixed Deposit')),
            Balance       REAL    NOT NULL DEFAULT 0.00,
            OpeningDate   TEXT    NOT NULL DEFAULT (date('now')),
            Status        TEXT    NOT NULL DEFAULT 'Active' CHECK(Status IN ('Active','Frozen','Closed')),
            BranchID      INTEGER,
            FOREIGN KEY (CustomerID) REFERENCES CUSTOMER(CustomerID) ON DELETE CASCADE,
            FOREIGN KEY (BranchID)   REFERENCES BRANCH(BranchID)
        )
    """)

    # ─────────────────────────────────────────────
    # TABLE: TRANSACTIONS
    # ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS TRANSACTIONS (
            TransactionID   INTEGER PRIMARY KEY AUTOINCREMENT,
            AccountID       INTEGER NOT NULL,
            TransactionType TEXT    NOT NULL CHECK(TransactionType IN ('Deposit','Withdrawal','Transfer')),
            Amount          REAL    NOT NULL,
            TransactionDate TEXT    NOT NULL DEFAULT (datetime('now')),
            Description     TEXT,
            BalanceAfter    REAL    NOT NULL,
            FOREIGN KEY (AccountID) REFERENCES ACCOUNT(AccountID) ON DELETE CASCADE
        )
    """)

    # ─────────────────────────────────────────────
    # TABLE: LOAN
    # ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS LOAN (
            LoanID       INTEGER PRIMARY KEY AUTOINCREMENT,
            CustomerID   INTEGER NOT NULL,
            LoanType     TEXT    NOT NULL CHECK(LoanType IN ('Home','Car','Personal','Education','Business')),
            Amount       REAL    NOT NULL,
            InterestRate REAL    NOT NULL,
            StartDate    TEXT    NOT NULL DEFAULT (date('now')),
            Status       TEXT    NOT NULL DEFAULT 'Pending' CHECK(Status IN ('Pending','Approved','Rejected','Closed')),
            DisbursementAccountID INTEGER,
            DisbursedAt TEXT,
            FOREIGN KEY (DisbursementAccountID) REFERENCES ACCOUNT(AccountID),
            FOREIGN KEY (CustomerID) REFERENCES CUSTOMER(CustomerID) ON DELETE CASCADE
        )
    """)
    loan_columns = {row["name"] for row in cur.execute("PRAGMA table_info(LOAN)")}
    if "DisbursementAccountID" not in loan_columns:
        cur.execute(
            "ALTER TABLE LOAN ADD COLUMN DisbursementAccountID INTEGER REFERENCES ACCOUNT(AccountID)"
        )
    if "DisbursedAt" not in loan_columns:
        cur.execute("ALTER TABLE LOAN ADD COLUMN DisbursedAt TEXT")

    # ─────────────────────────────────────────────
    # TABLE: USERS (owner, admin, and employee login)
    # ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS USERS (
            UserID   INTEGER PRIMARY KEY AUTOINCREMENT,
            Username TEXT    NOT NULL UNIQUE,
            Password TEXT    NOT NULL,
            ProfilePicture TEXT,
            FullName TEXT,
            Email TEXT,
            DateOfBirth TEXT,
            Phone TEXT,
            Address TEXT,
            NationalID TEXT,
            ApprovalStatus TEXT NOT NULL DEFAULT 'Approved'
                          CHECK(ApprovalStatus IN ('Pending','Approved','Rejected')),
            MustChangePassword INTEGER NOT NULL DEFAULT 0 CHECK(MustChangePassword IN (0,1)),
            Role     TEXT    NOT NULL DEFAULT 'Employee'
                     CHECK(Role IN ('Owner','Admin','Employee','Customer'))
        )
    """)

    user_info = cur.execute("PRAGMA table_info(USERS)").fetchall()
    user_columns = {row["name"] for row in user_info}
    user_table_sql = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='USERS'"
    ).fetchone()["sql"]
    if "'Customer'" not in user_table_sql or "ApprovalStatus" not in user_columns:
        legacy_columns = user_columns
        cur.execute("ALTER TABLE USERS RENAME TO USERS_legacy_roles")
        cur.execute("""
            CREATE TABLE USERS (
                UserID   INTEGER PRIMARY KEY AUTOINCREMENT,
                Username TEXT    NOT NULL UNIQUE,
                Password TEXT    NOT NULL,
                ProfilePicture TEXT,
                FullName TEXT,
                Email TEXT,
                DateOfBirth TEXT,
                Phone TEXT,
                Address TEXT,
                NationalID TEXT,
                ApprovalStatus TEXT NOT NULL DEFAULT 'Approved'
                              CHECK(ApprovalStatus IN ('Pending','Approved','Rejected')),
                MustChangePassword INTEGER NOT NULL DEFAULT 0 CHECK(MustChangePassword IN (0,1)),
                Role     TEXT    NOT NULL DEFAULT 'Employee'
                         CHECK(Role IN ('Owner','Admin','Employee','Customer'))
            )
        """)
        copy_columns = [
            column for column in
            (
                "UserID", "Username", "Password", "ProfilePicture", "FullName", "Email",
                "DateOfBirth", "Phone", "Address", "NationalID", "ApprovalStatus",
                "MustChangePassword", "Role",
            )
            if column in legacy_columns
        ]
        column_list = ", ".join(copy_columns)
        cur.execute(
            f"INSERT INTO USERS ({column_list}) SELECT {column_list} FROM USERS_legacy_roles"
        )
        cur.execute("DROP TABLE USERS_legacy_roles")

    user_columns = {row["name"] for row in cur.execute("PRAGMA table_info(USERS)")}
    for column, definition in (
        ("ProfilePicture", "TEXT"),
        ("FullName", "TEXT"),
        ("Email", "TEXT"),
        ("DateOfBirth", "TEXT"),
        ("Phone", "TEXT"),
        ("Address", "TEXT"),
        ("NationalID", "TEXT"),
        ("ApprovalStatus", "TEXT NOT NULL DEFAULT 'Approved'"),
        ("MustChangePassword", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in user_columns:
            cur.execute(f"ALTER TABLE USERS ADD COLUMN {column} {definition}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS PASSWORD_RESET_REQUEST (
            RequestID INTEGER PRIMARY KEY AUTOINCREMENT,
            UserID INTEGER NOT NULL,
            Status TEXT NOT NULL DEFAULT 'Pending'
                   CHECK(Status IN ('Pending','Approved','Rejected')),
            RequestedAt TEXT NOT NULL DEFAULT (datetime('now')),
            ReviewedAt TEXT,
            ReviewedBy INTEGER,
            FOREIGN KEY (UserID) REFERENCES USERS(UserID) ON DELETE CASCADE,
            FOREIGN KEY (ReviewedBy) REFERENCES USERS(UserID) ON DELETE SET NULL
        )
    """)
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_password_reset_pending "
        "ON PASSWORD_RESET_REQUEST(UserID) WHERE Status='Pending'"
    )

    cur.execute(
        "DELETE FROM USERS WHERE (Username='admin' AND Password='admin123') "
        "OR (Username='employee' AND Password='employee123')"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON USERS(Email) WHERE Email IS NOT NULL"
    )

    branch_columns = {row["name"] for row in cur.execute("PRAGMA table_info(BRANCH)")}
    if "IFSCCode" in branch_columns and "BranchCode" not in branch_columns:
        cur.execute("ALTER TABLE BRANCH RENAME COLUMN IFSCCode TO BranchCode")

    customer_columns = {row["name"] for row in cur.execute("PRAGMA table_info(CUSTOMER)")}
    if "AadhaarNo" in customer_columns and "NationalID" not in customer_columns:
        cur.execute("ALTER TABLE CUSTOMER RENAME COLUMN AadhaarNo TO NationalID")

    account_columns = {row["name"] for row in cur.execute("PRAGMA table_info(ACCOUNT)")}
    if "CardNumber" not in account_columns:
        cur.execute("ALTER TABLE ACCOUNT ADD COLUMN CardNumber TEXT")

    # Upgrade any legacy accounts without CardNumber or using non-RIB ACC format
    legacy_accs = cur.execute(
        "SELECT AccountID, BranchID, AccountNumber, CardNumber FROM ACCOUNT WHERE AccountNumber LIKE 'ACC%' OR CardNumber IS NULL"
    ).fetchall()
    for acc in legacy_accs:
        acc_id = acc["AccountID"]
        old_acc_num = acc["AccountNumber"]
        branch_id = acc["BranchID"] or 1
        new_acc_num = old_acc_num
        if old_acc_num.startswith("ACC"):
            new_acc_num = generate_moroccan_rib(branch_id=branch_id, seq=1000000 + acc_id)
            cur.execute("UPDATE ACCOUNT SET AccountNumber=? WHERE AccountID=?", (new_acc_num, acc_id))
            cur.execute(
                "UPDATE TRANSACTIONS SET Description=REPLACE(Description, ?, ?) WHERE Description LIKE ?",
                (old_acc_num, new_acc_num, f"%{old_acc_num}%"),
            )
        new_card = acc["CardNumber"] or generate_card_number(new_acc_num)
        cur.execute("UPDATE ACCOUNT SET CardNumber=? WHERE AccountID=?", (new_card, acc_id))

    legacy_branches = cur.execute(
        "SELECT COUNT(*) FROM BRANCH WHERE BranchCode LIKE 'BANK00%'"
    ).fetchone()[0]
    legacy_customers = cur.execute("""
        SELECT COUNT(*) FROM CUSTOMER
        WHERE Name IN (
            'Arjun Sharma', 'Priya Patel', 'Rahul Mehta', 'Sneha Reddy',
            'Vikram Singh', 'Kavya Nair', 'Ankit Gupta', 'Pooja Joshi',
            'Suresh Kumar', 'Meera Iyer'
        )
    """).fetchone()[0]
    if legacy_branches == 10 and legacy_customers == 10:
        branches = [
            ("Centre-ville Branch", "MA0001", "12 Boulevard Mohammed V", "Casablanca", "+212 522 11 22 01"),
            ("Agdal Branch", "MA0002", "45 Avenue de France", "Rabat", "+212 537 22 33 02"),
            ("Gueliz Branch", "MA0003", "78 Avenue Mohammed VI", "Marrakech", "+212 524 33 44 03"),
            ("Ville Nouvelle Branch", "MA0004", "23 Avenue Hassan II", "Fes", "+212 535 44 55 04"),
            ("City Centre Branch", "MA0005", "56 Boulevard Pasteur", "Tangier", "+212 539 55 66 05"),
            ("Seafront Branch", "MA0006", "89 Boulevard Hassan II", "Agadir", "+212 528 66 77 06"),
            ("Hamria Branch", "MA0007", "18 Avenue des FAR", "Meknes", "+212 535 77 88 07"),
            ("Medina Branch", "MA0008", "Near Bab Sidi Abdelwahab", "Oujda", "+212 536 88 99 08"),
            ("Centre Branch", "MA0009", "31 Avenue Mohammed V", "Kenitra", "+212 537 99 00 09"),
            ("M'diq Branch", "MA0010", "7 Avenue Hassan II", "Tetouan", "+212 539 10 20 10"),
        ]
        cur.executemany(
            """UPDATE BRANCH SET BranchName=?, BranchCode=?, Address=?, City=?, Phone=?
               WHERE BranchCode=?""",
            [(*branch, f"BANK{branch_id:04d}") for branch_id, branch in enumerate(branches, start=1)],
        )

        customers = [
            ("Youssef El Amrani", "youssef@example.ma", "+212 661 23 45 01", "23 Rue des Oudayas, Casablanca", "AB123456"),
            ("Salma Benali", "salma@example.ma", "+212 662 34 56 02", "45 Avenue Al Alaouiyine, Rabat", "CD234567"),
            ("Omar Alaoui", "omar@example.ma", "+212 663 45 67 03", "78 Rue de la Liberte, Marrakech", "EF345678"),
            ("Nadia Berrada", "nadia@example.ma", "+212 664 56 78 04", "12 Rue Atlas, Fes", "GH456789"),
            ("Karim Idrissi", "karim@example.ma", "+212 665 67 89 05", "56 Boulevard Pasteur, Tangier", "JK567890"),
            ("Imane Chraibi", "imane@example.ma", "+212 666 78 90 06", "89 Avenue des FAR, Agadir", "LM678901"),
            ("Mehdi Fassi", "mehdi@example.ma", "+212 667 89 01 07", "34 Rue de la Republique, Meknes", "NP789012"),
            ("Sara Tazi", "sara@example.ma", "+212 668 90 12 08", "67 Boulevard Mohammed V, Oujda", "QR890123"),
            ("Amine Lahlou", "amine@example.ma", "+212 669 01 23 09", "90 Avenue Hassan II, Kenitra", "ST901234"),
            ("Lina Benjelloun", "lina@example.ma", "+212 660 12 34 10", "11 Avenue Hassan II, Tetouan", "UV012345"),
        ]
        cur.executemany(
            """UPDATE CUSTOMER SET Name=?, Email=?, Phone=?, Address=?, NationalID=?
               WHERE Name=?""",
            [
                (*customer, old_name)
                for customer, old_name in zip(
                    customers,
                    (
                        "Arjun Sharma", "Priya Patel", "Rahul Mehta", "Sneha Reddy",
                        "Vikram Singh", "Kavya Nair", "Ankit Gupta", "Pooja Joshi",
                        "Suresh Kumar", "Meera Iyer",
                    ),
                )
            ],
        )
        # These are fictional demo figures, not customer balances to convert at an FX rate.
        cur.execute("UPDATE ACCOUNT SET Balance=ROUND(Balance * 0.1, 2) WHERE AccountID BETWEEN 1 AND 10")
        cur.execute("UPDATE TRANSACTIONS SET Amount=ROUND(Amount * 0.1, 2), BalanceAfter=ROUND(BalanceAfter * 0.1, 2) WHERE TransactionID BETWEEN 1 AND 12")
        cur.execute("UPDATE LOAN SET Amount=ROUND(Amount * 0.1, 2) WHERE LoanID BETWEEN 1 AND 10")

    # ─────────────────────────────────────────────
    # INDEX for faster lookups
    # ─────────────────────────────────────────────
    cur.execute("CREATE INDEX IF NOT EXISTS idx_account_customer ON ACCOUNT(CustomerID)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_account     ON TRANSACTIONS(AccountID)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_loan_customer   ON LOAN(CustomerID)")

    # ─────────────────────────────────────────────
    # VIEW: CustomerAccountSummary
    # Joins CUSTOMER + ACCOUNT to give a combined summary
    # ─────────────────────────────────────────────
    cur.execute("DROP VIEW IF EXISTS CustomerAccountSummary")
    cur.execute("""
        CREATE VIEW CustomerAccountSummary AS
        SELECT
            c.CustomerID,
            c.Name          AS CustomerName,
            c.Email,
            c.Phone,
            a.AccountID,
            a.AccountNumber,
            a.CardNumber,
            a.AccountType,
            a.Balance,
            a.Status        AS AccountStatus,
            b.BranchName
        FROM CUSTOMER c
        JOIN ACCOUNT  a ON c.CustomerID = a.CustomerID
        LEFT JOIN BRANCH b ON a.BranchID = b.BranchID
    """)

    # ─────────────────────────────────────────────
    # VIEW: TransactionDetails
    # Joins TRANSACTIONS + ACCOUNT + CUSTOMER
    # ─────────────────────────────────────────────
    cur.execute("DROP VIEW IF EXISTS TransactionDetails")
    cur.execute("""
        CREATE VIEW TransactionDetails AS
        SELECT
            t.TransactionID,
            t.TransactionDate,
            t.TransactionType,
            t.Amount,
            t.BalanceAfter,
            t.Description,
            a.AccountNumber,
            c.Name   AS CustomerName,
            c.Email
        FROM TRANSACTIONS t
        JOIN ACCOUNT  a ON t.AccountID  = a.AccountID
        JOIN CUSTOMER c ON a.CustomerID = c.CustomerID
    """)

    # ─────────────────────────────────────────────
    # TRIGGER: UpdateBalanceAfterTransaction
    # Automatically updates ACCOUNT.Balance after insert into TRANSACTIONS
    # ─────────────────────────────────────────────
    cur.execute("DROP TRIGGER IF EXISTS UpdateBalanceAfterTransaction")
    cur.execute("""
        CREATE TRIGGER UpdateBalanceAfterTransaction
        AFTER INSERT ON TRANSACTIONS
        FOR EACH ROW
        BEGIN
            UPDATE ACCOUNT
            SET Balance = NEW.BalanceAfter
            WHERE AccountID = NEW.AccountID;
        END
    """)

    # ─────────────────────────────────────────────
    # SEED DATA — only if tables are empty
    # ─────────────────────────────────────────────
    if seed_demo_data and cur.execute("SELECT COUNT(*) FROM BRANCH").fetchone()[0] == 0:
        branches = [
            ("Centre-ville Branch", "MA0001", "12 Boulevard Mohammed V", "Casablanca", "+212 522 11 22 01"),
            ("Agdal Branch",        "MA0002", "45 Avenue de France",      "Rabat",      "+212 537 22 33 02"),
            ("Gueliz Branch",       "MA0003", "78 Avenue Mohammed VI",    "Marrakech",  "+212 524 33 44 03"),
            ("Ville Nouvelle Branch","MA0004","23 Avenue Hassan II",      "Fes",        "+212 535 44 55 04"),
            ("City Centre Branch",  "MA0005", "56 Boulevard Pasteur",     "Tangier",    "+212 539 55 66 05"),
            ("Seafront Branch",     "MA0006", "89 Boulevard Hassan II",   "Agadir",     "+212 528 66 77 06"),
            ("Hamria Branch",       "MA0007", "18 Avenue des FAR",        "Meknes",     "+212 535 77 88 07"),
            ("Medina Branch",       "MA0008", "Near Bab Sidi Abdelwahab", "Oujda",      "+212 536 88 99 08"),
            ("Centre Branch",       "MA0009", "31 Avenue Mohammed V",     "Kenitra",    "+212 537 99 00 09"),
            ("M'diq Branch",        "MA0010", "7 Avenue Hassan II",       "Tetouan",    "+212 539 10 20 10"),
        ]
        cur.executemany(
            "INSERT INTO BRANCH (BranchName,BranchCode,Address,City,Phone) VALUES (?,?,?,?,?)",
            branches,
        )

    if seed_demo_data and cur.execute("SELECT COUNT(*) FROM CUSTOMER").fetchone()[0] == 0:
        customers = [
            ("Youssef El Amrani", "1992-04-15", "youssef@example.ma", "+212 661 23 45 01", "23 Rue des Oudayas, Casablanca", "AB123456"),
            ("Salma Benali",      "1988-07-22", "salma@example.ma",   "+212 662 34 56 02", "45 Avenue Al Alaouiyine, Rabat", "CD234567"),
            ("Omar Alaoui",       "1995-11-08", "omar@example.ma",    "+212 663 45 67 03", "78 Rue de la Liberte, Marrakech", "EF345678"),
            ("Nadia Berrada",     "1990-03-30", "nadia@example.ma",   "+212 664 56 78 04", "12 Rue Atlas, Fes", "GH456789"),
            ("Karim Idrissi",     "1985-09-14", "karim@example.ma",   "+212 665 67 89 05", "56 Boulevard Pasteur, Tangier", "JK567890"),
            ("Imane Chraibi",     "1993-06-25", "imane@example.ma",   "+212 666 78 90 06", "89 Avenue des FAR, Agadir", "LM678901"),
            ("Mehdi Fassi",       "1997-01-12", "mehdi@example.ma",   "+212 667 89 01 07", "34 Rue de la Republique, Meknes", "NP789012"),
            ("Sara Tazi",         "1986-12-05", "sara@example.ma",    "+212 668 90 12 08", "67 Boulevard Mohammed V, Oujda", "QR890123"),
            ("Amine Lahlou",      "1991-08-18", "amine@example.ma",   "+212 669 01 23 09", "90 Avenue Hassan II, Kenitra", "ST901234"),
            ("Lina Benjelloun",   "1994-02-27", "lina@example.ma",   "+212 660 12 34 10", "11 Avenue Hassan II, Tetouan", "UV012345"),
        ]
        cur.executemany(
            "INSERT INTO CUSTOMER (Name,DateOfBirth,Email,Phone,Address,NationalID) VALUES (?,?,?,?,?,?)",
            customers,
        )

    if seed_demo_data and cur.execute("SELECT COUNT(*) FROM ACCOUNT").fetchone()[0] == 0:
        base_accounts = [
            (1,  "Savings",       15000.00, "2020-01-10", "Active",  1),
            (2,  "Current",        8000.00, "2019-05-20", "Active",  2),
            (3,  "Savings",       22000.00, "2021-03-15", "Active",  3),
            (4,  "Fixed Deposit", 50000.00, "2018-11-01", "Active",  4),
            (5,  "Savings",        4500.00, "2022-07-25", "Active",  5),
            (6,  "Current",       31000.00, "2020-09-10", "Active",  6),
            (7,  "Savings",        7200.00, "2021-12-05", "Frozen",  7),
            (8,  "Savings",       19000.00, "2019-08-14", "Active",  8),
            (9,  "Current",       43000.00, "2017-06-30", "Active",  9),
            (10, "Savings",        9500.00, "2023-02-18", "Active", 10),
        ]
        accounts = []
        for i, (cid, atype, bal, odate, status, bid) in enumerate(base_accounts, start=1):
            rib = generate_moroccan_rib(branch_id=bid, seq=1000000 + i)
            card = generate_card_number(rib)
            accounts.append((cid, rib, card, atype, bal, odate, status, bid))

        cur.executemany(
            "INSERT INTO ACCOUNT (CustomerID,AccountNumber,CardNumber,AccountType,Balance,OpeningDate,Status,BranchID) VALUES (?,?,?,?,?,?,?,?)",
            accounts,
        )

    if seed_demo_data and cur.execute("SELECT COUNT(*) FROM TRANSACTIONS").fetchone()[0] == 0:
        # Get account 3's RIB for the transfer description
        dest_acc = cur.execute("SELECT AccountNumber FROM ACCOUNT WHERE AccountID=3").fetchone()
        dest_rib = dest_acc["AccountNumber"] if dest_acc else "240003000000000100000313"

        # Insert transactions and let the trigger update balances
        txns = [
            (1, "Deposit",    5000.00, "2024-01-05 10:00:00", "Initial deposit",        20000.00),
            (1, "Withdrawal", 1000.00, "2024-01-10 11:30:00", "ATM withdrawal",         19000.00),
            (2, "Deposit",    3000.00, "2024-01-08 09:15:00", "Cash deposit",           11000.00),
            (3, "Deposit",   10000.00, "2024-01-12 14:00:00", "Salary credit",          32000.00),
            (3, "Withdrawal", 2000.00, "2024-01-15 16:45:00", "Online shopping",        30000.00),
            (4, "Deposit",   20000.00, "2024-01-20 08:30:00", "FD renewal",             70000.00),
            (5, "Deposit",    1500.00, "2024-01-22 12:00:00", "Cash deposit",            6000.00),
            (6, "Transfer",   5000.00, "2024-01-25 10:30:00", "Transfer to savings",    26000.00),
            (8, "Deposit",    4000.00, "2024-01-28 15:00:00", "Dividend credit",        23000.00),
            (9, "Withdrawal", 8000.00, "2024-01-30 09:45:00", "Vendor payment",         35000.00),
            (10,"Deposit",    2500.00, "2024-02-01 11:00:00", "Birthday gift deposit",  12000.00),
            (1, "Transfer",   3000.00, "2024-02-05 13:15:00", f"Transfer to {dest_rib}", 16000.00),
        ]
        cur.executemany(
            "INSERT INTO TRANSACTIONS (AccountID,TransactionType,Amount,TransactionDate,Description,BalanceAfter) VALUES (?,?,?,?,?,?)",
            txns,
        )

    if seed_demo_data and cur.execute("SELECT COUNT(*) FROM LOAN").fetchone()[0] == 0:
        loans = [
            (1,  "Home",      250000.00, 8.5,  "2021-06-01", "Approved"),
            (2,  "Car",        65000.00, 10.0, "2022-03-15", "Approved"),
            (3,  "Personal",   20000.00, 12.5, "2023-01-20", "Approved"),
            (4,  "Education",  80000.00, 7.0,  "2020-09-05", "Closed"),
            (5,  "Business",  150000.00, 11.0, "2023-07-10", "Pending"),
            (6,  "Home",      350000.00, 8.0,  "2019-11-25", "Approved"),
            (7,  "Car",        45000.00, 9.5,  "2024-01-08", "Pending"),
            (8,  "Personal",   10000.00, 13.0, "2023-05-12", "Rejected"),
            (9,  "Business",  200000.00, 10.5, "2022-08-30", "Approved"),
            (10, "Education",  60000.00, 6.5,  "2024-02-14", "Pending"),
        ]
        cur.executemany(
            "INSERT INTO LOAN (CustomerID,LoanType,Amount,InterestRate,StartDate,Status) VALUES (?,?,?,?,?,?)",
            loans,
        )

    conn.commit()
    conn.close()


def clear_business_data(include_users=False):
    """Remove customer banking records and optionally login users."""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        tables = ["TRANSACTIONS", "LOAN", "ACCOUNT", "CUSTOMER", "BRANCH"]
        if include_users:
            tables.append("USERS")
        for table in tables:
            conn.execute(f"DELETE FROM {table}")
        placeholders = ", ".join("?" for _ in tables)
        conn.execute(
            f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
            tables,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def transfer_money(from_account_id: int, to_account_id: int, amount: float) -> dict:
    """
    Stored-procedure equivalent: TransferMoney()
    Atomically transfers `amount` from one account to another.
    Fee model: sender's balance is debited by exactly `amount`.
               recipient receives (amount - TRANSFER_FEE) — the fee is kept by the bank.
    Returns {'success': bool, 'message': str}
    """
    conn = get_db()
    cur = conn.cursor()
    try:
        try:
            transfer_amount = Decimal(str(amount))
            if (
                not transfer_amount.is_finite()
                or transfer_amount <= 0
                or transfer_amount != transfer_amount.quantize(Decimal("0.01"))
            ):
                return {"success": False, "message": "Enter a valid transfer amount."}
        except InvalidOperation:
            return {"success": False, "message": "Enter a valid transfer amount."}

        if transfer_amount <= TRANSFER_FEE:
            return {
                "success": False,
                "message": f"Transfer amount must exceed the MAD {TRANSFER_FEE:.2f} bank fee.",
            }

        cur.execute("BEGIN IMMEDIATE")
        # Validate source account
        src = cur.execute(
            "SELECT AccountID, AccountNumber, Balance, Status FROM ACCOUNT WHERE AccountID=?",
            (from_account_id,),
        ).fetchone()
        if not src:
            return {"success": False, "message": "Source account not found."}
        if src["Status"] != "Active":
            return {"success": False, "message": "Source account is not active."}
        source_balance = Decimal(str(src["Balance"]))
        if source_balance < transfer_amount:
            return {"success": False, "message": "Insufficient balance."}

        # Validate destination account
        dst = cur.execute(
            "SELECT AccountID, AccountNumber, Balance, Status FROM ACCOUNT WHERE AccountID=?",
            (to_account_id,),
        ).fetchone()
        if not dst:
            return {"success": False, "message": "Destination account not found."}
        if dst["Status"] != "Active":
            return {"success": False, "message": "Destination account is not active."}

        # Fee is deducted from the received amount, not from sender separately
        received_amount = transfer_amount - TRANSFER_FEE
        new_src_balance = source_balance - transfer_amount
        new_dst_balance = Decimal(str(dst["Balance"])) + received_amount

        # Debit sender (full amount)
        cur.execute(
            """INSERT INTO TRANSACTIONS (AccountID,TransactionType,Amount,Description,BalanceAfter)
               VALUES (?,?,?,?,?)""",
            (
                from_account_id, "Transfer", float(transfer_amount),
                f"Transfer to {dst['AccountNumber']}", float(new_src_balance),
            ),
        )
        # Credit recipient (amount minus bank fee)
        cur.execute(
            """INSERT INTO TRANSACTIONS (AccountID,TransactionType,Amount,Description,BalanceAfter)
               VALUES (?,?,?,?,?)""",
            (
                to_account_id, "Deposit", float(received_amount),
                f"Transfer from {src['AccountNumber']} (MAD {TRANSFER_FEE:.2f} bank fee deducted)",
                float(new_dst_balance),
            ),
        )

        conn.commit()
        return {
            "success": True,
            "message": (
                f"MAD {transfer_amount:,.2f} sent. "
                f"Recipient receives MAD {received_amount:,.2f} after the MAD {TRANSFER_FEE:,.2f} bank fee."
            ),
        }
    except Exception as e:
        conn.rollback()
        return {"success": False, "message": str(e)}
    finally:
        conn.close()
