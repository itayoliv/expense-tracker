"""ChatGPT unsorted categorization (mocked OpenAI)."""

from __future__ import annotations

from sqlalchemy import select

import expense_tracker.db as db
from expense_tracker.models import Category, Transaction


def _id_by_name_en(client, name_en: str) -> int:
    cats = client.get("/api/categories").get_json()["categories"]
    return next(c["id"] for c in cats if c["name_en"] == name_en)


def _add_txn(client, description, amount, direction, date, details=""):
    res = client.post(
        "/transactions",
        json={
            "description": description,
            "details": details,
            "amount": amount,
            "direction": direction,
            "date": date,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    return res.get_json()["id"]


def test_group_unsorted_names_collapses_same_description():
    from expense_tracker.gpt_sort import group_unsorted_names

    class Row:
        def __init__(self, description, details=""):
            self.description = description
            self.details = details

    grouped = group_unsorted_names(
        [Row("פז"), Row("פז"), Row("ZARA"), Row("  פז  ")]
    )
    by_key = {item["name"].strip().lower(): item for item in grouped}
    assert set(by_key) == {"פז", "zara"}
    assert by_key["פז"]["count"] == 3
    sent_names = {item["name"].strip() for item in grouped}
    assert "ZARA" in sent_names


def test_parse_gpt_json_matches_en_he_and_id():
    from expense_tracker.gpt_sort import parse_gpt_json

    shopping = Category(id=1, name_en="Shopping", name_he="קניות", kind="expense")
    fuel = Category(
        id=2, name_en="Fuel and transport", name_he="דלק ותחבורה", kind="expense"
    )
    parsed = parse_gpt_json(
        {
            "Shopping": ["ZARA"],
            "דלק ותחבורה": ["פז"],
            "99": ["unknown cat name"],
        },
        [shopping, fuel],
    )
    assert parsed["zara"] == 1
    assert parsed["פז"] == 2
    assert "unknown cat name" not in parsed


def test_parse_gpt_json_skips_unknown_category_and_name():
    from expense_tracker.gpt_sort import parse_gpt_json

    shopping = Category(id=1, name_en="Shopping", name_he="קניות", kind="expense")
    parsed = parse_gpt_json(
        {"Not A Category": ["ZARA"], "Shopping": ["ghost merchant"]},
        [shopping],
    )
    assert "zara" not in parsed
    assert parsed["ghost merchant"] == 1


def test_ask_openai_http_falls_back_to_curl_when_avg_blocks(monkeypatch):
    import urllib.request

    import expense_tracker.gpt_sort as gpt_sort

    def boom(*_a, **_k):
        raise PermissionError(
            "[Errno 13] Permission denied: '\\\\.\\avgMonFltProxy\\15eaa4cf5c884335'"
        )

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(
        gpt_sort,
        "_ask_openai_curl",
        lambda *_a, **_k: '{"Shopping": ["ZARA"]}',
    )
    content = gpt_sort._ask_openai_http("sk-test", {"model": "gpt-4o-mini", "messages": []})
    assert content == '{"Shopping": ["ZARA"]}'


def test_gpt_sort_requires_api_key(client):
    _add_txn(client, "פז", 50, "debit", "2026-08-01")
    res = client.post("/api/gpt/sort")
    assert res.status_code == 400
    body = res.get_json()
    assert body["ok"] is False
    assert "Settings" in body["error"]


def test_gpt_sort_groups_and_applies_only_unsorted(client, monkeypatch):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    shopping_id = _id_by_name_en(client, "Shopping")
    first = _add_txn(client, "פז", 50, "debit", "2026-07-01")
    second = _add_txn(client, "פז", 60, "debit", "2026-08-01")
    zara = _add_txn(client, "ZARA", 80, "debit", "2026-08-02")
    locked = _add_txn(client, "פז", 90, "debit", "2026-06-01")
    client.patch(
        f"/transactions/{locked}",
        json={"category_id": shopping_id},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    captured = {}

    def fake_ask(_key, _cats, names):
        captured["names"] = sorted(item["name"] for item in names)
        return {"Fuel and transport": ["פז"], "Shopping": ["ZARA"]}

    monkeypatch.setattr("expense_tracker.gpt_sort.ask_openai", fake_ask)
    monkeypatch.setattr("expense_tracker.gpt_sort.get_api_key", lambda: "sk-test")

    res = client.post("/api/gpt/sort")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["assigned"] == 3
    assert captured["names"] == ["ZARA", "פז"]

    with db.get_session() as session:
        by_id = {txn.id: txn for txn in session.scalars(select(Transaction)).all()}
        assert by_id[first].category_id == fuel_id
        assert by_id[second].category_id == fuel_id
        assert by_id[zara].category_id == shopping_id
        assert by_id[locked].category_id == shopping_id
        assert by_id[first].categorized_by == "gpt"
        assert by_id[second].categorized_by == "gpt"
        assert by_id[zara].categorized_by == "gpt"
        assert by_id[locked].categorized_by == ""


def test_gpt_sort_ignores_unknown_category_and_name(client, monkeypatch):
    _add_txn(client, "פז", 50, "debit", "2026-08-01")
    monkeypatch.setattr(
        "expense_tracker.gpt_sort.ask_openai",
        lambda *_a, **_k: {"No Such Category": ["פז"], "Shopping": ["not in list"]},
    )
    monkeypatch.setattr("expense_tracker.gpt_sort.get_api_key", lambda: "sk-test")
    res = client.post("/api/gpt/sort")
    assert res.status_code == 200
    body = res.get_json()
    assert body["assigned"] == 0
    with db.get_session() as session:
        txn = session.scalars(select(Transaction)).first()
        assert txn.category_id is None
        assert txn.categorized_by == ""


def test_manual_patch_clears_gpt_tag(client, monkeypatch):
    shopping_id = _id_by_name_en(client, "Shopping")
    tid = _add_txn(client, "ZARA", 80, "debit", "2026-08-02")
    monkeypatch.setattr(
        "expense_tracker.gpt_sort.ask_openai", lambda *_a, **_k: {"Shopping": ["ZARA"]}
    )
    monkeypatch.setattr("expense_tracker.gpt_sort.get_api_key", lambda: "sk-test")
    assert client.post("/api/gpt/sort").status_code == 200
    with db.get_session() as session:
        assert session.get(Transaction, tid).categorized_by == "gpt"
    client.patch(
        f"/transactions/{tid}",
        json={"category_id": shopping_id},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    with db.get_session() as session:
        assert session.get(Transaction, tid).categorized_by == ""


def test_dashboard_shows_gpt_badge_and_sort_button(client, monkeypatch):
    _add_txn(client, "ZARA", 80, "debit", "2026-08-02")
    html = client.get("/?month=2026-08&view=expenses").get_data(as_text=True)
    assert 'id="btn-gpt-sort"' in html
    monkeypatch.setattr(
        "expense_tracker.gpt_sort.ask_openai", lambda *_a, **_k: {"Shopping": ["ZARA"]}
    )
    monkeypatch.setattr("expense_tracker.gpt_sort.get_api_key", lambda: "sk-test")
    assert client.post("/api/gpt/sort").status_code == 200
    html = client.get("/?month=2026-08&view=expenses").get_data(as_text=True)
    assert 'class="gpt-badge"' in html
    txn_js = client.get("/static/js/transactions.js").get_data(as_text=True)
    settings_js = client.get("/static/js/settings.js").get_data(as_text=True)
    assert "/api/gpt/sort" in txn_js
    assert "/api/settings/openai-key" in settings_js


def test_save_and_clear_openai_key(client, tmp_path):
    from expense_tracker.gpt_sort import get_api_key, openai_key_path

    res = client.post(
        "/api/settings/openai-key",
        json={"api_key": "sk-secret-test"},
    )
    assert res.status_code == 200
    assert res.get_json()["has_key"] is True
    assert get_api_key() == "sk-secret-test"
    assert openai_key_path().parent == tmp_path
    cleared = client.post("/api/settings/openai-key", json={"clear": True})
    assert cleared.status_code == 200
    assert get_api_key() is None
