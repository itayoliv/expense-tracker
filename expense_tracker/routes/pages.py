"""Dashboard, language, and statement import routes."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from werkzeug.utils import secure_filename

from expense_tracker.db import get_session
from expense_tracker.gpt_sort import has_api_key
from expense_tracker.i18n import html_dir, t
from expense_tracker.importer import import_file
from expense_tracker.models import Category
from expense_tracker.routes.helpers import cat_sort_mode, lang, show_pie, sort_categories, view
from expense_tracker.services.payloads import category_payload, list_rule_payloads, list_tag_payloads
from expense_tracker.services.summary import (
    available_months,
    build_summary,
    current_month_key,
    first_day_of_month,
    last_day_of_month,
    parse_date_from_arg,
    parse_iso_date,
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


def _dashboard_dates() -> tuple[date | None, date | None, bool]:
    """Return from/to dates and whether the user chose an explicit range."""
    has_date_args = "date_from" in request.args or "date_to" in request.args
    if has_date_args:
        date_from = parse_date_from_arg(request.args.get("date_from"))
        date_to = parse_iso_date(request.args.get("date_to"))
        if date_from and not date_to:
            date_to = last_day_of_month(date_from)
        return date_from, date_to, True

    month_raw = (request.args.get("month") or "").strip()
    if month_raw:
        if month_raw == "all":
            return None, None, True
        parsed = parse_month(month_raw)
        if parsed:
            y, m = parsed
            start = date(y, m, 1)
            return start, last_day_of_month(start), True
        start = first_day_of_month()
        return start, last_day_of_month(start), False

    start = first_day_of_month()
    return start, last_day_of_month(start), False


@bp.route("/")
def dashboard():
    current_lang = lang()
    current_view = view()

    date_from, date_to, explicit_range = _dashboard_dates()
    if date_from and date_to and date_from > date_to:
        date_to = last_day_of_month(date_from)
    using_range = explicit_range and (date_from is not None or date_to is not None)
    date_from_raw = date_from.isoformat() if date_from else ""
    date_from_month = date_from.strftime("%Y-%m") if date_from else ""
    date_to_raw = date_to.isoformat() if date_to else ""

    with get_session() as session:
        months = available_months(session)
        current_month = current_month_key()
        if months and current_month not in months:
            months = sorted({*months, current_month}, reverse=True)

        sort_mode = cat_sort_mode()
        summary = build_summary(
            session,
            current_view,
            current_lang,
            date_from=date_from,
            date_to=date_to,
            cat_sort=sort_mode,
        )
        categories = sort_categories(
            session.scalars(select(Category)).all(),
            current_lang,
            sort_mode,
        )
        cats_json = [category_payload(current_lang, c) for c in categories]
        rules_json = list_rule_payloads(current_lang, session)
        tags_json = list_tag_payloads(session)

    filter_period: dict[str, str] = {"view": current_view}
    if date_from_raw:
        filter_period["date_from"] = date_from_raw
    if date_to_raw:
        filter_period["date_to"] = date_to_raw
    if using_range and not date_from_raw and not date_to_raw:
        filter_period["date_from"] = ""
        filter_period["date_to"] = ""

    nav_period = {k: v for k, v in filter_period.items() if k != "view"}

    return render_template(
        "dashboard.html",
        lang=current_lang,
        dir=html_dir(current_lang),
        view=current_view,
        month="all",
        months=months,
        date_from=date_from_raw,
        date_from_month=date_from_month,
        date_to=date_to_raw,
        using_range=using_range,
        filter_period=nav_period,
        summary=summary,
        categories=cats_json,
        rules=rules_json,
        tags=tags_json,
        cat_sort=sort_mode,
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
