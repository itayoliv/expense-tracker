"""Tag CRUD API routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from expense_tracker.db import get_session
from expense_tracker.i18n import t
from expense_tracker.models import Tag, Transaction
from expense_tracker.routes.helpers import lang
from expense_tracker.services.payloads import list_tag_payloads, normalize_color, tag_payload
from expense_tracker.services.summary import serialize_txn

bp = Blueprint("tags", __name__)


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
