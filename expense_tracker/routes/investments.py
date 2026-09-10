"""Yahoo Finance investments / portfolios page."""

from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, select

from expense_tracker.db import get_session
from expense_tracker.integrations.gpt_sort import has_api_key
from expense_tracker.i18n import html_dir, t
from expense_tracker.services.investment_sectors import (
    aggregate_sector_allocation,
    classify_portfolio_symbols,
    count_unassigned_symbols,
)
from expense_tracker.models import Category, InvestmentFxConversion
from expense_tracker.routes.helpers import (
    cat_sort_direction,
    cat_sort_mode,
    lang,
    show_pie,
    sort_categories,
)
from expense_tracker.services.payloads import category_payload, list_rule_payloads, list_tag_payloads
from expense_tracker.integrations.yahoo import (
    YahooFinanceError,
    build_holdings_history,
    fetch_live_quotes,
    fetch_portfolios,
    fetch_usd_ils_rate,
    fetch_usd_ils_rate_on_date,
    is_connected,
    load_cache,
)

bp = Blueprint("investments", __name__)


def _empty_summary() -> dict:
    return {
        "pie": {"labels": [], "values": [], "colors": []},
        "categories": [],
        "unsorted": [],
        "unsorted_count": 0,
        "grand_total": 0,
        "expense_total": 0,
        "income_total": 0,
        "net": 0,
    }


def _format_updated(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


@bp.route("/investments")
def investments():
    current_lang = lang()
    cache = load_cache() or {}
    portfolios = cache.get("portfolios") or []
    connected = is_connected()
    usd_ils = 0.0
    if portfolios:
        try:
            usd_ils = fetch_usd_ils_rate()
        except Exception:
            usd_ils = 0.0

    with get_session() as session:
        sort_mode = cat_sort_mode()
        sort_direction = cat_sort_direction()
        categories = sort_categories(
            session.scalars(select(Category)).all(),
            current_lang,
            sort_mode,
        )
        cats_json = [category_payload(current_lang, c) for c in categories]
        rules_json = list_rule_payloads(current_lang, session)
        tags_json = list_tag_payloads(session)
        conversions = session.scalars(
            select(InvestmentFxConversion).order_by(
                InvestmentFxConversion.conversion_date.desc(),
                InvestmentFxConversion.id.desc(),
            )
        ).all()
        onezero_saved_total = round(
            sum(float(item.saved_nis or 0) for item in conversions), 2
        )

    return render_template(
        "investments.html",
        lang=current_lang,
        dir=html_dir(current_lang),
        view="investments",
        month="all",
        date_from="",
        date_from_month="",
        date_to="",
        date_to_month="",
        using_range=False,
        filter_period={},
        categories=cats_json,
        rules=rules_json,
        tags=tags_json,
        summary=_empty_summary(),
        cat_sort=sort_mode,
        cat_sort_direction=sort_direction,
        show_pie=show_pie(),
        openai_key_set=has_api_key(),
        connected=connected,
        portfolios=portfolios,
        grand_total=cache.get("grand_total") or 0,
        usd_ils=usd_ils,
        fx_conversions=conversions,
        onezero_saved_total=onezero_saved_total,
        today=date.today().isoformat(),
        updated_at=_format_updated(cache.get("updated_at")),
        has_cache=bool(portfolios),
        t=lambda k, **kw: t(current_lang, k, **kw),
    )


@bp.route("/investments/conversions", methods=["POST"])
def create_conversion():
    current_lang = lang()
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    try:
        amount = float(request.form.get("nis_amount") or 0)
        if amount <= 0:
            raise ValueError(t(current_lang, "fx_conversion_invalid_amount"))
        conversion_date = date.fromisoformat(
            (request.form.get("conversion_date") or "").strip()
        )
        if conversion_date > date.today():
            raise ValueError(t(current_lang, "fx_conversion_future_date"))
        rate = fetch_usd_ils_rate_on_date(conversion_date)
        if rate <= 0:
            raise ValueError(t(current_lang, "fx_conversion_rate_unavailable"))

        onezero_fee_rate = 0.08
        comparison_fee_rate = 0.70
        conversion = InvestmentFxConversion(
            conversion_date=conversion_date,
            nis_amount=round(amount, 2),
            usd_ils_rate=rate,
            usd_amount=round(amount / rate, 2),
            onezero_fee_rate=onezero_fee_rate,
            comparison_name="Meitav Trade",
            comparison_fee_rate=comparison_fee_rate,
            saved_nis=round(
                amount * ((comparison_fee_rate - onezero_fee_rate) / 100), 2
            ),
        )
        with get_session() as session:
            session.add(conversion)
            session.commit()
            saved_total = float(
                session.scalar(select(func.sum(InvestmentFxConversion.saved_nis)))
                or 0
            )
        message = t(current_lang, "fx_conversion_saved")
        if wants_json:
            return jsonify(
                {
                    "ok": True,
                    "message": message,
                    "conversion": {
                        "id": conversion.id,
                        "conversion_date": conversion.conversion_date.isoformat(),
                        "nis_amount": conversion.nis_amount,
                        "usd_ils_rate": conversion.usd_ils_rate,
                        "usd_amount": conversion.usd_amount,
                        "saved_nis": conversion.saved_nis,
                    },
                    "onezero_saved_total": round(saved_total, 2),
                }
            )
        flash(message, "success")
    except (TypeError, ValueError) as exc:
        if wants_json:
            return jsonify({"ok": False, "error": str(exc)}), 400
        flash(str(exc), "error")
    except Exception as exc:
        message = t(current_lang, "fx_conversion_save_error", error=str(exc))
        if wants_json:
            return jsonify({"ok": False, "error": message}), 502
        flash(message, "error")
    return redirect(url_for("investments.investments") + "#fx-savings-panel")


@bp.route("/investments/quotes")
def quotes():
    """Live / extended-hours prices for symbols in the cached portfolios."""
    cache = load_cache() or {}
    symbols: list[str] = []
    for pf in cache.get("portfolios") or []:
        for h in pf.get("holdings") or []:
            sym = h.get("symbol")
            if sym:
                symbols.append(str(sym))
    if not symbols:
        rate = 0.0
        try:
            rate = fetch_usd_ils_rate()
        except Exception:
            rate = 0.0
        return jsonify({"quotes": {}, "live": False, "usd_ils": rate, "updated_at": None})
    try:
        payload = fetch_live_quotes(symbols)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "quotes": {}, "live": False, "usd_ils": 0}), 502
    return jsonify({"ok": True, **payload})


@bp.route("/investments/sectors")
def sectors():
    """Sector allocation for all portfolios or one selected portfolio."""
    cache = load_cache() or {}
    portfolios = cache.get("portfolios") or []
    portfolio_id = (request.args.get("portfolio") or "all").strip() or "all"
    payload = aggregate_sector_allocation(
        portfolios, portfolio_id=portfolio_id, lang=lang()
    )
    return jsonify(payload)


@bp.route("/investments/history")
def history():
    """Holdings value over time for all portfolios or one selected portfolio."""
    cache = load_cache() or {}
    portfolios = cache.get("portfolios") or []
    portfolio_id = (request.args.get("portfolio") or "all").strip() or "all"
    range_key = (request.args.get("range") or "6mo").strip() or "6mo"
    try:
        payload = build_holdings_history(portfolios, portfolio_id=portfolio_id, range_key=range_key)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "labels": [], "values": []}), 502
    return jsonify(payload)


@bp.route("/investments/refresh", methods=["POST"])
def refresh():
    current_lang = lang()
    try:
        data = fetch_portfolios()
        portfolios = data.get("portfolios") or []
        n = len(portfolios)
        parts = [t(current_lang, "investments_refresh_success", n=n)]

        if has_api_key():
            try:
                result = classify_portfolio_symbols(portfolios)
                if result.get("classified"):
                    parts.append(
                        t(
                            current_lang,
                            "investments_sectors_classified",
                            n=result["classified"],
                        )
                    )
                if result.get("unknown"):
                    parts.append(
                        t(
                            current_lang,
                            "investments_sectors_unknown",
                            n=result["unknown"],
                        )
                    )
            except Exception as exc:
                parts.append(
                    t(current_lang, "investments_sectors_error", error=str(exc))
                )
        elif count_unassigned_symbols(portfolios) > 0:
            flash(t(current_lang, "investments_sectors_skipped_no_key"), "info")

        flash(" ".join(parts), "success")
    except YahooFinanceError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        flash(t(current_lang, "investments_refresh_error", error=str(exc)), "error")
    return redirect(url_for("investments.investments"))
