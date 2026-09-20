"""Ignore transactions: PATCH validation, totals, banner, tags, rules, GPT."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

import expense_tracker.db as db
from expense_tracker.integrations.gpt_sort import apply_assignments
from expense_tracker.models import Transaction
from expense_tracker.services.summary import build_summary


def _id_by_name_en(client, name_en: str) -> int:
    cats = client.get("/api/categories").get_json()["categories"]
    return next(c["id"] for c in cats if c["name_en"] == name_en)


def _add_txn(client, description, amount, direction="debit", date_str="2026-08-15"):
    res = client.post(
        "/transactions",
        json={
            "description": description,
            "amount": amount,
            "direction": direction,
            "date": date_str,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    return res.get_json()["id"]


def test_ignore_requires_reason(client):
    tid = _add_txn(client, "Refund pending", 40)
    res = client.patch(
        f"/transactions/{tid}",
        json={"ignored": True, "ignore_reason": ""},
    )
    assert res.status_code == 400
    assert "reason" in res.get_json()["error"].lower()

    with db.get_session() as session:
        txn = session.get(Transaction, tid)
        assert txn.ignored is False
        assert txn.ignore_reason == ""


def test_ignore_and_unignore(client):
    tid = _add_txn(client, "Transfer", 100)
    res = client.patch(
        f"/transactions/{tid}",
        json={"ignored": True, "ignore_reason": "Internal transfer"},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    with db.get_session() as session:
        txn = session.get(Transaction, tid)
        assert txn.ignored is True
        assert txn.ignore_reason == "Internal transfer"

    res = client.patch(
        f"/transactions/{tid}",
        json={"ignored": False, "ignore_reason": "should clear"},
    )
    assert res.status_code == 200

    with db.get_session() as session:
        txn = session.get(Transaction, tid)
        assert txn.ignored is False
        assert txn.ignore_reason == ""


def test_ignored_excluded_from_summary_totals_but_visible(client):
    keep = _add_txn(client, "Coffee", 30)
    ignored = _add_txn(client, "Transfer", 70)
    client.patch(
        f"/transactions/{ignored}",
        json={"ignored": True, "ignore_reason": "Not a real expense"},
    )

    with db.get_session() as session:
        summary = build_summary(
            session,
            "expenses",
            "en",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
        )

    assert summary["grand_total"] == 30
    assert summary["expense_total"] == 30
    assert summary["unsorted_count"] == 1
    assert summary["unsorted"][0]["id"] == keep
    assert all(u["id"] != ignored for u in summary["unsorted"])

    unsorted_cat = next(
        c for c in summary["categories"] if c["key"] == "__unsorted__"
    )
    assert unsorted_cat["total"] == 30
    ids = {tx["id"] for tx in unsorted_cat["txns"]}
    assert ids == {keep, ignored}
    ignored_row = next(tx for tx in unsorted_cat["txns"] if tx["id"] == ignored)
    assert ignored_row["ignored"] is True
    assert ignored_row["ignore_reason"] == "Not a real expense"
    assert sum(summary["pie"]["values"]) == 30


def test_ignored_row_gray_on_dashboard_not_in_banner(client):
    keep = _add_txn(client, "Coffee", 30)
    ignored = _add_txn(client, "Transfer", 70)
    client.patch(
        f"/transactions/{ignored}",
        json={"ignored": True, "ignore_reason": "Duplicate payment"},
    )

    html = client.get(
        "/?view=expenses&date_from=2026-08-01&date_to=2026-08-31"
    ).get_data(as_text=True)
    assert "txn-ignored" in html
    assert "Duplicate payment" in html
    assert "Ignored" in html
    assert f'class="unsorted-item" data-id="{ignored}"' not in html
    assert f'class="unsorted-item" data-id="{keep}"' in html


def test_ignored_excluded_from_tag_totals(client):
    tag_id = client.post("/api/tags", json={"name": "Shared"}).get_json()["tag"]["id"]
    keep = _add_txn(client, "Keep", 25)
    ignored = _add_txn(client, "Skip", 75)
    client.patch(f"/transactions/{keep}", json={"tag_ids": [tag_id]})
    client.patch(
        f"/transactions/{ignored}",
        json={
            "tag_ids": [tag_id],
            "ignored": True,
            "ignore_reason": "Out of scope",
        },
    )

    listed = client.get("/api/tags").get_json()["tags"]
    tag = next(t for t in listed if t["id"] == tag_id)
    assert tag["txn_count"] == 1
    assert tag["total"] == 25

    detail = client.get(f"/api/tags/{tag_id}/transactions").get_json()
    assert detail["tag"]["total"] == 25
    assert detail["tag"]["txn_count"] == 1
    assert [tx["id"] for tx in detail["transactions"]] == [keep]


def test_apply_to_similar_skips_ignored(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    first = _add_txn(client, "פז", 50, date_str="2026-07-01")
    second = _add_txn(client, "פז", 60, date_str="2026-08-01")
    ignored = _add_txn(client, "פז", 70, date_str="2026-09-01")
    client.patch(
        f"/transactions/{ignored}",
        json={"ignored": True, "ignore_reason": "Wrong card"},
    )

    res = client.patch(
        f"/transactions/{first}",
        json={"category_id": fuel_id, "remember_rule": True},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    assert res.get_json()["applied"] == 1

    with db.get_session() as session:
        by_id = {txn.id: txn for txn in session.scalars(select(Transaction)).all()}
        assert by_id[first].category_id == fuel_id
        assert by_id[second].category_id == fuel_id
        assert by_id[ignored].category_id is None
        assert by_id[ignored].ignored is True


def test_gpt_apply_assignments_skips_ignored(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    keep = _add_txn(client, "פז", 50)
    ignored = _add_txn(client, "פז", 80)
    client.patch(
        f"/transactions/{ignored}",
        json={"ignored": True, "ignore_reason": "Ignore for GPT"},
    )

    with db.get_session() as session:
        assigned = apply_assignments(session, {"פז": fuel_id})
        session.commit()
        assert assigned == 1
        by_id = {txn.id: txn for txn in session.scalars(select(Transaction)).all()}
        assert by_id[keep].category_id == fuel_id
        assert by_id[keep].categorized_by == "gpt"
        assert by_id[ignored].category_id is None
        assert by_id[ignored].ignored is True
