# Expense Tracker (EN / עברית)

Local Python Flask app that imports Bank Hapoalim and Isracard monthly CSV/XLSX files into SQLite and shows a bilingual expense dashboard with pie chart, expandable categories, and recategorization.

## Requirements

- Windows
- [Python 3](https://www.python.org/downloads/) (check **Add python.exe to PATH** during install)

## Quick start (Windows)

1. **First time only** — double-click `install.bat`  
   Creates `.venv`, installs dependencies, and copies `.env.example` → `.env` if needed.
2. **Every time** — double-click `run.bat`  
   Starts the server and opens [http://127.0.0.1:5000](http://127.0.0.1:5000).
3. Press **Ctrl+C** in the console window to stop the server.

Optional: edit `.env` (or use **Settings** in the app) to set an OpenAI API key for “Sort with ChatGPT”.

## Upgrading

Your data lives in `data/` (especially `data/expenses.db`) and settings in `.env`. App code can be replaced; those folders should be kept.

**What to keep when upgrading**

| Keep | Do not copy |
|------|-------------|
| `data/` (database, Yahoo session, caches) | `.venv/` (machine-specific; recreate with `install.bat`) |
| `.env` | |

**Zip install → newer zip**

1. Download or unzip the **new** version into a new folder.
2. Double-click **`upgrade.bat`** in the new folder.
3. Enter (or drag in) the path to your **old** install when prompted.
4. The script copies `data/` and `.env` from the old folder, sets up `.venv`, and leaves the old folder untouched.
5. Double-click **`run.bat`**. On first start the database migrates automatically (new tables/columns are added in place).

**Git repo**

```bash
git pull
install.bat
run.bat
```

Your existing `data/` and `.env` stay in place; `install.bat` only refreshes dependencies.

**Automatic backups**

Before any schema migration, the app copies `data/expenses.db` to `data/backups/expenses-<version>-<timestamp>.db` (keeps the last 5 `expenses-*.db` files). You can also create a backup anytime from **Settings → Back up database** (`expenses-manual-<timestamp>.db`). `upgrade.bat` also saves a full `data/` snapshot under `data/backups/pre-upgrade-<timestamp>/` before importing from the old install.

## Versioning

This project uses [Semantic Versioning](https://semver.org/). Current version: **0.4.2** (see [CHANGELOG.md](CHANGELOG.md)).

- Bump `PATCH` for bug fixes and small internal improvements.
- Bump `MINOR` for new features that keep existing behavior working.
- Bump `MAJOR` for breaking changes, incompatible data changes, or behavior users must adapt to.

Update `expense_tracker.__version__` and `CHANGELOG.md` together for each release. Git tags should use the `vMAJOR.MINOR.PATCH` format, for example `v0.1.0`.

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
copy .env.example .env
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

- `.env` / `.env.example` — local config at project root (`.env` is gitignored; legacy `expense_tracker/.env` still loaded if present)
- `expense_tracker/` — application package (run with `python -m expense_tracker`)
  - `__main__.py` — server entrypoint
  - `models.py`, `i18n.py`
  - `db/` — engine, migrations, seeds, backups
  - `integrations/` — external services (`gpt_sort.py`, `yahoo/` for Yahoo Finance session + portfolios)
  - `services/` — domain logic (`categorizer`, `importer/`, `investment_sectors`, summary/split/payloads)
  - `routes/` — HTTP blueprints
  - `templates/`, `static/` (including split `transactions-*.js` files), `locales/` — UI and translations
- `data/` — SQLite DB, Yahoo session profile, and caches (gitignored)
- `install.bat` / `run.bat` / `upgrade.bat` / `connect_yahoo.bat` — Windows install, launch, upgrade, and Yahoo login

Personal bank exports under `files/`, the SQLite DB under `data/`, Yahoo session files, and `.env` are gitignored and should not be committed.

## Data

SQLite database: `data/expenses.db`. Categories and keyword rules are seeded on first run.
