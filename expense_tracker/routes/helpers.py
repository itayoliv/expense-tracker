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
    """Dashboard order: alphabetical (default) or by value."""
    raw = (request.cookies.get("cat_sort") or "").strip().lower()
    return "value" if raw == "value" else "alpha"


def cat_sort_direction() -> str:
    """Dashboard sort direction: ascending (default) or descending."""
    raw = (request.cookies.get("cat_sort_dir") or "").strip().lower()
    return "desc" if raw == "desc" else "asc"


def sort_categories(categories, current_lang: str | None = None, mode: str | None = None):
    """Return management categories alphabetically; values exist only in summaries."""
    cats = list(categories)
    lang_code = current_lang or lang()
    cats.sort(
        key=lambda c: (
            category_name(lang_code, c).casefold(),
            getattr(c, "id", 0),
        )
    )
    return cats