"""Import Bank Hapoalim and Isracard XLSX/CSV statements."""

from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from expense_tracker.categorizer import categorize_transaction, category_map, load_rules
from expense_tracker.models import Transaction

EXCEL_EPOCH = datetime(1899, 12, 30)

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
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%y"):
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


def _find_header_row(df_raw: pd.DataFrame) -> int | None:
    for i in range(min(30, len(df_raw))):
        row_vals = [_normalize_header(v).lower() for v in df_raw.iloc[i].tolist()]
        joined = " ".join(row_vals)
        # Hapoalim markers
        if "הפעולה" in joined or ("חובה" in joined and "זכות" in joined):
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


def _extract_account(meta_text: str) -> str:
    # e.g. מספר חשבון  12-628-654839
    m = re.search(r"(\d{1,3}-\d{2,4}-\d{4,})", meta_text)
    if m:
        return m.group(1)
    m = re.search(r"(\d{6,})", meta_text)
    return m.group(1) if m else ""


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
            if "שם בית עסק" in text or "פירוט עסקאות" in text:
                return True
    return False


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


def read_dataframe(file_bytes: bytes, filename: str) -> tuple[pd.DataFrame, str]:
    """Bank-statement path: return a headed dataframe + account."""
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


def rows_from_dataframe(df: pd.DataFrame, account: str) -> list[dict[str, Any]]:
    col_map = _map_columns(list(df.columns))
    if "txn_date" not in col_map.values() and "description" not in col_map.values():
        raise ValueError(
            "Unrecognized columns. Expected Hapoalim headers "
            "(תאריך, הפעולה, חובה, זכות), Isracard (שם בית עסק), "
            "or Date/Description/Amount."
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

        if debit and credit:
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


def parse_file(file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    """Detect format and return normalized transaction dicts."""
    raw = _load_raw(file_bytes, filename)
    if _is_credit_card_raw(raw):
        rows = rows_from_credit_card(raw)
        kind = "card"
    else:
        df, account = read_dataframe(file_bytes, filename)
        rows = rows_from_dataframe(df, account)
        kind = "bank"
    for row in rows:
        row["source"] = kind
    return rows


def import_file(
    session: Session, file_bytes: bytes, filename: str
) -> dict[str, int]:
    parsed = parse_file(file_bytes, filename)
    rules = load_rules(session)
    cats = category_map(session)

    added = 0
    skipped = 0

    for row in parsed:
        exists = session.scalars(
            select(Transaction).where(
                Transaction.txn_date == row["txn_date"],
                Transaction.reference == row["reference"],
                Transaction.amount == row["amount"],
                Transaction.description == row["description"],
                Transaction.direction == row["direction"],
            )
        ).first()
        if exists:
            if row.get("value_date") and exists.value_date != row["value_date"]:
                exists.value_date = row["value_date"]
            skipped += 1
            continue

        txn = Transaction(
            txn_date=row["txn_date"],
            value_date=row["value_date"],
            description=row["description"],
            details=row["details"],
            reference=row["reference"],
            beneficiary=row["beneficiary"],
            purpose=row["purpose"],
            amount=row["amount"],
            direction=row["direction"],
            account=row["account"],
            source_filename=Path(filename).name,
            source=row.get("source") or "bank",
            is_manual=False,
        )
        categorize_transaction(session, txn, rules=rules, cats=cats)
        try:
            with session.begin_nested():
                session.add(txn)
                session.flush()
            added += 1
        except IntegrityError:
            skipped += 1

    session.commit()
    return {"added": added, "skipped": skipped, "total_parsed": len(parsed)}
