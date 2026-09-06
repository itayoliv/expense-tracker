"""Public Yahoo Finance quotes (no Playwright)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from expense_tracker.integrations.yahoo._common import USER_AGENT, _num


def _http_json(url: str, timeout: int = 20) -> dict[str, Any] | None:
    """Fetch JSON without Playwright (for live public quotes)."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _quote_from_yahoo_result(q: dict[str, Any]) -> dict[str, Any]:
    """Pick regular / pre / post price based on marketState."""
    state = str(q.get("marketState") or "CLOSED").upper()
    price = _num(q.get("regularMarketPrice"))
    change_pct = _num(q.get("regularMarketChangePercent"))
    session = "regular"

    if state in ("PRE", "PREPRE") and _num(q.get("preMarketPrice")):
        price = _num(q.get("preMarketPrice"))
        change_pct = _num(q.get("preMarketChangePercent"), change_pct)
        session = "pre"
    elif state in ("POST", "POSTPOST") and _num(q.get("postMarketPrice")):
        price = _num(q.get("postMarketPrice"))
        change_pct = _num(q.get("postMarketChangePercent"), change_pct)
        session = "post"

    return {
        "price": round(price, 4),
        "change_pct": round(change_pct, 4),
        "market_state": state,
        "session": session,
        "name": str(q.get("shortName") or q.get("longName") or ""),
    }


def fetch_usd_ils_rate() -> float:
    """ILS per 1 USD from Yahoo (USDILS=X). Returns 0 if unavailable."""
    data = _http_json(
        "https://query1.finance.yahoo.com/v7/finance/quote?symbols=USDILS%3DX"
    )
    try:
        q = data["quoteResponse"]["result"][0]  # type: ignore[index]
        rate = _num(q.get("regularMarketPrice"))
        if rate > 0:
            return round(rate, 4)
    except (TypeError, KeyError, IndexError):
        pass
    chart = _http_json(
        "https://query1.finance.yahoo.com/v8/finance/chart/USDILS=X?interval=1d&range=1d"
    )
    try:
        meta = chart["chart"]["result"][0]["meta"]  # type: ignore[index]
        rate = _num(meta.get("regularMarketPrice"))
        if rate > 0:
            return round(rate, 4)
    except (TypeError, KeyError, IndexError):
        pass
    return 0.0


def fetch_live_quotes(symbols: list[str]) -> dict[str, Any]:
    """Fetch live (or extended-hours) quotes for symbols. No Playwright required."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = str(raw or "").strip().upper()
        if not sym or sym in seen or sym == "CASH" or not sym[0].isalpha():
            continue
        seen.add(sym)
        cleaned.append(sym)

    quotes: dict[str, dict[str, Any]] = {}
    for i in range(0, len(cleaned), 25):
        chunk = cleaned[i : i + 25]
        joined = ",".join(chunk)
        data = _http_json(
            f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={joined}"
        )
        results = []
        if isinstance(data, dict):
            try:
                results = data["quoteResponse"]["result"] or []
            except (KeyError, TypeError):
                results = []
        found: set[str] = set()
        for q in results:
            if not isinstance(q, dict):
                continue
            sym = str(q.get("symbol") or "").upper()
            if not sym:
                continue
            quotes[sym] = _quote_from_yahoo_result(q)
            found.add(sym)
        for sym in chunk:
            if sym in found:
                continue
            chart = _http_json(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
            )
            try:
                meta = chart["chart"]["result"][0]["meta"]  # type: ignore[index]
                quotes[sym] = {
                    "price": round(_num(meta.get("regularMarketPrice")), 4),
                    "change_pct": 0.0,
                    "market_state": str(meta.get("marketState") or "CLOSED").upper(),
                    "session": "regular",
                    "name": sym,
                }
            except (TypeError, KeyError, IndexError):
                continue

    states = {q.get("market_state") for q in quotes.values()}
    live = bool(states & {"PRE", "PREPRE", "REGULAR", "POST", "POSTPOST"})
    return {
        "quotes": quotes,
        "live": live,
        "usd_ils": fetch_usd_ils_rate(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
