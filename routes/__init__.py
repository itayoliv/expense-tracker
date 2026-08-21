"""Flask blueprints for the expense tracker."""

from __future__ import annotations

from flask import Flask

from routes.categories import bp as categories_bp
from routes.pages import bp as pages_bp
from routes.rules import bp as rules_bp
from routes.settings import bp as settings_bp
from routes.transactions import bp as transactions_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(pages_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(settings_bp)
