# AkumaBank

AkumaBank is a Flask banking management application configured for Morocco. It uses SQLite for data storage and displays balances in Moroccan dirhams (MAD).

## Features

- Staff dashboard, customer, account, branch, loan, transaction, and report management.
- Public customer signup with personal details and owner/admin approval.
- Customer password reset requests reviewed by owners/admins, with a one-time temporary password and forced password change.
- Customer portal for viewing linked accounts and recent transactions.
- Customer withdrawals and transfers, limited to the customer's own accounts, with a MAD 10 transfer fee.
- Customer loan requests reviewed by staff through the loan management page.
- Deposits and bank-account creation restricted to owners and admins.
- Profile picture uploads, including animated GIFs.
- Local SQLite database that is initialized empty; application startup does not seed demo banking data.

## Requirements

- Python 3.8 or newer
- pip

## Setup

From the project directory, create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

The database schema is created automatically when the app starts. The SQLite database is stored at `database/banking_system.db`.

## Create the first owner

Create an owner account interactively:

```bash
python tools/create_owner.py
```

Enter an owner username, email address, and password when prompted. Passwords must be at least 12 characters. The tool refuses to create another owner if one already exists.

## Run the application

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser. Sign in through **Admin or owner login** with the staff username or email and password.

For deployments, set a persistent secret before starting the app so sessions remain valid across restarts:

```bash
export SESSION_SECRET="replace-with-a-long-random-secret"
```

In PowerShell:

```powershell
$env:SESSION_SECRET = "replace-with-a-long-random-secret"
```

## Customer onboarding

1. A customer submits a signup request from the login page with their name, email, date of birth, phone, address, CIN, and password.
2. An owner or admin reviews the request on the **Customers** page.
3. Approval creates the customer's profile and enables customer login.
4. An owner or admin opens a bank account for the approved customer from **Accounts**.
5. Once the account is active, the customer can withdraw or transfer funds from **My Banking**. Cash deposits are made by an owner or admin.
6. Customers can submit loan requests from **My Banking** and choose an active account. Owners/admins review them on **Loans**, set the final rate, and approval deposits the loan into that account as a transaction.

## Customer password recovery

1. A customer submits their email from **Forgot password?** on the customer login page.
2. An owner or admin reviews the request under **Password Reset Requests** on **Customers**.
3. Approval creates a temporary password that remains in the Customers page until the reviewing staff member copies it. Deliver it through a verified channel; this app does not send email.
4. The temporary password can only be used to sign in once. The customer must set a new password before accessing the banking portal.

When an owner or admin creates a customer from the **Customers** page, the app also creates an approved customer login and keeps its temporary password visible there until it is copied. Deliver that password through a verified channel; the customer must change it at first sign-in.

## Staff roles

- **Owner:** Full staff access; can create admin and employee accounts, approve customer signups, open bank accounts, and make deposits.
- **Admin:** Can approve customer signups, open bank accounts, and make deposits.
- **Employee:** Staff access to banking management; cannot create staff accounts, approve signups, open bank accounts, or make deposits.
- **Customer:** Can view their own banking information, make withdrawals or transfers from their own active accounts, request loans, and submit password reset requests.

## Reset the database

To clear banking data and all login accounts while keeping the SQLite file and schema:

```bash
python tools/reset_db.py
```

This removes customers, branches, accounts, loans, transactions, owner/admin/employee accounts, and customer logins. Recreate the owner afterward with `python tools/create_owner.py`.

## Project layout

```text
app.py                  Flask application entry point
database.py             SQLite initialization and database helpers
database/               SQLite database and profile picture storage
routes/                 Flask route blueprints
schema.sql              Reference database schema
static/                 CSS and JavaScript assets
templates/              Jinja HTML templates
tools/create_owner.py   Interactive first-owner setup
tools/reset_db.py       Database reset utility
```
