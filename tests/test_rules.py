"""Learned categorization rules: empty start, apply-to-similar, reset."""

from __future__ import annotations

from sqlalchemy import select

import expense_tracker.db as db
from expense_tracker.models import CategorizationRule, Transaction


def _id_by_name_en(client, name_en: str) -> int:
    cats = client.get("/api/categories").get_json()["categories"]
    return next(c["id"] for c in cats if c["name_en"] == name_en)


def _add_txn(client, description, amount, direction, date):
    res = client.post(
        "/transactions",
        json={
            "description": description,
            "amount": amount,
            "direction": direction,
            "date": date,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    return res.get_json()["id"]


def test_init_starts_with_no_rules(client):
    res = client.get("/api/rules")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["ok"] is True
    assert payload["rules"] == []


def test_seed_defaults_does_not_add_rules(client):
    before = client.get("/api/rules").get_json()["rules"]
    seeded = client.post("/api/settings/seed").get_json()
    assert seeded["ok"] is True
    assert seeded["rules_added"] == 0
    after = client.get("/api/rules").get_json()["rules"]
    assert after == before == []


def test_import_does_not_auto_categorize(client):
    from expense_tracker.importer import import_file
    from tests.test_importer import _isracard_bytes

    with db.get_session() as session:
        result = import_file(session, _isracard_bytes(), "0423_09_2026.xlsx")
        session.commit()
        txns = session.scalars(select(Transaction)).all()
    assert result["added"] == 3
    assert txns
    assert all(txn.category_id is None for txn in txns)


def test_credits_stay_unsorted_without_rule():
    from expense_tracker.categorizer import match_category_id
    from expense_tracker.models import Category

    cats = {
        1: Category(
            id=1,
            name_en="Income",
            name_he="הכנסות",
            color="#22C55E",
            kind="income",
        )
    }
    assert match_category_id("אמדוקס", "", "credit", [], cats=cats) is None
    assert match_category_id("פז", "", "debit", [], cats=cats) is None


def test_remember_applies_to_similar_unsorted(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    shopping_id = _id_by_name_en(client, "Shopping")

    first = _add_txn(client, "פז", 50, "debit", "2026-07-01")
    second = _add_txn(client, "פז", 60, "debit", "2026-08-01")
    third = _add_txn(client, "פז", 70, "debit", "2026-09-01")
    other = _add_txn(client, "yellow", 80, "debit", "2026-08-15")
    already = _add_txn(client, "פז", 90, "debit", "2026-06-01")

    locked = client.patch(
        f"/transactions/{already}",
        json={"category_id": shopping_id},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert locked.status_code == 200
    assert locked.get_json().get("applied", 0) == 0

    res = client.patch(
        f"/transactions/{first}",
        json={"category_id": fuel_id, "remember_rule": True},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["applied"] == 2

    with db.get_session() as session:
        by_id = {txn.id: txn for txn in session.scalars(select(Transaction)).all()}
        assert by_id[first].category_id == fuel_id
        assert by_id[second].category_id == fuel_id
        assert by_id[third].category_id == fuel_id
        assert by_id[other].category_id is None
        assert by_id[already].category_id == shopping_id
        rules = session.scalars(select(CategorizationRule)).all()
        assert len(rules) == 1
        assert rules[0].pattern == "פז"
        assert rules[0].category_id == fuel_id


def test_apply_to_categorized_overwrites_matching_rows(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    shopping_id = _id_by_name_en(client, "Shopping")

    first = _add_txn(client, "פז", 50, "debit", "2026-07-01")
    second = _add_txn(client, "פז", 60, "debit", "2026-08-01")
    already = _add_txn(client, "פז", 90, "debit", "2026-06-01")
    other = _add_txn(client, "yellow", 80, "debit", "2026-08-15")

    client.patch(
        f"/transactions/{already}",
        json={"category_id": shopping_id},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    res = client.patch(
        f"/transactions/{first}",
        json={
            "category_id": fuel_id,
            "remember_rule": True,
            "apply_to_categorized": True,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    assert res.get_json()["applied"] == 2

    with db.get_session() as session:
        by_id = {txn.id: txn for txn in session.scalars(select(Transaction)).all()}
        assert by_id[first].category_id == fuel_id
        assert by_id[second].category_id == fuel_id
        assert by_id[already].category_id == fuel_id
        assert by_id[other].category_id is None
        rules = session.scalars(select(CategorizationRule)).all()
        assert len(rules) == 1
        assert rules[0].pattern == "פז"


def test_apply_to_categorized_without_remember_skips_rule(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    shopping_id = _id_by_name_en(client, "Shopping")
    first = _add_txn(client, "פז", 50, "debit", "2026-07-01")
    already = _add_txn(client, "פז", 90, "debit", "2026-06-01")
    client.patch(
        f"/transactions/{already}",
        json={"category_id": shopping_id},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    res = client.patch(
        f"/transactions/{first}",
        json={"category_id": fuel_id, "apply_to_categorized": True},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    assert res.get_json()["applied"] == 1
    with db.get_session() as session:
        by_id = {txn.id: txn for txn in session.scalars(select(Transaction)).all()}
        assert by_id[already].category_id == fuel_id
        assert session.scalars(select(CategorizationRule)).first() is None


def test_without_remember_does_not_apply_similar(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    first = _add_txn(client, "פז", 50, "debit", "2026-07-01")
    second = _add_txn(client, "פז", 60, "debit", "2026-08-01")

    res = client.patch(
        f"/transactions/{first}",
        json={"category_id": fuel_id, "remember_rule": False},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    assert res.get_json()["applied"] == 0

    with db.get_session() as session:
        by_id = {txn.id: txn for txn in session.scalars(select(Transaction)).all()}
        assert by_id[first].category_id == fuel_id
        assert by_id[second].category_id is None
        assert session.scalars(select(CategorizationRule)).first() is None


def test_reset_rules_deletes_rules_keeps_categories_and_transactions(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    txn_id = _add_txn(client, "פז", 50, "debit", "2026-07-01")
    client.patch(
        f"/transactions/{txn_id}",
        json={"category_id": fuel_id, "remember_rule": True},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert client.get("/api/rules").get_json()["rules"]

    before_cats = len(client.get("/api/categories").get_json()["categories"])
    res = client.post("/api/settings/reset-rules")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["deleted"] == 1
    assert client.get("/api/rules").get_json()["rules"] == []

    seeded = client.post("/api/settings/seed").get_json()
    assert seeded["rules_added"] == 0
    assert client.get("/api/rules").get_json()["rules"] == []
    assert len(client.get("/api/categories").get_json()["categories"]) == before_cats

    with db.get_session() as session:
        txn = session.get(Transaction, txn_id)
        assert txn.category_id == fuel_id


def test_reset_rules_when_empty(client):
    res = client.post("/api/settings/reset-rules")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["deleted"] == 0


def test_dashboard_includes_rules_manager(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="btn-manage-rules"' in html
    assert 'id="rules-modal"' in html
    assert 'id="btn-add-rule"' in html
    assert 'id="rule-name"' in html
    assert 'id="btn-reset-rules"' in html
    rules_js = client.get("/static/js/rules.js").get_data(as_text=True)
    settings_js = client.get("/static/js/settings.js").get_data(as_text=True)
    assert "/api/rules" in rules_js
    assert "/api/settings/reset-rules" in settings_js


def test_create_rule_persists(client):
    shopping_id = _id_by_name_en(client, "Shopping")
    res = client.post(
        "/api/rules",
        json={"pattern": "סופר פארם", "category_id": shopping_id, "priority": 175},
    )
    assert res.status_code == 200
    created = res.get_json()["rule"]
    assert created["pattern"] == "סופר פארם"
    rid = created["id"]
    with db.get_session() as session:
        rule = session.get(CategorizationRule, rid)
        assert rule.pattern == "סופר פארם"
        assert rule.category_id == shopping_id


def test_manual_add_applies_matching_rule(client):
    shopping_id = _id_by_name_en(client, "Shopping")
    client.post(
        "/api/rules",
        json={"pattern": "סופר פארם", "category_id": shopping_id},
    )
    tid = _add_txn(client, "סופר פארם רמת גן", 12.5, "debit", "2026-08-01")
    with db.get_session() as session:
        txn = session.get(Transaction, tid)
        assert txn.category_id == shopping_id


def test_manual_add_unmatched_stays_unsorted(client):
    shopping_id = _id_by_name_en(client, "Shopping")
    client.post(
        "/api/rules",
        json={"pattern": "סופר פארם", "category_id": shopping_id},
    )
    tid = _add_txn(client, "unknown merchant", 12.5, "debit", "2026-08-01")
    with db.get_session() as session:
        txn = session.get(Transaction, tid)
        assert txn.category_id is None


def test_manual_add_explicit_category_overrides_rules(client):
    shopping_id = _id_by_name_en(client, "Shopping")
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    client.post("/api/rules", json={"pattern": "פז", "category_id": fuel_id})
    res = client.post(
        "/transactions",
        json={
            "description": "פז",
            "amount": 40,
            "direction": "debit",
            "date": "2026-08-01",
            "category_id": shopping_id,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    tid = res.get_json()["id"]
    with db.get_session() as session:
        assert session.get(Transaction, tid).category_id == shopping_id


def test_update_rule_changes_pattern_and_name(client):
    shopping_id = _id_by_name_en(client, "Shopping")
    created = client.post(
        "/api/rules",
        json={"pattern": "סופר פארם", "category_id": shopping_id},
    ).get_json()["rule"]
    res = client.patch(
        f"/api/rules/{created['id']}",
        json={"name": "Super-Pharm", "pattern": "SUPER-PHARM", "priority": 200},
    )
    assert res.status_code == 200
    updated = res.get_json()["rule"]
    assert updated["name"] == "Super-Pharm"
    assert updated["display_name"] == "Super-Pharm"
    assert updated["pattern"] == "SUPER-PHARM"
    assert updated["priority"] == 200


def test_init_db_adds_rule_name_column(tmp_path):
    import sqlite3

    from sqlalchemy import inspect

    path = tmp_path / "legacy-rules.db"
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
        CREATE TABLE categorization_rules (
            id INTEGER PRIMARY KEY,
            pattern VARCHAR(256) NOT NULL,
            category_id INTEGER NOT NULL,
            priority INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    db.configure_engine(path)
    db.init_db()
    cols = {c["name"] for c in inspect(db.engine).get_columns("categorization_rules")}
    assert "name" in cols
    with db.get_session() as session:
        assert session.scalars(select(CategorizationRule)).first() is None


def test_init_db_adds_transaction_source_column(tmp_path):
    import sqlite3

    from sqlalchemy import inspect, text

    path = tmp_path / "legacy-source.db"
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
    conn.execute(
        """
        INSERT INTO transactions (
            txn_date, description, details, reference, amount, direction,
            account, source_filename, imported_at, is_manual
        ) VALUES
        ('2026-08-01', 'Cash', '', 'm1', 10, 'debit', '', 'manual', '2026-08-01', 1),
        ('2026-08-02', 'Shop', '', 'c1', 20, 'debit', '0423', 'card.xlsx', '2026-08-02', 0),
        ('2026-08-03', 'ATM', '', 'b1', 30, 'debit', '12-345', 'bank.xlsx', '2026-08-03', 0)
        """
    )
    conn.commit()
    conn.close()

    db.configure_engine(path)
    db.init_db()
    cols = {c["name"] for c in inspect(db.engine).get_columns("transactions")}
    assert "source" in cols
    with db.get_session() as session:
        kinds = {
            row[0]
            for row in session.execute(
                text("SELECT source FROM transactions")
            )
        }
    assert kinds == {"manual", "card", "bank"}
