"""API payload builders and validators for categories and rules."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from categorizer import category_map
from i18n import category_name
from models import CategorizationRule, Category

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_color(raw: str | None) -> str:
    color = (raw or "").strip()
    if not color:
        return "#6B7280"
    if not color.startswith("#"):
        color = f"#{color}"
    if not HEX_COLOR_RE.match(color):
        raise ValueError("Color must be a hex value like #22C55E")
    return color.upper()


def category_payload(lang: str, cat: Category) -> dict[str, Any]:
    return {
        "id": cat.id,
        "name": category_name(lang, cat),
        "name_en": cat.name_en,
        "name_he": cat.name_he,
        "kind": cat.kind,
        "color": cat.color,
        "sort_order": cat.sort_order,
    }


def rule_payload(
    lang: str, rule: CategorizationRule, cats: dict[int, Category]
) -> dict[str, Any]:
    cat = cats.get(rule.category_id)
    return {
        "id": rule.id,
        "name": rule.name or "",
        "display_name": rule.display_name,
        "pattern": rule.pattern,
        "category_id": rule.category_id,
        "priority": rule.priority,
        "category_name": category_name(lang, cat) if cat else "",
        "category_color": cat.color if cat else "#9CA3AF",
        "category_missing": cat is None,
    }


def list_rule_payloads(lang: str, session) -> list[dict[str, Any]]:
    cats = category_map(session)
    rules = session.scalars(
        select(CategorizationRule).order_by(
            CategorizationRule.priority.desc(),
            CategorizationRule.id,
        )
    ).all()
    return [rule_payload(lang, rule, cats) for rule in rules]


def parse_rule_fields(payload: dict, *, partial: bool = False) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if len(name) > 128:
            raise ValueError("Name is too long")
        fields["name"] = name
    if not partial or "pattern" in payload:
        pattern = str(payload.get("pattern") or "").strip()
        if not pattern:
            raise ValueError("Pattern is required")
        if len(pattern) > 256:
            raise ValueError("Pattern is too long")
        fields["pattern"] = pattern
    if not partial or "category_id" in payload:
        raw_cid = payload.get("category_id")
        if raw_cid in (None, "", "null"):
            raise ValueError("Category is required")
        try:
            fields["category_id"] = int(raw_cid)
        except (TypeError, ValueError) as exc:
            raise ValueError("Category is required") from exc
    if not partial or "priority" in payload:
        raw_priority = payload.get("priority", 100 if not partial else None)
        if raw_priority not in (None, ""):
            try:
                fields["priority"] = int(raw_priority)
            except (TypeError, ValueError) as exc:
                raise ValueError("Priority must be a number") from exc
    return fields


def require_category_id(session, category_id: int) -> Category:
    cat = session.get(Category, category_id)
    if not cat:
        raise ValueError("Unknown category")
    return cat


def ensure_unique_rule(
    session, pattern: str, category_id: int, exclude_id: int | None = None
) -> None:
    existing = session.scalars(
        select(CategorizationRule).where(
            CategorizationRule.pattern == pattern,
            CategorizationRule.category_id == category_id,
        )
    ).first()
    if existing and existing.id != exclude_id:
        raise ValueError("A rule with this pattern and category already exists")
