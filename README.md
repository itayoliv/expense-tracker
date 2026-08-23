# Expense Tracker (EN / עברית)

Local Python Flask app that imports Bank Hapoalim and Isracard monthly CSV/XLSX files into SQLite and shows a bilingual expense dashboard with pie chart, expandable categories, and recategorization.

## Requirements

- Windows
- [Python 3](https://www.python.org/downloads/) (check **Add python.exe to PATH** during install)

## Quick start (Windows)

1. **First time only** — double-click `install.bat`  
   Creates `.venv`, installs dependencies, and copies `expense_tracker/.env.example` → `expense_tracker/.env` if needed.
2. **Every time** — double-click `run.bat`  
   Starts the server and opens [http://127.0.0.1:5000](http://127.0.0.1:5000).
3. Press **Ctrl+C** in the console window to stop the server.

Optional: edit `expense_tracker/.env` (or use **Settings** in the app) to set an OpenAI API key for “Sort with ChatGPT”.

## Connect Yahoo Finance (portfolios)

1. After `install.bat`, double-click **`connect_yahoo.bat`**.
2. A browser window opens — log in to Yahoo Finance manually.
3. When your portfolios page loads, the session is saved locally (password is never stored).
4. Start the app with `run.bat`, open **Investments** in the sidebar, and click **Refresh**.

If the session expires later, run `connect_yahoo.bat` again.

## Manual setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
REM Optional: python -m playwright install chromium
copy expense_tracker\.env.example expense_tracker\.env
python -m expense_tracker
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Usage

1. Click **Import file** / **ייבוא קובץ** and upload either:
   - a Hapoalim **account movements** export, or
   - an Isracard **פירוט עסקאות** credit-card details export (`.xlsx` or `.csv`).
2. Switch language with **EN** / **עב** in the sidebar.
3. Filter by month or from/to dates; switch **Expenses**, **Income**, or **Bottom line**.
4. Expand a category to see transactions; use the pencil to edit or recategorize (optionally “remember” the rule).
5. Uncategorized expenses appear in the orange banner for quick sorting.
6. Open **Investments** to see Yahoo Finance portfolios by stock (after connecting).

Credit-card files are imported as **one expense per merchant**. When card details exist, bank lump rows like `ישראכרט` are hidden from totals so spending is not double-counted.

## Sample files

- Bank: `tr_randomized.xlsx` — columns תאריך, הפעולה, פרטים, אסמכתא, חובה, זכות, …
- Card: `0423_09_2026.xlsx` — columns תאריך רכישה, שם בית עסק, סכום עסקה, סכום חיוב, מס' שובר, …

## Project layout

- `expense_tracker/` — application package (run with `python -m expense_tracker`)
  - `__main__.py` — server entrypoint
  - `.env` / `.env.example` — local config (`.env` is gitignored)
  - `yahoo_finance.py` — Yahoo session connect + portfolio fetch
  - `db.py`, `models.py`, `importer.py`, `categorizer.py`, `gpt_sort.py`, `i18n.py`
  - `routes/` — HTTP blueprints (including `investments`)
  - `services/` — summary and API payload helpers
  - `templates/`, `static/`, `locales/` — UI and translations
- `data/` — SQLite DB, Yahoo session profile, and caches (gitignored)
- `install.bat` / `run.bat` / `connect_yahoo.bat` — Windows install, launch, and Yahoo login

Personal bank exports under `files/`, the SQLite DB under `data/`, Yahoo session files, and `expense_tracker/.env` are gitignored and should not be committed.

## Data

SQLite database: `data/expenses.db`. Categories and keyword rules are seeded on first run.
