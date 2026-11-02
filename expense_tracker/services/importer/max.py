"""Max (מקס) credit-card transaction-details export parsing."""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

from expense_tracker.services.importer.common import (
    _normalize_header,
    _parse_signed_amount,
    excel_serial_to_date,
)
from expense_tracker.services.importer.isracard import PENDING_DETAILS

MAX_HEADER_MAP = {
    "תאריך עסקה": "txn_date",
    "שם בית העסק": "description",
    "4 ספרות אחרונות של כרטיס האשראי": "card",
    "סכום חיוב": "charge_amount",
    "סכום עסקה מקורי": "original_amount",
    "תאריך חיוב": "value_date",
    "הערות": "details",
}


def _is_max_credit_card_raw(raw: pd.DataFrame) -> bool:
    for i in range(min(12, len(raw))):
        row_vals = [_normalize_header(v) for v in raw.iloc[i].tolist()]
        if (
            "שם בית העסק" in row_vals
            and "תאריך עסקה" in row_vals
            and "סכום חיוב" in row_vals
        ):
            return True
    return False


def _map_max_header_row(row_vals: list[str]) -> dict[int, str] | None:
    mapping: dict[int, str] = {}
    for idx, raw in enumerate(row_vals):
        key = _normalize_header(raw)
        field = MAX_HEADER_MAP.get(key)
        if field:
            mapping[idx] = field
    if {"description", "txn_date", "charge_amount"} <= set(mapping.values()):
        return mapping
    return None


def _card_last4(card_text: str) -> str:
    text = card_text.strip()
    if text.endswith(".0"):
        text = text[:-2]
    match = re.search(r"(\d{4})\s*$", text)
    return match.group(1) if match else ""


def _is_total_row(description: str) -> bool:
    text = description.strip()
    return not text or text.startswith("סך") or text.startswith("סה")


def rows_from_max_sheet(raw: pd.DataFrame, *, pending: bool) -> list[dict[str, Any]]:
    """Parse one Max sheet. Pending sheets are marked so import skips them."""
    rows: list[dict[str, Any]] = []
    col_map: dict[int, str] | None = None

    for i in range(len(raw)):
        row_vals = [_normalize_header(v) for v in raw.iloc[i].tolist()]
        new_map = _map_max_header_row(row_vals)
        if new_map:
            col_map = new_map
            continue
        if not col_map or not any(row_vals):
            continue

        def get(field: str) -> str:
            for idx, fname in col_map.items():
                if fname == field and idx < len(row_vals):
                    return row_vals[idx]
            return ""

        desc = get("description").strip()
        if _is_total_row(desc):
            continue

        txn_date = excel_serial_to_date(get("txn_date"))
        if txn_date is None:
            continue

        signed = _parse_signed_amount(get("charge_amount"))
        if signed is None:
            signed = _parse_signed_amount(get("original_amount"))
        if signed is None:
            continue

        notes = get("details").replace("\n", " ").strip()
        rows.append(
            {
                "txn_date": txn_date,
                "value_date": excel_serial_to_date(get("value_date")) or txn_date,
                "description": desc,
                "details": PENDING_DETAILS if pending else notes,
                "reference": "",
                "beneficiary": "",
                "purpose": "",
                "amount": float(signed),
                "direction": "debit",
                "account": _card_last4(get("card")),
            }
        )
    return rows


def rows_from_max_workbook(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse every sheet of a Max transaction-details workbook."""
    sheets = pd.read_excel(
        io.BytesIO(file_bytes), sheet_name=None, header=None, dtype=object
    )
    rows: list[dict[str, Any]] = []
    for name, raw in sheets.items():
        rows.extend(rows_from_max_sheet(raw, pending="טרם" in str(name)))
    return rows
