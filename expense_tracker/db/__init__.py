"""Database setup and seed data."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from expense_tracker.models import (  # noqa: F401 — models register their tables
    Base,
    Category,
    InvestmentFxConversion,
    Tag,
    TagSumFormula,
)

# expense_tracker/ (same meaning as when this lived in expense_tracker/db.py)
PACKAGE_DIR = Path(__file__).resolve().parent.parent
ROOT = PACKAGE_DIR.parent
ENV_PATH = ROOT / ".env"
LEGACY_ENV_PATH = PACKAGE_DIR / ".env"


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


def _resolve_env_path() -> Path:
    """Prefer root .env; fall back to legacy expense_tracker/.env for old installs."""
    if ENV_PATH.exists():
        return ENV_PATH
    if LEGACY_ENV_PATH.exists():
        return LEGACY_ENV_PATH
    return ENV_PATH


try:
    from dotenv import load_dotenv

    load_dotenv(_resolve_env_path())
except ImportError:
    _load_env_file(_resolve_env_path())

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
MAX_MIGRATION_BACKUPS = 5

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

from expense_tracker.db.backups import (  # noqa: E402
    _backup_db_before_migration,
    _backup_dir,
    _copy_db_file,
    _prune_db_backups,
    _prune_migration_backups,
    create_db_backup,
)
from expense_tracker.db.migrations import (  # noqa: E402
    _backfill_split_groups,
    _has_legacy_schema,
    _migrate_schema,
    _schema_migration_pending,
    _table_columns,
    _wipe_db_file,
)
from expense_tracker.db.seed import (  # noqa: E402
    SEED_CATEGORIES,
    _seed_categories,
    seed_defaults,
)


def init_db() -> None:
    _backup_db_before_migration()
    if _has_legacy_schema():
        _wipe_db_file()
    Base.metadata.create_all(engine)
    _migrate_schema()
    with SessionLocal() as session:
        seed_defaults(session)
        session.commit()


def get_session() -> Session:
    return SessionLocal()


__all__ = [
    "PACKAGE_DIR",
    "ROOT",
    "ENV_PATH",
    "LEGACY_ENV_PATH",
    "DATA_DIR",
    "MAX_MIGRATION_BACKUPS",
    "DB_PATH",
    "engine",
    "SessionLocal",
    "SEED_CATEGORIES",
    "configure_engine",
    "get_session",
    "init_db",
    "seed_defaults",
    "create_db_backup",
    "_load_env_file",
    "_resolve_env_path",
    "_seed_categories",
    "_has_legacy_schema",
    "_wipe_db_file",
    "_table_columns",
    "_schema_migration_pending",
    "_migrate_schema",
    "_backfill_split_groups",
    "_copy_db_file",
    "_backup_dir",
    "_prune_db_backups",
    "_prune_migration_backups",
    "_backup_db_before_migration",
]
