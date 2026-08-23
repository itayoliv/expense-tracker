"""Investment sector taxonomy, GPT parsing, persistence, and aggregation."""

from __future__ import annotations

import json

import pytest

from expense_tracker.investment_sectors import (
    SECTOR_ETF,
    SECTOR_UNKNOWN,
    VALID_SECTOR_IDS,
    aggregate_sector_allocation,
    classify_portfolio_symbols,
    classify_symbols,
    load_assignments,
    parse_gpt_sector_response,
    save_assignments,
    sectors_path,
    symbols_needing_classification,
)


PORTFOLIOS = [
    {
        "id": "p1",
        "name": "Growth",
        "holdings": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "quantity": 10,
                "price": 150.0,
                "market_value": 1500.0,
            },
            {
                "symbol": "QQQM",
                "name": "Invesco NASDAQ 100 ETF",
                "quantity": 5,
                "price": 200.0,
                "market_value": 1000.0,
            },
        ],
    },
    {
        "id": "p2",
        "name": "Other",
        "holdings": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "quantity": 2,
                "price": 150.0,
                "market_value": 300.0,
            },
            {
                "symbol": "XYZ",
                "name": "Mystery Co",
                "quantity": 1,
                "price": 50.0,
                "market_value": 50.0,
            },
        ],
    },
]


def test_sector_taxonomy_has_gics_plus_etf_and_unknown():
    assert len(VALID_SECTOR_IDS) == 13
    assert SECTOR_ETF in VALID_SECTOR_IDS
    assert SECTOR_UNKNOWN in VALID_SECTOR_IDS


def test_parse_gpt_sector_response_validates_sectors():
    parsed = parse_gpt_sector_response(
        {
            "assignments": {
                "AAPL": "information_technology",
                "QQQM": "etf_diversified",
                "BAD": "not_a_real_sector",
            }
        }
    )
    assert parsed["AAPL"] == "information_technology"
    assert parsed["QQQM"] == SECTOR_ETF
    assert parsed["BAD"] == SECTOR_UNKNOWN


def test_assignments_persist_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "expense_tracker.investment_sectors.sectors_path",
        lambda: tmp_path / "investment_sectors.json",
    )
    save_assignments(
        {
            "AAPL": {
                "sector_id": "information_technology",
                "assigned_by": "gpt",
                "assigned_at": "2026-08-22T12:00:00+00:00",
                "name": "Apple Inc.",
            }
        }
    )
    loaded = load_assignments()
    assert loaded["AAPL"]["sector_id"] == "information_technology"
    assert loaded["AAPL"]["assigned_by"] == "gpt"
    assert json.loads((tmp_path / "investment_sectors.json").read_text(encoding="utf-8"))["AAPL"][
        "sector_id"
    ] == "information_technology"


def test_symbols_needing_classification_only_new_symbols():
    assignments = {
        "AAPL": {"sector_id": "information_technology", "assigned_by": "gpt"},
        "OLD": {"sector_id": SECTOR_UNKNOWN, "assigned_by": "gpt"},
    }
    pending = symbols_needing_classification(PORTFOLIOS, assignments)
    symbols = {item["symbol"] for item in pending}
    assert symbols == {"QQQM", "XYZ"}
    assert "AAPL" not in symbols
    assert "OLD" not in symbols


def test_classify_symbols_uses_gpt_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "expense_tracker.investment_sectors.sectors_path",
        lambda: tmp_path / "investment_sectors.json",
    )
    monkeypatch.setattr(
        "expense_tracker.investment_sectors.get_api_key",
        lambda: "test-key",
    )

    def fake_ask(_api_key, symbols):
        assert len(symbols) == 2
        return {
            "AAPL": "information_technology",
            "QQQM": "etf_diversified",
        }

    result = classify_symbols(
        [
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "QQQM", "name": "Invesco NASDAQ 100 ETF"},
        ],
        ask=fake_ask,
    )
    assert result == {"classified": 2, "unknown": 0, "skipped": 0}
    loaded = load_assignments()
    assert loaded["AAPL"]["sector_id"] == "information_technology"
    assert loaded["QQQM"]["sector_id"] == SECTOR_ETF


def test_classify_symbols_unknown_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "expense_tracker.investment_sectors.sectors_path",
        lambda: tmp_path / "investment_sectors.json",
    )
    monkeypatch.setattr(
        "expense_tracker.investment_sectors.get_api_key",
        lambda: "test-key",
    )

    def fake_ask(_api_key, _symbols):
        return {"XYZ": "unknown"}

    result = classify_symbols([{"symbol": "XYZ", "name": "Mystery Co"}], ask=fake_ask)
    assert result["classified"] == 1
    assert result["unknown"] == 1
    assert load_assignments()["XYZ"]["sector_id"] == SECTOR_UNKNOWN


def test_classify_portfolio_symbols_skips_without_api_key(monkeypatch):
    monkeypatch.setattr("expense_tracker.investment_sectors.get_api_key", lambda: None)
    result = classify_portfolio_symbols(PORTFOLIOS)
    assert result["classified"] == 0
    assert result["skipped"] == 3


def test_aggregate_all_portfolios():
    assignments = {
        "AAPL": {"sector_id": "information_technology", "assigned_by": "gpt"},
        "QQQM": {"sector_id": SECTOR_ETF, "assigned_by": "gpt"},
    }
    payload = aggregate_sector_allocation(PORTFOLIOS, portfolio_id="all", assignments=assignments)
    assert payload["ok"] is True
    assert payload["total"] == 2850.0
    by_id = {item["id"]: item for item in payload["sectors"]}
    assert by_id["information_technology"]["value"] == 1800.0
    assert by_id[SECTOR_ETF]["value"] == 1000.0
    assert by_id[SECTOR_UNKNOWN]["value"] == 50.0
    assert payload["unclassified"] == [{"symbol": "XYZ", "name": "Mystery Co"}]
    assert len(payload["catalog"]) == 13


def test_aggregate_single_portfolio_filter():
    assignments = {
        "AAPL": {"sector_id": "information_technology", "assigned_by": "gpt"},
        "QQQM": {"sector_id": SECTOR_ETF, "assigned_by": "gpt"},
        "XYZ": {"sector_id": SECTOR_UNKNOWN, "assigned_by": "gpt"},
    }
    payload = aggregate_sector_allocation(
        PORTFOLIOS, portfolio_id="p1", assignments=assignments, lang="en"
    )
    assert payload["portfolio_id"] == "p1"
    assert payload["total"] == 2500.0
    assert payload["unclassified"] == []
    labels = [item["label"] for item in payload["sectors"]]
    assert "Information Technology" in labels
    assert "ETF / Diversified" in labels


def test_sectors_path_uses_db_parent(monkeypatch, tmp_path):
    import expense_tracker.db as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "expenses.db")
    path = sectors_path()
    assert path == tmp_path / "investment_sectors.json"
