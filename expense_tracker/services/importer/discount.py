"""Discount Bank credit-card statement parsing."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from expense_tracker.services.importer.common import (
    _cell_str,
    _normalize_header,
    _parse_signed_amount,
    excel_serial_to_date,
)
from expense_tracker.services.importer.hapoalim import _extract_account

# Discount Bank credit-card column aliases
DISCOUNT_CC_HEADER_MAP = {
    "כרטיס": "card",
    "בית עסק": "description",
    "תאריך עסקה": "txn_date",
    "סכום העסקה": "txn_amount",
    "תאריך החיוב": "value_date",
    "סכום החיוב": "charge_amount",
    "פירוט": "details",
}


def _is_discount_credit_card_raw(raw: pd.DataFrame) -> bool:
    for i in range(min(20, len(raw))):
        row_vals = [_normalize_header(v) for v in raw.iloc[i].tolist()]
        if "בית עסק" in row_vals and "תאריך עסקה" in row_vals and "סכום החיוב" in row_vals:
            return True
        joined = " ".join(row_vals)
        if "פירוט עסקאות - כל הכרטיסים" in joined:
            return True
    return False


def _map_discount_cc_header_row(row_vals: list[str]) -> dict[int, str] | None:
    mapping: dict[int, str] = {}
    for idx, raw in enumerate(row_vals):
        key = _normalize_header(raw)
        if not key:
            continue
        for alias, field in DISCOUNT_CC_HEADER_MAP.items():
            if key == alias or alias in key:
                mapping[idx] = field
                break
    if "description" in mapping.values() and "txn_date" in mapping.values():
        return mapping
    return None


def _card_last4(card_text: str) -> str:
    m = re.search(r"(\d{4})\s*$", card_text.strip())
    return m.group(1) if m else ""


def rows_from_discount_credit_card(raw: pd.DataFrame) -> list[dict[str, Any]]:
    """Parse Discount Bank כרטיסי אשראי export."""
    account = ""
    for i in range(min(8, len(raw))):
        for v in raw.iloc[i].tolist():
            text = _cell_str(v)
            if "חשבון:" in text:
                account = _extract_account(text) or account

    rows: list[dict[str, Any]] = []
    col_map: dict[int, str] | None = None

    for i in range(len(raw)):
        row_vals = [_normalize_header(v) for v in raw.iloc[i].tolist()]
        joined = " ".join(v for v in row_vals if v)

        new_map = _map_discount_cc_header_row(row_vals)
        if new_map:
            col_map = new_map
            continue

        if not col_map:
            continue

        if not any(row_vals):
            col_map = None
            continue

        def get(field: str) -> str:
            for idx, fname in col_map.items():
                if fname == field and idx < len(row_vals):
                    return row_vals[idx]
            return ""

        desc = get("description").strip()
        if not desc or desc.startswith("סה") or "עסקאות לחיוב" in desc:
            continue

        txn_date = excel_serial_to_date(get("txn_date"))
        if txn_date is None:
            continue

        charge_signed = _parse_signed_amount(get("charge_amount"))
        txn_signed = _parse_signed_amount(get("txn_amount"))
        signed = charge_signed if charge_signed is not None else txn_signed
        if signed is None:
            continue

        if signed < 0:
            direction = "credit"
            amount = abs(signed)
        else:
            direction = "debit"
            amount = signed

        value_date = excel_serial_to_date(get("value_date")) or txn_date
        details = get("details").replace("\n", " ").strip()
        card = get("card")
        card4 = _card_last4(card) if card else ""

        rows.append(
            {
                "txn_date": txn_date,
                "value_date": value_date,
                "description": desc,
                "details": details,
                "reference": "",
                "beneficiary": "",
                "purpose": card.strip(),
                "amount": float(amount),
                "direction": direction,
                "account": card4 or account,
            }
        )

    return rows
