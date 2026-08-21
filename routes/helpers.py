"""Shared request helpers for blueprints."""

from __future__ import annotations

from flask import request

from i18n import get_lang


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
