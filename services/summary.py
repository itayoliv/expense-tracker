"""Dashboard summary building, month filters, and source labels."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import extract, func, select
from sqlalchemy.orm import joinedload

from i18n import category_name, t
from models import Transaction


def parse_month(raw: str | None) -> tuple[int, int] | None:
    if not raw or raw == "all":
        return None
    try:
        y, m = raw.split("-")
        parsed = int(y), int(m)
        if parsed[1] < 1 or parsed[1] > 12:
            return None
        return parsed
    except (ValueError, AttributeError):
        return None


def current_month_key() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def billing_date_expr():
    """Month grouping uses the billing/value date when present (credit-card statements)."""
    return func.coalesce(Transaction.value_date, Transaction.txn_date)


def available_months(session) -> list[str]:
    billing = billing_date_expr()
    rows = session.execute(
        select(
            extract("year", billing),
            extract("month", billing),
        )
        .distinct()
        .order_by(
            extract("year", billing).desc(),
            extract("month", billing).desc(),
        )
    ).all()
    return [f"{int(y):04d}-{int(m):02d}" for y, m in rows if y and m]


def month_filter(query, month: tuple[int, int] | None):
    if month:
        y, m = month
        billing = billing_date_expr()
        query = query.where(
            extract("year", billing) == y,
            extract("month", billing) == m,
        )
    return query


def source_kind(txn) -> str:
    src = (getattr(txn, "source", None) or "").strip()
    if src in ("bank", "card", "manual"):
        return src
    if txn.is_manual or (txn.source_filename or "").strip().lower() == "manual":
        return "manual"
    acc = (txn.account or "").strip()
    if len(acc) == 4 and acc.isdigit():
        return "card"
    return "bank"


def source_label(lang: str, kind: str) -> str:
    keys = {
        "bank": "source_bank",
        "card": "source_card",
        "manual": "source_manual",
    }
    return t(lang, keys.get(kind, "source_bank"))


def txn_source_fields(lang: str, txn) -> dict[str, str]:
    kind = source_kind(txn)
    account = (txn.account or "").strip()
    return {
        "source": kind,
        "source_label": source_label(lang, kind),
        "account": account or "—",
    }


def split_accent(split_group: str) -> dict[str, str]:
    """Stable HSL accent so sibling split parts share the same highlight."""
    group = (split_group or "").strip()
    if not group:
        return {"split_group": "", "split_accent": ""}
    hue = sum(ord(c) for c in group) % 360
    return {
        "split_group": group,
        "split_accent": f"hsl({hue} 48% 42%)",
    }


def serialize_txn(lang: str, x) -> dict[str, Any]:
    return {
        "id": x.id,
        "description": x.description,
        "details": x.details,
        "date": x.txn_date.strftime("%d/%m/%y"),
        "amount": x.amount,
        "direction": x.direction,
        "category_id": x.category_id,
        "categorized_by": x.categorized_by or "",
        **split_accent(getattr(x, "split_group", "") or ""),
        **txn_source_fields(lang, x),
    }


def has_card_detail_imports(txns: list) -> bool:
    """True if any transaction looks like an Isracard line item."""
    return any(source_kind(t) == "card" for t in txns)


def is_bank_card_lump(txn) -> bool:
    """Bank statement lump charge for a credit card (not a merchant line item)."""
    desc = (txn.description or "").lower()
    lumps = ("ישראכרט", "ויזה", "מקס")
    if not any(x in desc for x in lumps):
        return False
    return source_kind(txn) != "card"


def build_summary(session, view: str, month: tuple[int, int] | None, lang: str) -> dict:
    base = select(Transaction).options(joinedload(Transaction.category))
    base = month_filter(base, month)
    txns = list(session.scalars(base).unique().all())

    # Avoid double-counting: when card merchant details exist, hide bank card lumps
    if has_card_detail_imports(txns):
        txns = [t for t in txns if not is_bank_card_lump(t)]

    if view == "expenses":
        filtered = [t for t in txns if t.direction == "debit"]
    elif view == "income":
        filtered = [t for t in txns if t.direction == "credit"]
    else:
        filtered = txns

    groups: dict[str, dict[str, Any]] = {}

    for txn in filtered:
        if view == "bottom":
            key = "income" if txn.direction == "credit" else "expenses"
            if key not in groups:
                label = t(lang, "income") if key == "income" else t(lang, "expenses")
                color = "#22C55E" if key == "income" else "#EF4444"
                groups[key] = {
                    "key": key,
                    "name": label,
                    "color": color,
                    "icon": "wallet" if key == "income" else "tag",
                    "total": 0.0,
                    "transactions": [],
                    "category_id": None,
                }
            groups[key]["total"] += txn.amount
            groups[key]["transactions"].append(txn)
            continue

        if txn.category_id is None:
            cat_key = "__unsorted__"
            if cat_key not in groups:
                groups[cat_key] = {
                    "key": cat_key,
                    "name": t(lang, "unsorted"),
                    "color": "#9CA3AF",
                    "icon": "question",
                    "total": 0.0,
                    "transactions": [],
                    "category_id": None,
                }
            groups[cat_key]["total"] += txn.amount
            groups[cat_key]["transactions"].append(txn)
        else:
            cat = txn.category
            key = str(cat.id)
            if key not in groups:
                groups[key] = {
                    "key": key,
                    "name": category_name(lang, cat),
                    "color": cat.color,
                    "icon": cat.icon,
                    "total": 0.0,
                    "transactions": [],
                    "category_id": cat.id,
                    "sort_order": cat.sort_order,
                }
            groups[key]["total"] += txn.amount
            groups[key]["transactions"].append(txn)

    grand = sum(g["total"] for g in groups.values())
    categories = sorted(
        groups.values(),
        key=lambda g: (-g["total"], g.get("sort_order", 999)),
    )
    for g in categories:
        g["pct"] = round((g["total"] / grand * 100) if grand else 0, 2)
        g["transactions"].sort(
            key=lambda x: (
                x.txn_date.toordinal() * -1,
                getattr(x, "split_group", "") or f"~{x.id}",
                x.id,
            )
        )
        g["txns"] = [serialize_txn(lang, x) for x in g["transactions"]]
        del g["transactions"]

    expense_total = sum(t.amount for t in txns if t.direction == "debit")
    income_total = sum(t.amount for t in txns if t.direction == "credit")

    unsorted_expense = [
        serialize_txn(lang, x)
        for x in sorted(
            [t for t in txns if t.direction == "debit" and t.category_id is None],
            key=lambda t: (t.value_date or t.txn_date, t.txn_date, t.id),
            reverse=True,
        )
    ]

    return {
        "categories": categories,
        "grand_total": grand,
        "expense_total": expense_total,
        "income_total": income_total,
        "net": income_total - expense_total,
        "unsorted": unsorted_expense,
        "unsorted_count": len(unsorted_expense),
        "pie": {
            "labels": [c["name"] for c in categories],
            "values": [round(c["total"], 2) for c in categories],
            "colors": [c["color"] for c in categories],
        },
    }
