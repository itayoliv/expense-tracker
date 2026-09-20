"""Dashboard summary building, month/date filters, and source labels."""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any

from sqlalchemy import case, extract, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from expense_tracker.i18n import category_name, t
from expense_tracker.models import Transaction

_INSTALLMENT_RE = re.compile(
    r"(תשלום\s*\d+\s*מתוך\s*\d+)|(\binstallment\b)|(\bpayment\s*\d+\s*of\s*\d+)",
    re.IGNORECASE,
)


def is_installment_details(text: str | None) -> bool:
    """True for card payment-plan lines (e.g. תשלום 7 מתוך 12)."""
    return bool(_INSTALLMENT_RE.search(text or ""))


def is_installment(txn) -> bool:
    return is_installment_details(getattr(txn, "details", None))


def is_installment_sql():
    details = func.coalesce(Transaction.details, "")
    return or_(
        details.like("%תשלום%מתוך%"),
        details.ilike("%installment%"),
        details.ilike("%payment%of%"),
    )


def display_date_column():
    """Billing date for installments, otherwise purchase date."""
    return case(
        (
            is_installment_sql(),
            func.coalesce(Transaction.value_date, Transaction.txn_date),
        ),
        else_=Transaction.txn_date,
    )


def display_txn_date(txn) -> date:
    if is_installment(txn) and getattr(txn, "value_date", None):
        return txn.value_date
    return txn.txn_date


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


def parse_iso_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def parse_date_from_arg(raw: str | None) -> date | None:
    """Accept YYYY-MM-DD or YYYY-MM (month picker → first day)."""
    text = (raw or "").strip()
    if not text:
        return None
    if len(text) == 7 and text[4] == "-":
        parsed = parse_month(text)
        if parsed:
            y, m = parsed
            return date(y, m, 1)
    return parse_iso_date(text)


def parse_date_to_arg(raw: str | None) -> date | None:
    """Accept YYYY-MM-DD or YYYY-MM (month picker → last day of that month)."""
    text = (raw or "").strip()
    if not text:
        return None
    if len(text) == 7 and text[4] == "-":
        parsed = parse_month(text)
        if parsed:
            y, m = parsed
            return last_day_of_month(date(y, m, 1))
    return parse_iso_date(text)

def current_month_key() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def first_day_of_month(when: date | None = None) -> date:
    today = when or date.today()
    return date(today.year, today.month, 1)


def last_day_of_month(when: date) -> date:
    last = calendar.monthrange(when.year, when.month)[1]
    return date(when.year, when.month, last)


def resolve_date_range(
    date_from: date | None, date_to: date | None
) -> tuple[date | None, date | None]:
    """Open-ended to-date means through the end of the from-date month."""
    if not date_from and not date_to:
        return None, None
    start, end = date_from, date_to
    # If To is before From (stale To after changing the month), keep From and
    # snap To to the end of that month — never swap into the previous month.
    if start and end and start > end:
        end = last_day_of_month(start)
    if start and not end:
        end = last_day_of_month(start)
    return start, end


def available_months(session) -> list[str]:
    shown = display_date_column()
    rows = session.execute(
        select(
            extract("year", shown),
            extract("month", shown),
        )
        .distinct()
        .order_by(
            extract("year", shown).desc(),
            extract("month", shown).desc(),
        )
    ).all()
    return [f"{int(y):04d}-{int(m):02d}" for y, m in rows if y and m]


def month_filter(query, month: tuple[int, int] | None):
    if month:
        y, m = month
        shown = display_date_column()
        query = query.where(
            extract("year", shown) == y,
            extract("month", shown) == m,
        )
    return query


def date_range_filter(query, date_from: date | None, date_to: date | None):
    """Filter by purchase date, except installment rows use billing date."""
    if not date_from and not date_to:
        return query
    start, end = resolve_date_range(date_from, date_to)
    shown = display_date_column()
    if start:
        query = query.where(shown >= start)
    if end:
        query = query.where(shown <= end)
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


def is_ignored(txn) -> bool:
    return bool(getattr(txn, "ignored", False))


def serialize_txn(lang: str, x) -> dict[str, Any]:
    tags = [
        {"id": tag.id, "name": tag.name, "color": tag.color}
        for tag in sorted(
            getattr(x, "tags", None) or [],
            key=lambda t: (t.name or "").casefold(),
        )
    ]
    return {
        "id": x.id,
        "description": x.description,
        "details": x.details,
        "custom_description": getattr(x, "custom_description", "") or "",
        "date": display_txn_date(x).strftime("%d/%m/%y"),
        "amount": x.amount,
        "direction": x.direction,
        "category_id": x.category_id,
        "categorized_by": x.categorized_by or "",
        "ignored": is_ignored(x),
        "ignore_reason": getattr(x, "ignore_reason", "") or "",
        "tags": tags,
        **split_accent(getattr(x, "split_group", "") or ""),
        **txn_source_fields(lang, x),
    }


def has_card_detail_imports(txns: list) -> bool:
    """True if any transaction looks like an Isracard line item."""
    return any(source_kind(t) == "card" for t in txns)


def is_bank_card_lump(txn) -> bool:
    """Bank statement lump charge for a credit card (not a merchant line item)."""
    desc = (txn.description or "").lower()
    lumps = ("ישראכרט", "ויזה", "מקס", "מאסטרכארד")
    if not any(x in desc for x in lumps) and "חיוב לכרטיס" not in desc:
        return False
    return source_kind(txn) != "card"


def build_summary(
    session,
    view: str,
    lang: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    cat_sort: str = "alpha",
    cat_sort_direction: str = "asc",
) -> dict:
    base = select(Transaction).options(
        joinedload(Transaction.category),
        selectinload(Transaction.tags),
    )
    start, end = resolve_date_range(date_from, date_to)
    if start or end:
        base = date_range_filter(base, start, end)
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
        count_amount = not is_ignored(txn)
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
            if count_amount:
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
            if count_amount:
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
            if count_amount:
                groups[key]["total"] += txn.amount
            groups[key]["transactions"].append(txn)

    grand = sum(g["total"] for g in groups.values())

    unsorted_group = groups.pop("__unsorted__", None)
    if cat_sort == "value":
        group_key = lambda g: (g["total"], (g.get("name") or "").casefold())
    else:
        group_key = lambda g: ((g.get("name") or "").casefold(), g.get("key") or "")
    categories = sorted(
        groups.values(),
        key=group_key,
        reverse=cat_sort_direction == "desc",
    )
    if unsorted_group:
        categories.append(unsorted_group)
    for g in categories:
        g["pct"] = round((g["total"] / grand * 100) if grand else 0, 2)
        if cat_sort == "value":
            txn_key = lambda x: (x.amount, display_txn_date(x), x.id)
        else:
            txn_key = lambda x: (
                (x.custom_description or x.description or "").casefold(),
                display_txn_date(x),
                x.id,
            )
        g["transactions"].sort(
            key=txn_key,
            reverse=cat_sort_direction == "desc",
        )
        g["txns"] = [serialize_txn(lang, x) for x in g["transactions"]]
        del g["transactions"]

    expense_total = sum(
        t.amount for t in txns if t.direction == "debit" and not is_ignored(t)
    )
    income_total = sum(
        t.amount for t in txns if t.direction == "credit" and not is_ignored(t)
    )

    unsorted_expense = [
        serialize_txn(lang, x)
        for x in sorted(
            [
                t
                for t in txns
                if t.direction == "debit"
                and t.category_id is None
                and not is_ignored(t)
            ],
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
