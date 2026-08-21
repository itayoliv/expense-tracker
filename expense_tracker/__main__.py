"""Run with: python -m expense_tracker"""

from __future__ import annotations

import os

from expense_tracker import create_app
from expense_tracker.db import init_db

app = create_app()


def main() -> None:
    init_db()
    debug_raw = (os.environ.get("FLASK_DEBUG") or "1").strip().lower()
    debug = debug_raw not in ("0", "false", "off", "")
    port = int(os.environ.get("FLASK_PORT") or 5000)
    app.run(debug=debug, port=port)


if __name__ == "__main__":
    main()
