"""Flask expense tracker — bilingual EN/HE dashboard."""

from __future__ import annotations

import os

from flask import Flask

from db import init_db
from routes import register_blueprints

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "local-expense-tracker-dev-key"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

register_blueprints(app)


@app.before_request
def _ensure_db():
    if not getattr(app, "_db_ready", False):
        init_db()
        app._db_ready = True


if __name__ == "__main__":
    init_db()
    debug_raw = (os.environ.get("FLASK_DEBUG") or "1").strip().lower()
    debug = debug_raw not in ("0", "false", "off", "")
    port = int(os.environ.get("FLASK_PORT") or 5000)
    app.run(debug=debug, port=port)
