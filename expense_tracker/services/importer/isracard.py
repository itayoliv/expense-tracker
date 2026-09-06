"""Isracard credit-card statement parsing."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd

from expense_tracker.services.importer.common import (
    _cell_str,
    _normalize_header,
    _parse_amount,
    excel_serial_to_date,
)

HEBREW_MONTHS = {
    "ינואר": 1,
    "פברואר": 2,
    "מרץ": 3,
    "אפריל": 4,
    "מאי": 5,
    "יוני": 6,
    "יולי": 7,
    "אוגוסט": 8,
    "ספטמבר": 9,
    "אוקטובר": 10,
    "נובמבר": 11,
    "דצמבר": 12,
}

# Isracard / credit-card column aliases -> canonical field
CC_HEADER_MAP = {
    "תאריך רכישה": "txn_date",
    "שם בית עסק": "description",
    "סכום עסקה": "txn_amount",
    "מטבע עסקה": "txn_currency",
    "סכום חיוב": "charge_amount",
    "מטבע חיוב": "charge_currency",
    "מס' שובר": "reference",
    "מס׳ שובר": "reference",
    'מס" שובר': "reference",
    "פירוט נוסף": "details",
    "חיוב בחשבון הבנק": "value_date",
}


def _extract_card_last4(raw: pd.DataFrame) -> str:
    """Pull last 4 digits from card header like 'קורפוריט - זהב - 0423'."""
    for i in range(min(12, len(raw))):
        for v in raw.iloc[i].tolist():
            text = _cell_str(v)
            if not text:
                continue
            # Prefer trailing - 0423 pattern
            m = re.search(r"[-–]\s*(\d{4})\s*$", text)
            if m:
                return m.group(1)
            if "קורפוריט" in text or "כרטיס" in text or "זהב" in text:
                m = re.search(r"(\d{4})", text)
                if m:
                    return m.group(1)
    return ""


def _extract_statement_charge_date(raw: pd.DataFrame) -> date | None:
    """Billing date for an Isracard sheet, e.g. 'ספטמבר 2026' + 'לחיוב ב-10.09'."""
    year = None
    month = None
    day = None
    for i in range(min(16, len(raw))):
        for v in raw.iloc[i].tolist():
            text = _cell_str(v)
            if not text:
                continue
            for name, num in HEBREW_MONTHS.items():
                match = re.search(rf"{name}\s+(\d{{4}})", text)
                if match:
                    month = num
                    year = int(match.group(1))
                    break
            charge = re.search(r"לחיוב ב[-\s]*(\d{1,2})[./](\d{1,2})", text)
            if charge:
                day = int(charge.group(1))
                if month is None:
                    month = int(charge.group(2))
    if year and month:
        return date(year, month, min(day or 1, 28))
    return None


def _is_credit_card_raw(raw: pd.DataFrame) -> bool:
    for i in range(len(raw)):
        for v in raw.iloc[i].tolist():
            text = _cell_str(v)
            if "שם בית עסק" in text or (
                "פירוט עסקאות" in text and "כל הכרטיסים" not in text
            ):
                return True
    return False


def _map_cc_header_row(row_vals: list[str]) -> dict[int, str] | None:
    """Map column index -> canonical field for an Isracard header row."""
    mapping: dict[int, str] = {}
    for idx, raw in enumerate(row_vals):
        key = _normalize_header(raw)
        if not key:
            continue
        key_l = key.lower()
        for alias, field in CC_HEADER_MAP.items():
            if key == alias or key_l == alias.lower():
                mapping[idx] = field
                break
        else:
            # Soft match for voucher column variants
            if "שובר" in key:
                mapping[idx] = "reference"
            elif "תאריך רכישה" in key:
                mapping[idx] = "txn_date"
            elif "בית עסק" in key:
                mapping[idx] = "description"
            elif "סכום חיוב" in key:
                mapping[idx] = "charge_amount"
            elif "סכום עסקה" in key:
                mapping[idx] = "txn_amount"
            elif "פירוט" in key:
                mapping[idx] = "details"
            elif "חיוב בחשבון" in key:
                mapping[idx] = "value_date"
    if "description" in mapping.values() and "txn_date" in mapping.values():
        return mapping
    return None


def _is_skip_merchant(desc: str) -> bool:
    if not desc:
        return True
    # Totals / section titles / footnotes (prefix match only)
    skip_prefixes = (
        'סה"כ',
        "סה״כ",
        "סהכ",
        "עסקאות",
        "תנאים משפטיים",
        "מסגרת",
        "נותר לניצול",
        "על שם",
        "פירוט עסקאות",
    )
    return any(desc.startswith(p) for p in skip_prefixes)


def rows_from_credit_card(raw: pd.DataFrame) -> list[dict[str, Any]]:
    """Parse all Isracard tables on one sheet into debit line items."""
    account = _extract_card_last4(raw)
    statement_date = _extract_statement_charge_date(raw)
    rows: list[dict[str, Any]] = []
    col_map: dict[int, str] | None = None
    pending_section = False

    for i in range(len(raw)):
        row_vals = [_normalize_header(v) for v in raw.iloc[i].tolist()]
        joined = " ".join(v for v in row_vals if v)

        # Section markers
        if "עסקאות שטרם נקלטו" in joined and "שם בית עסק" not in joined:
            pending_section = True
            col_map = None
            continue
        if "עסקאות למועד חיוב" in joined or "עסקאות בחיוב מחוץ למועד" in joined:
            if "שם בית עסק" not in joined:
                pending_section = False
                col_map = None
                continue

        # Header row?
        new_map = _map_cc_header_row(row_vals)
        if new_map:
            col_map = new_map
            # If this header is under pending section title we already set
            continue

        if not col_map:
            continue

        # Blank row ends current table
        if not any(row_vals):
            col_map = None
            continue

        def get(field: str) -> str:
            for idx, fname in col_map.items():
                if fname == field and idx < len(row_vals):
                    return row_vals[idx]
            return ""

        desc = get("description").strip()
        if _is_skip_merchant(desc):
            # Totals often have no date — end table if total-like
            if desc.startswith('סה"כ') or desc.startswith("סה״כ") or 'סה"כ' in desc:
                col_map = None
            continue

        txn_date = excel_serial_to_date(get("txn_date"))
        if txn_date is None:
            # Non-data row inside a table — maybe section noise
            if not get("txn_date") and not _parse_amount(get("charge_amount") or get("txn_amount")):
                col_map = None
            continue

        charge = _parse_amount(get("charge_amount"))
        txn_amt = _parse_amount(get("txn_amount"))
        amount = charge if charge is not None else txn_amt
        if amount is None:
            continue

        details = get("details").replace("\n", " ").strip()
        if pending_section and not details:
            details = "pending"

        value_date = (
            excel_serial_to_date(get("value_date")) or statement_date or txn_date
        )
        ref = get("reference").strip()

        rows.append(
            {
                "txn_date": txn_date,
                "value_date": value_date,
                "description": desc,
                "details": details,
                "reference": ref,
                "beneficiary": "",
                "purpose": "",
                "amount": float(amount),
                "direction": "debit",
                "account": account,
            }
        )

    return rows
