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
    assert 'class="tag-picker-chips"' in html
    js = client.get("/static/js/transactions.js").get_data(as_text=True)
    assert "tag-add-btn" in js
    assert "tag-add-select" in js
    assert "tag-chip-toggle" not in js
    tags_js = client.get("/static/js/tags.js").get_data(as_text=True)
    assert "tag-formula-add" in tags_js
    assert "tag-add-select" in tags_js
    assert "tag-add-btn" not in tags_js
    assert "tag-chip-toggle" not in tags_js


def test_tag_formula_crud_and_persistence(client):
    tag_a = client.post("/api/tags", json={"name": "Formula A"}).get_json()["tag"]["id"]
    tag_b = client.post("/api/tags", json={"name": "Formula B"}).get_json()["tag"]["id"]

    created = client.post("/api/tag-formulas", json={"tag_ids": [tag_a]})
    assert created.status_code == 200
    formula = created.get_json()["formula"]
    assert formula["tag_ids"] == [tag_a]
    assert formula["scope"] == "global"
    formula_id = formula["id"]

    listed = client.get("/api/tag-formulas").get_json()
    assert listed["ok"] is True
    assert any(
        item["id"] == formula_id and item["tag_ids"] == [tag_a]
        for item in listed["formulas"]
    )

    updated = client.patch(
        f"/api/tag-formulas/{formula_id}",
        json={"tag_ids": [tag_a, tag_b]},
    )
    assert updated.status_code == 200
    assert set(updated.get_json()["formula"]["tag_ids"]) == {tag_a, tag_b}

    persisted = client.get("/api/tag-formulas").get_json()["formulas"]
    saved = next(item for item in persisted if item["id"] == formula_id)
    assert set(saved["tag_ids"]) == {tag_a, tag_b}

    deleted = client.delete(f"/api/tag-formulas/{formula_id}")
    assert deleted.status_code == 200
    assert all(
        item["id"] != formula_id
        for item in client.get("/api/tag-formulas").get_json()["formulas"]
    )


def test_tag_formula_allows_empty_and_rejects_unknown_tag(client):
    empty = client.post("/api/tag-formulas", json={"tag_ids": []})
    assert empty.status_code == 200
    formula_id = empty.get_json()["formula"]["id"]

    rejected = client.patch(
        f"/api/tag-formulas/{formula_id}",
        json={"tag_ids": [999999]},
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["error"] == "Unknown tag id"
    formulas = client.get("/api/tag-formulas").get_json()["formulas"]
    assert next(item for item in formulas if item["id"] == formula_id)["tag_ids"] == []


def test_tag_formulas_are_independent_per_category(client):
    tag_id = client.post("/api/tags", json={"name": "Scoped"}).get_json()["tag"]["id"]
    categories = client.get("/api/categories").get_json()["categories"]
    category_a, category_b = categories[:2]

    global_formula = client.post(
        "/api/tag-formulas",
        json={"scope": "global", "tag_ids": [tag_id]},
    ).get_json()["formula"]
    category_formula = client.post(
        "/api/tag-formulas",
        json={
            "scope": f"category:{category_a['id']}",
            "tag_ids": [tag_id],
        },
    ).get_json()["formula"]

    formulas = client.get("/api/tag-formulas").get_json()["formulas"]
    assert next(item for item in formulas if item["id"] == global_formula["id"])[
        "scope"
    ] == "global"
    assert next(item for item in formulas if item["id"] == category_formula["id"])[
        "scope"
    ] == f"category:{category_a['id']}"
    assert not any(
        item["scope"] == f"category:{category_b['id']}" for item in formulas
    )


def test_tag_formula_rejects_unknown_category_scope(client):
    res = client.post(
        "/api/tag-formulas",
        json={"scope": "category:999999", "tag_ids": []},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "Unknown formula scope"


def test_delete_tag_detaches_it_from_formula(client):
    tag_id = client.post("/api/tags", json={"name": "Formula tag"}).get_json()["tag"]["id"]
    formula = client.post(
        "/api/tag-formulas",
        json={"tag_ids": [tag_id]},
    ).get_json()["formula"]

    assert client.delete(f"/api/tags/{tag_id}").status_code == 200
    formulas = client.get("/api/tag-formulas").get_json()["formulas"]
    assert next(item for item in formulas if item["id"] == formula["id"])["tag_ids"] == []


def test_dashboard_includes_saved_tag_formulas(client):
    tag_id = client.post("/api/tags", json={"name": "Saved formula"}).get_json()["tag"]["id"]
    formula_id = client.post(
        "/api/tag-formulas",
        json={"tag_ids": [tag_id]},
    ).get_json()["formula"]["id"]

    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "tagFormulas" in html
    assert f'"id": {formula_id}' in html
