"""Split one transaction into several category/description parts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from expense_tracker.categorizer import apply_description, remember_rule
from expense_tracker.models import Category, Transaction


def _parse_splits(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("splits must be a list")
    if len(raw) < 2:
        raise ValueError("Split needs at least two parts")
    parts: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Split part {i + 1} is invalid")
        desc = str(item.get("description") or "").strip()
        if not desc:
            raise ValueError(f"Split part {i + 1} needs a description")
        try:
            amount = abs(float(item.get("amount", 0)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Split part {i + 1} needs a valid amount") from exc
        if amount <= 0:
            raise ValueError(f"Split part {i + 1} amount must be positive")
        cid_raw = item.get("category_id")
        category_id = (
            int(cid_raw) if cid_raw not in (None, "", "null") else None
        )
        parts.append(
            {
                "description": desc,
                "amount": round(amount, 2),
                "category_id": category_id,
            }
        )
    return parts


def split_transaction(
    session: Session,
    txn: Transaction,
    raw_splits: Any,
    *,
    remember: bool = False,
    apply_all: bool = False,
) -> dict[str, Any]:
    """
    Replace ``txn`` with multiple parts that sum to its amount.

    Each part keeps its own description. Category defaults to the parent's
    category when a part does not specify one. Optional remember/apply runs
    per part description (same behavior as a normal edit).
    """
    parts = _parse_splits(raw_splits)
    parent_category_id = txn.category_id
    for part in parts:
        if part["category_id"] is None:
            part["category_id"] = parent_category_id

    total = round(sum(p["amount"] for p in parts), 2)
    expected = round(abs(float(txn.amount)), 2)
    if abs(total - expected) > 0.01:
        raise ValueError(
            f"Split amounts ({total:.2f}) must equal the transaction ({expected:.2f})"
        )

    for part in parts:
        if part["category_id"] is not None:
            cat = session.get(Category, part["category_id"])
            if not cat:
                raise ValueError("Unknown category in split")

    stamp = datetime.utcnow().timestamp()
    split_group = uuid4().hex
    base_ref = (txn.reference or "txn").strip() or "txn"
    # Keep original description in details so the bank line is still visible
    parent_desc = (txn.description or "").strip()
    parent_details = (txn.details or "").strip()
    detail_note = parent_desc
    if parent_details and parent_details != parent_desc:
        detail_note = f"{parent_desc} · {parent_details}".strip(" ·")

    created: list[Transaction] = []
    for i, part in enumerate(parts):
        child = Transaction(
            txn_date=txn.txn_date,
            value_date=txn.value_date,
            description=part["description"],
            details=detail_note,
            reference=f"{base_ref}-split-{i + 1}-{stamp}",
            beneficiary=txn.beneficiary or "",
            purpose=txn.purpose or "",
            amount=part["amount"],
            direction=txn.direction,
            account=txn.account or "",
            category_id=part["category_id"],
            source_filename=txn.source_filename or "",
            source=txn.source or "bank",
            categorized_by="",
            split_group=split_group,
            is_manual=txn.is_manual,
        )
        session.add(child)
        created.append(child)

    session.delete(txn)
    session.flush()

    exclude = {c.id for c in created}
    applied = 0
    for child in created:
        if not child.category_id:
            continue
        if remember:
            remember_rule(session, child.description, child.category_id)
        if apply_all:
            applied += apply_description(
                session,
                description=child.description,
                direction=child.direction,
                category_id=child.category_id,
                exclude_ids=exclude,
                unsorted_only=False,
            )
        elif remember:
            applied += apply_description(
                session,
                description=child.description,
                direction=child.direction,
                category_id=child.category_id,
                exclude_ids=exclude,
                unsorted_only=True,
            )

    return {
        "created_ids": [c.id for c in created],
        "applied": applied,
        "parts": len(created),
    }
