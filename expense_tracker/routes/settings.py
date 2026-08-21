"""Settings and GPT sort API routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import delete, func, select

from expense_tracker.db import get_session, seed_defaults
from expense_tracker.gpt_sort import (
    GptSortError,
    clear_api_key,
    save_api_key,
    sort_unsorted_expenses,
)
from expense_tracker.i18n import t
from expense_tracker.models import CategorizationRule, Transaction
from expense_tracker.routes.helpers import lang

bp = Blueprint("settings", __name__)


@bp.route("/api/settings/seed", methods=["POST"])
def seed_default_categories():
    current_lang = lang()
    with get_session() as session:
        result = seed_defaults(session)
        session.commit()
    n = result["categories_added"]
    message = (
        t(current_lang, "seed_categories_success", n=n)
        if n
        else t(current_lang, "seed_categories_none")
    )
    return jsonify({"ok": True, "message": message, **result})


@bp.route("/api/settings/clear-transactions", methods=["POST"])
def clear_transactions():
    current_lang = lang()
    with get_session() as session:
        count = session.scalar(select(func.count()).select_from(Transaction)) or 0
        session.execute(delete(Transaction))
        session.commit()
    message = (
        t(current_lang, "clear_transactions_success", n=count)
        if count
        else t(current_lang, "clear_transactions_none")
    )
    return jsonify({"ok": True, "deleted": count, "message": message})


@bp.route("/api/settings/reset-rules", methods=["POST"])
def reset_rules():
    current_lang = lang()
    with get_session() as session:
        count = (
            session.scalar(select(func.count()).select_from(CategorizationRule)) or 0
        )
        session.execute(delete(CategorizationRule))
        session.commit()
    message = (
        t(current_lang, "reset_rules_success", n=count)
        if count
        else t(current_lang, "reset_rules_none")
    )
    return jsonify({"ok": True, "deleted": count, "message": message})


@bp.route("/api/settings/openai-key", methods=["POST"])
def set_openai_key():
    current_lang = lang()
    payload = request.get_json(silent=True) or request.form
    try:
        if payload.get("clear") in (True, "true", "1", "on"):
            clear_api_key()
            message = t(current_lang, "openai_key_cleared")
            return jsonify({"ok": True, "has_key": False, "message": message})
        save_api_key(str(payload.get("api_key") or ""))
    except GptSortError as e:
        return jsonify({"ok": False, "error": e.message}), e.status
    return jsonify(
        {
            "ok": True,
            "has_key": True,
            "message": t(current_lang, "openai_key_saved"),
        }
    )


@bp.route("/api/gpt/sort", methods=["POST"])
def gpt_sort_unsorted():
    current_lang = lang()
    try:
        with get_session() as session:
            result = sort_unsorted_expenses(session)
            session.commit()
    except GptSortError as e:
        return jsonify({"ok": False, "error": e.message}), e.status
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    assigned = result["assigned"]
    skipped = result["skipped"]
    if assigned:
        message = t(current_lang, "gpt_sort_success", n=assigned)
    elif skipped:
        message = t(current_lang, "gpt_sort_none")
    else:
        message = t(current_lang, "no_unsorted")
    return jsonify(
        {
            "ok": True,
            "assigned": assigned,
            "skipped": skipped,
            "message": message,
        }
    )


@bp.route("/api/settings/pie", methods=["POST"])
def set_pie_visibility():
    payload = request.get_json(silent=True) or request.form
    raw = payload.get("show_pie")
    if isinstance(raw, str):
        show = raw.strip().lower() not in ("0", "false", "off", "")
    else:
        show = bool(raw) if raw is not None else True
    resp = jsonify({"ok": True, "show_pie": show})
    resp.set_cookie("show_pie", "1" if show else "0", max_age=365 * 24 * 3600)
    return resp
