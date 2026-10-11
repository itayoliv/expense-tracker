"""Repair installment rows whose purchase date was overwritten with their slice date.

Older edit-modal saves sent the displayed slice date back as txn_date, pushing the
row (payment number - 1) months into the future and sometimes duplicating a slice
that was imported again later.

Slices of one card purchase share description/amount/plan size and have
consecutive references (reference - payment number is constant), so they can be
grouped. Within a group the earliest txn_date is the real purchase date; a row is
repaired only when its txn_date equals exactly its own expected slice date.

Usage: python repair_installment_dates.py [path/to/expenses.db]
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from expense_tracker.services.installments import add_months, parse_installment  # noqa: E402


def load_groups(conn: sqlite3.Connection):
    rows = conn.execute(
        "SELECT id, txn_date, reference, amount, direction, description, details,"
        " custom_description, category_id FROM transactions"
    ).fetchall()
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        tid, txn_date, ref, amount, direction, desc, details, custom, cat = r
        parsed = parse_installment(details) or parse_installment(desc)
        if not parsed or not (ref or "").isdigit():
            continue
        n, total = parsed
        key = (desc, round(amount, 2), direction, total, int(ref) - n)
        groups[key].append(
            {
                "id": tid,
                "txn_date": date.fromisoformat(txn_date),
                "reference": ref,
                "n": n,
                "total": total,
                "description": desc,
                "details": details,
                "custom_description": custom or "",
                "category_id": cat,
            }
        )
    return groups


def plan_repairs(groups):
    fixes, merges = [], []
    for slices in groups.values():
        purchase = min(s["txn_date"] for s in slices)
        for s in slices:
            if s["n"] <= 1 or s["txn_date"] == purchase:
                continue
            if s["txn_date"] != add_months(purchase, s["n"] - 1):
                continue
            twin = next(
                (
                    o
                    for o in slices
                    if o is not s
                    and o["reference"] == s["reference"]
                    and o["txn_date"] == purchase
                ),
                None,
            )
            if twin:
                merges.append((s, twin))
            else:
                fixes.append((s, purchase))
    return fixes, merges


def describe(s) -> str:
    return f"#{s['id']} {s['description']} | {s['details']} | {s['custom_description'] or '-'}"


def apply(conn, fixes, merges) -> None:
    for dup, keep in merges:
        if not keep["custom_description"] and dup["custom_description"]:
            conn.execute(
                "UPDATE transactions SET custom_description=? WHERE id=?",
                (dup["custom_description"], keep["id"]),
            )
        if keep["category_id"] is None and dup["category_id"] is not None:
            conn.execute(
                "UPDATE transactions SET category_id=? WHERE id=?",
                (dup["category_id"], keep["id"]),
            )
        conn.execute(
            "INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id)"
            " SELECT ?, tag_id FROM transaction_tags WHERE transaction_id=?",
            (keep["id"], dup["id"]),
        )
        conn.execute("DELETE FROM transaction_tags WHERE transaction_id=?", (dup["id"],))
        conn.execute("DELETE FROM transactions WHERE id=?", (dup["id"],))
    for s, purchase in fixes:
        conn.execute(
            "UPDATE transactions SET txn_date=?, installment_date=? WHERE id=?",
            (
                purchase.isoformat(),
                add_months(purchase, s["n"] - 1).isoformat(),
                s["id"],
            ),
        )
    conn.commit()


def main() -> int:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "dev" / "expenses.db"
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    fixes, merges = plan_repairs(load_groups(conn))
    if not fixes and not merges:
        print("Nothing to repair.")
        return 0

    for s, purchase in fixes:
        slice_date = add_months(purchase, s["n"] - 1)
        print(f"FIX    {describe(s)}")
        print(f"       purchase {s['txn_date']} -> {purchase}  (shows in {slice_date:%m/%Y})")
    for dup, keep in merges:
        print(f"DELETE {describe(dup)}")
        print(f"       duplicate of #{keep['id']} (purchase {keep['txn_date']}), details merged into it")

    answer = input(f"\nApply {len(fixes)} fix(es) and {len(merges)} delete(s)? [y/N] ").strip().lower()
    if answer != "y":
        print("Cancelled, nothing changed.")
        return 0

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / f"expenses-repair-installments-{datetime.now():%Y%m%d-%H%M%S}.db"
    conn.close()
    shutil.copy2(db_path, backup)
    print(f"Backup: {backup}")

    conn = sqlite3.connect(db_path)
    apply(conn, fixes, merges)
    conn.close()
    print("Done. Refresh the dashboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
