"""CLI entry: python -m expense_tracker.integrations.yahoo [connect|fetch]."""

from __future__ import annotations

import sys

from expense_tracker.integrations.yahoo.portfolios import fetch_portfolios
from expense_tracker.integrations.yahoo.session import (
    CACHE_PATH,
    YahooFinanceError,
    connect,
)


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    cmd = (args[0] if args else "").strip().lower()
    try:
        if cmd == "connect":
            connect()
            return 0
        if cmd == "fetch":
            data = fetch_portfolios()
            print(
                f"Fetched {len(data.get('portfolios', []))} portfolios "
                f"(total {data.get('grand_total', 0)})."
            )
            print(f"Cache: {CACHE_PATH}")
            return 0
        print("Usage: python -m expense_tracker.integrations.yahoo [connect|fetch]")
        return 2
    except YahooFinanceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
