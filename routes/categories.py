"""Category CRUD API routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from db import get_session
from i18n import t
from models import CategorizationRule, Category, Transaction
from routes.helpers import lang
from services.payloads import category_payload, normalize_color

bp = Blueprint("categories", __name__)


@bp.route("/api/categories", methods=["GET"])
def list_categories():
    current_lang = lang()
    with get_session() as session:
        categories = list(
            session.scalars(
                select(Category).order_by(Category.sort_order, Category.id)
            ).all()
        )
        return jsonify(
            {
                "ok": True,
                "categories": [category_payload(current_lang, c) for c in categories],
            }
        )


@bp.route("/api/categories", methods=["POST"])
def create_category():
    current_lang = lang()
    payload = request.get_json(silent=True) or {}
    try:
        name_en = (payload.get("name_en") or "").strip()
        name_he = (payload.get("name_he") or "").strip()
        if not name_en and not name_he:
            raise ValueError("Name is required")
        if not name_en:
            name_en = name_he
        if not name_he:
            name_he = name_en
        kind = payload.get("kind") or "expense"
        if kind not in ("expense", "income"):
            kind = "expense"
        color = normalize_color(payload.get("color"))
        sort_order = int(payload.get("sort_order") or 100)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    with get_session() as session:
        cat = Category(
            name_en=name_en,
            name_he=name_he,
            color=color,
            kind=kind,
            sort_order=sort_order,
        )
        session.add(cat)
        session.commit()
        return jsonify(
            {
                "ok": True,
                "category": category_payload(current_lang, cat),
                "message": t(current_lang, "category_saved"),
            }
        )


@bp.route("/api/categories/<int:cat_id>", methods=["PATCH", "PUT"])
def update_category(cat_id: int):
    current_lang = lang()
    payload = request.get_json(silent=True) or {}

    with get_session() as session:
        cat = session.get(Category, cat_id)
        if not cat:
            return jsonify({"ok": False, "error": "Not found"}), 404

        try:
            if "name_en" in payload and payload["name_en"] is not None:
                name_en = str(payload["name_en"]).strip()
                if name_en:
                    cat.name_en = name_en
            if "name_he" in payload and payload["name_he"] is not None:
                name_he = str(payload["name_he"]).strip()
                if name_he:
                    cat.name_he = name_he
            if "kind" in payload and payload["kind"] in ("expense", "income"):
                cat.kind = payload["kind"]
            if "color" in payload and payload["color"] is not None:
                cat.color = normalize_color(payload["color"])
            if "sort_order" in payload and payload["sort_order"] not in (None, ""):
                cat.sort_order = int(payload["sort_order"])
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        session.commit()
        return jsonify(
            {
                "ok": True,
                "category": category_payload(current_lang, cat),
                "message": t(current_lang, "category_saved"),
            }
        )


@bp.route("/api/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id: int):
    current_lang = lang()
    with get_session() as session:
        cat = session.get(Category, cat_id)
        if not cat:
            return jsonify({"ok": False, "error": "Not found"}), 404

        for txn in session.scalars(
            select(Transaction).where(Transaction.category_id == cat.id)
        ).all():
            txn.category_id = None

        for rule in session.scalars(
            select(CategorizationRule).where(CategorizationRule.category_id == cat.id)
        ).all():
            session.delete(rule)

        session.delete(cat)
        session.commit()

    return jsonify({"ok": True, "message": t(current_lang, "category_deleted")})
