"""Schema inspection and SQLite migrations."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, select

from expense_tracker.models import Base


def _has_legacy_schema() -> bool:
    """True if this SQLite file still uses slug keys instead of integer FKs."""
    import expense_tracker.db as dbstate

    if dbstate.engine is None or not dbstate.DB_PATH.exists() or dbstate.DB_PATH.stat().st_size == 0:
        return False
    insp = inspect(dbstate.engine)
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
    import expense_tracker.db as dbstate

    path = dbstate.DB_PATH
    if dbstate.engine is not None:
        dbstate.engine.dispose()
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            candidate.unlink()
    dbstate.configure_engine(path)


def _table_columns(table: str) -> set[str]:
    import expense_tracker.db as dbstate

    if dbstate.engine is None:
        return set()
    insp = inspect(dbstate.engine)
    if hasattr(insp, "clear_cache"):
        insp.clear_cache()
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _schema_migration_pending() -> bool:
    """True when init_db would change an existing SQLite schema."""
    import expense_tracker.db as dbstate

    if _has_legacy_schema():
        return True
    if dbstate.engine is None or not dbstate.DB_PATH.exists() or dbstate.DB_PATH.stat().st_size == 0:
        return False
    insp = inspect(dbstate.engine)
    existing_tables = set(insp.get_table_names())
    for table_name in Base.metadata.tables:
        if table_name not in existing_tables:
            return True
    rule_cols = _table_columns("categorization_rules")
    if rule_cols and "name" not in rule_cols:
        return True
    txn_cols = _table_columns("transactions")
    if txn_cols:
        for col in ("source", "categorized_by", "custom_description", "split_group"):
            if col not in txn_cols:
                return True
    return False


def _migrate_schema() -> None:
    """Add columns that create_all will not attach to an existing SQLite file."""
    import expense_tracker.db as dbstate

    if dbstate.engine is None:
        return
    rule_cols = _table_columns("categorization_rules")
    if rule_cols and "name" not in rule_cols:
        with dbstate.engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE categorization_rules "
                "ADD COLUMN name VARCHAR(128) NOT NULL DEFAULT ''"
            )
    txn_cols = _table_columns("transactions")
    if txn_cols and "source" not in txn_cols:
        with dbstate.engine.begin() as conn:
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
        with dbstate.engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE transactions "
                "ADD COLUMN categorized_by VARCHAR(16) NOT NULL DEFAULT ''"
            )
    txn_cols = _table_columns("transactions")
    if txn_cols and "custom_description" not in txn_cols:
        with dbstate.engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE transactions "
                "ADD COLUMN custom_description TEXT NOT NULL DEFAULT ''"
            )
    txn_cols = _table_columns("transactions")
    if txn_cols and "split_group" not in txn_cols:
        with dbstate.engine.begin() as conn:
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

    import expense_tracker.db as dbstate
    from expense_tracker.models import Transaction

    if dbstate.engine is None or dbstate.SessionLocal is None:
        return
    with dbstate.SessionLocal() as session:
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
