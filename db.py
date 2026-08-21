"""Database setup and seed data."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from models import Base, Category

ROOT = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines without overriding existing environment variables."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    _load_env_file(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

engine = None
SessionLocal = None
DB_PATH = DATA_DIR / "expenses.db"


def configure_engine(db_path: Path | str | None = None) -> None:
    """Bind SQLAlchemy to a SQLite file (defaults to EXPENSE_DB or data/expenses.db)."""
    global engine, SessionLocal, DB_PATH
    if db_path is not None:
        DB_PATH = Path(db_path)
    else:
        env = os.environ.get("EXPENSE_DB")
        DB_PATH = Path(env) if env else DATA_DIR / "expenses.db"
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


configure_engine()

SEED_CATEGORIES = [
    {
        "key": "culture_leisure",
        "name_en": "Culture and leisure",
        "name_he": "תרבות ופנאי",
        "color": "#8B5CF6",
        "icon": "theater",
        "sort_order": 10,
        "kind": "expense",
    },
    {
        "key": "food_groceries",
        "name_en": "Food and groceries",
        "name_he": "מזון וקניות",
        "color": "#F97316",
        "icon": "cart",
        "sort_order": 15,
        "kind": "expense",
    },
    {
        "key": "fuel_transport",
        "name_en": "Fuel and transport",
        "name_he": "דלק ותחבורה",
        "color": "#0EA5E9",
        "icon": "car",
        "sort_order": 18,
        "kind": "expense",
    },
    {
        "key": "insurance",
        "name_en": "Insurance",
        "name_he": "ביטוח",
        "color": "#3B82F6",
        "icon": "umbrella",
        "sort_order": 20,
        "kind": "expense",
    },
    {
        "key": "taxes_payments",
        "name_en": "Taxes and payments",
        "name_he": "מיסים ותשלומים",
        "color": "#EF4444",
        "icon": "building",
        "sort_order": 30,
        "kind": "expense",
    },
    {
        "key": "loans_mortgage",
        "name_en": "Loans and mortgage",
        "name_he": "הלוואות ומשכנתא",
        "color": "#F59E0B",
        "icon": "piggy",
        "sort_order": 40,
        "kind": "expense",
    },
    {
        "key": "banking",
        "name_en": "Banking services",
        "name_he": "שירותים בנקאיים",
        "color": "#06B6D4",
        "icon": "bank",
        "sort_order": 50,
        "kind": "expense",
    },
    {
        "key": "credit_cards",
        "name_en": "Credit cards",
        "name_he": "כרטיסי אשראי",
        "color": "#EC4899",
        "icon": "card",
        "sort_order": 60,
        "kind": "expense",
    },
    {
        "key": "shopping",
        "name_en": "Shopping",
        "name_he": "קניות",
        "color": "#D946EF",
        "icon": "bag",
        "sort_order": 65,
        "kind": "expense",
    },
    {
        "key": "travel",
        "name_en": "Travel",
        "name_he": "נסיעות",
        "color": "#14B8A6",
        "icon": "plane",
        "sort_order": 68,
        "kind": "expense",
    },
    {
        "key": "subscriptions",
        "name_en": "Subscriptions",
        "name_he": "מנויים",
        "color": "#A855F7",
        "icon": "repeat",
        "sort_order": 72,
        "kind": "expense",
    },
    {
        "key": "pension_savings",
        "name_en": "Pension and savings",
        "name_he": "פנסיה וגמל",
        "color": "#10B981",
        "icon": "leaf",
        "sort_order": 70,
        "kind": "expense",
    },
    {
        "key": "transfers",
        "name_en": "Transfers",
        "name_he": "העברות",
        "color": "#6366F1",
        "icon": "swap",
        "sort_order": 80,
        "kind": "expense",
    },
    {
        "key": "miscellaneous",
        "name_en": "Miscellaneous",
        "name_he": "שונות",
        "color": "#9CA3AF",
        "icon": "dots",
        "sort_order": 90,
        "kind": "expense",
    },
    {
        "key": "income",
        "name_en": "Income",
        "name_he": "הכנסות",
        "color": "#22C55E",
        "icon": "wallet",
        "sort_order": 5,
        "kind": "income",
    },
]


def _has_legacy_schema() -> bool:
    """True if this SQLite file still uses slug keys instead of integer FKs."""
    if engine is None or not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return False
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "categories" in tables:
        cols = {c["name"] for c in insp.get_columns("categories")}
        if "key" in cols:
            return True
    if "categorization_rules" in tables:
        cols = {c["name"] for c in insp.get_columns("categorization_rules")}
        if "category_key" in cols:
            return True
    return False


def _wipe_db_file() -> None:
    """Delete the SQLite file and sidecars so the new schema can be created cleanly."""
    global engine
    path = DB_PATH
    if engine is not None:
        engine.dispose()
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            candidate.unlink()
    configure_engine(path)


def _table_columns(table: str) -> set[str]:
    if engine is None:
        return set()
    insp = inspect(engine)
    if hasattr(insp, "clear_cache"):
        insp.clear_cache()
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _migrate_schema() -> None:
    """Add columns that create_all will not attach to an existing SQLite file."""
    if engine is None:
        return
    rule_cols = _table_columns("categorization_rules")
    if rule_cols and "name" not in rule_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE categorization_rules "
                "ADD COLUMN name VARCHAR(128) NOT NULL DEFAULT ''"
            )
    txn_cols = _table_columns("transactions")
    if txn_cols and "source" not in txn_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE transactions "
                "ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT ''"
            )
            conn.exec_driver_sql(
                """
                UPDATE transactions
                SET source = 'manual'
                WHERE is_manual = 1
                   OR lower(coalesce(source_filename, '')) = 'manual'
                """
            )
            conn.exec_driver_sql(
                """
                UPDATE transactions
                SET source = 'card'
                WHERE source = ''
                  AND length(trim(account)) = 4
                  AND trim(account) GLOB '[0-9][0-9][0-9][0-9]'
                """
            )
            conn.exec_driver_sql(
                "UPDATE transactions SET source = 'bank' WHERE source = ''"
            )
    txn_cols = _table_columns("transactions")
    if txn_cols and "categorized_by" not in txn_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE transactions "
                "ADD COLUMN categorized_by VARCHAR(16) NOT NULL DEFAULT ''"
            )
    txn_cols = _table_columns("transactions")
    if txn_cols and "split_group" not in txn_cols:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE transactions "
                "ADD COLUMN split_group VARCHAR(64) NOT NULL DEFAULT ''"
            )
        _backfill_split_groups()
    elif txn_cols and "split_group" in txn_cols:
        _backfill_split_groups()


def _backfill_split_groups() -> None:
    """Link older split rows that share the same reference stamp but lack split_group."""
    import re
    from uuid import uuid4

    from models import Transaction

    if engine is None or SessionLocal is None:
        return
    with SessionLocal() as session:
        rows = session.scalars(
            select(Transaction).where(Transaction.split_group == "")
        ).all()
        buckets: dict[str, list] = {}
        for txn in rows:
            match = re.search(r"-split-\d+-([\d.]+)$", txn.reference or "")
            if not match:
                continue
            buckets.setdefault(match.group(1), []).append(txn)
        changed = False
        for members in buckets.values():
            if len(members) < 2:
                continue
            group_id = uuid4().hex
            for txn in members:
                txn.split_group = group_id
            changed = True
        if changed:
            session.commit()


def init_db() -> None:
    if _has_legacy_schema():
        _wipe_db_file()
    Base.metadata.create_all(engine)
    _migrate_schema()
    with SessionLocal() as session:
        seed_defaults(session)
        session.commit()


def seed_defaults(session: Session) -> dict[str, int]:
    """Insert any missing seed categories. Does not overwrite existing rows or add rules."""
    return {
        "categories_added": _seed_categories(session),
        "rules_added": 0,
    }


def _seed_categories(session: Session) -> int:
    existing = {c.name_en for c in session.scalars(select(Category)).all()}
    added = 0
    for spec in SEED_CATEGORIES:
        if spec["name_en"] in existing:
            continue
        fields = {k: v for k, v in spec.items() if k != "key"}
        session.add(Category(**fields))
        added += 1
    if added:
        session.flush()
    return added


def get_session() -> Session:
    return SessionLocal()
