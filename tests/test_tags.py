"""Tag CRUD and assignment to transactions."""

from __future__ import annotations

import expense_tracker.db as db
from expense_tracker.models import Tag, Transaction


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


def test_create_list_update_delete_tag(client):
    res = client.post("/api/tags", json={"name": "Vacation", "color": "#0EA5E9"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    tag = body["tag"]
    assert tag["name"] == "Vacation"
    assert tag["color"] == "#0EA5E9"
    tag_id = tag["id"]

    listed = client.get("/api/tags").get_json()
    assert listed["ok"] is True
    assert any(t["id"] == tag_id for t in listed["tags"])

    updated = client.patch(
        f"/api/tags/{tag_id}",
        json={"name": "Trip", "color": "#22C55E"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["tag"]["name"] == "Trip"
    assert updated.get_json()["tag"]["color"] == "#22C55E"

    deleted = client.delete(f"/api/tags/{tag_id}")
    assert deleted.status_code == 200
    assert deleted.get_json()["ok"] is True
    leftover = client.get("/api/tags").get_json()["tags"]
    assert all(t["id"] != tag_id for t in leftover)


def test_duplicate_tag_name_rejected(client):
    assert client.post("/api/tags", json={"name": "Food"}).status_code == 200
    res = client.post("/api/tags", json={"name": "Food"})
    assert res.status_code == 400


def test_assign_tags_via_transaction_patch(client):
    tag_a = client.post("/api/tags", json={"name": "A", "color": "#111111"}).get_json()[
        "tag"
    ]["id"]
    tag_b = client.post("/api/tags", json={"name": "B", "color": "#222222"}).get_json()[
        "tag"
    ]["id"]
    tid = _add_txn(client, "Coffee shop", 25)

    res = client.patch(
        f"/transactions/{tid}",
        json={"tag_ids": [tag_a, tag_b]},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    with db.get_session() as session:
        txn = session.get(Transaction, tid)
        assert {t.id for t in txn.tags} == {tag_a, tag_b}

    res = client.patch(f"/transactions/{tid}", json={"tag_ids": [tag_b]})
    assert res.status_code == 200
    with db.get_session() as session:
        txn = session.get(Transaction, tid)
        assert {t.id for t in txn.tags} == {tag_b}

    res = client.patch(f"/transactions/{tid}", json={"tag_ids": []})
    assert res.status_code == 200
    with db.get_session() as session:
        txn = session.get(Transaction, tid)
        assert list(txn.tags) == []


def test_tag_transactions_endpoint(client):
    tag_id = client.post("/api/tags", json={"name": "Shared"}).get_json()["tag"]["id"]
    tid1 = _add_txn(client, "One", 10)
    tid2 = _add_txn(client, "Two", 20)
    client.patch(f"/transactions/{tid1}", json={"tag_ids": [tag_id]})
    client.patch(f"/transactions/{tid2}", json={"tag_ids": [tag_id]})

    res = client.get(f"/api/tags/{tag_id}/transactions")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["tag"]["txn_count"] == 2
    assert body["tag"]["total"] == 30
    ids = {tx["id"] for tx in body["transactions"]}
    assert ids == {tid1, tid2}
    for tx in body["transactions"]:
        assert any(t["id"] == tag_id for t in tx["tags"])


def test_delete_tag_detaches_from_transactions(client):
    tag_id = client.post("/api/tags", json={"name": "Temp"}).get_json()["tag"]["id"]
    tid = _add_txn(client, "Tagged", 5)
    client.patch(f"/transactions/{tid}", json={"tag_ids": [tag_id]})
    assert client.delete(f"/api/tags/{tag_id}").status_code == 200

    with db.get_session() as session:
        assert session.get(Tag, tag_id) is None
        txn = session.get(Transaction, tid)
        assert list(txn.tags) == []


def test_dashboard_includes_tags(client):
    tag_id = client.post("/api/tags", json={"name": "Dash"}).get_json()["tag"]["id"]
    tid = _add_txn(client, "Tagged expense", 12)
    client.patch(f"/transactions/{tid}", json={"tag_ids": [tag_id]})
    page = client.get("/?view=expenses&date_from=2026-08&date_to=2026-08-31")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Manage tags" in html or "ניהול תגיות" in html
    assert "Dash" in html
    assert f'data-tags="{tag_id}"' in html or f"data-tags='{tag_id}'" in html
