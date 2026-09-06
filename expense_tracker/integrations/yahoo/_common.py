"""Shared helpers for Yahoo Finance submodules."""

from __future__ import annotations

import re
from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
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
