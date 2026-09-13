# RentFlow — Rental Property Management

A Django-based rental property management system with **post-paid rent billing**,
automated PDF invoice generation, security-deposit settlement, payment tracking
and legal document storage. Runs as a normal web app **or as a standalone
Windows desktop application** (no browser, no server setup).

Default login: **admin / rentflow123**

---

## The billing model (important)

RentFlow bills rent **in arrears (post-paid)** — exactly like a utility bill:

| Event | What happens |
|---|---|
| Tenancy starts **1 August** | August is the first rent month, but **nothing is payable in August** |
| **1–20 September** | August's rent is *payable* (due by the 20th) |
| **After 20 September** | August's rent becomes **overdue** |
| **October** | September's rent is collected … and so on |

Rules the system enforces automatically:

- The **current (running) month is never billable** — it only becomes payable
  on the 1st of the next month.
- Unpaid months **accumulate** (skip a month and both show as due/overdue).
- Months must be paid **oldest-first** — you cannot skip an older due month.

### Security deposit

- The deposit is **locked** during the tenancy. It can only be used to pay rent
  once the occupant has **given notice to leave** (toggle on the flat page).
- The deposit covers the **original contract rent only**. If rent has been
  increased since move-in, the **increase must always be paid separately**
  (cash / bank / Bkash) — RentFlow calculates the top-up automatically and
  refuses to generate the invoice until the top-up method and details are given.
- Rent increases are recorded as **rent revisions** (flat page → “Revise rent”);
  every month is billed at the rent effective *for that month*.

---

## Run as a Windows desktop app

### What you need to download (once)

1. **Python 3.11+** — https://www.python.org/downloads/
   (tick *“Add python.exe to PATH”* in the installer)
2. This repository (Download ZIP or `git clone`).

That's all. Everything else installs automatically.

### Build the app (PowerShell)

```powershell
cd rentflow
.\build_windows.ps1
```

The script creates a virtualenv, installs Django + ReportLab + pywebview +
PyInstaller, prepares the database, and produces:

```
dist\RentFlow\RentFlow.exe      ← double-click to run
```

- Opens in its **own native window** (pywebview) — not a browser tab.
- No console window, no server to manage — waitress runs embedded.
- The database is stored in `%LOCALAPPDATA%\RentFlow\rentflow.sqlite3`,
  so your data survives app updates.
- Copy the whole `dist\RentFlow` folder to any Windows PC — **Python is not
  required on the target machine**.

### Quick run without packaging

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt pywebview
python manage.py migrate
python manage.py seed_demo
python desktop.py        # native desktop window
# or:  python manage.py runserver   (classic web mode)
```

---

## Email (invoices)

By default invoices “send” to the console (safe for local use). To send real
email via Gmail SMTP, set environment variables before launching:

```powershell
$env:RENTFLOW_SMTP_HOST = "smtp.gmail.com"
$env:RENTFLOW_SMTP_USER = "you@gmail.com"
$env:RENTFLOW_SMTP_PASSWORD = "your-app-password"   # Gmail App Password
$env:RENTFLOW_FROM_EMAIL = "you@gmail.com"
```

---

## Project layout

```
config/       settings, urls, wsgi
accounts/     authentication (login/logout)
properties/   buildings, levels, flats, occupants, occupancies,
              rent revisions, documents
payments/     payments, invoices, post-paid month logic (utils.py),
              PDF + email services (services.py), portal API
dashboard/    analytics dashboard
templates/    all pages (base.html + per-app)
static/       css / js / images (Chart.js vendored)
media/        uploads: documents, invoices, screenshots
```

## Tests

```bash
python manage.py test payments
```

Covers: post-paid month math (Aug start → payable in Sept, overdue after the
20th), accumulation of skipped months, rent revisions, deposit lock without
notice, deposit + rent-increase top-up flow, and oldest-first enforcement.
