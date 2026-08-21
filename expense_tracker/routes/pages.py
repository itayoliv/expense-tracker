"""Dashboard, language, and statement import routes."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from werkzeug.utils import secure_filename

from expense_tracker.db import get_session
from expense_tracker.gpt_sort import has_api_key
from expense_tracker.i18n import html_dir, t
from expense_tracker.importer import import_file
from expense_tracker.models import Category
from expense_tracker.routes.helpers import lang, show_pie, view
from expense_tracker.services.payloads import category_payload, list_rule_payloads
from expense_tracker.services.summary import (
    available_months,
    build_summary,
    current_month_key,
    parse_month,
)

bp = Blueprint("pages", __name__)

ALLOWED_EXT = {".csv", ".xlsx", ".xls"}


def _upload_ext(filename: str) -> str:
    if "." not in (filename or ""):
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def _allowed_upload(storage) -> bool:
    original = storage.filename or ""
    secure_name = secure_filename(original) or "upload.xlsx"
    ext = _upload_ext(secure_name)
    if ext in ALLOWED_EXT:
        return True
    return _upload_ext(original) in ALLOWED_EXT


@bp.route("/")
def dashboard():
    current_lang = lang()
    current_view = view()
    current_month = current_month_key()

    with get_session() as session:
        months = available_months(session)
        if months and current_month not in months:
            months = sorted({*months, current_month}, reverse=True)

        if "month" not in request.args:
            if months:
                month_raw = current_month
                month = parse_month(current_month)
            else:
                month_raw = "all"
                month = None
        else:
            month_raw = request.args.get("month") or "all"
            month = parse_month(month_raw)
            if month_raw != "all" and month is None:
                month_raw = current_month if months else "all"
                month = parse_month(month_raw)

        summary = build_summary(session, current_view, month, current_lang)
        categories = list(
            session.scalars(select(Category).order_by(Category.sort_order)).all()
        )
        cats_json = [category_payload(current_lang, c) for c in categories]
        rules_json = list_rule_payloads(current_lang, session)

    return render_template(
        "dashboard.html",
        lang=current_lang,
        dir=html_dir(current_lang),
        view=current_view,
        month=month_raw,
        months=months,
        summary=summary,
        categories=cats_json,
        rules=rules_json,
        show_pie=show_pie(),
        openai_key_set=has_api_key(),
        t=lambda k, **kw: t(current_lang, k, **kw),
    )


@bp.route("/set-lang/<lang>")
def set_lang(lang: str):
    if lang not in ("en", "he"):
        lang = "en"
    next_url = request.args.get("next") or url_for("pages.dashboard")
    resp = redirect(next_url)
    resp.set_cookie("lang", lang, max_age=365 * 24 * 3600)
    return resp


@bp.route("/import", methods=["POST"])
def import_statement():
    current_lang = lang()
    uploads = [f for f in request.files.getlist("file") if f and f.filename]
    if not uploads:
        flash(t(current_lang, "import_error", error="No file selected"), "error")
        return redirect(url_for("pages.dashboard"))

    added = 0
    skipped = 0
    errors: list[str] = []
    for storage in uploads:
        original = storage.filename
        if not _allowed_upload(storage):
            errors.append(f"{original}: Use CSV or XLSX")
            continue
        try:
            data = storage.read()
            with get_session() as session:
                result = import_file(session, data, original)
            added += result["added"]
            skipped += result["skipped"]
        except Exception as e:
            errors.append(f"{original}: {e}")

    if added or skipped:
        flash(
            t(current_lang, "import_success", added=added, skipped=skipped),
            "success",
        )
    if errors:
        flash(t(current_lang, "import_error", error="; ".join(errors)), "error")
    elif not added and not skipped:
        flash(t(current_lang, "import_error", error="No file selected"), "error")

    return redirect(
        url_for("pages.dashboard", view=request.form.get("view", "expenses"))
    )
