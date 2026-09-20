# Changelog

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/).

Build metadata (`+N`) marks interim builds without bumping `MAJOR.MINOR.PATCH`. Example: **0.4.2+1** is still release **0.4.2**, build **1**.

## [Unreleased]

Work in progress since **0.4.2**. Version not bumped yet — release when ready (planned: **0.5.0**).

### Investments

- Add a stock buy planner with USD/NIS budgets, Yahoo USD/ILS conversion, percentage allocation across selected holdings, and whole or fractional share estimates.
- Add an editable OneZero FX-cost comparison against Meitav Trade, Altshuler Shaham Trade, and major Israeli banks.
- Save dated OneZero NIS conversions with Yahoo historical USD values and show cumulative savings versus Meitav Trade in the portfolios table.
- Keep Yahoo **watchlist** symbols (0 shares) in portfolio data so they appear in the buy-planner stock dropdown.
- Buy planner table shows **share price** (USD, with ILS when the Yahoo rate is available).
- Buy planner: defaults to entering **share count**; click **Budget %** or **Shares** headers to switch input mode.

### Transaction tags

- Add **Manage tags** to the sidebar (dashboard and investments pages).
- Create, edit, and delete tags (name + color) in a modal.
- Assign **multiple tags** per transaction via chip pickers in:
  - the edit transaction modal
  - uncategorized (orange banner) rows (tags can be saved without choosing a category)
- Show tag chips on transaction rows in the dashboard table.
- New API: `GET/POST /api/tags`, `PATCH/DELETE /api/tags/<id>`, `GET /api/tags/<id>/transactions`; transaction `PATCH` accepts `tag_ids`.
- New DB tables: `tags`, `transaction_tags`.
- English and Hebrew strings for all tag UI.
- Tests in `tests/test_tags.py`.

### UI and layout

- Keep sidebar brand as **Expense Tracker**; move app version directly below the brand on all pages (removed from under the dashboard page title).
- **Manage rules**: group rules by category — click a category header to expand/collapse its rules (same pattern as tag groups).

### Date filters

- **From** field is a month picker (`YYYY-MM`), defaulting to the 1st of the current month.
- **To** field is a month picker (`YYYY-MM`), defaulting to the same month as From (through the last day of that month).
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

## 0.4.2+2 - 2026-09-14

Build **2** under **0.4.2** (SemVer build metadata). Core version unchanged.

### Ignore transactions

- Edit modal: **Ignore this transaction** checkbox with a required reason.
- Ignored rows stay visible in the dashboard table (gray) but are excluded from category totals, pie chart, footer net, tag sums, unsorted banner, GPT sort, and apply-to-similar rules.
- New DB columns: `ignored`, `ignore_reason` (migrated on startup with a pre-migration backup).

### Manage rules

- Fix category group rows in **Manage rules** showing only color dots with missing names and counts (flex shrink was clipping the labels).

### Dashboard

- Show a **#** column on the expense table with the number of transactions in each category.
- Enable the tag-sum **+** button only when the current scope has at least one tagged transaction.
- Discard unfinished tag-sum formulas (created with **+** but no tag chosen) when the category is collapsed or the page reloads.
- Hide the share **%** column on the Income view.
- Import modal: show selected files in a table (name, date, size) and show added/skipped results inside the modal under the table instead of a side flash.
- Credit-card **payment-plan** rows (`תשלום X מתוך Y`) filter and display by **billing date**; regular purchases and standing orders (`הוראת קבע`) stay on **purchase date**.

---

## 0.4.2+1 - 2026-09-10

First build under **0.4.2** (SemVer build metadata). Core version unchanged.

### Tags — persisted sum formulas

- **Sum tags** — save multiple formulas of one or more tags and see each combined total:
  - per open category (above that category’s transaction list)
  - globally in the table header (across all categories, respects the current date range)
- Allow a formula with **one or more** tags (previously required two or more).
- Global and per-category formula lists are independent, so every category can use different formulas.
- Tag-sum formulas are persisted in the database and restored after a reload; use **+** to add formulas and **×** to remove them.
- Each transaction is counted once in a sum even if it has several of the selected tags.
- New API: formula CRUD under `/api/tag-formulas`.
- New DB tables: `tag_sum_formulas` and `tag_formula_tags` (with `scope` migration support).

### Categories — A–Z / Value sorting

- Move the category-sort button above the global tag-sum formulas so the formula header can use the full table width.
- Replace custom category ordering with an **A–Z / Value** selector and an adjacent ascending/descending arrow; the same selection also sorts transactions inside each category by description or amount.

### Close app from the web

- Add **Close app** in the sidebar (under Settings) and in Settings — stop the local server from the browser (same effect as Ctrl+C in the `run.bat` window).

### Date filters — purchase month

- **To** is a month picker like **From** (`YYYY-MM`); the range covers whole months through the last day of To.
- Filter the transaction table by **purchase date** (`txn_date`) so choosing a From month shows that month’s transactions (not earlier purchase dates that were billed later on a credit-card statement).
- If To is still set before the new From month, snap To to the selected From month instead of falling into the previous month.

### Dashboard updates without full reload

- After editing, adding, deleting, or splitting a transaction (and after sorting categories), refresh the table, unsorted banner, tag sums, and pie chart in place — no full page reload.

### Manage tags — list only

- Show only tag name, color, and edit/delete actions in **Manage tags** (no per-tag transaction list, count, or sum).

### Tag picker — dropdown via +

- Replace tag toggle chips with selected-tag chips and a **+** control that opens a dropdown to choose another tag (edit modal and unsorted banner). Remove a tag with **×** on its chip.
- Sum-tag formulas: use **+** (`tag-formula-add`) to add a formula row with a tag dropdown; no extra tag **+** on empty formulas.

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
