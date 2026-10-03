"""Holdings value history from Yahoo chart data."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import quote

from expense_tracker.integrations.yahoo._common import _num, _valid_symbol
from expense_tracker.integrations.yahoo.quotes import _http_json

_HISTORY_RANGES: dict[str, tuple[str, str]] = {
    "1d": ("5m", "1d"),
    "5d": ("15m", "5d"),
    "1mo": ("1d", "1mo"),
    "6mo": ("1d", "6mo"),
    "ytd": ("1d", "ytd"),
    "1y": ("1d", "1y"),
}


def _chart_closes(symbol: str, interval: str, range_key: str) -> list[tuple[int, float]]:
    """Return [(unix_ts, close), ...] for a symbol."""
    data = _http_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval={interval}&range={range_key}"
    )
    try:
        result = data["chart"]["result"][0]  # type: ignore[index]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators") or {}).get("quote") or [{}]
        closes = (quote[0] or {}).get("close") or []
        adj = ((result.get("indicators") or {}).get("adjclose") or [{}])
        adj_closes = (adj[0] or {}).get("adjclose") if adj else None
        series: list[tuple[int, float]] = []
        for i, ts in enumerate(timestamps):
            price = None
            if adj_closes and i < len(adj_closes) and adj_closes[i] is not None:
                price = float(adj_closes[i])
            elif i < len(closes) and closes[i] is not None:
                price = float(closes[i])
            if price is None or price <= 0:
                continue
            series.append((int(ts), price))
        return series
    except (TypeError, KeyError, IndexError, ValueError):
        return []


def build_holdings_history(
    portfolios: list[dict[str, Any]],
    portfolio_id: str = "all",
    range_key: str = "6mo",
) -> dict[str, Any]:
    """
    Reconstruct holdings value over time: current share counts × historical prices.
    portfolio_id='all' sums every portfolio; otherwise one portfolio id.
    """
    range_key = (range_key or "6mo").lower()
    if range_key not in _HISTORY_RANGES:
        range_key = "6mo"
    interval, yahoo_range = _HISTORY_RANGES[range_key]

    selected = portfolios
    if portfolio_id and portfolio_id != "all":
        selected = [p for p in portfolios if str(p.get("id")) == str(portfolio_id)]

    qty_by_sym: dict[str, float] = {}
    for pf in selected:
        for h in pf.get("holdings") or []:
            sym = str(h.get("symbol") or "").strip().upper()
            if not _valid_symbol(sym):
                continue
            qty_by_sym[sym] = qty_by_sym.get(sym, 0.0) + _num(h.get("quantity"))

    positions = [(s, q) for s, q in qty_by_sym.items() if q > 0]
    if not positions:
        return {
            "ok": True,
            "range": range_key,
            "portfolio_id": portfolio_id or "all",
            "labels": [],
            "values": [],
            "current_total": 0.0,
        }

    from concurrent.futures import ThreadPoolExecutor, as_completed

    series_by_sym: dict[str, list[tuple[int, float]]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_chart_closes, sym, interval, yahoo_range): sym for sym, _ in positions
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                series_by_sym[sym] = fut.result()
            except Exception:
                series_by_sym[sym] = []

    all_ts: set[int] = set()
    for series in series_by_sym.values():
        all_ts.update(ts for ts, _ in series)
    timestamps = sorted(all_ts)
    if not timestamps:
        current = round(sum(_num(h.get("market_value")) for pf in selected for h in (pf.get("holdings") or [])), 2)
        return {
            "ok": True,
            "range": range_key,
            "portfolio_id": portfolio_id or "all",
            "labels": [],
            "values": [],
            "current_total": current,
        }

    # Pointers for forward-fill
    idxs = {sym: 0 for sym, _ in positions}
    last_price = {sym: None for sym, _ in positions}
    values: list[float] = []
    labels: list[str] = []

    for ts in timestamps:
        total = 0.0
        for sym, qty in positions:
            series = series_by_sym.get(sym) or []
            i = idxs[sym]
            while i < len(series) and series[i][0] <= ts:
                last_price[sym] = series[i][1]
                i += 1
            idxs[sym] = i
            px = last_price[sym]
            if px:
                total += qty * px
        if total <= 0:
            continue
        values.append(round(total, 2))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        if range_key == "1d":
            labels.append(dt.strftime("%H:%M"))
        elif range_key == "5d":
            labels.append(dt.strftime("%a %H:%M"))
        else:
            labels.append(dt.strftime("%Y-%m-%d"))

    current_total = values[-1] if values else 0.0
    return {
        "ok": True,
        "range": range_key,
        "portfolio_id": portfolio_id or "all",
        "labels": labels,
        "values": values,
        "current_total": current_total,
    }


_TV_EXCHANGE = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NAS": "NASDAQ",
    "NYQ": "NYSE",
    "NYE": "NYSE",
    "NYS": "NYSE",
    "PCX": "AMEX",
    "ASE": "AMEX",
    "TAE": "TASE",
    "TLV": "TASE",
}


def tradingview_symbol(yahoo_symbol: str, exchange: str = "") -> str:
    """Map a Yahoo ticker to a TradingView symbol when the exchange is known."""
    raw = (yahoo_symbol or "").strip().upper()
    if raw.endswith(".TA"):
        return f"TASE:{raw[:-3]}"
    code = _TV_EXCHANGE.get((exchange or "").strip().upper(), "")
    if code:
        return f"{code}:{raw}"
    return raw


def fetch_daily_ohlc(
    symbol: str, start: date, end: date | None = None, *, lookback_days: int = 450
) -> dict[str, Any]:
    """Daily OHLC from Yahoo, including extra history so indicators can warm up."""
    sym = (symbol or "").strip().upper()
    if not _valid_symbol(sym):
        raise ValueError("Invalid symbol")
    today = date.today()
    last = min(end or today, today)
    first = start - timedelta(days=lookback_days)
    period1 = int(datetime.combine(first, time.min, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(last + timedelta(days=1), time.min, tzinfo=timezone.utc).timestamp())
    encoded = quote(sym, safe=".")
    data = _http_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        f"?interval=1d&period1={period1}&period2={period2}&events=history"
    )
    try:
        result = data["chart"]["result"][0]  # type: ignore[index]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators") or {}).get("quote") or [{}]
        q0 = quote[0] or {}
        opens = q0.get("open") or []
        highs = q0.get("high") or []
        lows = q0.get("low") or []
        closes = q0.get("close") or []
        volumes = q0.get("volume") or []
        adj = ((result.get("indicators") or {}).get("adjclose") or [{}])
        adj_closes = (adj[0] or {}).get("adjclose") if adj else None
        meta = result.get("meta") or {}
        exchange = str(meta.get("exchangeName") or meta.get("fullExchangeName") or "")
        candles: list[dict[str, Any]] = []
        for i, ts in enumerate(timestamps):
            close = None
            if adj_closes and i < len(adj_closes) and adj_closes[i] is not None:
                close = float(adj_closes[i])
            elif i < len(closes) and closes[i] is not None:
                close = float(closes[i])
            if close is None or close <= 0:
                continue
            high = float(highs[i]) if i < len(highs) and highs[i] is not None else close
            low = float(lows[i]) if i < len(lows) and lows[i] is not None else close
            open_px = float(opens[i]) if i < len(opens) and opens[i] is not None else close
            volume = float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0.0
            day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
            candles.append(
                {
                    "date": day,
                    "open": open_px,
                    "high": max(high, close, open_px),
                    "low": min(low, close, open_px),
                    "close": close,
                    "volume": volume,
                }
            )
        return {
            "symbol": str(meta.get("symbol") or sym).upper(),
            "exchange": exchange,
            "tv_symbol": tradingview_symbol(sym, exchange),
            "candles": candles,
        }
    except (TypeError, KeyError, IndexError, ValueError, AttributeError):
        return {"symbol": sym, "exchange": "", "tv_symbol": tradingview_symbol(sym), "candles": []}
