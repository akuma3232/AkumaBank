-- ═══════════════════════════════════════════════════════════════════════════
--  AkumaBank — Morocco Banking
--  Complete SQL Schema (MySQL-compatible syntax, runs on SQLite)
--  Database: banking_system
-- ═══════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────
-- 1. TABLE: BRANCH
--    Stores all bank branch information.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS BRANCH (
    BranchID   INTEGER PRIMARY KEY AUTOINCREMENT,
    BranchName TEXT    NOT NULL,
    BranchCode TEXT    NOT NULL UNIQUE,
    Address    TEXT    NOT NULL,
    City       TEXT    NOT NULL,
    Phone      TEXT    NOT NULL
);

-- ─────────────────────────────────────────────────────────────────────────
-- 2. TABLE: CUSTOMER
--    Stores personal information for every bank customer.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS CUSTOMER (
    CustomerID   INTEGER PRIMARY KEY AUTOINCREMENT,
    Name         TEXT    NOT NULL,
    DateOfBirth  TEXT    NOT NULL,
    Email        TEXT    NOT NULL UNIQUE,
    Phone        TEXT    NOT NULL,
    Address      TEXT    NOT NULL,
    NationalID   TEXT    NOT NULL UNIQUE,
    CreatedAt    TEXT    DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────────────────────
-- 3. TABLE: ACCOUNT
--    One customer can have multiple accounts.
--    FK → CUSTOMER, BRANCH
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ACCOUNT (
    AccountID     INTEGER PRIMARY KEY AUTOINCREMENT,
    CustomerID    INTEGER NOT NULL,
    AccountNumber TEXT    NOT NULL UNIQUE,
    CardNumber    TEXT,
    CardTier      TEXT    DEFAULT 'standard',
    AccountType   TEXT    NOT NULL CHECK(AccountType IN ('Savings','Current','Fixed Deposit')),
    Balance       REAL    NOT NULL DEFAULT 0.00,
    OpeningDate   TEXT    NOT NULL DEFAULT (date('now')),
    Status        TEXT    NOT NULL DEFAULT 'Active' CHECK(Status IN ('Active','Frozen','Closed')),
    BranchID      INTEGER,
    FOREIGN KEY (CustomerID) REFERENCES CUSTOMER(CustomerID) ON DELETE CASCADE,
    FOREIGN KEY (BranchID)   REFERENCES BRANCH(BranchID)
);

-- ─────────────────────────────────────────────────────────────────────────
-- 4. TABLE: TRANSACTIONS
--    Every deposit, withdrawal, or transfer is logged here.
--    NOTE: "TRANSACTION" is a reserved keyword in SQLite → renamed TRANSACTIONS
--    The trigger UpdateBalanceAfterTransaction fires on each INSERT.
--    FK → ACCOUNT
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS TRANSACTIONS (
    TransactionID   INTEGER PRIMARY KEY AUTOINCREMENT,
    AccountID       INTEGER NOT NULL,
    TransactionType TEXT    NOT NULL CHECK(TransactionType IN ('Deposit','Withdrawal','Transfer')),
    Amount          REAL    NOT NULL CHECK(Amount > 0),
    TransactionDate TEXT    NOT NULL DEFAULT (datetime('now')),
    Description     TEXT,
    BalanceAfter    REAL    NOT NULL,
    FOREIGN KEY (AccountID) REFERENCES ACCOUNT(AccountID) ON DELETE CASCADE
);

-- ─────────────────────────────────────────────────────────────────────────
-- 5. TABLE: LOAN
--    Loan applications linked to a customer.
--    FK → CUSTOMER
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS LOAN (
    LoanID       INTEGER PRIMARY KEY AUTOINCREMENT,
    CustomerID   INTEGER NOT NULL,
    LoanType     TEXT    NOT NULL CHECK(LoanType IN ('Home','Car','Personal','Education','Business')),
    Amount       REAL    NOT NULL CHECK(Amount > 0),
    InterestRate REAL    NOT NULL CHECK(InterestRate > 0),
    StartDate    TEXT    NOT NULL DEFAULT (date('now')),
    Status       TEXT    NOT NULL DEFAULT 'Pending' CHECK(Status IN ('Pending','Approved','Rejected','Closed')),
    DisbursementAccountID INTEGER,
    DisbursedAt TEXT,
    FOREIGN KEY (DisbursementAccountID) REFERENCES ACCOUNT(AccountID),
    FOREIGN KEY (CustomerID) REFERENCES CUSTOMER(CustomerID) ON DELETE CASCADE
);

-- ─────────────────────────────────────────────────────────────────────────
-- 6. TABLE: USERS
--    Application login table (Admin / Employee roles).
-- ─────────────────────────────────────────────────────────────────────────
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
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON USERS(Email) WHERE Email IS NOT NULL;

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
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_password_reset_pending
    ON PASSWORD_RESET_REQUEST(UserID) WHERE Status='Pending';

-- ─────────────────────────────────────────────────────────────────────────
-- 8. TABLE: ACCOUNT_CLOSURE_REQUEST
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ACCOUNT_CLOSURE_REQUEST (
    RequestID   INTEGER PRIMARY KEY AUTOINCREMENT,
    AccountID   INTEGER NOT NULL,
    CustomerID  INTEGER NOT NULL,
    Reason      TEXT,
    Status      TEXT NOT NULL DEFAULT 'Pending'
               CHECK(Status IN ('Pending','Approved','Rejected')),
    RequestedAt TEXT NOT NULL DEFAULT (datetime('now')),
    ReviewedAt  TEXT,
    ReviewedBy  INTEGER,
    AdminNote   TEXT,
    FOREIGN KEY (AccountID) REFERENCES ACCOUNT(AccountID) ON DELETE CASCADE,
    FOREIGN KEY (CustomerID) REFERENCES CUSTOMER(CustomerID) ON DELETE CASCADE,
    FOREIGN KEY (ReviewedBy) REFERENCES USERS(UserID) ON DELETE SET NULL
);

-- ─────────────────────────────────────────────────────────────────────────
-- 9. TABLE: DOCUMENT_REQUEST
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS DOCUMENT_REQUEST (
    RequestID     INTEGER PRIMARY KEY AUTOINCREMENT,
    CustomerID    INTEGER NOT NULL,
    AccountID     INTEGER,
    DocumentType  TEXT NOT NULL,
    DocumentTitle TEXT NOT NULL,
    Purpose       TEXT,
    Status        TEXT NOT NULL DEFAULT 'Pending'
                  CHECK(Status IN ('Pending','Approved','Rejected','Cancelled')),
    RequestedAt   TEXT NOT NULL DEFAULT (datetime('now')),
    ProcessedAt   TEXT,
    ProcessedBy   INTEGER,
    AdminNote     TEXT,
    SignedPdfFile TEXT,
    FOREIGN KEY (CustomerID) REFERENCES CUSTOMER(CustomerID) ON DELETE CASCADE,
    FOREIGN KEY (AccountID) REFERENCES ACCOUNT(AccountID) ON DELETE SET NULL,
    FOREIGN KEY (ProcessedBy) REFERENCES USERS(UserID) ON DELETE SET NULL
);

-- ─────────────────────────────────────────────────────────────────────────
-- 10. TABLE: ACCOUNT_OPENING_REQUEST
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ACCOUNT_OPENING_REQUEST (
    RequestID        INTEGER PRIMARY KEY AUTOINCREMENT,
    CustomerID       INTEGER NOT NULL,
    AccountType      TEXT NOT NULL DEFAULT 'Current',
    CardTier         TEXT NOT NULL DEFAULT 'standard',
    InitialDeposit   REAL DEFAULT 0.0,
    BranchID         INTEGER,
    Reason           TEXT,
    Status           TEXT NOT NULL DEFAULT 'Pending'
                     CHECK(Status IN ('Pending','Approved','Rejected')),
    RequestedAt      TEXT NOT NULL DEFAULT (datetime('now')),
    ReviewedAt       TEXT,
    ReviewedBy       INTEGER,
    AdminNote        TEXT,
    CreatedAccountID INTEGER,
    FOREIGN KEY (CustomerID) REFERENCES CUSTOMER(CustomerID) ON DELETE CASCADE,
    FOREIGN KEY (BranchID) REFERENCES BRANCH(BranchID),
    FOREIGN KEY (ReviewedBy) REFERENCES USERS(UserID),
    FOREIGN KEY (CreatedAccountID) REFERENCES ACCOUNT(AccountID)
);


-- ═══════════════════════════════════════════════════════════════════════════
-- INDEXES — for faster lookups on foreign-key columns
-- ═══════════════════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_account_customer ON ACCOUNT(CustomerID);
CREATE INDEX IF NOT EXISTS idx_txn_account      ON TRANSACTIONS(AccountID);
CREATE INDEX IF NOT EXISTS idx_loan_customer    ON LOAN(CustomerID);
CREATE INDEX IF NOT EXISTS idx_account_branch   ON ACCOUNT(BranchID);
CREATE INDEX IF NOT EXISTS idx_txn_date         ON TRANSACTIONS(TransactionDate);
CREATE INDEX IF NOT EXISTS idx_txn_type         ON TRANSACTIONS(TransactionType);


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEW 1: CustomerAccountSummary
-- Purpose : Join CUSTOMER + ACCOUNT + BRANCH to give a complete
--           account-level summary for every customer.
-- Used in : Accounts page, Reports page.
-- ═══════════════════════════════════════════════════════════════════════════
CREATE VIEW IF NOT EXISTS CustomerAccountSummary AS
SELECT
    c.CustomerID,
    c.Name          AS CustomerName,
    c.Email,
    c.Phone,
    a.AccountID,
    a.AccountNumber,
    a.CardNumber,
    a.CardTier,
    a.AccountType,
    a.Balance,
    a.OpeningDate,
    a.Status        AS AccountStatus,
    b.BranchName,
    b.City,
    b.BranchCode
FROM CUSTOMER c
JOIN   ACCOUNT a ON c.CustomerID = a.CustomerID
LEFT JOIN BRANCH b ON a.BranchID = b.BranchID;


-- ═══════════════════════════════════════════════════════════════════════════
-- VIEW 2: TransactionDetails
-- Purpose : Join TRANSACTIONS + ACCOUNT + CUSTOMER to enrich every
--           transaction row with customer and account information.
-- Used in : Transactions page, Reports page.
-- ═══════════════════════════════════════════════════════════════════════════
CREATE VIEW IF NOT EXISTS TransactionDetails AS
SELECT
    t.TransactionID,
    t.TransactionDate,
    t.TransactionType,
    t.Amount,
    t.BalanceAfter,
    t.Description,
    a.AccountNumber,
    a.AccountType,
    c.CustomerID,
    c.Name   AS CustomerName,
    c.Email
FROM TRANSACTIONS t
JOIN ACCOUNT  a ON t.AccountID  = a.AccountID
JOIN CUSTOMER c ON a.CustomerID = c.CustomerID;


-- ═══════════════════════════════════════════════════════════════════════════
-- TRIGGER: UpdateBalanceAfterTransaction
-- Purpose : Automatically update ACCOUNT.Balance whenever a new row is
--           inserted into TRANSACTIONS (eliminates manual balance updates).
-- Fires   : AFTER INSERT ON TRANSACTIONS, FOR EACH ROW.
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TRIGGER IF NOT EXISTS UpdateBalanceAfterTransaction
AFTER INSERT ON TRANSACTIONS
FOR EACH ROW
BEGIN
    UPDATE ACCOUNT
    SET Balance = NEW.BalanceAfter
    WHERE AccountID = NEW.AccountID;
END;


-- ═══════════════════════════════════════════════════════════════════════════
-- STORED PROCEDURE EQUIVALENT: TransferMoney
-- SQLite has no stored procedures; the logic is implemented as a Python
-- function (database.py → transfer_money) using a single atomic
-- SQLite transaction (BEGIN / COMMIT / ROLLBACK).
--
-- Equivalent MySQL stored procedure shown below for reference:
-- ───────────────────────────────────────────────────────────────────────────
-- DELIMITER $$
-- CREATE PROCEDURE TransferMoney(
--     IN  p_from_account INT,
--     IN  p_to_account   INT,
--     IN  p_amount       DECIMAL(15,2),
--     OUT p_message      VARCHAR(255)
-- )
-- BEGIN
--     DECLARE v_src_balance DECIMAL(15,2);
--     DECLARE v_dst_balance DECIMAL(15,2);
--     DECLARE EXIT HANDLER FOR SQLEXCEPTION
--     BEGIN
--         ROLLBACK;
--         SET p_message = 'Transfer failed — rolled back.';
--     END;
--
--     START TRANSACTION;
--
--     SELECT Balance INTO v_src_balance FROM ACCOUNT
--     WHERE AccountID = p_from_account AND Status = 'Active' FOR UPDATE;
--
--     IF v_src_balance IS NULL THEN
--         SET p_message = 'Source account not found or not active.';
--         ROLLBACK;
--     ELSEIF v_src_balance < p_amount THEN
--         SET p_message = 'Insufficient balance.';
--         ROLLBACK;
--     ELSE
--         INSERT INTO TRANSACTIONS(AccountID,TransactionType,Amount,Description,BalanceAfter)
--         VALUES(p_from_account,'Transfer',p_amount,
--                CONCAT('Transfer to AccountID ',p_to_account), v_src_balance - p_amount);
--
--         INSERT INTO TRANSACTIONS(AccountID,TransactionType,Amount,Description,BalanceAfter)
--         VALUES(p_to_account,'Deposit',p_amount,
--                CONCAT('Transfer from AccountID ',p_from_account),
--                (SELECT Balance FROM ACCOUNT WHERE AccountID = p_to_account) + p_amount);
--
--         COMMIT;
--         SET p_message = 'Transfer successful.';
--     END IF;
-- END$$
-- DELIMITER ;
-- ═══════════════════════════════════════════════════════════════════════════


-- ═══════════════════════════════════════════════════════════════════════════
-- SAMPLE QUERIES (for reference / DBMS project submission)
-- ═══════════════════════════════════════════════════════════════════════════

-- Q1. JOIN — Customer with their account details
-- SELECT c.Name, c.Email, a.AccountNumber, a.AccountType, a.Balance
-- FROM CUSTOMER c JOIN ACCOUNT a ON c.CustomerID = a.CustomerID;

-- Q2. JOIN — Transactions with customer names (3-table join)
-- SELECT t.TransactionID, c.Name, a.AccountNumber, t.TransactionType, t.Amount
-- FROM TRANSACTIONS t
-- JOIN ACCOUNT a  ON t.AccountID  = a.AccountID
-- JOIN CUSTOMER c ON a.CustomerID = c.CustomerID
-- ORDER BY t.TransactionDate DESC;

-- Q3. AGGREGATE — Total balance per account type
-- SELECT AccountType, COUNT(*) AS accounts, SUM(Balance) AS total, AVG(Balance) AS average
-- FROM ACCOUNT GROUP BY AccountType;

-- Q4. AGGREGATE — Monthly transaction summary
-- SELECT strftime('%Y-%m', TransactionDate) AS month,
--        COUNT(*) AS txn_count, SUM(Amount) AS total_amount
-- FROM TRANSACTIONS GROUP BY month ORDER BY month DESC;

-- Q5. SUBQUERY — Customers with balance above average
-- SELECT c.Name, SUM(a.Balance) AS total
-- FROM CUSTOMER c JOIN ACCOUNT a ON c.CustomerID = a.CustomerID
-- GROUP BY c.CustomerID
-- HAVING SUM(a.Balance) > (SELECT AVG(Balance) FROM ACCOUNT WHERE Status='Active')
-- ORDER BY total DESC;

-- Q6. SUBQUERY — Accounts with no transactions in last 90 days
-- SELECT a.AccountNumber, c.Name, a.Balance
-- FROM ACCOUNT a JOIN CUSTOMER c ON a.CustomerID = c.CustomerID
-- WHERE a.AccountID NOT IN (
--     SELECT DISTINCT AccountID FROM TRANSACTIONS
--     WHERE TransactionDate >= date('now', '-90 days')
-- );

-- Q7. VIEW usage
-- SELECT * FROM CustomerAccountSummary;
-- SELECT * FROM TransactionDetails ORDER BY TransactionDate DESC LIMIT 10;

-- Q8. Loan statistics with aggregates
-- SELECT LoanType, COUNT(*) AS count, SUM(Amount) AS total, AVG(InterestRate) AS avg_rate
-- FROM LOAN GROUP BY LoanType ORDER BY total DESC;
