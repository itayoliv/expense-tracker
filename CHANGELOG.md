# Changelog

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

Work in progress since **0.4.2**. Version not bumped yet — release when ready (planned: **0.5.0**).

### Transaction tags

- Add **Manage tags** to the sidebar (dashboard and investments pages).
- Create, edit, and delete tags (name + color) in a modal grouped like Manage rules: expand a tag to see all transactions that carry it.
- Assign **multiple tags** per transaction via chip pickers in:
  - the edit transaction modal
  - uncategorized (orange banner) rows (tags can be saved without choosing a category)
- Show tag chips on transaction rows in the dashboard table.
- **Sum tags** — pick two or more tags to see their combined total:
  - per open category (above that category’s transaction list)
  - globally in the table header (across all categories, respects the current date range)
- Each transaction is counted once in a sum even if it has several of the selected tags.
- New API: `GET/POST /api/tags`, `PATCH/DELETE /api/tags/<id>`, `GET /api/tags/<id>/transactions`; transaction `PATCH` accepts `tag_ids`.
- New DB tables: `tags`, `transaction_tags` (many-to-many).
- English and Hebrew strings for all tag UI.
- Tests in `tests/test_tags.py`.

### UI and layout

- Keep sidebar brand as **Expense Tracker**; move app version directly below the brand on all pages (removed from under the dashboard page title).
- **Manage rules**: group rules by category — click a category header to expand/collapse its rules (same pattern as tag groups).

### Date filters

- **From** field is a month picker (`YYYY-MM`), defaulting to the 1st of the current month.
- **To** field defaults to the last day of the selected From month.
- **To** cannot be set earlier than the From month.

### Transaction splitting

- Allow splitting a transaction **only once** (split parts cannot be split again); hide Split on already-split rows.
- Fix split modal layout so split rows display correctly.
- Add a **custom description** field for each split part.
- Split part **description** is read-only and pre-filled from the original transaction.

### Upgrading and data migration

- Add **`upgrade.bat`** — one-click upgrade from an older install: copies `data/` and `.env` (root or legacy `expense_tracker/.env`), backs up any existing data in the new folder, sets up `.venv`, and installs dependencies. The old folder is left untouched. Works for any prior version (zip install → newer zip).
- **Automatic DB backup before migration** — on startup, if a schema change is pending, copy `data/expenses.db` to `data/backups/expenses-<version>-<timestamp>.db` before `create_all` / column migrations (keeps the last 5). Also runs before the legacy-schema wipe so very old databases are not lost silently.
- **Manual backup in Settings** — **Back up database** saves `data/backups/expenses-manual-<timestamp>.db`. Manual and migration snapshots share the same last-5 pool of `expenses-*.db` files.
- **In-place schema migration** on first start after an upgrade: new tables via `create_all`, new columns via `_migrate_schema()` — no manual DB steps. Same path for git pull in an existing folder (`install.bat` then `run.bat`).
- **`install.bat`**, **`run.bat`**, and **`connect_yahoo.bat`** detect a `.venv` copied from another PC and recreate it or show a clear message.
- README **Upgrading** section: zip install (`upgrade.bat`) vs git (`git pull` + `install.bat`), what to keep (`data/`, `.env`) and what not to copy (`.venv`).
- Tests in `tests/test_db_backup.py`.

### Internal restructuring

- Move `.env` / `.env.example` to the project root (legacy `expense_tracker/.env` still loaded if present).
- Introduce `integrations/` (`gpt_sort`, `yahoo/`) and expand `services/` (`categorizer`, `importer/`, `investment_sectors`).
- Split `db.py` into `db/` package (`seed`, `migrations`, `backups`).
- Split Yahoo Finance into `integrations/yahoo/` (`session`, `portfolios`, `quotes`, `history`).
- Split bank/card import into `services/importer/` (`common`, `hapoalim`, `isracard`, `discount`).
- Split dashboard transaction JS into `transactions.js` + `transactions-edit.js` / `transactions-split.js` / `transactions-banner.js`.

---

## 0.4.2 - 2026-08-26

- Refresh the dashboard table and pie chart in the background after each category drag-and-drop, while Manage Categories stays open.

## 0.4.1 - 2026-08-26

- Add a custom description field to uncategorized transactions in the orange banner, placed before the category selector.

## 0.4.0 - 2026-08-25

- Sort categories A–Z by default across the dashboard, dropdowns, and Manage Categories.
- Add a toggle and drag-and-drop custom category order.

## 0.3.0 - 2026-08-25

- Keep original description and details read-only when editing a transaction.
- Add a custom description field shown above the original text in the transaction list.

## 0.2.0 - 2026-08-25

- Show the app version under the dashboard page title.

## 0.1.0 - 2026-08-25

- Start semantic versioning for the Expense Tracker app.
