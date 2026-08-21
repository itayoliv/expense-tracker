"""Shared date parsing for manual transactions."""

from __future__ import annotations

from datetime import date, datetime


def parse_txn_date(raw: str | None) -> date:
    """Parse ISO (YYYY-MM-DD) or DD/MM/YY / DD/MM/YYYY into a date."""
    text = (raw or "").strip() or date.today().isoformat()
    if "/" in text:
        try:
            return datetime.strptime(text, "%d/%m/%y").date()
        except ValueError:
            return datetime.strptime(text, "%d/%m/%Y").date()
    return date.fromisoformat(text)
