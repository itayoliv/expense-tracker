"""Playwright login/session for Yahoo Finance."""

from __future__ import annotations

import json
import time
from typing import Any

from expense_tracker.db import DATA_DIR
from expense_tracker.integrations.yahoo._common import USER_AGENT

PROFILE_DIR = DATA_DIR / "yahoo_profile"
STORAGE_PATH = DATA_DIR / "yahoo_storage.json"
CACHE_PATH = DATA_DIR / "yahoo_portfolios.json"
PORTFOLIOS_URL = "https://finance.yahoo.com/portfolios"


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
