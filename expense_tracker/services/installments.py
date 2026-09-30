"""Card payment-plan lines (תשלום X מתוך Y): detection and per-slice dates."""

from __future__ import annotations

import calendar
import re
from datetime import date

_INSTALLMENT_RE = re.compile(
    r"(תשלום\s*\d+\s*מתוך\s*\d+)|(\binstallment\b)|(\bpayment\s*\d+\s*of\s*\d+)",
    re.IGNORECASE,
)

_INSTALLMENT_INDEX_RE = re.compile(
    r"תשלום\s*(\d+)\s*מתוך\s*(\d+)|\bpayment\s*(\d+)\s*of\s*(\d+)",
    re.IGNORECASE,
)


def is_installment_details(text: str | None) -> bool:
    """True for card payment-plan lines (e.g. תשלום 7 מתוך 12)."""
    return bool(_INSTALLMENT_RE.search(text or ""))


def is_installment(txn) -> bool:
    if isinstance(txn, dict):
        return is_installment_details(txn.get("details")) or is_installment_details(
            txn.get("description")
        )
    return is_installment_details(getattr(txn, "details", None)) or is_installment_details(
        getattr(txn, "description", None)
    )


def parse_installment(text: str | None) -> tuple[int, int] | None:
    """Return (payment number, total payments) from e.g. 'תשלום 3 מתוך 24'."""
    match = _INSTALLMENT_INDEX_RE.search(text or "")
    if not match:
        return None
    index, total = (g for g in match.groups() if g is not None)
    return int(index), int(total)


def add_months(start: date, months: int) -> date:
    """Shift by whole months, clamping the day to the end of the target month."""
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def installment_date_for(
    txn_date: date | None, details: str | None, description: str | None = None
) -> date | None:
    """Purchase date shifted by (payment number - 1) months; None if not a numbered slice."""
    if txn_date is None:
        return None
    parsed = parse_installment(details) or parse_installment(description)
    if not parsed or parsed[0] < 1:
        return None
    return add_months(txn_date, parsed[0] - 1)
