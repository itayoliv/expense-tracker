"""Default category seed data."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_tracker.models import Category

SEED_CATEGORIES = [
    {
        "key": "culture_leisure",
        "name_en": "Culture and leisure",
        "name_he": "תרבות ופנאי",
        "color": "#8B5CF6",
        "icon": "theater",
        "sort_order": 10,
        "kind": "expense",
    },
    {
        "key": "food_groceries",
        "name_en": "Food and groceries",
        "name_he": "מזון וקניות",
        "color": "#F97316",
        "icon": "cart",
        "sort_order": 15,
        "kind": "expense",
    },
    {
        "key": "fuel_transport",
        "name_en": "Fuel and transport",
        "name_he": "דלק ותחבורה",
        "color": "#0EA5E9",
        "icon": "car",
        "sort_order": 18,
        "kind": "expense",
    },
    {
        "key": "insurance",
        "name_en": "Insurance",
        "name_he": "ביטוח",
        "color": "#3B82F6",
        "icon": "umbrella",
        "sort_order": 20,
        "kind": "expense",
    },
    {
        "key": "health",
        "name_en": "Health",
        "name_he": "בריאות",
        "color": "#E11D48",
        "icon": "heart",
        "sort_order": 25,
        "kind": "expense",
    },
    {
        "key": "taxes_payments",
        "name_en": "Taxes and payments",
        "name_he": "מיסים ותשלומים",
        "color": "#EF4444",
        "icon": "building",
        "sort_order": 30,
        "kind": "expense",
    },
    {
        "key": "loans_mortgage",
        "name_en": "Loans and mortgage",
        "name_he": "הלוואות ומשכנתא",
        "color": "#F59E0B",
        "icon": "piggy",
        "sort_order": 40,
        "kind": "expense",
    },
    {
        "key": "banking",
        "name_en": "Banking services",
        "name_he": "שירותים בנקאיים",
        "color": "#06B6D4",
        "icon": "bank",
        "sort_order": 50,
        "kind": "expense",
    },
    {
        "key": "credit_cards",
        "name_en": "Credit cards",
        "name_he": "כרטיסי אשראי",
        "color": "#EC4899",
        "icon": "card",
        "sort_order": 60,
        "kind": "expense",
    },
    {
        "key": "shopping",
        "name_en": "Shopping",
        "name_he": "קניות",
        "color": "#D946EF",
        "icon": "bag",
        "sort_order": 65,
        "kind": "expense",
    },
    {
        "key": "travel",
        "name_en": "Travel",
        "name_he": "נסיעות",
        "color": "#14B8A6",
        "icon": "plane",
        "sort_order": 68,
        "kind": "expense",
    },
    {
        "key": "subscriptions",
        "name_en": "Subscriptions",
        "name_he": "מנויים",
        "color": "#A855F7",
        "icon": "repeat",
        "sort_order": 72,
        "kind": "expense",
    },
    {
        "key": "pension_savings",
        "name_en": "Pension and savings",
        "name_he": "פנסיה וגמל",
        "color": "#10B981",
        "icon": "leaf",
        "sort_order": 70,
        "kind": "expense",
    },
    {
        "key": "transfers",
        "name_en": "Transfers",
        "name_he": "העברות",
        "color": "#6366F1",
        "icon": "swap",
        "sort_order": 80,
        "kind": "expense",
    },
    {
        "key": "miscellaneous",
        "name_en": "Miscellaneous",
        "name_he": "שונות",
        "color": "#9CA3AF",
        "icon": "dots",
        "sort_order": 90,
        "kind": "expense",
    },
    {
        "key": "income",
        "name_en": "Income",
        "name_he": "הכנסות",
        "color": "#22C55E",
        "icon": "wallet",
        "sort_order": 5,
        "kind": "income",
    },
]


def seed_defaults(session: Session) -> dict[str, int]:
    """Insert any missing seed categories. Does not overwrite existing rows or add rules."""
    return {
        "categories_added": _seed_categories(session),
        "rules_added": 0,
    }


def _seed_categories(session: Session) -> int:
    existing = {c.name_en for c in session.scalars(select(Category)).all()}
    added = 0
    for spec in SEED_CATEGORIES:
        if spec["name_en"] in existing:
            continue
        fields = {k: v for k, v in spec.items() if k != "key"}
        session.add(Category(**fields))
        added += 1
    if added:
        session.flush()
    return added
