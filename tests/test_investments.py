"""Investments / Yahoo Finance route tests (fetcher mocked)."""

from __future__ import annotations


def test_investments_page_not_connected(client, monkeypatch):
    monkeypatch.setattr("expense_tracker.routes.investments.is_connected", lambda: False)
    monkeypatch.setattr("expense_tracker.routes.investments.load_cache", lambda: None)

    html = client.get("/investments").get_data(as_text=True)
    assert "Investments" in html or "השקעות" in html
    assert "connect_yahoo.bat" in html
    assert 'id="btn-refresh-investments"' not in html


def test_investments_page_shows_cached_portfolios(client, monkeypatch):
    monkeypatch.setattr("expense_tracker.routes.investments.is_connected", lambda: True)
    monkeypatch.setattr("expense_tracker.routes.investments.fetch_usd_ils_rate", lambda: 3.7)
    monkeypatch.setattr(
        "expense_tracker.routes.investments.load_cache",
        lambda: {
            "updated_at": "2026-08-22T12:00:00+00:00",
            "grand_total": 1500.5,
            "portfolios": [
                {
                    "id": "p_demo",
                    "name": "Demo Portfolio",
                    "total_value": 1500.5,
                    "holdings": [
                        {
                            "symbol": "AAPL",
                            "name": "Apple Inc.",
                            "quantity": 10,
                            "price": 150.05,
                            "change_pct": 1.25,
                            "market_value": 1500.5,
                        }
                    ],
                }
            ],
        },
    )

    html = client.get("/investments").get_data(as_text=True)
    assert "Demo Portfolio" in html
    assert "AAPL" in html
    assert "Apple Inc." in html
    assert 'id="btn-refresh-investments"' in html
    assert 'id="buy-planner"' in html
    assert 'id="buy-budget-input"' in html
    assert 'id="buy-currency-tabs"' in html
    assert 'id="buy-fractional"' in html
    assert 'id="buy-stock-select"' in html
    assert 'id="buy-planner-table"' in html
    assert 'id="buy-planner-body"' in html
    assert "Share price" in html or "מחיר למניה" in html
    assert 'id="buy-th-percent"' in html
    assert 'id="buy-th-shares"' in html
    assert 'class="buy-mode-toggle buy-mode-active"' in html
    assert 'aria-controls="buy-planner-body-wrap"' in html
    assert 'class="collapsible-panel-body hidden" id="buy-planner-body-wrap"' in html


def test_investments_page_shows_fx_savings_comparison(client, monkeypatch):
    monkeypatch.setattr("expense_tracker.routes.investments.is_connected", lambda: True)
    monkeypatch.setattr("expense_tracker.routes.investments.fetch_usd_ils_rate", lambda: 3.0)
    monkeypatch.setattr(
        "expense_tracker.routes.investments.load_cache",
        lambda: {
            "grand_total": 100,
            "portfolios": [
                {
                    "id": "p_demo",
                    "name": "Demo Portfolio",
                    "total_value": 100,
                    "holdings": [],
                }
            ],
        },
    )

    html = client.get("/investments").get_data(as_text=True)
    assert 'id="fx-savings-panel"' in html
    assert 'id="fx-savings-amount"' in html
    assert 'id="fx-onezero-rate"' in html
    assert "Meitav Trade" in html
    assert "Altshuler Shaham Trade" in html
    assert "Bank Hapoalim" in html
    assert "Mizrahi-Tefahot" in html
    assert "Discount Bank" in html
    assert 'aria-controls="fx-savings-body"' in html
    assert 'class="collapsible-panel-body hidden" id="fx-savings-body"' in html


def test_create_onezero_conversion_saves_historical_value_and_savings(
    client, monkeypatch
):
    import expense_tracker.db as db
    from expense_tracker.models import InvestmentFxConversion

    monkeypatch.setattr("expense_tracker.routes.investments.is_connected", lambda: True)
    monkeypatch.setattr("expense_tracker.routes.investments.fetch_usd_ils_rate", lambda: 3.2)
    monkeypatch.setattr(
        "expense_tracker.routes.investments.fetch_usd_ils_rate_on_date",
        lambda _date: 3.2,
    )
    monkeypatch.setattr(
        "expense_tracker.routes.investments.load_cache",
        lambda: {
            "grand_total": 100,
            "portfolios": [
                {
                    "id": "p_onezero",
                    "name": "OneZero",
                    "total_value": 100,
                    "holdings": [],
                }
            ],
        },
    )

    response = client.post(
        "/investments/conversions",
        data={"nis_amount": "10000", "conversion_date": "2026-09-08"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["conversion"]["saved_nis"] == 62
    assert payload["onezero_saved_total"] == 62

    html = client.get("/investments").get_data(as_text=True)
    assert "2026-09-08" in html
    assert "3.2000" in html
    assert "$3,125.00" in html
    assert "62.00 ₪" in html

    with db.get_session() as session:
        conversion = session.query(InvestmentFxConversion).one()
        assert conversion.nis_amount == 10000
        assert conversion.usd_ils_rate == 3.2
        assert conversion.usd_amount == 3125
        assert conversion.saved_nis == 62


def test_investments_refresh_success(client, monkeypatch):
    monkeypatch.setattr(
        "expense_tracker.routes.investments.fetch_portfolios",
        lambda: {
            "updated_at": "2026-08-22T12:00:00+00:00",
            "grand_total": 100,
            "portfolios": [{"id": "p1", "name": "One", "total_value": 100, "holdings": []}],
        },
    )
    resp = client.post("/investments/refresh", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Updated 1 portfolios" in html or "עודכנו 1 תיקים" in html


def test_investments_refresh_error(client, monkeypatch):
    from expense_tracker.integrations.yahoo import YahooFinanceError

    def _boom():
        raise YahooFinanceError("Yahoo Finance is not connected. Run connect_yahoo.bat once to log in.")

    monkeypatch.setattr("expense_tracker.routes.investments.fetch_portfolios", _boom)
    resp = client.post("/investments/refresh", follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "connect_yahoo.bat" in html


def test_investments_quotes_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        "expense_tracker.routes.investments.load_cache",
        lambda: {
            "portfolios": [
                {
                    "id": "p1",
                    "holdings": [
                        {"symbol": "QQQM", "quantity": 1, "price": 100},
                        {"symbol": "AAPL", "quantity": 2, "price": 200},
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        "expense_tracker.routes.investments.fetch_live_quotes",
        lambda symbols: {
            "quotes": {
                "QQQM": {
                    "price": 250.5,
                    "change_pct": 1.25,
                    "market_state": "REGULAR",
                    "session": "regular",
                    "name": "Invesco NASDAQ 100 ETF",
                }
            },
            "live": True,
            "usd_ils": 3.65,
            "updated_at": "2026-08-22T18:00:00+00:00",
        },
    )
    resp = client.get("/investments/quotes")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["live"] is True
    assert data["quotes"]["QQQM"]["price"] == 250.5
    assert data["quotes"]["QQQM"]["change_pct"] == 1.25
    assert data["usd_ils"] == 3.65


def test_quote_from_yahoo_prefers_post_market():
    from expense_tracker.integrations.yahoo.quotes import _quote_from_yahoo_result

    q = _quote_from_yahoo_result(
        {
            "marketState": "POST",
            "regularMarketPrice": 100,
            "regularMarketChangePercent": 1.0,
            "postMarketPrice": 101.5,
            "postMarketChangePercent": 1.5,
            "shortName": "Demo",
        }
    )
    assert q["price"] == 101.5
    assert q["change_pct"] == 1.5
    assert q["session"] == "post"


def test_normalize_holding_recovers_qty_from_market_value():
    from expense_tracker.integrations.yahoo.portfolios import _normalize_holding

    h = _normalize_holding(
        {
            "symbol": "SPY",
            "name": "SPY",
            "quantity": 500.0,
            "price": 500.0,
            "change_pct": 0,
            "market_value": 5000.0,
        }
    )
    assert h is not None
    assert abs(h["quantity"] - 10.0) < 1e-6
    assert abs(h["market_value"] - 5000.0) < 0.02

    assert (
        _normalize_holding(
            {
                "symbol": "QQQM",
                "name": "QQQM",
                "quantity": 293.76,
                "price": 293.76,
                "change_pct": 0,
                "market_value": 293.76,
            }
        )
        is None
    )


def test_holding_from_dom_uses_shares_and_rejects_junk():
    from expense_tracker.integrations.yahoo.portfolios import _holding_from_row

    good = _holding_from_row(
        {
            "symbol": "AAPL",
            "name": "Apple",
            "quantity": "2",
            "price": "150",
            "change_pct": "1.5",
            "market_value": "300",
            "_from_dom": True,
        }
    )
    assert good is not None
    assert good["quantity"] == 2
    assert good["market_value"] == 300

    junk = _holding_from_row(
        {
            "symbol": "0",
            "name": "0\nApr",
            "quantity": "0",
            "price": "0",
            "market_value": "0",
            "_from_dom": True,
        }
    )
    assert junk is None

    watch = _holding_from_row(
        {
            "symbol": "NVDA",
            "name": "NVIDIA",
            "quantity": "0",
            "price": "110.25",
            "change_pct": "1.1",
            "market_value": "0",
            "_from_dom": True,
        }
    )
    assert watch is not None
    assert watch["symbol"] == "NVDA"
    assert watch["quantity"] == 0
    assert watch["price"] == 110.25


def test_normalize_holding_keeps_watchlist_zero_shares():
    from expense_tracker.integrations.yahoo.portfolios import _normalize_holding

    h = _normalize_holding(
        {
            "symbol": "MSFT",
            "name": "Microsoft",
            "quantity": 0,
            "price": 420.5,
            "change_pct": 0.5,
            "market_value": 0,
        }
    )
    assert h is not None
    assert h["symbol"] == "MSFT"
    assert h["quantity"] == 0
    assert h["market_value"] == 0
    assert h["price"] == 420.5


def test_extract_ignores_bare_quotes():
    from expense_tracker.integrations.yahoo.portfolios import _extract_holdings_from_payload

    payload = {
        "quoteResponse": {
            "result": [
                {"symbol": "AAPL", "regularMarketPrice": 150, "regularMarketChangePercent": 1},
            ]
        },
        "finance": {
            "result": [
                {
                    "positions": [
                        {
                            "symbol": "QQQM",
                            "quantity": 1,
                            "regularMarketPrice": 250,
                            "marketValue": 250,
                        }
                    ],
                    "securities": [
                        {
                            "symbol": "TSLA",
                            "shortName": "Tesla",
                            "regularMarketPrice": 250.5,
                            "regularMarketChangePercent": -0.5,
                        }
                    ],
                }
            ]
        },
    }
    holdings = _extract_holdings_from_payload(payload)
    by_symbol = {h["symbol"]: h for h in holdings}
    assert set(by_symbol) == {"QQQM", "TSLA"}
    assert by_symbol["QQQM"]["quantity"] == 1
    assert by_symbol["TSLA"]["quantity"] == 0
    assert by_symbol["TSLA"]["price"] == 250.5


def test_investments_page_includes_watchlist_symbols_in_buy_catalog(client, monkeypatch):
    monkeypatch.setattr(
        "expense_tracker.routes.investments.is_connected",
        lambda: True,
    )
    monkeypatch.setattr(
        "expense_tracker.routes.investments.load_cache",
        lambda: {
            "updated_at": "2026-09-11T10:00:00+00:00",
            "grand_total": 0,
            "portfolios": [
                {
                    "id": "watch1",
                    "name": "y watchlist",
                    "total_value": 0,
                    "holdings": [
                        {
                            "symbol": "AMD",
                            "name": "AMD",
                            "quantity": 0,
                            "price": 160.0,
                            "change_pct": 1.2,
                            "market_value": 0,
                        }
                    ],
                }
            ],
        },
    )
    html = client.get("/investments").get_data(as_text=True)
    assert 'data-symbol="AMD"' in html
    assert "Watch" in html or "מעקב" in html
    assert 'id="buy-stock-select"' in html


def test_investments_history_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        "expense_tracker.routes.investments.load_cache",
        lambda: {
            "portfolios": [
                {
                    "id": "p1",
                    "name": "One",
                    "holdings": [{"symbol": "AAPL", "quantity": 2, "price": 100, "market_value": 200}],
                }
            ]
        },
    )
    monkeypatch.setattr(
        "expense_tracker.routes.investments.build_holdings_history",
        lambda portfolios, portfolio_id="all", range_key="6mo": {
            "ok": True,
            "range": range_key,
            "portfolio_id": portfolio_id,
            "labels": ["2026-01-01", "2026-02-01"],
            "values": [180.0, 200.0],
            "current_total": 200.0,
        },
    )
    resp = client.get("/investments/history?portfolio=p1&range=6mo")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["values"] == [180.0, 200.0]
    assert data["portfolio_id"] == "p1"


def test_fetch_usd_ils_rate_uses_yahoo_quote(monkeypatch):
    from expense_tracker.integrations.yahoo import quotes as yf

    monkeypatch.setattr(
        yf,
        "_http_json",
        lambda url, timeout=20: {
            "quoteResponse": {"result": [{"regularMarketPrice": 3.701}]}
        },
    )
    assert yf.fetch_usd_ils_rate() == 3.701


def test_fetch_usd_ils_rate_on_date_uses_last_available_close(monkeypatch):
    from datetime import date, datetime, timezone

    from expense_tracker.integrations.yahoo import quotes as yf

    monkeypatch.setattr(
        yf,
        "_http_json",
        lambda url, timeout=20: {
            "chart": {
                "result": [
                    {
                        "timestamp": [
                            int(datetime(2026, 9, 6, tzinfo=timezone.utc).timestamp()),
                            int(datetime(2026, 9, 7, tzinfo=timezone.utc).timestamp()),
                        ],
                        "indicators": {"quote": [{"close": [3.1, 3.2]}]},
                    }
                ]
            }
        },
    )

    assert yf.fetch_usd_ils_rate_on_date(date(2026, 9, 8)) == 3.2


def test_investments_sectors_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        "expense_tracker.routes.investments.load_cache",
        lambda: {
            "portfolios": [
                {
                    "id": "p1",
                    "name": "One",
                    "holdings": [
                        {
                            "symbol": "AAPL",
                            "name": "Apple Inc.",
                            "quantity": 2,
                            "price": 100,
                            "market_value": 200,
                        },
                        {
                            "symbol": "QQQM",
                            "name": "Invesco NASDAQ 100 ETF",
                            "quantity": 1,
                            "price": 250,
                            "market_value": 250,
                        },
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        "expense_tracker.routes.investments.aggregate_sector_allocation",
        lambda portfolios, portfolio_id="all", lang="en": {
            "ok": True,
            "portfolio_id": portfolio_id,
            "total": 450.0,
            "sectors": [
                {
                    "id": "information_technology",
                    "label": "Information Technology",
                    "color": "#2563eb",
                    "value": 200.0,
                    "pct": 44.44,
                },
                {
                    "id": "etf_diversified",
                    "label": "ETF / Diversified",
                    "color": "#7c3aed",
                    "value": 250.0,
                    "pct": 55.56,
                },
            ],
            "catalog": [],
            "assignments": {"AAPL": "information_technology", "QQQM": "etf_diversified"},
            "unclassified": [],
        },
    )
    resp = client.get("/investments/sectors?portfolio=p1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["portfolio_id"] == "p1"
    assert len(data["sectors"]) == 2


def test_investments_page_sector_panel_markup(client, monkeypatch):
    monkeypatch.setattr("expense_tracker.routes.investments.is_connected", lambda: True)
    monkeypatch.setattr("expense_tracker.routes.investments.fetch_usd_ils_rate", lambda: 3.7)
    monkeypatch.setattr(
        "expense_tracker.routes.investments.load_cache",
        lambda: {
            "updated_at": "2026-08-22T12:00:00+00:00",
            "grand_total": 1500.5,
            "portfolios": [
                {
                    "id": "p_demo",
                    "name": "Demo Portfolio",
                    "total_value": 1500.5,
                    "holdings": [
                        {
                            "symbol": "AAPL",
                            "name": "Apple Inc.",
                            "quantity": 10,
                            "price": 150.05,
                            "change_pct": 1.25,
                            "market_value": 1500.5,
                        }
                    ],
                }
            ],
        },
    )

    html = client.get("/investments").get_data(as_text=True)
    assert 'id="sector-allocation-chart"' in html
    assert 'id="sector-unclassified"' in html
    assert "Sector allocation" in html or "חלוקה לפי סקטורים" in html
    assert 'data-sectors-url' in html
    assert 'aria-controls="sector-panel-body"' in html
    assert 'class="collapsible-panel-body hidden" id="sector-panel-body"' in html


def test_investments_refresh_classifies_with_api_key(client, monkeypatch):
    monkeypatch.setattr("expense_tracker.routes.investments.has_api_key", lambda: True)
    monkeypatch.setattr(
        "expense_tracker.routes.investments.fetch_portfolios",
        lambda: {
            "updated_at": "2026-08-22T12:00:00+00:00",
            "portfolios": [
                {
                    "id": "p1",
                    "name": "One",
                    "total_value": 100,
                    "holdings": [{"symbol": "AAPL", "name": "Apple Inc."}],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "expense_tracker.routes.investments.classify_portfolio_symbols",
        lambda portfolios: {"classified": 1, "unknown": 0, "skipped": 0},
    )
    resp = client.post("/investments/refresh", follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert "Classified 1 symbols" in html or "סווגו 1 סימולים" in html


def test_investments_refresh_skips_classification_without_key(client, monkeypatch):
    monkeypatch.setattr("expense_tracker.routes.investments.has_api_key", lambda: False)
    monkeypatch.setattr(
        "expense_tracker.routes.investments.fetch_portfolios",
        lambda: {
            "updated_at": "2026-08-22T12:00:00+00:00",
            "portfolios": [
                {
                    "id": "p1",
                    "name": "One",
                    "total_value": 100,
                    "holdings": [{"symbol": "AAPL", "name": "Apple Inc."}],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "expense_tracker.routes.investments.count_unassigned_symbols",
        lambda portfolios: 1,
    )
    resp = client.post("/investments/refresh", follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert "OpenAI API key" in html or "מפתח OpenAI" in html


def test_investments_refresh_classification_error(client, monkeypatch):
    monkeypatch.setattr("expense_tracker.routes.investments.has_api_key", lambda: True)
    monkeypatch.setattr(
        "expense_tracker.routes.investments.fetch_portfolios",
        lambda: {
            "updated_at": "2026-08-22T12:00:00+00:00",
            "portfolios": [{"id": "p1", "name": "One", "holdings": []}],
        },
    )

    def _boom(_portfolios):
        raise RuntimeError("GPT offline")

    monkeypatch.setattr(
        "expense_tracker.routes.investments.classify_portfolio_symbols",
        _boom,
    )
    resp = client.post("/investments/refresh", follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert "Sector classification failed" in html or "סיווג סקטורים נכשל" in html

