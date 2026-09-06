"""Database file backup helpers."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def _copy_db_file(src: Path, dest: Path) -> None:
    """Copy a SQLite file and any WAL/SHM sidecars."""
    shutil.copy2(src, dest)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{src}{suffix}")
        if sidecar.exists():
            shutil.copy2(sidecar, Path(f"{dest}{suffix}"))


def _backup_dir() -> Path:
    import expense_tracker.db as dbstate

    return dbstate.DB_PATH.parent / "backups"


def _prune_db_backups(max_keep: int | None = None) -> None:
    """Keep only the newest expenses-*.db snapshots (manual + migration)."""
    import expense_tracker.db as dbstate

    if max_keep is None:
        max_keep = dbstate.MAX_MIGRATION_BACKUPS
    backup_dir = _backup_dir()
    if not backup_dir.exists():
        return
    backups = sorted(
        backup_dir.glob("expenses-*.db"),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    for old in backups[max_keep:]:
        old.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(f"{old}{suffix}").unlink(missing_ok=True)


# Keep old name as an alias for tests / callers.
_prune_migration_backups = _prune_db_backups


def create_db_backup(*, label: str | None = None) -> Path:
    """Copy expenses.db into data/backups/; keep the last few expenses-*.db files.

    ``label`` is an optional tag in the filename (e.g. ``manual``). Migration
    backups omit the label and use the app version instead.
    """
    import expense_tracker.db as dbstate

    if not dbstate.DB_PATH.exists() or dbstate.DB_PATH.stat().st_size == 0:
        raise FileNotFoundError(f"Database not found: {dbstate.DB_PATH}")

    from expense_tracker import __version__
    from uuid import uuid4

    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    if label:
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label.strip())
        dest = backup_dir / f"expenses-{safe}-{stamp}.db"
    else:
        dest = backup_dir / f"expenses-{__version__}-{stamp}.db"
    _copy_db_file(dbstate.DB_PATH, dest)
    _prune_db_backups()
    return dest


def _backup_db_before_migration() -> Path | None:
    """Snapshot expenses.db before schema changes; keep the last few copies."""
    import expense_tracker.db as dbstate
    from expense_tracker.db.migrations import _schema_migration_pending

    if not _schema_migration_pending():
        return None
    if dbstate.engine is None or not dbstate.DB_PATH.exists() or dbstate.DB_PATH.stat().st_size == 0:
        return None
    return create_db_backup()
