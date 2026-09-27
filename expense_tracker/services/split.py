"""Split one transaction into several category/description parts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from expense_tracker.services.categorizer import apply_description, remember_rule
from expense_tracker.models import Category, Transaction

_SPLIT_REF_RE = re.compile(r"^(?P<base>.+)-split-\d+-[\d.]+$")


def split_part_base_ref(reference: str | None) -> str | None:
    match = _SPLIT_REF_RE.match(reference or "")
    return match.group("base") if match else None


def resolve_split_parents(txns: list[Transaction]) -> list[Transaction]:
    """Originals that still sit next to their split parts (e.g. after re-import)."""
    groups: dict[str, list[Transaction]] = {}
    for txn in txns:
        group = (getattr(txn, "split_group", "") or "").strip()
        if not group or getattr(txn, "is_split_parent", False):
            continue
        groups.setdefault(group, []).append(txn)

    already_parented = {
        (txn.split_group or "").strip()
        for txn in txns
        if getattr(txn, "is_split_parent", False)
        and (txn.split_group or "").strip()
    }

    found: list[Transaction] = []
    used_ids: set[int] = set()
    for group_id, members in groups.items():
        if len(members) < 2 or group_id in already_parented:
            continue
        parent = _match_split_parent(members, txns, used_ids)
        if parent is not None:
            found.append(parent)
            used_ids.add(parent.id)
    return found


def _match_split_parent(
    members: list[Transaction],
    txns: list[Transaction],
    used_ids: set[int],
) -> Transaction | None:
    total = round(sum(float(member.amount) for member in members), 2)
    direction = members[0].direction
    bases = {split_part_base_ref(member.reference) for member in members}
    bases.discard(None)

    def is_candidate(txn: Transaction) -> bool:
        if getattr(txn, "is_split_parent", False) or txn.id in used_ids:
            return False
        if (getattr(txn, "split_group", "") or "").strip():
            return False
        if txn.direction != direction:
            return False
        return abs(round(float(txn.amount), 2) - total) <= 0.01

    candidates = [txn for txn in txns if is_candidate(txn)]
    if len(bases) == 1:
        base = next(iter(bases))
        ref_hits = [txn for txn in candidates if (txn.reference or "") == base]
        if ref_hits:
            candidates = ref_hits

    if not candidates:
        parent_descs = {
            (member.details or "").split(" · ", 1)[0].strip()
            for member in members
            if (member.details or "").strip()
        }
        parent_descs.discard("")
        account = (members[0].account or "").strip()
        if parent_descs:
            candidates = [
                txn
                for txn in txns
                if is_candidate(txn)
                and (txn.description or "").strip() in parent_descs
                and (txn.account or "").strip() == account
            ]

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    child_dates = {member.txn_date for member in members}
    child_dates.update(
        member.value_date for member in members if getattr(member, "value_date", None)
    )
    exact = [
        txn
        for txn in candidates
        if txn.txn_date in child_dates
        or getattr(txn, "value_date", None) in child_dates
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    def date_distance(txn: Transaction) -> int:
        return min(abs((txn.txn_date - child_date).days) for child_date in child_dates)

    ranked = sorted(candidates, key=date_distance)
    if date_distance(ranked[0]) < date_distance(ranked[1]):
        return ranked[0]
    return None


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
                "custom_description": str(item.get("custom_description") or "").strip(),
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
    part_date=None,
) -> dict[str, Any]:
    """
    Keep ``txn`` as a hidden parent and add parts that sum to its amount.

    Each part keeps its own description. Category defaults to the parent's
    category when a part does not specify one. Optional remember/apply runs
    per part description (same behavior as a normal edit).
    """
    if (getattr(txn, "split_group", "") or "").strip() or getattr(
        txn, "is_split_parent", False
    ):
        raise ValueError("This transaction was already split and cannot be split again")

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

    child_date = part_date or txn.txn_date
    child_value = part_date or txn.value_date
    parent_tags = list(txn.tags or [])

    created: list[Transaction] = []
    for i, part in enumerate(parts):
        child = Transaction(
            txn_date=child_date,
            value_date=child_value,
            description=part["description"],
            details=detail_note,
            custom_description=part.get("custom_description") or "",
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
        if parent_tags:
            child.tags = list(parent_tags)
        created.append(child)

    txn.split_group = split_group
    txn.is_split_parent = True
    session.flush()

    exclude = {txn.id, *[c.id for c in created]}
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
