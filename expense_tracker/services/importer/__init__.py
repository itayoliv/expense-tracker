"""Import Bank Hapoalim, Discount Bank, and Isracard XLSX/CSV statements."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from expense_tracker.models import Transaction
from expense_tracker.services.categorizer import categorize_transaction, category_map, load_rules
from expense_tracker.services.importer.common import (
    _load_raw,
    excel_serial_to_date,
    read_dataframe,
)
from expense_tracker.services.importer.discount import (
    rows_from_discount_credit_card,
    _is_discount_credit_card_raw,
)
from expense_tracker.services.importer.hapoalim import rows_from_dataframe
from expense_tracker.services.importer.isracard import (
    PENDING_DETAILS,
    rows_from_credit_card,
    _is_credit_card_raw,
)

__all__ = [
    "excel_serial_to_date",
    "read_dataframe",
    "rows_from_dataframe",
    "rows_from_credit_card",
    "rows_from_discount_credit_card",
    "parse_file",
    "import_file",
]


def parse_file(file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    """Detect format and return normalized transaction dicts."""
    raw = _load_raw(file_bytes, filename)
    if _is_credit_card_raw(raw):
        rows = rows_from_credit_card(raw)
        kind = "card"
    elif _is_discount_credit_card_raw(raw):
        rows = rows_from_discount_credit_card(raw)
        kind = "card"
    else:
        df, account = read_dataframe(file_bytes, filename)
        rows = rows_from_dataframe(df, account)
        kind = "bank"
    for row in rows:
        row["source"] = kind
    return rows


def _pending_twin(session: Session, row: dict[str, Any]) -> Transaction | None:
    """Row already imported from the 'עסקאות שטרם נקלטו' section of an earlier export.

    Pending lines carry no voucher number, so the final statement — which does —
    never matches the dedup key and would land as a second copy.
    """
    if row["details"] == PENDING_DETAILS or not row["reference"]:
        return None
    candidates = session.scalars(
        select(Transaction).where(
            Transaction.txn_date == row["txn_date"],
            Transaction.amount == row["amount"],
            Transaction.direction == row["direction"],
            Transaction.details == PENDING_DETAILS,
            Transaction.reference == "",
        )
    ).all()
    desc = (row["description"] or "").casefold()
    for txn in candidates:
        if (txn.description or "").casefold() != desc:
            continue
        if txn.account and row["account"] and txn.account != row["account"]:
            continue
        return txn
    return None


def import_file(
    session: Session, file_bytes: bytes, filename: str
) -> dict[str, int]:
    parsed = parse_file(file_bytes, filename)
    rules = load_rules(session)
    cats = category_map(session)

    added = 0
    skipped = 0
    merged = 0

    for row in parsed:
        # Not-yet-captured lines (עסקאות שטרם נקלטו) are provisional; wait for the
        # final statement row, which carries a voucher number and the real details.
        if row["details"] == PENDING_DETAILS:
            skipped += 1
            continue

        exists = session.scalars(
            select(Transaction).where(
                Transaction.txn_date == row["txn_date"],
                Transaction.reference == row["reference"],
                Transaction.amount == row["amount"],
                Transaction.description == row["description"],
                Transaction.direction == row["direction"],
            )
        ).first()
        pending = _pending_twin(session, row)
        if exists:
            if row.get("value_date") and exists.value_date != row["value_date"]:
                exists.value_date = row["value_date"]
            if exists.details == PENDING_DETAILS and row["details"] != PENDING_DETAILS:
                exists.details = row["details"]
            if pending is not None and pending.id != exists.id:
                session.delete(pending)
                merged += 1
            skipped += 1
            continue

        if pending is not None:
            # Keep the existing row so its category, tags, and splits survive.
            pending.description = row["description"]
            pending.details = row["details"]
            pending.reference = row["reference"]
            if row.get("value_date"):
                pending.value_date = row["value_date"]
            pending.source_filename = Path(filename).name
            merged += 1
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
        try:
            with session.begin_nested():
                session.add(txn)
                categorize_transaction(session, txn, rules=rules, cats=cats)
                session.flush()
            added += 1
        except IntegrityError:
            skipped += 1

    session.commit()
    return {
        "added": added,
        "skipped": skipped,
        "merged": merged,
        "total_parsed": len(parsed),
    }
