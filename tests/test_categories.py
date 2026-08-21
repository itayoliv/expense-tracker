"""Category seed defaults and save/persistence API tests."""

from __future__ import annotations

from sqlalchemy import func, select

import expense_tracker.db as db
from expense_tracker.models import CategorizationRule, Category, Transaction

DEFAULT_HEBREW_NAMES = {"הלוואות ומשכנתא", "תרבות ופנאי", "ביטוח"}


def _id_by_name_en(client, name_en: str) -> int:
    cats = client.get("/api/categories").get_json()["categories"]
    return next(c["id"] for c in cats if c["name_en"] == name_en)


def test_init_db_seeds_default_hebrew_categories(tmp_path):
    db.configure_engine(tmp_path / "empty.db")
    db.init_db()
    with db.get_session() as session:
        names = {c.name_he for c in session.scalars(select(Category)).all()}
    assert DEFAULT_HEBREW_NAMES <= names


def test_init_db_restores_deleted_factory_category(tmp_path):
    db.configure_engine(tmp_path / "deleted.db")
    db.init_db()
    with db.get_session() as session:
        cat = session.scalars(select(Category).where(Category.name_en == "Insurance")).one()
        session.delete(cat)
        session.commit()

    db.init_db()
    with db.get_session() as session:
        names = {c.name_en for c in session.scalars(select(Category)).all()}
    assert "Insurance" in names


def test_seed_defaults_restores_missing_category(tmp_path):
    db.configure_engine(tmp_path / "restore.db")
    db.init_db()
    with db.get_session() as session:
        cat = session.scalars(select(Category).where(Category.name_en == "Insurance")).one()
        session.delete(cat)
        session.commit()

    with db.get_session() as session:
        result = db.seed_defaults(session)
        session.commit()
        names = {c.name_en for c in session.scalars(select(Category)).all()}
    assert result["categories_added"] == 1
    assert "Insurance" in names


def test_list_categories_includes_seeded_hebrew_defaults(client):
    res = client.get("/api/categories")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["ok"] is True
    names = {c["name_he"] for c in payload["categories"]}
    assert DEFAULT_HEBREW_NAMES <= names
    assert all("key" not in c for c in payload["categories"])
    assert all(isinstance(c["id"], int) for c in payload["categories"])


def test_create_category_persists(client):
    res = client.post(
        "/api/categories",
        json={
            "name_en": "Pets",
            "name_he": "חיות",
            "color": "#AA11BB",
            "kind": "expense",
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    created = body["category"]
    assert created["name_en"] == "Pets"
    assert created["name_he"] == "חיות"
    assert created["color"] == "#AA11BB"
    assert created["kind"] == "expense"
    assert "key" not in created
    cid = created["id"]

    listed = client.get("/api/categories").get_json()["categories"]
    assert any(c["id"] == cid and c["name_en"] == "Pets" for c in listed)

    with db.get_session() as session:
        cat = session.get(Category, cid)
        assert cat is not None
        assert cat.name_en == "Pets"
        assert cat.name_he == "חיות"
        assert cat.color == "#AA11BB"
        assert cat.kind == "expense"


def test_create_category_requires_name(client):
    before = len(client.get("/api/categories").get_json()["categories"])
    res = client.post("/api/categories", json={"color": "#123456"})
    assert res.status_code == 400
    assert res.get_json()["ok"] is False
    after = len(client.get("/api/categories").get_json()["categories"])
    assert after == before


def test_create_category_invalid_color(client):
    before = len(client.get("/api/categories").get_json()["categories"])
    res = client.post(
        "/api/categories",
        json={"name_en": "Bad", "name_he": "רע", "color": "not-a-hex"},
    )
    assert res.status_code == 400
    assert res.get_json()["ok"] is False
    after = len(client.get("/api/categories").get_json()["categories"])
    assert after == before


def test_seed_endpoint_restores_deleted_category(client):
    insurance_id = _id_by_name_en(client, "Insurance")
    deleted = client.delete(f"/api/categories/{insurance_id}")
    assert deleted.status_code == 200
    assert deleted.get_json()["ok"] is True

    names_after_delete = {c["name_en"] for c in client.get("/api/categories").get_json()["categories"]}
    assert "Insurance" not in names_after_delete

    seeded = client.post("/api/settings/seed")
    assert seeded.status_code == 200
    body = seeded.get_json()
    assert body["ok"] is True
    assert body["categories_added"] == 1
    names = {c["name_en"] for c in client.get("/api/categories").get_json()["categories"]}
    assert "Insurance" in names


def test_seed_endpoint_is_idempotent(client):
    first = client.post("/api/settings/seed").get_json()
    assert first["ok"] is True
    assert first["categories_added"] == 0
    second = client.post("/api/settings/seed").get_json()
    assert second["ok"] is True
    assert second["categories_added"] == 0


def test_dashboard_includes_settings_seed_controls(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="btn-settings"' in html
    assert 'id="settings-modal"' in html
    assert 'id="btn-seed-categories"' in html
    assert 'id="btn-clear-transactions"' in html
    assert 'id="btn-reset-rules"' in html
    assert 'id="setting-show-pie"' in html
    js = client.get("/static/js/settings.js").get_data(as_text=True)
    assert "/api/settings/seed" in js
    assert "/api/settings/clear-transactions" in js
    assert "/api/settings/reset-rules" in js
    assert "/api/settings/pie" in js


def test_clear_transactions_deletes_rows_and_keeps_rules(client):
    created = client.post(
        "/transactions",
        json={
            "description": "Coffee",
            "amount": 12.5,
            "direction": "debit",
            "date": "2026-08-01",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert created.status_code == 200
    client.post(
        "/transactions",
        json={
            "description": "Salary",
            "amount": 100,
            "direction": "credit",
            "date": "2026-08-02",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    before_rules = len(client.get("/api/rules").get_json()["rules"])
    before_cats = len(client.get("/api/categories").get_json()["categories"])
    res = client.post("/api/settings/clear-transactions")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["deleted"] == 2

    with db.get_session() as session:
        remaining = session.scalar(select(func.count()).select_from(Transaction))
        assert remaining == 0
        rules_left = session.scalars(select(CategorizationRule)).all()
        assert len(rules_left) == before_rules

    assert len(client.get("/api/categories").get_json()["categories"]) == before_cats
    html = client.get("/").get_data(as_text=True)
    assert 'id="empty-import-dropzone"' in html


def test_clear_transactions_when_empty(client):
    res = client.post("/api/settings/clear-transactions")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["deleted"] == 0


def test_pie_chart_can_be_hidden(client):
    created = client.post(
        "/transactions",
        json={
            "description": "Coffee",
            "amount": 12.5,
            "direction": "debit",
            "date": "2026-08-01",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert created.status_code == 200

    html = client.get("/").get_data(as_text=True)
    assert 'id="pie-chart"' in html
    assert 'id="setting-show-pie"' in html
    assert "checked" in html

    res = client.post("/api/settings/pie", json={"show_pie": False})
    assert res.status_code == 200
    assert res.get_json()["show_pie"] is False

    html = client.get("/").get_data(as_text=True)
    assert 'id="pie-chart"' not in html
    assert "content-grid no-chart" in html
    assert 'id="expense-table"' in html

    res = client.post("/api/settings/pie", json={"show_pie": True})
    assert res.status_code == 200
    html = client.get("/").get_data(as_text=True)
    assert 'id="pie-chart"' in html
