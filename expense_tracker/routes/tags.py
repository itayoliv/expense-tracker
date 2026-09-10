"""Tag CRUD API routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from expense_tracker.db import get_session
from expense_tracker.i18n import t
from expense_tracker.models import Category, Tag, TagSumFormula, Transaction
from expense_tracker.routes.helpers import lang
from expense_tracker.services.payloads import (
    list_tag_formula_payloads,
    list_tag_payloads,
    normalize_color,
    parse_tag_ids,
    resolve_tags,
    tag_formula_payload,
    tag_payload,
)
from expense_tracker.services.summary import serialize_txn

bp = Blueprint("tags", __name__)


def _formula_scope(session, raw_scope) -> str:
    scope = str(raw_scope or "global").strip()
    if scope == "global" or scope in {
        "category:__unsorted__",
        "category:income",
        "category:expenses",
    }:
        return scope
    if not scope.startswith("category:"):
        raise ValueError("Unknown formula scope")
    try:
        category_id = int(scope.removeprefix("category:"))
    except ValueError as exc:
        raise ValueError("Unknown formula scope") from exc
    if not session.get(Category, category_id):
        raise ValueError("Unknown formula scope")
    return f"category:{category_id}"


@bp.route("/api/tags", methods=["GET"])
def list_tags():
    with get_session() as session:
        return jsonify({"ok": True, "tags": list_tag_payloads(session)})


@bp.route("/api/tags", methods=["POST"])
def create_tag():
    current_lang = lang()
    payload = request.get_json(silent=True) or {}
    try:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("Name is required")
        if len(name) > 128:
            raise ValueError("Name is too long")
        color = normalize_color(payload.get("color"))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    with get_session() as session:
        existing = session.scalars(select(Tag).where(Tag.name == name)).first()
        if existing:
            return jsonify({"ok": False, "error": "A tag with this name already exists"}), 400
        tag = Tag(name=name, color=color)
        session.add(tag)
        session.commit()
        return jsonify(
            {
                "ok": True,
                "tag": tag_payload(tag),
                "message": t(current_lang, "tag_saved"),
            }
        )


@bp.route("/api/tags/<int:tag_id>", methods=["PATCH", "PUT"])
def update_tag(tag_id: int):
    current_lang = lang()
    payload = request.get_json(silent=True) or {}

    with get_session() as session:
        tag = session.get(Tag, tag_id)
        if not tag:
            return jsonify({"ok": False, "error": "Not found"}), 404

        try:
            if "name" in payload and payload["name"] is not None:
                name = str(payload["name"]).strip()
                if not name:
                    raise ValueError("Name is required")
                if len(name) > 128:
                    raise ValueError("Name is too long")
                clash = session.scalars(
                    select(Tag).where(Tag.name == name, Tag.id != tag_id)
                ).first()
                if clash:
                    raise ValueError("A tag with this name already exists")
                tag.name = name
            if "color" in payload and payload["color"] is not None:
                tag.color = normalize_color(payload["color"])
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        session.commit()
        txns = list(tag.transactions or [])
        return jsonify(
            {
                "ok": True,
                "tag": tag_payload(
                    tag,
                    txn_count=len(txns),
                    total=sum(float(txn.amount or 0) for txn in txns),
                ),
                "message": t(current_lang, "tag_saved"),
            }
        )


@bp.route("/api/tags/<int:tag_id>", methods=["DELETE"])
def delete_tag(tag_id: int):
    current_lang = lang()
    with get_session() as session:
        tag = session.get(Tag, tag_id)
        if not tag:
            return jsonify({"ok": False, "error": "Not found"}), 404
        tag.transactions = []
        tag.formulas = []
        session.delete(tag)
        session.commit()
    return jsonify({"ok": True, "message": t(current_lang, "tag_deleted")})


@bp.route("/api/tags/<int:tag_id>/transactions", methods=["GET"])
def tag_transactions(tag_id: int):
    current_lang = lang()
    with get_session() as session:
        tag = session.scalars(
            select(Tag)
            .where(Tag.id == tag_id)
            .options(selectinload(Tag.transactions).selectinload(Transaction.tags))
        ).first()
        if not tag:
            return jsonify({"ok": False, "error": "Not found"}), 404
        txns = sorted(
            tag.transactions or [],
            key=lambda x: (
                x.txn_date.toordinal() * -1,
                x.id,
            ),
        )
        return jsonify(
            {
                "ok": True,
                "tag": tag_payload(
                    tag,
                    txn_count=len(txns),
                    total=sum(float(txn.amount or 0) for txn in txns),
                ),
                "transactions": [serialize_txn(current_lang, x) for x in txns],
            }
        )


@bp.route("/api/tag-formulas", methods=["GET"])
def list_tag_formulas():
    with get_session() as session:
        return jsonify(
            {"ok": True, "formulas": list_tag_formula_payloads(session)}
        )


@bp.route("/api/tag-formulas", methods=["POST"])
def create_tag_formula():
    payload = request.get_json(silent=True) or {}
    try:
        tag_ids = parse_tag_ids(payload)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    with get_session() as session:
        try:
            tags = resolve_tags(session, tag_ids or [])
            scope = _formula_scope(session, payload.get("scope"))
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        highest = session.scalar(
            select(func.max(TagSumFormula.sort_order)).where(
                TagSumFormula.scope == scope
            )
        ) or 0
        formula = TagSumFormula(scope=scope, sort_order=highest + 100, tags=tags)
        session.add(formula)
        session.commit()
        return jsonify({"ok": True, "formula": tag_formula_payload(formula)})


@bp.route("/api/tag-formulas/<int:formula_id>", methods=["PATCH"])
def update_tag_formula(formula_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        tag_ids = parse_tag_ids(payload)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    with get_session() as session:
        formula = session.get(TagSumFormula, formula_id)
        if not formula:
            return jsonify({"ok": False, "error": "Not found"}), 404
        if tag_ids is not None:
            try:
                formula.tags = resolve_tags(session, tag_ids)
            except ValueError as e:
                return jsonify({"ok": False, "error": str(e)}), 400
        session.commit()
        return jsonify({"ok": True, "formula": tag_formula_payload(formula)})


@bp.route("/api/tag-formulas/<int:formula_id>", methods=["DELETE"])
def delete_tag_formula(formula_id: int):
    with get_session() as session:
        formula = session.get(TagSumFormula, formula_id)
        if not formula:
            return jsonify({"ok": False, "error": "Not found"}), 404
        formula.tags = []
        session.delete(formula)
        session.commit()
    return jsonify({"ok": True})
