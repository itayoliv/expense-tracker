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

## Manual setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Usage

1. Click **Import file** / **ייבוא קובץ** and upload either:
   - a Hapoalim **account movements** export, or
   - an Isracard **פירוט עסקאות** credit-card details export (`.xlsx` or `.csv`).
2. Switch language with **EN** / **עב** in the sidebar.
3. Filter by month; switch **Expenses**, **Income**, or **Bottom line**.
4. Expand a category to see transactions; use the pencil to edit or recategorize (optionally “remember” the rule).
5. Uncategorized expenses appear in the orange banner for quick sorting.

Credit-card files are imported as **one expense per merchant**. When card details exist, bank lump rows like `ישראכרט` are hidden from totals so spending is not double-counted.

## Sample files

- Bank: `tr_randomized.xlsx` — columns תאריך, הפעולה, פרטים, אסמכתא, חובה, זכות, …
- Card: `0423_09_2026.xlsx` — columns תאריך רכישה, שם בית עסק, סכום עסקה, סכום חיוב, מס' שובר, …

## Project layout

- `app.py` — Flask entrypoint (registers blueprints, DB init)
- `routes/` — HTTP blueprints (`pages`, `transactions`, `categories`, `rules`, `settings`)
- `services/` — summary building and API payload helpers
- Root domain modules: `models.py`, `db.py`, `importer.py`, `categorizer.py`, `gpt_sort.py`, `i18n.py`
- `static/js/` — feature scripts (`core`, `pie`, `import`, `transactions`, `categories`, `rules`, `settings`)
- `install.bat` / `run.bat` — Windows first-time install and daily launch

Personal bank exports under `files/`, the SQLite DB under `data/`, and `.env` are gitignored and should not be committed.

## Data

SQLite database: `data/expenses.db`. Categories and keyword rules are seeded on first run.
