"""Shared request helpers for blueprints."""

from __future__ import annotations

from flask import request

from expense_tracker.i18n import category_name, get_lang


def lang() -> str:
    return get_lang(request.cookies.get("lang"))


def view() -> str:
    v = request.args.get("view", "expenses")
    return v if v in ("expenses", "income", "bottom") else "expenses"


def show_pie() -> bool:
    raw = request.cookies.get("show_pie")
    if raw is None:
        return True
    return raw not in ("0", "false", "off", "")


def cat_sort_mode() -> str:
    """Category list order: alpha (default) or custom sort_order."""
    raw = (request.cookies.get("cat_sort") or "").strip().lower()
    return "custom" if raw == "custom" else "alpha"


def sort_categories(categories, current_lang: str | None = None, mode: str | None = None):
    """Return categories ordered by A-Z name or custom sort_order."""
    cats = list(categories)
    sort_mode = mode or cat_sort_mode()
    lang_code = current_lang or lang()
    if sort_mode == "custom":
        cats.sort(key=lambda c: (getattr(c, "sort_order", 999), getattr(c, "id", 0)))
    else:
        cats.sort(
            key=lambda c: (
                category_name(lang_code, c).casefold(),
                getattr(c, "id", 0),
            )
        )
    return cats