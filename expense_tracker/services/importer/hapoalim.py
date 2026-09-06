"""Bank Hapoalim / Discount checking-account statement parsing."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from expense_tracker.services.importer.common import (
    _normalize_header,
    _parse_amount,
    _parse_signed_amount,
    excel_serial_to_date,
)

# Hebrew and English header aliases -> canonical field (bank statements)
HEADER_MAP = {
    "תאריך": "txn_date",
    "date": "txn_date",
    "הפעולה": "description",
    "פעולה": "description",
    "description": "description",
    "action": "description",
    "פרטים": "details",
    "details": "details",
    "אסמכתא": "reference",
    "reference": "reference",
    "ref": "reference",
    "חובה": "debit",
    "debit": "debit",
    "expense": "debit",
    "זכות": "credit",
    "credit": "credit",
    "income": "credit",
    "תאריך ערך": "value_date",
    "value date": "value_date",
    "value_date": "value_date",
    "לטובת": "beneficiary",
    "beneficiary": "beneficiary",
    "עבור": "purpose",
    "purpose": "purpose",
    "amount": "amount",
    "סכום": "amount",
    "category": "category",
    "קטגוריה": "category",
    # Discount Bank (עובר ושב)
    "תיאור התנועה": "description",
    "יום ערך": "value_date",
    "זכות/חובה": "signed_amount",
    "ערוץ ביצוע": "purpose",
}


def _find_header_row(df_raw: pd.DataFrame) -> int | None:
    for i in range(min(30, len(df_raw))):
        row_vals = [_normalize_header(v).lower() for v in df_raw.iloc[i].tolist()]
        joined = " ".join(row_vals)
        # Hapoalim markers
        if "הפעולה" in joined or ("חובה" in joined and "זכות" in joined):
            return i
        # Discount Bank (עובר ושב)
        if "תיאור התנועה" in joined or ("זכות/חובה" in joined and "תאריך" in joined):
            return i
        if "description" in row_vals and ("debit" in row_vals or "credit" in row_vals):
            return i
        if "date" in row_vals and "amount" in row_vals:
            return i
    return None


def _map_columns(headers: list[str]) -> dict[str, str]:
    """Map dataframe column name -> canonical field."""
    mapping: dict[str, str] = {}
    for h in headers:
        key = _normalize_header(h).lower()
        if "זכות/חובה" in key:
            mapping[h] = "signed_amount"
            continue
        for alias, field in HEADER_MAP.items():
            if key == alias.lower():
                mapping[h] = field
                break
        else:
            for alias, field in HEADER_MAP.items():
                if alias.lower() in key and h not in mapping:
                    mapping[h] = field
                    break
    return mapping


def _extract_account(meta_text: str) -> str:
    # Discount: חשבון: 0140178718 | name
    m = re.search(r"חשבון:\s*(\d+)", meta_text)
    if m:
        return m.group(1)
    # e.g. מספר חשבון  12-628-654839
    m = re.search(r"(\d{1,3}-\d{2,4}-\d{4,})", meta_text)
    if m:
        return m.group(1)
    m = re.search(r"(\d{6,})", meta_text)
    return m.group(1) if m else ""


def rows_from_dataframe(df: pd.DataFrame, account: str) -> list[dict[str, Any]]:
    col_map = _map_columns(list(df.columns))
    if "txn_date" not in col_map.values() and "description" not in col_map.values():
        raise ValueError(
            "Unrecognized columns. Expected Hapoalim headers "
            "(תאריך, הפעולה, חובה, זכות), Discount Bank (תיאור התנועה), "
            "Isracard (שם בית עסק), or Date/Description/Amount."
        )

    inv = {v: k for k, v in col_map.items()}
    rows: list[dict[str, Any]] = []

    for _, series in df.iterrows():
        get = lambda field: series.get(inv[field]) if field in inv else None

        desc = get("description")
        desc_s = (
            ""
            if desc is None or (isinstance(desc, float) and pd.isna(desc))
            else str(desc).strip()
        )
        if not desc_s:
            continue

        txn_date = excel_serial_to_date(get("txn_date"))
        if txn_date is None:
            continue

        value_date = excel_serial_to_date(get("value_date")) or txn_date
        details = get("details")
        details_s = (
            ""
            if details is None or (isinstance(details, float) and pd.isna(details))
            else str(details).strip()
        )
        ref = get("reference")
        ref_s = (
            ""
            if ref is None or (isinstance(ref, float) and pd.isna(ref))
            else str(ref).strip()
        )
        ben = get("beneficiary")
        ben_s = (
            ""
            if ben is None or (isinstance(ben, float) and pd.isna(ben))
            else str(ben).strip()
        )
        purpose = get("purpose")
        purpose_s = (
            ""
            if purpose is None or (isinstance(purpose, float) and pd.isna(purpose))
            else str(purpose).strip()
        )

        debit = _parse_amount(get("debit")) if "debit" in inv else None
        credit = _parse_amount(get("credit")) if "credit" in inv else None
        single = _parse_amount(get("amount")) if "amount" in inv else None
        signed = _parse_signed_amount(get("signed_amount")) if "signed_amount" in inv else None

        if signed is not None:
            if signed < 0:
                direction = "debit"
                amount = abs(signed)
            else:
                direction = "credit"
                amount = signed
        elif debit and credit:
            direction = "debit"
            amount = debit
        elif debit:
            direction = "debit"
            amount = debit
        elif credit:
            direction = "credit"
            amount = credit
        elif single is not None:
            direction = "debit"
            amount = single
        else:
            continue

        rows.append(
            {
                "txn_date": txn_date,
                "value_date": value_date,
                "description": desc_s,
                "details": details_s,
                "reference": ref_s,
                "beneficiary": ben_s,
                "purpose": purpose_s,
                "amount": float(amount),
                "direction": direction,
                "account": account,
            }
        )
    return rows
