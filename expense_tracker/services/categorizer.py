"""Keyword-based transaction categorization."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from expense_tracker.models import CategorizationRule, Category, Transaction


def load_rules(session: Session) -> list[CategorizationRule]:
    return list(
        session.scalars(
            select(CategorizationRule).order_by(CategorizationRule.priority.desc())
        ).all()
    )


def category_map(session: Session) -> dict[int, Category]:
    return {c.id: c for c in session.scalars(select(Category)).all()}


def match_category_id(
    description: str,
    details: str,
    direction: str,
    rules: list[CategorizationRule],
    cats: dict[int, Category] | None = None,
) -> int | None:
    haystack = f"{description} {details}".lower()
    for rule in rules:
        if rule.pattern.lower() not in haystack:
            continue
        cid = rule.category_id
        if cats:
            cat = cats.get(cid)
            if cat is None:
                continue
            if direction == "debit" and cat.kind == "income":
                continue
            if direction == "credit" and cat.kind == "expense":
                continue
        return cid
    return None


def categorize_transaction(
    session: Session,
    txn: Transaction,
    rules: list[CategorizationRule] | None = None,
    cats: dict[int, Category] | None = None,
) -> None:
    rules = rules if rules is not None else load_rules(session)
    cats = cats if cats is not None else category_map(session)
    cid = match_category_id(
        txn.description, txn.details, txn.direction, rules, cats=cats
    )
    txn.category_id = cid if cid and cid in cats else None


def remember_rule(
    session: Session,
    pattern: str,
    category_id: int,
    priority: int = 250,
) -> CategorizationRule:
    pattern = pattern.strip()
    existing = session.scalars(
        select(CategorizationRule).where(
            CategorizationRule.pattern == pattern,
            CategorizationRule.category_id == category_id,
        )
    ).first()
    if existing:
        existing.priority = max(existing.priority, priority)
        return existing
    rule = CategorizationRule(
        pattern=pattern, category_id=category_id, priority=priority
    )
    session.add(rule)
    return rule


def apply_description(
    session: Session,
    *,
    description: str,
    direction: str,
    category_id: int,
    exclude_ids: set[int] | frozenset[int] | None = None,
    unsorted_only: bool = False,
) -> int:
    """Assign category_id to other transactions with the same description."""
    desc = (description or "").strip()
    if not desc:
        return 0
    clauses = [
        Transaction.direction == direction,
        func.lower(Transaction.description) == desc.lower(),
    ]
    if exclude_ids:
        clauses.append(Transaction.id.notin_(list(exclude_ids)))
    if unsorted_only:
        clauses.append(Transaction.category_id.is_(None))
    matches = session.scalars(select(Transaction).where(*clauses)).all()
    for other in matches:
        other.category_id = category_id
        if hasattr(other, "categorized_by"):
            other.categorized_by = ""
    return len(matches)


def apply_to_similar_unsorted(
    session: Session, txn: Transaction, category_id: int
) -> int:
    return apply_description(
        session,
        description=txn.description or "",
        direction=txn.direction,
        category_id=category_id,
        exclude_ids={txn.id},
        unsorted_only=True,
    )


def apply_to_similar_all(
    session: Session, txn: Transaction, category_id: int
) -> int:
    """Apply category to every matching description (unsorted and already categorized)."""
    return apply_description(
        session,
        description=txn.description or "",
        direction=txn.direction,
        category_id=category_id,
        exclude_ids={txn.id},
        unsorted_only=False,
    )
