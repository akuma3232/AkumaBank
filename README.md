<div align="center">

# ⚡ AkumaBank — Moroccan Cyber Banking Suite 🇲🇦

<p align="center">
  <strong>An enterprise-grade, high-security Moroccan digital banking platform engineered with Python Flask, atomic SQLite ledgers, Bank Al-Maghrib regulatory compliance, vector PDF document generation, and an Operations Requests Hub.</strong>
</p>

[![Python Version](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask Framework](https://img.shields.io/badge/Flask-3.1%2B-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/SQLite3-Atomic_Ledger-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![PDF Engine](https://img.shields.io/badge/ReportLab-4.0%2B-E25A1C?style=for-the-badge&logo=adobe-acrobat-reader&logoColor=white)](https://www.reportlab.com/)
[![BAM Regulatory](https://img.shields.io/badge/Bank_Al--Maghrib-BAM%2F2026%2F088-C1272D?style=for-the-badge&logo=morocco&logoColor=white)](#-moroccan-banking-standards)
[![Currency](https://img.shields.io/badge/Currency-MAD_%28Morocco%29-10B981?style=for-the-badge)](#-core-banking-capabilities)
[![UI Design](https://img.shields.io/badge/UI-Cyber_Fintech_Suite-00F2FE?style=for-the-badge&logo=bootstrap&logoColor=black)](#-interface--experience)
[![License](https://img.shields.io/badge/License-All_Rights_Reserved-red?style=for-the-badge)](#-proprietary-license--intellectual-property)

<br/>

<a href="#-whats-new-in-v40">🚀 What's New</a> •
<a href="#-core-banking-capabilities">🏛️ Core Banking</a> •
<a href="#-unified-operations-requests-center">📥 Requests Center</a> •
<a href="#-official-bank-al-maghrib-pdf-suite">📄 PDF Suite</a> •
<a href="#-card-subscription-tiers">💳 Card Tiers</a> •
<a href="#-role-based-access-control-rbac">👥 User Roles</a> •
<a href="#-quick-start--installation">⚡ Quick Start</a> •
<a href="#-database--architecture">🗄️ Architecture</a> •
<a href="#-proprietary-license--intellectual-property">⚖️ License</a>

---

</div>

<br/>

## 🚀 What's New in v4.0

AkumaBank v4.0 introduces major architectural enhancements tailored to authentic Moroccan and international retail banking standards:

* 📥 **Unified Operations Requests Center (`/requests`):** A centralized command hub managing all 6 request lifecycles (Customer Signups, Account Openings, Account Closures, Document Certifications, Loan Underwriting, and Password Resets) with real-time pending badges.
* 📄 **Official Bank Al-Maghrib PDF Generation Suite:** 6 regulatory PDF certificates dynamically rendered with ReportLab, featuring clean vector EMV smart cards, Bank Al-Maghrib circular stamps, and electronic signatures.
* 📁 **Customer "My Documents" Portal (`/my-documents`):** Self-service document issuance with a dynamic state lifecycle — customer requests certificate &rarr; staff inspects draft &rarr; uploads physically signed/stamped PDF &rarr; customer's **"Cancel Request"** button transforms into **"Download PDF"**.
* 💳 **Multi-Tier Card Subscription Framework:** 4 distinct Moroccan banking tiers (`Silver Pulse`, `Titanium Elite`, `Gold Sovereign`, and `Obsidian Noir`) with specific spending ceilings, contactless limits, and insurance coverage.
* 🖼️ **Pure-Code Profile Avatar System:** Profile pictures are downscaled to 128&times;128 and converted into Base64 WebP code stored directly in the database. **Zero image files are saved to disk.**
* 🪟 **Official Bank Document Windows:** Clean, responsive modals replace cramped dropdowns, providing in-browser preview (`target="_blank"`) and direct file downloads for all accounts.

---

## 🏛️ Core Banking Capabilities

* 🇲🇦 **Moroccan Banking Standards (BAM):**
  * **24-Digit RIB Generation:** Authentic Bank Al-Maghrib Modulo 97 checksum validation (`generate_moroccan_rib`).
  * **16-Digit Payment Cards:** Deterministic Luhn algorithm (`generate_card_number`) matching ISO/IEC 7812.
  * **Fee Model:** Standard **MAD 1.00** deposit administrative fee and **MAD 10.00** inter-account transfer fee deducted automatically from recipient funds.
* 🔄 **Atomic Transaction Ledgers:** Guaranteed zero concurrency drift via SQLite immediate transactions and SQL trigger `UpdateBalanceAfterTransaction`.
* 🛡️ **Account Liquidation & Closure Protocol:** Liquidates balances to MAD 0.00, permanently deactivates cards, and issues an official Bank Discharge certificate (*Quittus*).
* 🪙 **Credit Facilities & Loan Underwriting:** Full credit application lifecycle (Home, Car, Personal, Academic, Business) with variable interest rates and direct disbursement into active checking accounts.
* 🔐 **Temporary Password & Access Recovery:** Password resets are approved by administration, issuing single-use credentials with forced rotation on subsequent sign-in.

---

## 📥 Unified Operations Requests Center

All bank requests are consolidated into a dedicated, full-page operations workspace accessible from the sidebar at `/requests` or via quick-action modals:

<table>
  <thead>
    <tr>
      <th>Request Category</th>
      <th>Triggered By</th>
      <th>Administrative Action</th>
      <th>Final Artifact / Result</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>👤 Customer Signups</strong></td>
      <td>Prospective customer registration</td>
      <td>Verify National ID (CIN), approve applicant</td>
      <td>Generates customer profile &amp; enables account opening</td>
    </tr>
    <tr>
      <td><strong>💳 Account Openings</strong></td>
      <td>Existing customer portal application</td>
      <td>Approve card tier &amp; initial deposit</td>
      <td>Generates 24-digit Moroccan RIB &amp; 16-digit card</td>
    </tr>
    <tr>
      <td><strong>❌ Account Closures</strong></td>
      <td>Customer closure submission</td>
      <td>Authorize liquidation &amp; discharge</td>
      <td>Zero-balances account &amp; generates Quittus PDF</td>
    </tr>
    <tr>
      <td><strong>📄 Official Documents</strong></td>
      <td>Customer certificate request</td>
      <td>Preview draft &amp; upload signed physical PDF</td>
      <td>Customer "Cancel" button &rarr; "Download PDF"</td>
    </tr>
    <tr>
      <td><strong>🪙 Loan Applications</strong></td>
      <td>Customer credit application</td>
      <td>Underwrite rate &amp; assign disbursement account</td>
      <td>Capital disbursed into active account ledger</td>
    </tr>
    <tr>
      <td><strong>🔑 Password Resets</strong></td>
      <td>Customer forgotten credentials</td>
      <td>Issue temporary password</td>
      <td>Delivered via Temporary Passwords Queue</td>
    </tr>
  </tbody>
</table>

> [!TIP]
> A live notification badge in the sidebar dynamically displays the aggregate number of all pending requests across the entire bank.

---

## 📄 Official Bank Al-Maghrib PDF Suite

AkumaBank integrates a vector PDF compilation engine built on ReportLab. Every document includes Bank Al-Maghrib legal mentions, Modulo 97 verification, branch domiciliation, and digital seal blocks:

| Document Type | Purpose &amp; Regulatory Standard | Visual Elements Included |
| :--- | :--- | :--- |
| **Welcome Pack &amp; Opening Cert** | Official confirmation of bank account creation | Vector credit card matching tier template, BAM license BAM/2026/088 |
| **Official 24-Digit RIB Slip** | Banking identity statement for salary &amp; direct debits | 24-digit split RIB (Bank, Guichet, Account, Key), IBAN, BIC |
| **Card Subscription Agreement** | Contractual card documentation &amp; ceilings | Card visual template, EMV chip parameters, contactless &amp; insurance specs |
| **Account Statement &amp; Logs** | Certified financial history &amp; ledger movements | Chronological transaction table, running balances, credit/debit totals |
| **Attestation de Solvabilité** | Solvency certificate for visa &amp; administrative bodies | Certified liquid balance statement, branch manager signature stamp |
| **Account Closure Quittus** | Official liquidation and debt discharge certificate | Final liquidation settlement confirmation, definitive zero-balance seal |

### Vector Credit Card Rendering
The visual credit card rendered inside Welcome Packs and Card Agreements is drawn with clean vector geometry:
* **EMV Microchip:** Realistic metallic 4-pad contact grid with gold trim.
* **Contactless Indicator:** Crisp typographic wave emitter (`))))`).
* **Card Details:** Masked 16-digit number (`4532 •••• •••• 9012`), expiration date, cardholder legal name, and VISA branding.
* **Zero Circles:** Clean rectangular layout matching physical smart cards.

---

## 💳 Card Subscription Tiers

AkumaBank offers 4 tailored card subscription tiers:

```
[ Silver Pulse ]       [ Titanium Elite ]       [ Gold Sovereign ]       [ Obsidian Noir ]
   Standard                  Premium                   Gold                    Black
 0 MAD / month            49 MAD / month          99 MAD / month          199 MAD / month
```

<table>
  <thead>
    <tr>
      <th>Tier</th>
      <th>Display Name</th>
      <th>Monthly Fee</th>
      <th>Max Balance Ceiling</th>
      <th>Contactless Limit</th>
      <th>Insurance &amp; Privileges</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>standard</code></td>
      <td><strong>Silver Pulse</strong></td>
      <td>Free (0 MAD)</td>
      <td>MAD 50,000</td>
      <td>MAD 200 / tap</td>
      <td>National ATM/POS network &bull; 3D Secure e-commerce</td>
    </tr>
    <tr>
      <td><code>premium</code></td>
      <td><strong>Titanium Elite</strong></td>
      <td>MAD 49 / mo</td>
      <td>MAD 200,000</td>
      <td>MAD 400 / tap</td>
      <td>Morocco airport lounge &bull; International payment enablement</td>
    </tr>
    <tr>
      <td><code>gold</code></td>
      <td><strong>Gold Sovereign</strong></td>
      <td>MAD 99 / mo</td>
      <td>MAD 500,000</td>
      <td>MAD 600 / tap</td>
      <td>Global VIP lounges &bull; All-risk medical &amp; travel insurance</td>
    </tr>
    <tr>
      <td><code>black</code></td>
      <td><strong>Obsidian Noir</strong></td>
      <td>MAD 199 / mo</td>
      <td>Unlimited</td>
      <td>MAD 1,000 / tap</td>
      <td>24/7 dedicated concierge &bull; Bespoke financial ceilings</td>
    </tr>
  </tbody>
</table>

---

## 🖼️ Zero-Disk Avatar Architecture (Code Storage)

To guarantee database self-containment and eliminate image file storage on the server:

1. **Upload &amp; Transform:** When a user uploads a photo (JPEG, PNG, WebP), the server decodes the image in memory.
2. **Dimension Normalization:** Pillow downscales and crops the image to a standardized $128 \times 128$ square.
3. **Encoding:** The pixels are converted directly into a Base64-encoded WebP string (`data:image/webp;base64,...`).
4. **Pure-Text Storage:** The resulting string is saved directly into the `USERS.ProfilePicture` text field.
5. **Disk Hygiene:** Zero image files exist on the host filesystem.

---

## 👥 Role-Based Access Control (RBAC)

AkumaBank enforces strict operational separation across 4 distinct user roles:

| Capability | 👑 Owner | 🛡️ Admin | 👔 Employee | 👤 Customer |
| :--- | :---: | :---: | :---: | :---: |
| **System Dashboard &amp; Telemetry** | ✅ | ✅ | ✅ | ❌ |
| **Review Customer Signups** | ✅ | ✅ | ❌ | ❌ |
| **Create &amp; Open Accounts** | ✅ | ✅ | ❌ | ❌ |
| **Close &amp; Liquidate Accounts** | ✅ | ✅ | ❌ | ❌ |
| **Approve / Sign Official PDFs** | ✅ | ✅ | ❌ | ❌ |
| **Underwrite &amp; Disburse Loans** | ✅ | ✅ | 👁️ Review | ❌ |
| **Manage Staff Users** | ✅ | ❌ | ❌ | ❌ |
| **Client Portal Self-Service** | ❌ | ❌ | ❌ | ✅ |
| **Customer Document Requests** | ❌ | ❌ | ❌ | ✅ |

---

## ⚡ Quick Start & Installation

### Prerequisites
* **Python 3.8** or newer
* **pip** package manager
* **SQLite3** (bundled with Python)

### 1. Clone the Repository
```bash
git clone https://github.com/akuma3232/AkumaBank.git
cd AkumaBank
```

### 2. Set Up Virtual Environment
<details open>
<summary><b>Linux / macOS (Bash / Zsh)</b></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
```
</details>

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
</details>

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Initialize Database & Provision Master Owner
```bash
# Provision the first master administrative credentials
python tools/create_owner.py
```
> [!IMPORTANT]
> The setup prompt will ask for a staff username, email, and password. Once created, the tool locks down to prevent duplicate owner provisioning.

### 5. Launch Application
```bash
python app.py
```

Open your browser at:
```text
http://127.0.0.1:5000
```
* Sign in as staff via **Staff Login**.
* Register a new account via **Apply for Customer Account**.

---

## 🗂️ Project Directory Structure

```text
AkumaBank/
├── app.py                         # Application factory, blueprints & context processors
├── database.py                    # SQLite connection engine, triggers & liquidation logic
├── card_tiers.py                  # Moroccan card subscription tiers (Silver/Titanium/Gold/Obsidian)
├── morocco_banking.py             # 24-digit BAM Modulo 97 RIB & 16-digit Luhn card generator
├── pdf_generator.py               # ReportLab official PDF compilation & vector card engine
├── requirements.txt               # Dependencies (Flask, ReportLab, Pillow)
├── schema.sql                     # Reference SQL schema definition
├── LICENSE                        # Proprietary software license
├── README.md                      # Comprehensive documentation
├── database/
│   ├── banking_system.db          # SQLite production database
│   └── signed_documents/          # Storage for staff-uploaded physically signed PDFs (.gitignore)
├── routes/
│   ├── accounts.py                # Accounts management, Requests Center & opening approval
│   ├── auth.py                    # Authentication, sessions, signups & recovery
│   ├── branches.py                # Moroccan branch directory (Casablanca, Rabat, etc.)
│   ├── customer_portal.py         # 3D holographic cards, transfers, loan & opening requests
│   ├── customers.py               # Customer directory & signup approval logic
│   ├── dashboard.py               # Executive telemetry & Chart.js inflow/outflow charts
│   ├── database_panel.py          # Interactive SQL query console & table explorer
│   ├── documents.py               # PDF downloads, draft preview, and signature upload
│   ├── loans.py                   # Credit underwriting & loan disbursement
│   ├── profiles.py                # Profile settings & Base64 code avatar transformation
│   ├── reports.py                 # Financial audit statements & balance sheets
│   ├── transactions.py            # Deposit, withdrawal, and transfer ledger
│   └── users.py                   # Staff credentials & password reset approval
├── static/
│   ├── css/
│   │   └── style.css              # Design system, glassmorphism, 3D card tilt, dark/light theme
│   └── js/
│       └── main.js                # Command HUD (Ctrl+K), Web Audio oscillators, 3D tilt engine
├── templates/
│   ├── base.html                  # Master layout with Command HUD, theme switcher & sidebar
│   ├── accounts.html              # Bank accounts list with official PDF tools modals
│   ├── requests_center.html       # Full-page unified Operations Requests Center (6 categories)
│   ├── customer_documents.html    # Customer 'My Documents' portal with Cancel/Download actions
│   ├── customer_portal.html       # Customer banking portal with 3D cards & request actions
│   ├── customers.html             # Customer directory with direct account PDF jump links
│   ├── dashboard.html             # Executive telemetry & Chart.js analytics
│   ├── account_settings.html      # Custom profile picture upload (code transformation)
│   └── ...                        # Supporting templates (login, register, loans, reports...)
└── tools/
    ├── create_owner.py            # Initial administrator provisioner CLI
    └── reset_db.py                # Database clearing and reset utility
```

---

## 🗄️ Database Architecture & Entity Relationships

AkumaBank enforces strict relational integrity with SQLite `PRAGMA foreign_keys = ON`:

```mermaid
erDiagram
    BRANCH ||--o{ ACCOUNT : locates
    CUSTOMER ||--o{ ACCOUNT : owns
    CUSTOMER ||--o{ LOAN : applies
    CUSTOMER ||--o{ ACCOUNT_CLOSURE_REQUEST : submits
    CUSTOMER ||--o{ DOCUMENT_REQUEST : requests
    CUSTOMER ||--o{ ACCOUNT_OPENING_REQUEST : applies
    ACCOUNT ||--o{ TRANSACTIONS : records
    ACCOUNT ||--o{ LOAN : disburses_to
    ACCOUNT ||--o{ ACCOUNT_CLOSURE_REQUEST : targets
    ACCOUNT ||--o{ DOCUMENT_REQUEST : targets
    USERS ||--o{ PASSWORD_RESET_REQUEST : submits

    CUSTOMER {
        int CustomerID PK
        string Name
        string Email UK
        string Phone
        string NationalID UK
        date DateOfBirth
    }
    ACCOUNT {
        int AccountID PK
        string AccountNumber UK
        string CardNumber
        string CardTier
        string AccountType
        decimal Balance
        string Status
    }
    DOCUMENT_REQUEST {
        int RequestID PK
        int CustomerID FK
        int AccountID FK
        string DocumentType
        string Status
        string SignedPdfFile
    }
    ACCOUNT_CLOSURE_REQUEST {
        int RequestID PK
        int AccountID FK
        int CustomerID FK
        string Reason
        string Status
    }
    ACCOUNT_OPENING_REQUEST {
        int RequestID PK
        int CustomerID FK
        string AccountType
        string CardTier
        decimal InitialDeposit
        string Status
    }
    LOAN {
        int LoanID PK
        int CustomerID FK
        string LoanType
        decimal Amount
        decimal InterestRate
        string Status
    }
    TRANSACTIONS {
        int TransactionID PK
        int AccountID FK
        string TransactionType
        decimal Amount
        decimal BalanceAfter
        datetime TransactionDate
    }
```

---

## 🛠️ Maintenance & Reset Utilities

To purge all business records and test user accounts without altering the schema:
```bash
python tools/reset_db.py
```
> [!NOTE]
> This safely disables foreign keys, flushes all transaction, account, loan, request, and customer tables, resets SQLite sequence counters, and re-enables constraints. Recreate the master administrator using `python tools/create_owner.py`.

---

## ⚖️ Proprietary License & Intellectual Property

```text
PROPRIETARY SOFTWARE LICENSE — ALL RIGHTS RESERVED
Copyright (c) 2026 AkumaBank. All Rights Reserved.
```

> [!CAUTION]
> **Strict Prohibition on Modification & Redistribution:**  
> This software codebase, its UI styling, 3D card physics, ReportLab PDF generation algorithms, and database structures are the exclusive proprietary property of the Author.  
> 
> **No person or entity is permitted to:**
> - Modify, alter, adapt, or create derivative works of any file in this repository.
> - Fork, copy, clone, distribute, sublicense, sell, or mirror the code publicly or privately.
> - Reverse-engineer, decompile, or extract the proprietary components.
> 
> Refer to the full [LICENSE](LICENSE) file for legal provisions.

---

<div align="center">
  <sub>Engineered with precision for Bank Al-Maghrib compliance &bull; <strong>AkumaBank Core v4.0</strong></sub>
</div>
