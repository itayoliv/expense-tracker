"""Expense Tracker application package."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from expense_tracker.db import init_db
from expense_tracker.routes import register_blueprints

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PACKAGE_DIR / "templates"),
        static_folder=str(PACKAGE_DIR / "static"),
    )
    app.secret_key = os.environ.get("SECRET_KEY") or "local-expense-tracker-dev-key"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

    register_blueprints(app)

    @app.before_request
    def _ensure_db():
        if not getattr(app, "_db_ready", False):
            init_db()
            app._db_ready = True

    return app
