"""Categorization rule CRUD API routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from expense_tracker.categorizer import category_map
from expense_tracker.db import get_session
from expense_tracker.i18n import t
from expense_tracker.models import CategorizationRule
from expense_tracker.routes.helpers import lang
from expense_tracker.services.payloads import (
    ensure_unique_rule,
    list_rule_payloads,
    parse_rule_fields,
    require_category_id,
    rule_payload,
)

bp = Blueprint("rules", __name__)


@bp.route("/api/rules", methods=["GET"])
def list_rules():
    current_lang = lang()
    with get_session() as session:
        return jsonify({"ok": True, "rules": list_rule_payloads(current_lang, session)})


@bp.route("/api/rules", methods=["POST"])
def create_rule():
    current_lang = lang()
    payload = request.get_json(silent=True) or {}
    try:
        fields = parse_rule_fields(payload)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    with get_session() as session:
        try:
            require_category_id(session, fields["category_id"])
            ensure_unique_rule(session, fields["pattern"], fields["category_id"])
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        rule = CategorizationRule(
            name=fields.get("name", ""),
            pattern=fields["pattern"],
            category_id=fields["category_id"],
            priority=fields.get("priority", 100),
        )
        session.add(rule)
        session.commit()
        cats = category_map(session)
        return jsonify(
            {
                "ok": True,
                "rule": rule_payload(current_lang, rule, cats),
                "message": t(current_lang, "rule_saved"),
            }
        )


@bp.route("/api/rules/<int:rule_id>", methods=["PATCH", "PUT"])
def update_rule(rule_id: int):
    current_lang = lang()
    payload = request.get_json(silent=True) or {}
    try:
        fields = parse_rule_fields(payload, partial=True)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    with get_session() as session:
        rule = session.get(CategorizationRule, rule_id)
        if not rule:
            return jsonify({"ok": False, "error": "Not found"}), 404
        try:
            pattern = fields.get("pattern", rule.pattern)
            category_id = fields.get("category_id", rule.category_id)
            if "category_id" in fields:
                require_category_id(session, category_id)
            ensure_unique_rule(session, pattern, category_id, exclude_id=rule.id)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        if "name" in fields:
            rule.name = fields["name"]
        if "pattern" in fields:
            rule.pattern = fields["pattern"]
        if "category_id" in fields:
            rule.category_id = fields["category_id"]
        if "priority" in fields:
            rule.priority = fields["priority"]
        session.commit()
        cats = category_map(session)
        return jsonify(
            {
                "ok": True,
                "rule": rule_payload(current_lang, rule, cats),
                "message": t(current_lang, "rule_saved"),
            }
        )


@bp.route("/api/rules/<int:rule_id>", methods=["DELETE"])
def delete_rule(rule_id: int):
    current_lang = lang()
    with get_session() as session:
        rule = session.get(CategorizationRule, rule_id)
        if not rule:
            return jsonify({"ok": False, "error": "Not found"}), 404
        session.delete(rule)
        session.commit()
    return jsonify({"ok": True, "message": t(current_lang, "rule_deleted")})
