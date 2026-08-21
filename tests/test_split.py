"""Split one transaction into multiple parts."""

from __future__ import annotations

from sqlalchemy import select

import expense_tracker.db as db
from expense_tracker.models import CategorizationRule, Transaction


def _id_by_name_en(client, name_en: str) -> int:
    cats = client.get("/api/categories").get_json()["categories"]
    return next(c["id"] for c in cats if c["name_en"] == name_en)


def _add_txn(client, description, amount, direction="debit", date="2026-08-15"):
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


def test_split_creates_parts_and_keeps_categories(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    shopping_id = _id_by_name_en(client, "Shopping")
    tid = _add_txn(client, "SUPERMARKET", 100)

    res = client.patch(
        f"/transactions/{tid}",
        json={
            "splits": [
                {
                    "description": "Groceries",
                    "amount": 60,
                    "category_id": shopping_id,
                },
                {
                    "description": "Parking",
                    "amount": 40,
                    "category_id": fuel_id,
                },
            ]
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["created_ids"]
    assert len(body["created_ids"]) == 2

    with db.get_session() as session:
        assert session.get(Transaction, tid) is None
        parts = list(
            session.scalars(
                select(Transaction).where(Transaction.id.in_(body["created_ids"]))
            ).all()
        )
        assert len(parts) == 2
        by_desc = {p.description: p for p in parts}
        assert by_desc["Groceries"].amount == 60
        assert by_desc["Groceries"].category_id == shopping_id
        assert by_desc["Parking"].amount == 40
        assert by_desc["Parking"].category_id == fuel_id
        assert "SUPERMARKET" in (by_desc["Groceries"].details or "")


def test_split_inherits_parent_category_when_omitted(client):
    shopping_id = _id_by_name_en(client, "Shopping")
    tid = _add_txn(client, "אינפיניטי גמל", 100)
    client.patch(f"/transactions/{tid}", json={"category_id": shopping_id})

    res = client.patch(
        f"/transactions/{tid}",
        json={
            "splits": [
                {"description": "אינפיניטי גמל", "amount": 70},
                {"description": "TEST", "amount": 30},
            ]
        },
    )
    assert res.status_code == 200
    ids = res.get_json()["created_ids"]
    with db.get_session() as session:
        parts = list(
            session.scalars(select(Transaction).where(Transaction.id.in_(ids))).all()
        )
        assert len(parts) == 2
        assert all(p.category_id == shopping_id for p in parts)
        by_desc = {p.description: p for p in parts}
        assert by_desc["TEST"].category_id == shopping_id
        groups = {p.split_group for p in parts}
        assert len(groups) == 1
        assert next(iter(groups))


def test_dashboard_marks_split_parts(client):
    shopping_id = _id_by_name_en(client, "Shopping")
    tid = _add_txn(client, "PARENT", 50, date="2026-08-10")
    client.patch(f"/transactions/{tid}", json={"category_id": shopping_id})
    client.patch(
        f"/transactions/{tid}",
        json={
            "splits": [
                {"description": "Part A", "amount": 20, "category_id": shopping_id},
                {"description": "Part B", "amount": 30, "category_id": shopping_id},
            ]
        },
    )
    html = client.get("/?month=2026-08&view=expenses").get_data(as_text=True)
    assert "txn-split-part" in html
    assert "split-badge" in html or "Split" in html
    assert "--split-accent:" in html


def test_split_amounts_must_match(client):
    tid = _add_txn(client, "BIG BILL", 50)
    shopping_id = _id_by_name_en(client, "Shopping")
    res = client.patch(
        f"/transactions/{tid}",
        json={
            "splits": [
                {"description": "A", "amount": 10, "category_id": shopping_id},
                {"description": "B", "amount": 10, "category_id": shopping_id},
            ]
        },
    )
    assert res.status_code == 400
    with db.get_session() as session:
        assert session.get(Transaction, tid) is not None


def test_split_remember_and_apply_per_description(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    shopping_id = _id_by_name_en(client, "Shopping")
    other_id = _id_by_name_en(client, "Food and groceries")

    parent = _add_txn(client, "COMBO STORE", 80)
    twin_fuel = _add_txn(client, "Parking", 15)
    twin_shop = _add_txn(client, "Groceries", 20)
    # Already categorized differently — apply_all should overwrite
    client.patch(
        f"/transactions/{twin_shop}",
        json={"category_id": other_id},
    )

    res = client.patch(
        f"/transactions/{parent}",
        json={
            "splits": [
                {
                    "description": "Groceries",
                    "amount": 50,
                    "category_id": shopping_id,
                },
                {
                    "description": "Parking",
                    "amount": 30,
                    "category_id": fuel_id,
                },
            ],
            "remember_rule": True,
            "apply_to_categorized": True,
        },
    )
    assert res.status_code == 200
    assert res.get_json()["applied"] >= 2

    with db.get_session() as session:
        rules = session.scalars(select(CategorizationRule)).all()
        patterns = {(r.pattern, r.category_id) for r in rules}
        assert ("Groceries", shopping_id) in patterns
        assert ("Parking", fuel_id) in patterns

        fuel_txn = session.get(Transaction, twin_fuel)
        shop_txn = session.get(Transaction, twin_shop)
        assert fuel_txn.category_id == fuel_id
        assert shop_txn.category_id == shopping_id


def test_edit_modal_includes_split_controls(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="btn-split-toggle"' in html
    assert 'id="txn-split-panel"' in html
    js = client.get("/static/js/transactions.js").get_data(as_text=True)
    assert '"splits"' in js or "splits" in js
    assert "splitMode" in js
