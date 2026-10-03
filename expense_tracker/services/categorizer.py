"""Keyword-based transaction categorization."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from expense_tracker.models import CategorizationRule, Category, Tag, Transaction


def load_rules(session: Session) -> list[CategorizationRule]:
    return list(
        session.scalars(
            select(CategorizationRule)
            .options(selectinload(CategorizationRule.tags))
            .order_by(CategorizationRule.priority.desc())
        ).all()
    )


def category_map(session: Session) -> dict[int, Category]:
    return {c.id: c for c in session.scalars(select(Category)).all()}


def match_rule(
    description: str,
    details: str,
    direction: str,
    rules: list[CategorizationRule],
    cats: dict[int, Category] | None = None,
) -> CategorizationRule | None:
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
        return rule
    return None


def match_category_id(
    description: str,
    details: str,
    direction: str,
    rules: list[CategorizationRule],
    cats: dict[int, Category] | None = None,
) -> int | None:
    rule = match_rule(description, details, direction, rules, cats=cats)
    return rule.category_id if rule else None


def categorize_transaction(
    session: Session,
    txn: Transaction,
    rules: list[CategorizationRule] | None = None,
    cats: dict[int, Category] | None = None,
) -> None:
    rules = rules if rules is not None else load_rules(session)
    cats = cats if cats is not None else category_map(session)
    rule = match_rule(txn.description, txn.details, txn.direction, rules, cats=cats)
    cid = rule.category_id if rule else None
    txn.category_id = cid if cid and cid in cats else None
    if rule and rule.tags and not txn.tags:
        txn.tags = list(rule.tags)


def remember_rule(
    session: Session,
    pattern: str,
    category_id: int,
    priority: int = 250,
    tags: list[Tag] | None = None,
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
        if tags is not None:
            existing.tags = list(tags)
        return existing
    rule = CategorizationRule(
        pattern=pattern, category_id=category_id, priority=priority
    )
    if tags is not None:
        rule.tags = list(tags)
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
    tags: list[Tag] | None = None,
) -> int:
    """Assign category_id to other transactions with the same description."""
    desc = (description or "").strip()
    if not desc:
        return 0
    clauses = [
        Transaction.direction == direction,
        func.lower(Transaction.description) == desc.lower(),
        Transaction.ignored.is_(False),
        Transaction.is_split_parent.is_(False),
    ]
    if exclude_ids:
        clauses.append(Transaction.id.notin_(list(exclude_ids)))
    if unsorted_only:
        clauses.append(Transaction.category_id.is_(None))
    matches = session.scalars(select(Transaction).where(*clauses)).all()
    for other in matches:
        other.category_id = category_id
        if tags:
            have = {tag.id for tag in other.tags}
            for tag in tags:
                if tag.id not in have:
                    other.tags.append(tag)
                    have.add(tag.id)
        if hasattr(other, "categorized_by"):
            other.categorized_by = ""
    return len(matches)


def apply_to_similar_unsorted(
    session: Session,
    txn: Transaction,
    category_id: int,
    tags: list[Tag] | None = None,
) -> int:
    return apply_description(
        session,
        description=txn.description or "",
        direction=txn.direction,
        category_id=category_id,
        exclude_ids={txn.id},
        unsorted_only=True,
        tags=tags,
    )


def apply_to_similar_all(
    session: Session,
    txn: Transaction,
    category_id: int,
    tags: list[Tag] | None = None,
) -> int:
    """Apply category to every matching description (unsorted and already categorized)."""
    return apply_description(
        session,
        description=txn.description or "",
        direction=txn.direction,
        category_id=category_id,
        exclude_ids={txn.id},
        unsorted_only=False,
        tags=tags,
    )
