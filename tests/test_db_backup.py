"""Tests for pre-migration and manual database backups."""

from __future__ import annotations

import sqlite3

from sqlalchemy import inspect, select, text

import expense_tracker.db as db
from expense_tracker.models import Transaction


def test_init_db_creates_backup_when_tags_table_missing(tmp_path):
    path = tmp_path / "expenses.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY,
            name_en VARCHAR(128) NOT NULL,
            name_he VARCHAR(128) NOT NULL,
            color VARCHAR(16) NOT NULL,
            icon VARCHAR(32) NOT NULL,
            sort_order INTEGER NOT NULL,
            kind VARCHAR(16) NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            txn_date DATE NOT NULL,
            value_date DATE,
            description VARCHAR(512) NOT NULL,
            details TEXT NOT NULL,
            custom_description TEXT NOT NULL DEFAULT '',
            reference VARCHAR(128) NOT NULL,
            beneficiary VARCHAR(256) NOT NULL DEFAULT '',
            purpose VARCHAR(256) NOT NULL DEFAULT '',
            amount FLOAT NOT NULL,
            direction VARCHAR(8) NOT NULL,
            account VARCHAR(64) NOT NULL DEFAULT '',
            category_id INTEGER,
            source_filename VARCHAR(256) NOT NULL DEFAULT '',
            source VARCHAR(16) NOT NULL DEFAULT 'bank',
            categorized_by VARCHAR(16) NOT NULL DEFAULT '',
            split_group VARCHAR(64) NOT NULL DEFAULT '',
            ignored BOOLEAN NOT NULL DEFAULT 0,
            ignore_reason TEXT NOT NULL DEFAULT '',
            imported_at DATETIME NOT NULL,
            is_manual BOOLEAN NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO transactions (
            txn_date, description, details, reference, amount, direction,
            source_filename, imported_at
        ) VALUES ('2026-08-01', 'Coffee', '', 'ref-1', 12.5, 'debit', 'bank.xlsx', '2026-08-01')
        """
    )
    conn.commit()
    conn.close()

    db.configure_engine(path)
    backup_root = path.parent / "backups"
    db.init_db()

    backups = list(backup_root.glob("expenses-*.db"))
    assert len(backups) == 1
    backup_conn = sqlite3.connect(backups[0])
    count = backup_conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    backup_conn.close()
    assert count == 1

    with db.get_session() as session:
        assert session.scalar(select(Transaction).where(Transaction.description == "Coffee"))


def test_init_db_skips_backup_when_schema_current(tmp_path):
    path = tmp_path / "expenses.db"
    db.configure_engine(path)
    db.init_db()
    backup_root = path.parent / "backups"
    assert list(backup_root.glob("expenses-*.db")) == []

    db.init_db()
    assert list(backup_root.glob("expenses-*.db")) == []


def test_prune_migration_backups_keeps_last_five(tmp_path, monkeypatch):
    path = tmp_path / "expenses.db"
    db.configure_engine(path)
    monkeypatch.setattr(db, "MAX_MIGRATION_BACKUPS", 5)
    backup_root = path.parent / "backups"
    backup_root.mkdir(parents=True)

    for idx in range(7):
        dest = backup_root / f"expenses-0.4.2-2026010{idx}-120000.db"
        dest.write_text(f"backup-{idx}", encoding="utf-8")
        dest.touch()

    db._prune_migration_backups()
    remaining = sorted(backup_root.glob("expenses-*.db"), key=lambda p: p.name)
    assert len(remaining) == 5


def test_create_db_backup_manual_prunes_to_five(tmp_path, monkeypatch):
    path = tmp_path / "expenses.db"
    db.configure_engine(path)
    db.init_db()
    monkeypatch.setattr(db, "MAX_MIGRATION_BACKUPS", 5)
    backup_root = path.parent / "backups"

    for _ in range(6):
        dest = db.create_db_backup(label="manual")
        assert dest.exists()
        assert dest.name.startswith("expenses-manual-")

    backups = list(backup_root.glob("expenses-*.db"))
    assert len(backups) == 5


def test_settings_backup_endpoint(client, tmp_path):
    res = client.post("/api/settings/backup")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["filename"].startswith("expenses-manual-")
    assert (tmp_path / "backups" / data["filename"]).exists()


def test_settings_backup_missing_db(tmp_path, client):
    missing = tmp_path / "gone" / "expenses.db"
    db.configure_engine(missing)
    res = client.post("/api/settings/backup")
    assert res.status_code == 400
    assert res.get_json()["ok"] is False


def test_schema_migration_pending_detects_missing_column(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            txn_date DATE NOT NULL,
            value_date DATE,
            description VARCHAR(512) NOT NULL,
            details TEXT NOT NULL,
            reference VARCHAR(128) NOT NULL,
            beneficiary VARCHAR(256) NOT NULL DEFAULT '',
            purpose VARCHAR(256) NOT NULL DEFAULT '',
            amount FLOAT NOT NULL,
            direction VARCHAR(8) NOT NULL,
            account VARCHAR(64) NOT NULL DEFAULT '',
            category_id INTEGER,
            source_filename VARCHAR(256) NOT NULL DEFAULT '',
            imported_at DATETIME NOT NULL,
            is_manual BOOLEAN NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()

    db.configure_engine(path)
    assert db._schema_migration_pending() is True

    db.init_db()
    assert db._schema_migration_pending() is False
    cols = {c["name"] for c in inspect(db.engine).get_columns("transactions")}
    assert "source" in cols
    with db.get_session() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1
