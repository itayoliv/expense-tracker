"""Yahoo Finance portfolio listing and holdings fetch."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from expense_tracker.integrations.yahoo._common import _num, _valid_symbol
from expense_tracker.integrations.yahoo.session import (
    PORTFOLIOS_URL,
    YahooFinanceError,
    _api_json,
    _get_crumb,
    _get_user_id,
    _launch_fetch_session,
    _looks_logged_in,
    is_connected,
    save_cache,
)


def _holding_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    symbol = row.get("symbol") or row.get("ticker")
    quote_type = row.get("quoteType")
    if not symbol and isinstance(quote_type, dict):
        symbol = quote_type.get("symbol")
    quote = row.get("quote")
    if not symbol and isinstance(quote, dict):
        symbol = quote.get("symbol")
    if not symbol:
        return None
    symbol = str(symbol).strip().upper()
    # Strip quote suffix noise like "QQQM\nInvesco..."
    if "\n" in symbol:
        symbol = symbol.split("\n", 1)[0].strip()
    if not _valid_symbol(symbol):
        return None

    name = row.get("shortName") or row.get("longName") or row.get("name")
    if not name and isinstance(quote, dict):
        name = quote.get("shortName") or quote.get("longName")
    name = str(name or symbol).split("\n", 1)[0].strip()

    quantity = _num(
        row.get("quantity")
        or row.get("shares")
        or row.get("totalQuantity")
        or row.get("holdingQuantity")
        or row.get("qty")
    )
    price = _num(
        row.get("regularMarketPrice")
        or row.get("lastPrice")
        or row.get("price")
        or row.get("currentPrice")
        or row.get("last")
    )
    if not price and isinstance(quote, dict):
        price = _num(quote.get("regularMarketPrice"))
    change_pct = _num(
        row.get("regularMarketChangePercent")
        or row.get("dayChangePercent")
        or row.get("changePercent")
        or row.get("chg_pct")
    )
    if not change_pct and isinstance(quote, dict):
        change_pct = _num(quote.get("regularMarketChangePercent"))
    market_value = _num(
        row.get("marketValue")
        or row.get("totalValue")
        or row.get("positionValue")
        or row.get("market_value")
    )

    # Position / securities rows: keep even when quantity is explicitly 0 (watchlists).
    qty_keys = ("quantity", "shares", "totalQuantity", "holdingQuantity", "qty")
    value_keys = ("marketValue", "totalValue", "positionValue", "market_value")
    has_position = (
        any(k in row for k in qty_keys)
        or any(row.get(k) not in (None, "") for k in value_keys)
        or bool(row.get("_from_dom"))
        or bool(row.get("_from_securities"))
    )
    if not has_position:
        return None

    holding = {
        "symbol": symbol,
        "name": name,
        "quantity": quantity,
        "price": price,
        "change_pct": change_pct,
        "market_value": market_value,
    }
    return _normalize_holding(holding)


def _normalize_holding(h: dict[str, Any]) -> dict[str, Any] | None:
    """Fix mixed-up qty/price; keep zero-share watchlist symbols."""
    symbol = str(h.get("symbol") or "").upper()
    if not _valid_symbol(symbol):
        return None
    price = _num(h.get("price"))
    quantity = _num(h.get("quantity"))
    market_value = _num(h.get("market_value"))
    scrape_ambiguous = False

    # Classic scrape bug: first numeric cell (last price) stored as quantity
    if price > 0 and quantity > 0 and abs(quantity - price) / price < 0.02:
        if market_value > price * 1.05:
            quantity = market_value / price
        else:
            # No trustworthy total — treat as ambiguous scrape, not a watchlist
            scrape_ambiguous = True
            quantity = 0.0
            market_value = 0.0

    if quantity <= 0 and market_value > 0 and price > 0:
        quantity = market_value / price

    if quantity > 0 and price > 0:
        market_value = quantity * price

    if quantity <= 0 and market_value <= 0:
        if scrape_ambiguous:
            return None
        # Watchlist / zero-share symbol — keep for display + buy planner
        return {
            "symbol": symbol,
            "name": str(h.get("name") or symbol),
            "quantity": 0.0,
            "price": round(price, 4),
            "change_pct": round(_num(h.get("change_pct")), 4),
            "market_value": 0.0,
        }

    return {
        "symbol": symbol,
        "name": str(h.get("name") or symbol),
        "quantity": round(quantity, 6),
        "price": round(price, 4),
        "change_pct": round(_num(h.get("change_pct")), 4),
        "market_value": round(market_value, 2),
    }


def _extract_holdings_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Extract positions only — never treat bare quote ticks as holdings."""
    holdings: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_row(item: dict[str, Any], *, allow_zero: bool = False) -> None:
        payload = dict(item)
        if allow_zero:
            payload["_from_securities"] = True
        h = _holding_from_row(payload)
        if h and h["symbol"] not in seen:
            seen.add(h["symbol"])
            holdings.append(h)

    def walk(node: Any, from_positions: bool = False) -> None:
        if isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    if from_positions:
                        add_row(item, allow_zero=True)
                    else:
                        walk(item, False)
            return
        if not isinstance(node, dict):
            return
        # Real portfolio payloads put lots under these keys (not "quotes")
        for key in ("positions", "holdings", "securities", "rows"):
            items = node.get(key)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        add_row(item, allow_zero=True)
        for key, value in node.items():
            if key in ("quoteResponse", "quotes", "spark", "chart"):
                continue
            if isinstance(value, (dict, list)):
                walk(value, from_positions=(key in ("positions", "holdings", "securities")))

    walk(payload)
    return holdings


def _list_portfolios_api(page, crumb: str, user_id: str) -> list[dict[str, str]]:
    portfolios: list[dict[str, str]] = []
    urls = []
    if crumb and user_id:
        urls.append(
            "https://query1.finance.yahoo.com/v7/finance/desktop/portfolio"
            f"?formatted=true&crumb={crumb}&lang=en-US&region=US"
            f"&userId={user_id}&corsDomain=finance.yahoo.com"
        )
        urls.append(
            "https://query2.finance.yahoo.com/v7/finance/desktop/portfolio"
            f"?formatted=true&crumb={crumb}&lang=en-US&region=US"
            f"&userId={user_id}&corsDomain=finance.yahoo.com"
        )
    for url in urls:
        data = _api_json(page, url)
        if not isinstance(data, dict) or data.get("__error"):
            continue
        try:
            items = data["finance"]["result"][0]["portfolios"]
        except (KeyError, IndexError, TypeError):
            items = []
        for item in items or []:
            pf_id = str(item.get("pfId") or item.get("portfolioId") or "").strip()
            name = str(item.get("pfName") or item.get("name") or pf_id).strip()
            if pf_id:
                portfolios.append({"id": pf_id, "name": name or pf_id})
        if portfolios:
            break
    return portfolios


def _list_portfolios_dom(page) -> list[dict[str, str]]:
    page.goto(PORTFOLIOS_URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(2500)
    rows = page.evaluate(
        """() => {
            const out = [];
            const seen = new Set();
            for (const a of document.querySelectorAll('a[href*="/portfolio/"]')) {
                const href = a.getAttribute('href') || '';
                const m = href.match(/\\/portfolio\\/([^\\/?#]+)/);
                if (!m) continue;
                const id = decodeURIComponent(m[1]);
                if (!id || seen.has(id)) continue;
                seen.add(id);
                const name = (a.textContent || '').trim() || id;
                out.push({ id, name });
            }
            return out;
        }"""
    )
    return [{"id": r["id"], "name": r["name"]} for r in (rows or [])]


def _fetch_holdings_api(page, pf_id: str, crumb: str) -> list[dict[str, Any]]:
    candidates = [
        f"https://query1.finance.yahoo.com/ws/portfolio-api/v1/portfolio/{pf_id}/positions?lang=en-US&region=US",
        f"https://query2.finance.yahoo.com/ws/portfolio-api/v1/portfolio/{pf_id}/positions?lang=en-US&region=US",
        f"https://query1.finance.yahoo.com/ws/portfolio-api/v1/portfolio/holdings?pfId={pf_id}&lang=en-US&region=US",
        f"https://query2.finance.yahoo.com/ws/portfolio-api/v1/portfolio/holdings?pfId={pf_id}&lang=en-US&region=US",
        (
            "https://query1.finance.yahoo.com/v7/finance/portfolio"
            f"?formatted=true&crumb={crumb}&lang=en-US&region=US&pfId={pf_id}"
            "&corsDomain=finance.yahoo.com"
            if crumb
            else ""
        ),
    ]
    for url in candidates:
        if not url:
            continue
        data = _api_json(page, url)
        if not isinstance(data, dict) or data.get("__error"):
            continue
        holdings = _extract_holdings_from_payload(data)
        if holdings:
            return holdings
    return []


def _fetch_holdings_dom(page, pf_id: str) -> list[dict[str, Any]]:
    url = f"https://finance.yahoo.com/portfolio/{pf_id}/view/v1"
    captured: list[Any] = []

    def on_response(response):
        try:
            req_url = response.url.lower()
            if (
                "portfolio" not in req_url
                and "holding" not in req_url
                and "position" not in req_url
                and "watchlist" not in req_url
            ):
                return
            ctype = (response.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                return
            captured.append({"url": response.url[:200], "body": response.json()})
        except Exception:
            return

    page.on("response", on_response)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(3500)
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass

    for item in captured:
        payload = item.get("body") if isinstance(item, dict) else item
        holdings = _extract_holdings_from_payload(payload)
        if holdings:
            return holdings

    # DOM table fallback — prefer data-field attrs, else map by header
    rows = page.evaluate(
        """() => {
            const out = [];
            const norm = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const headers = [...table.querySelectorAll('thead th, thead td')]
                    .map(th => norm(th.innerText || th.textContent));
                const idx = {
                    shares: headers.findIndex(h => /^(shares|qty|quantity|units)$/.test(h) || h.includes('share')),
                    price: headers.findIndex(h => /^(last|price|last price|last close)$/.test(h) || h.includes('last price') || h === 'last'),
                    chgPct: headers.findIndex(h => h.includes('chg %') || h.includes('change %') || h.includes('% chg') || h === '% change'),
                    value: headers.findIndex(h => h.includes('market value') || h.includes('total value') || h === 'value' || h.includes('mkt value')),
                };

                for (const tr of table.querySelectorAll('tbody tr')) {
                    const symbolLink = tr.querySelector('a[href*="/quote/"]');
                    if (!symbolLink && !tr.querySelector('[data-field="symbol"]')) continue;

                    let symbol = '';
                    if (symbolLink) {
                        const href = symbolLink.getAttribute('href') || '';
                        const m = href.match(/\\/quote\\/([^\\/?#]+)/);
                        symbol = m ? decodeURIComponent(m[1]) : (symbolLink.textContent || '').trim();
                    }
                    const cells = [...tr.querySelectorAll('td')];
                    const cellText = cells.map(td => (td.innerText || '').trim());
                    const field = (name) => {
                        const el = tr.querySelector(`[data-field="${name}"]`);
                        return el ? (el.innerText || el.textContent || '').trim() : '';
                    };
                    if (!symbol) symbol = (field('symbol') || cellText[0] || '').split('\\n')[0].trim();
                    if (!symbol) continue;

                    const name = (symbolLink ? (symbolLink.textContent || symbol) : symbol).split('\\n')[0].trim();
                    const cellNum = (i) => {
                        if (i < 0 || i >= cellText.length) return '';
                        return (cellText[i] || '').replace(/,/g, '').replace(/[^0-9.\\-%]/g, '');
                    };
                    const clean = (s) => (s || '').replace(/,/g, '').replace(/[^0-9.\\-%]/g, '');

                    let quantity = clean(field('quantity') || field('shares') || field('qty'));
                    let price = clean(field('lastPrice') || field('regularMarketPrice') || field('price'));
                    let change_pct = clean(field('regularMarketChangePercent') || field('percentChange') || field('chg'));
                    let market_value = clean(field('totalFairValue') || field('marketValue') || field('totalValue'));

                    if (!quantity && idx.shares >= 0) quantity = cellNum(idx.shares);
                    if (!price && idx.price >= 0) price = cellNum(idx.price);
                    if (!change_pct && idx.chgPct >= 0) change_pct = cellNum(idx.chgPct);
                    if (!market_value && idx.value >= 0) market_value = cellNum(idx.value);

                    // Keep quote/watchlist rows that have a real symbol link even with 0 shares
                    if (change_pct.includes('%')) change_pct = change_pct.replace('%', '');

                    out.push({
                        symbol,
                        name,
                        quantity: quantity || '0',
                        price: price || '0',
                        change_pct: change_pct || '0',
                        market_value: market_value || '0',
                        _from_dom: true,
                    });
                }
            }
            return out;
        }"""
    )
    holdings: list[dict[str, Any]] = []
    for row in rows or []:
        h = _holding_from_row(row)
        if h:
            holdings.append(h)
    return holdings


def _enrich_quotes(page, holdings: list[dict[str, Any]]) -> None:
    symbols = [h["symbol"] for h in holdings if h.get("symbol") and h["symbol"] != "CASH"]
    if not symbols:
        return
    # Batch in chunks of 25
    quotes: dict[str, dict[str, float]] = {}
    for i in range(0, len(symbols), 25):
        chunk = symbols[i : i + 25]
        joined = ",".join(chunk)
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={joined}"
        data = _api_json(page, url)
        if isinstance(data, dict) and not data.get("__error"):
            try:
                results = data["quoteResponse"]["result"] or []
            except (KeyError, TypeError):
                results = []
            for q in results:
                sym = str(q.get("symbol") or "").upper()
                if not sym:
                    continue
                quotes[sym] = {
                    "price": _num(q.get("regularMarketPrice")),
                    "change_pct": _num(q.get("regularMarketChangePercent")),
                    "name": str(q.get("shortName") or q.get("longName") or sym),
                }
        else:
            # chart fallback per symbol (no crumb)
            for sym in chunk:
                chart = _api_json(
                    page,
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d",
                )
                try:
                    meta = chart["chart"]["result"][0]["meta"]
                    quotes[sym] = {
                        "price": _num(meta.get("regularMarketPrice")),
                        "change_pct": 0.0,
                        "name": sym,
                    }
                except (KeyError, TypeError, IndexError):
                    continue

    for h in holdings:
        q = quotes.get(h["symbol"])
        if not q:
            continue
        old_price = _num(h.get("price"))
        qty = _num(h.get("quantity"))
        mv = _num(h.get("market_value"))
        # If qty was accidentally equal to the old scraped "price", recover from market value
        if old_price > 0 and qty > 0 and abs(qty - old_price) / old_price < 0.02 and mv > old_price * 1.05:
            qty = mv / old_price
            h["quantity"] = round(qty, 6)
        if q["price"]:
            h["price"] = round(q["price"], 4)
        if q.get("change_pct") is not None:
            h["change_pct"] = round(q["change_pct"], 4)
        if q.get("name") and (not h.get("name") or h["name"] == h["symbol"]):
            h["name"] = q["name"]
        if qty > 0 and h.get("price"):
            h["market_value"] = round(qty * h["price"], 2)
        elif qty <= 0:
            h["market_value"] = 0.0


def fetch_portfolios() -> dict[str, Any]:
    """Fetch all Yahoo portfolios using the saved session; write cache JSON."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise YahooFinanceError(
            "Playwright is not installed. Run install.bat again."
        ) from exc

    if not is_connected():
        raise YahooFinanceError(
            "Yahoo Finance is not connected. Run connect_yahoo.bat once to log in."
        )

    with sync_playwright() as p:
        browser, context = _launch_fetch_session(p)
        page = context.new_page()
        try:
            page.goto(PORTFOLIOS_URL, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(2000)
            logged_in = _looks_logged_in(page)
            if not logged_in:
                raise YahooFinanceError(
                    "Yahoo session expired or not logged in. Run connect_yahoo.bat again."
                )

            crumb = _get_crumb(page)
            user_id = _get_user_id(context, page)
            portfolios_meta = _list_portfolios_api(page, crumb, user_id)
            if not portfolios_meta:
                portfolios_meta = _list_portfolios_dom(page)
            if not portfolios_meta:
                raise YahooFinanceError(
                    "No portfolios found on your Yahoo account "
                    "(or the page layout changed). Check finance.yahoo.com/portfolios."
                )

            portfolios_out: list[dict[str, Any]] = []
            for meta in portfolios_meta:
                pf_id = meta["id"]
                name = meta["name"]
                holdings = _fetch_holdings_api(page, pf_id, crumb)
                if not holdings:
                    holdings = _fetch_holdings_dom(page, pf_id)
                _enrich_quotes(page, holdings)
                total = round(sum(h.get("market_value", 0) or 0 for h in holdings), 2)
                portfolios_out.append(
                    {
                        "id": pf_id,
                        "name": name,
                        "total_value": total,
                        "holdings": holdings,
                    }
                )

            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "portfolios": portfolios_out,
                "grand_total": round(
                    sum(p["total_value"] for p in portfolios_out), 2
                ),
            }
            save_cache(payload)
            return payload
        finally:
            context.close()
            browser.close()
