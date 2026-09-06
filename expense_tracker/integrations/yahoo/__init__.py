"""Yahoo Finance portfolio connect + fetch.

Usage:
  python -m expense_tracker.integrations.yahoo connect
  python -m expense_tracker.integrations.yahoo fetch
"""

from expense_tracker.integrations.yahoo.history import build_holdings_history
from expense_tracker.integrations.yahoo.portfolios import fetch_portfolios
from expense_tracker.integrations.yahoo.quotes import fetch_live_quotes, fetch_usd_ils_rate
from expense_tracker.integrations.yahoo.session import (
    YahooFinanceError,
    connect,
    is_connected,
    load_cache,
    save_cache,
)

__all__ = [
    "YahooFinanceError",
    "is_connected",
    "load_cache",
    "save_cache",
    "connect",
    "fetch_portfolios",
    "fetch_live_quotes",
    "fetch_usd_ils_rate",
    "build_holdings_history",
]
