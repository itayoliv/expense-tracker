"""Shared helpers for statement import parsers."""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

EXCEL_EPOCH = datetime(1899, 12, 30)


def excel_serial_to_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            n = int(value)
            if 30000 < n < 60000:  # plausible Excel serial range
                return (EXCEL_EPOCH + timedelta(days=n)).date()
        except (ValueError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return excel_serial_to_date(int(text))
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _cell_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _normalize_header(cell: Any) -> str:
    return _cell_str(cell).replace("\n", " ")


def _parse_signed_amount(value: Any) -> float | None:
    """Parse amount keeping sign (Discount Bank זכות/חובה column)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value) if float(value) != 0 else None
    text = str(value).strip().replace(",", "").replace("₪", "").replace("$", "")
    text = text.replace(" ", "")
    if not text or text == "-":
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        n = float(text)
        return n if n != 0 else None
    except ValueError:
        return None


def _parse_amount(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return abs(float(value)) if float(value) != 0 else None
    text = str(value).strip().replace(",", "").replace("₪", "").replace("$", "")
    text = text.replace(" ", "")
    if not text or text == "-":
        return None
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    try:
        n = float(text)
        if n == 0:
            return None
        return abs(n)
    except ValueError:
        return None


def _load_raw(file_bytes: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(file_bytes), header=None, dtype=object)

    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1255", "iso-8859-8"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Could not decode CSV file encoding.")
    return pd.read_csv(io.StringIO(text), header=None, dtype=object)


def read_dataframe(file_bytes: bytes, filename: str) -> tuple[pd.DataFrame, str]:
    """Bank-statement path: return a headed dataframe + account."""
    # Lazy import avoids common <-> hapoalim cycle at module load.
    from expense_tracker.services.importer.hapoalim import _extract_account, _find_header_row

    raw = _load_raw(file_bytes, filename)
    account = ""
    for i in range(min(8, len(raw))):
        for v in raw.iloc[i].tolist():
            if isinstance(v, str) and ("חשבון" in v or "account" in v.lower()):
                account = _extract_account(v) or account

    header_idx = _find_header_row(raw)
    if header_idx is None:
        # Assume first row is header (simple English CSV)
        name = filename.lower()
        if name.endswith((".xlsx", ".xls")):
            raise ValueError("Could not find a header row in the Excel file.")
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp1255", "iso-8859-8"):
            try:
                text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Could not decode CSV file encoding.")
        df = pd.read_csv(io.StringIO(text), dtype=object)
        return df, account

    headers = [
        _normalize_header(v) or f"col_{j}" for j, v in enumerate(raw.iloc[header_idx])
    ]
    data = raw.iloc[header_idx + 1 :].copy()
    data.columns = headers
    data = data.dropna(how="all")
    return data, account
