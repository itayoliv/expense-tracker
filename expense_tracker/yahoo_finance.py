"""Yahoo Finance portfolio connect + fetch (Playwright persistent session).

Usage:
  python -m expense_tracker.yahoo_finance connect
  python -m expense_tracker.yahoo_finance fetch
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any

from expense_tracker.db import DATA_DIR

PROFILE_DIR = DATA_DIR / "yahoo_profile"
STORAGE_PATH = DATA_DIR / "yahoo_storage.json"
CACHE_PATH = DATA_DIR / "yahoo_portfolios.json"
PORTFOLIOS_URL = "https://finance.yahoo.com/portfolios"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class YahooFinanceError(Exception):
    """User-facing Yahoo Finance integration error."""


def is_connected() -> bool:
    """True when a saved login session exists."""
    return STORAGE_PATH.exists() and STORAGE_PATH.stat().st_size > 10


def load_cache() -> dict[str, Any] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_cache(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _launch_connect_context(playwright):
    """Headed persistent profile for one-time manual login."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for channel in ("msedge", "chrome"):
        try:
            return playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel=channel,
                headless=False,
                viewport={"width": 1400, "height": 900},
                locale="en-US",
                user_agent=USER_AGENT,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as exc:
            last_error = exc
            continue
    detail = str(last_error) if last_error else "unknown error"
    raise YahooFinanceError(
        "Could not open a browser for Yahoo Finance login. "
        "Install Microsoft Edge or Google Chrome, close other Yahoo browser windows, "
        f"then try again. ({detail[:180]})"
    ) from last_error


def _launch_fetch_session(playwright):
    """Headless browser using saved cookies — avoids locked profile directory."""
    if not is_connected():
        raise YahooFinanceError(
            "Yahoo Finance is not connected. Run connect_yahoo.bat once to log in."
        )
    last_error: Exception | None = None
    for channel in ("msedge", "chrome"):
        browser = None
        try:
            browser = playwright.chromium.launch(channel=channel, headless=True)
            context = browser.new_context(
                storage_state=str(STORAGE_PATH),
                viewport={"width": 1400, "height": 900},
                locale="en-US",
                user_agent=USER_AGENT,
            )
            return browser, context
        except Exception as exc:
            last_error = exc
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            continue
    detail = str(last_error) if last_error else "unknown error"
    raise YahooFinanceError(
        "Could not open a browser for Yahoo Finance. "
        "Install Microsoft Edge or Google Chrome, then try again. "
        f"({detail[:180]})"
    ) from last_error


def _looks_logged_in(page) -> bool:
    url = (page.url or "").lower()
    if "login" in url or "signin" in url or "challenge" in url:
        return False
    try:
        body = page.locator("body").inner_text(timeout=3000).lower()
        has_sign_in = ("sign in" in body) or ("log in" in body)
        has_create = "create portfolio" in body
        link_count = page.locator('a[href*="/portfolio/"]').count()
        # Personal Yahoo portfolios often use ids like p_…
        personal_link_count = page.locator('a[href*="/portfolio/p_"]').count()
        # Guest / marketing page always has Sign in (nav "My Portfolio" alone is NOT login).
        if has_sign_in:
            return False
        if has_create or personal_link_count > 0 or link_count > 0:
            return True
    except Exception:
        return False
    return False


def connect(timeout_seconds: int = 600) -> None:
    """Open a headed browser for manual Yahoo login; keep the persistent profile."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise YahooFinanceError(
            "Playwright is not installed. Run install.bat again."
        ) from exc

    print("Opening Yahoo Finance…")
    print("Log in in the browser window if needed.")
    print("Waiting until your portfolios page is available…")

    with sync_playwright() as p:
        context = _launch_connect_context(p)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(PORTFOLIOS_URL, wait_until="domcontentloaded", timeout=90_000)

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if _looks_logged_in(page):
                    # Give cookies a moment to settle
                    time.sleep(2)
                    DATA_DIR.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(STORAGE_PATH))
                    print("Login detected. Session saved.")
                    context.close()
                    return
            except Exception:
                pass
            time.sleep(1.5)

        context.close()
        raise YahooFinanceError(
            "Timed out waiting for login. Run connect_yahoo.bat again and finish signing in."
        )


def _get_crumb(page) -> str:
    for url in (
        "https://query1.finance.yahoo.com/v1/test/getcrumb",
        "https://query2.finance.yahoo.com/v1/test/getcrumb",
    ):
        try:
            result = page.evaluate(
                """async (url) => {
                    const res = await fetch(url, { credentials: 'include' });
                    if (!res.ok) return '';
                    return await res.text();
                }""",
                url,
            )
            crumb = (result or "").strip()
            if crumb and "<" not in crumb and len(crumb) < 80:
                return crumb
        except Exception:
            continue
    return ""


def _get_user_id(context, page) -> str:
    for cookie in context.cookies():
        name = cookie.get("name") or ""
        value = cookie.get("value") or ""
        if name in ("A1", "A3", "T", "Y") and value:
            # Sometimes GUID-like ids appear in page scripts
            pass
    # Prefer GUID from page / Redux bootstrap if present
    try:
        found = page.evaluate(
            """() => {
                const html = document.documentElement.innerHTML;
                const m = html.match(/"userId"\\s*:\\s*"([A-Z0-9]{10,})"/i)
                    || html.match(/userId=([A-Z0-9]{10,})/i);
                return m ? m[1] : '';
            }"""
        )
        if found:
            return str(found)
    except Exception:
        pass
    return ""


def _api_json(page, url: str) -> Any:
    return page.evaluate(
        """async (url) => {
            const res = await fetch(url, {
                credentials: 'include',
                headers: { 'Accept': 'application/json' }
            });
            const text = await res.text();
            if (!res.ok) {
                return { __error: true, status: res.status, body: text.slice(0, 500) };
            }
            try { return JSON.parse(text); }
            catch { return { __error: true, status: res.status, body: text.slice(0, 500) }; }
        }""",
        url,
    )


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("raw", "fmt", "value"):
            if key in value:
                return _num(value[key], default)
        return default
    text = str(value).strip().replace(",", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return default


def _valid_symbol(symbol: str) -> bool:
    """Reject junk scraped from dates / numbers (e.g. '0', '0.02')."""
    s = (symbol or "").strip().upper()
    if not s or s == "CASH":
        return False
    # Tickers are mostly letters; allow digits/.- but must start with a letter
    if not re.match(r"^[A-Z][A-Z0-9.\-]{0,14}$", s):
        return False
    return True


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

    # Position rows need shares and/or market value — skip bare quote ticks
    has_position = bool(
        row.get("quantity")
        or row.get("shares")
        or row.get("totalQuantity")
        or row.get("holdingQuantity")
        or row.get("qty")
        or row.get("marketValue")
        or row.get("totalValue")
        or row.get("positionValue")
        or row.get("market_value")
        or row.get("_from_dom")
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
    """Fix mixed-up qty/price and drop empty/invalid rows."""
    symbol = str(h.get("symbol") or "").upper()
    if not _valid_symbol(symbol):
        return None
    price = _num(h.get("price"))
    quantity = _num(h.get("quantity"))
    market_value = _num(h.get("market_value"))

    # Classic scrape bug: first numeric cell (last price) stored as quantity
    if price > 0 and quantity > 0 and abs(quantity - price) / price < 0.02:
        if market_value > price * 1.05:
            quantity = market_value / price
        else:
            # No trustworthy total — treat as unknown shares (watchlist quote)
            quantity = 0.0
            market_value = 0.0

    if quantity <= 0 and market_value > 0 and price > 0:
        quantity = market_value / price

    if quantity > 0 and price > 0:
        market_value = quantity * price

    if quantity <= 0 and market_value <= 0:
        return None

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

    def add_row(item: dict[str, Any]) -> None:
        h = _holding_from_row(item)
        if h and h["symbol"] not in seen:
            seen.add(h["symbol"])
            holdings.append(h)

    def walk(node: Any, from_positions: bool = False) -> None:
        if isinstance(node, list):
            for item in node:
                if isinstance(item, dict):
                    if from_positions:
                        add_row(item)
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
                        add_row(item)
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
            if "portfolio" not in req_url and "holding" not in req_url and "position" not in req_url:
                return
            ctype = (response.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                return
            captured.append(response.json())
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

    for payload in captured:
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

                    // Skip quote-only rows with no shares/value signals at all
                    if (!quantity && !market_value && idx.shares < 0 && idx.value < 0 && !field('quantity')) {
                        continue;
                    }
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
        if h.get("quantity") and h.get("price"):
            h["market_value"] = round(h["quantity"] * h["price"], 2)


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


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    cmd = (args[0] if args else "").strip().lower()
    try:
        if cmd == "connect":
            connect()
            return 0
        if cmd == "fetch":
            data = fetch_portfolios()
            print(
                f"Fetched {len(data.get('portfolios', []))} portfolios "
                f"(total {data.get('grand_total', 0)})."
            )
            print(f"Cache: {CACHE_PATH}")
            return 0
        print("Usage: python -m expense_tracker.yahoo_finance [connect|fetch]")
        return 2
    except YahooFinanceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
