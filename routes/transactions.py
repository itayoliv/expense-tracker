"""Manual transaction CRUD routes."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, request, url_for

from categorizer import (
    apply_to_similar_all,
    apply_to_similar_unsorted,
    categorize_transaction,
    remember_rule,
)
from db import get_session
from i18n import t
from models import Category, Transaction
from routes.helpers import lang
from services.dates import parse_txn_date
from services.split import split_transaction

bp = Blueprint("transactions", __name__)


@bp.route("/transactions", methods=["POST"])
def add_transaction():
    current_lang = lang()
    payload = request.get_json(silent=True) or request.form
    try:
        amount = float(payload.get("amount", 0))
        if amount <= 0:
            raise ValueError("Amount must be positive")
        direction = payload.get("direction", "debit")
        if direction not in ("debit", "credit"):
            direction = "debit"
        desc = (payload.get("description") or "").strip()
        if not desc:
            raise ValueError("Description required")
        txn_date = parse_txn_date(payload.get("date"))
        category_id = payload.get("category_id")
        category_id = int(category_id) if category_id not in (None, "", "null") else None
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    with get_session() as session:
        txn = Transaction(
            txn_date=txn_date,
            value_date=txn_date,
            description=desc,
            details=(payload.get("details") or "").strip(),
            reference=f"manual-{datetime.utcnow().timestamp()}",
            amount=amount,
            direction=direction,
            account=(payload.get("account") or "").strip(),
            category_id=category_id,
            source_filename="manual",
            source="manual",
            is_manual=True,
        )
        session.add(txn)
        if category_id is None:
            categorize_transaction(session, txn)
        session.commit()
        tid = txn.id

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            {"ok": True, "id": tid, "message": t(current_lang, "transaction_added")}
        )
    flash(t(current_lang, "transaction_added"), "success")
    return redirect(url_for("pages.dashboard"))


@bp.route("/transactions/<int:txn_id>", methods=["PATCH", "POST"])
def update_transaction(txn_id: int):
    current_lang = lang()
    payload = request.get_json(silent=True) or request.form
    method_override = (payload.get("_method") or "").upper()
    if request.method == "POST" and method_override == "DELETE":
        return delete_transaction(txn_id)

    remember = payload.get("remember_rule") in (True, "true", "1", "on")
    apply_all = payload.get("apply_to_categorized") in (True, "true", "1", "on")
    splits = payload.get("splits")

    with get_session() as session:
        txn = session.get(Transaction, txn_id)
        if not txn:
            return jsonify({"ok": False, "error": "Not found"}), 404

        if splits is not None:
            try:
                # Optional date update before split uses current txn fields
                if "date" in payload and payload["date"]:
                    txn.txn_date = parse_txn_date(payload["date"])
                    txn.value_date = txn.txn_date
                result = split_transaction(
                    session,
                    txn,
                    splits,
                    remember=remember,
                    apply_all=apply_all,
                )
                session.commit()
            except Exception as e:
                session.rollback()
                return jsonify({"ok": False, "error": str(e)}), 400
            return jsonify(
                {
                    "ok": True,
                    "message": t(current_lang, "transaction_split", n=result["parts"]),
                    "applied": result["applied"],
                    "created_ids": result["created_ids"],
                }
            )

        if "description" in payload and payload["description"] is not None:
            txn.description = str(payload["description"]).strip() or txn.description
        if "details" in payload and payload["details"] is not None:
            txn.details = str(payload["details"]).strip()
        if "amount" in payload and payload["amount"] not in (None, ""):
            txn.amount = abs(float(payload["amount"]))
        if "date" in payload and payload["date"]:
            txn.txn_date = parse_txn_date(payload["date"])
        if "category_id" in payload:
            cid = payload["category_id"]
            txn.category_id = int(cid) if cid not in (None, "", "null") else None
            txn.categorized_by = ""

        applied = 0
        if txn.category_id and txn.description:
            cat = session.get(Category, txn.category_id)
            if cat:
                if remember:
                    remember_rule(session, txn.description, cat.id)
                if apply_all:
                    applied = apply_to_similar_all(session, txn, cat.id)
                elif remember:
                    applied = apply_to_similar_unsorted(session, txn, cat.id)

        session.commit()

    return jsonify(
        {
            "ok": True,
            "message": t(current_lang, "transaction_saved"),
            "applied": applied,
        }
    )


@bp.route("/transactions/<int:txn_id>", methods=["DELETE"])
def delete_transaction(txn_id: int):
    with get_session() as session:
        txn = session.get(Transaction, txn_id)
        if not txn:
            return jsonify({"ok": False, "error": "Not found"}), 404
        session.delete(txn)
        session.commit()
    return jsonify({"ok": True})
