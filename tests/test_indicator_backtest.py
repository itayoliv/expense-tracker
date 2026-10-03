"""Indicator catalog and long-only backtest."""

from __future__ import annotations

from datetime import date, timedelta

from expense_tracker.integrations.yahoo.history import tradingview_symbol
from expense_tracker.services.indicator_backtest import (
    catalog_for_lang,
    run_backtest,
)


def _candle(day: date, close: float, high: float | None = None, low: float | None = None) -> dict:
    return {
        "date": day,
        "open": close,
        "high": high if high is not None else close,
        "low": low if low is not None else close,
        "close": close,
        "volume": 1000,
    }


def test_catalog_includes_explanations_in_both_languages():
    en = catalog_for_lang("en")
    he = catalog_for_lang("he")
    ids = {item["id"] for item in en}
    assert "rsi_14" in ids
    assert "macd" in ids
    assert "sma_50_200" in ids
    assert all(item["explanation"] for item in en)
    assert all(item["explanation"] for item in he)
    assert en[0]["tv_studies"]


def test_sma_crossover_records_buy_then_sell_and_profit():
    start = date(2026, 1, 1)
    candles = []
    # 50 low closes, then 30 high closes so SMA 20 crosses above SMA 50, then drop.
    for i in range(50):
        candles.append(_candle(start + timedelta(days=i), 10))
    for i in range(30):
        candles.append(_candle(start + timedelta(days=50 + i), 20))
    for i in range(30):
        candles.append(_candle(start + timedelta(days=80 + i), 5))

    result = run_backtest(candles, "sma_20_50", start, 1000)
    assert result["buy_count"] >= 1
    assert result["sell_count"] >= 1
    assert result["trades"][0]["side"] == "buy"
    assert result["pnl"] < 0
    assert result["starting_capital"] == 1000


def test_no_trades_before_start_date():
    start = date(2026, 3, 1)
    candles = [_candle(date(2026, 1, 1) + timedelta(days=i), 10 + (i % 3)) for i in range(80)]
    result = run_backtest(candles, "sma_20_50", start, 1000)
    for trade in result["trades"]:
        assert trade["date"] >= start.isoformat()


def test_tradingview_symbol_maps_tase_and_nasdaq():
    assert tradingview_symbol("TEVA.TA") == "TASE:TEVA"
    assert tradingview_symbol("AAPL", "NMS") == "NASDAQ:AAPL"
    assert tradingview_symbol("IBM", "NYQ") == "NYSE:IBM"


def test_indicators_endpoint_lists_catalog(client):
    data = client.get("/investments/indicators").get_json()
    assert data["ok"] is True
    assert len(data["indicators"]) >= 5
    assert data["indicators"][0]["name"]
    assert data["indicators"][0]["explanation"]


def test_backtest_endpoint_uses_fetched_history(client, monkeypatch):
    start = date(2026, 1, 1)
    candles = [_candle(start + timedelta(days=i), 10 if i < 50 else 20) for i in range(80)]

    monkeypatch.setattr(
        "expense_tracker.routes.investments.fetch_daily_ohlc",
        lambda symbol, start_date: {
            "symbol": symbol,
            "tv_symbol": "NASDAQ:AAPL",
            "candles": candles,
        },
    )
    resp = client.post(
        "/investments/indicator-backtest",
        json={
            "symbol": "AAPL",
            "indicator_id": "sma_20_50",
            "start_date": "2026-01-01",
            "capital": 1000,
        },
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["tv_symbol"] == "NASDAQ:AAPL"
    assert data["buy_count"] >= 1
    assert "tv_studies" in data


def test_backtest_endpoint_rejects_unknown_indicator(client):
    resp = client.post(
        "/investments/indicator-backtest",
        json={"symbol": "AAPL", "indicator_id": "magic", "start_date": "2026-01-01"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_investments_page_includes_indicator_panel(client, monkeypatch):
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
    assert 'id="indicator-backtest"' in html
    assert 'id="tv-chart"' in html
