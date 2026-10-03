"""Installment slice dates: תאריך רכישה + (payment number - 1) months."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from expense_tracker.services.installments import (
    add_months,
    installment_date_for,
    is_followup_installment,
    is_last_installment,
    parse_installment,
)


def test_is_last_installment_only_when_payment_number_matches_total():
    last = SimpleNamespace(details="תשלום 12 מתוך 12", description="")
    middle = SimpleNamespace(details="תשלום 3 מתוך 12", description="")
    only = SimpleNamespace(details="תשלום 1 מתוך 1", description="")
    unnumbered = SimpleNamespace(details="installment", description="")
    from_description = SimpleNamespace(details="", description="payment 6 of 6")
    assert is_last_installment(last) is True
    assert is_last_installment(middle) is False
    assert is_last_installment(only) is True
    assert is_last_installment(unnumbered) is False
    assert is_last_installment(from_description) is True


def test_last_installment_icon_shows_only_on_final_slice(client):
    from sqlalchemy import select

    import expense_tracker.db as db
    from expense_tracker.models import Category, Transaction

    with db.get_session() as session:
        category = session.scalars(select(Category).limit(1)).one()
        category_id = category.id
        session.add_all(
            [
                Transaction(
                    txn_date=date(2026, 8, 4),
                    description="Final slice",
                    details="תשלום 1 מתוך 1",
                    amount=50,
                    direction="debit",
                    category_id=category_id,
                ),
                Transaction(
                    txn_date=date(2026, 8, 4),
                    description="Middle slice",
                    details="תשלום 1 מתוך 4",
                    amount=50,
                    direction="debit",
                    category_id=category_id,
                ),
            ]
        )
        session.commit()

    html = client.get("/?view=expenses&date_from=2026-08").get_data(as_text=True)
    assert html.count("last-installment-icon") == 1
    assert 'aria-label="Last installment"' in html


def test_is_followup_installment_only_after_first_payment():
    first = SimpleNamespace(details="תשלום 1 מתוך 12", description="")
    third = SimpleNamespace(details="תשלום 3 מתוך 12", description="")
    unnumbered = SimpleNamespace(details="installment", description="")
    from_description = SimpleNamespace(details="", description="payment 2 of 6")
    assert is_followup_installment(first) is False
    assert is_followup_installment(third) is True
    assert is_followup_installment(unnumbered) is False
    assert is_followup_installment(from_description) is True


def test_carryover_total_sums_followup_installments_only(client):
    from sqlalchemy import select

    import expense_tracker.db as db
    from expense_tracker.models import Category, Transaction
    from expense_tracker.services.summary import build_summary

    with db.get_session() as session:
        category = session.scalars(select(Category).limit(1)).one()
        category_id = category.id
        session.add_all(
            [
                Transaction(
                    txn_date=date(2026, 8, 15),
                    description="First slice",
                    details="תשלום 1 מתוך 12",
                    amount=100,
                    direction="debit",
                    category_id=category_id,
                ),
                Transaction(
                    txn_date=date(2026, 6, 15),
                    description="Third slice",
                    details="תשלום 3 מתוך 12",
                    amount=40,
                    direction="debit",
                    category_id=category_id,
                ),
                Transaction(
                    txn_date=date(2026, 8, 10),
                    description="Regular",
                    amount=25,
                    direction="debit",
                    category_id=category_id,
                ),
                Transaction(
                    txn_date=date(2026, 7, 10),
                    description="Ignored slice",
                    details="תשלום 2 מתוך 4",
                    amount=70,
                    direction="debit",
                    category_id=category_id,
                    ignored=True,
                    ignore_reason="Not counted",
                ),
            ]
        )
        session.commit()
        summary = build_summary(
            session,
            "expenses",
            "en",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
        )

    category_summary = next(
        item for item in summary["categories"] if item["category_id"] == category_id
    )
    assert category_summary["total"] == 165
    assert category_summary["carryover_total"] == 40
    assert summary["carryover_total"] == 40

    html = client.get("/?view=expenses&date_from=2026-08").get_data(as_text=True)
    assert "From earlier purchases:" in html
    assert html.count("total-carryover") == 2


def test_parse_installment_reads_payment_number_and_total():
    assert parse_installment("תשלום 3 מתוך 24") == (3, 24)
    assert parse_installment("תשלום 2 מתוך 2 תשלום אחרון הנחה ₪3.58") == (2, 2)
    assert parse_installment("payment 4 of 6") == (4, 6)
    assert parse_installment("installment 1") is None
    assert parse_installment("הוראת קבע") is None
    assert parse_installment(None) is None


def test_add_months_clamps_to_end_of_month_and_crosses_years():
    assert add_months(date(2026, 8, 31), 1) == date(2026, 9, 30)
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 12, 19), 21) == date(2026, 9, 19)
    assert add_months(date(2026, 7, 20), 0) == date(2026, 7, 20)


def test_installment_date_for_shifts_by_payment_number():
    purchase = date(2026, 7, 20)
    assert installment_date_for(purchase, "תשלום 1 מתוך 24") == purchase
    assert installment_date_for(purchase, "תשלום 3 מתוך 24") == date(2026, 9, 20)
    assert installment_date_for(date(2026, 8, 31), "תשלום 2 מתוך 4") == date(2026, 9, 30)
    assert installment_date_for(purchase, "", "תשלום 2 מתוך 3") == date(2026, 8, 20)
    assert installment_date_for(purchase, "installment 1") is None
    assert installment_date_for(purchase, "") is None


def test_installment_date_is_kept_in_sync_on_insert_and_update(client):
    import expense_tracker.db as db
    from expense_tracker.models import Transaction

    with db.get_session() as session:
        slice_ = Transaction(
            txn_date=date(2026, 7, 20),
            description="דינמיקה אינטרנט",
            details="תשלום 3 מתוך 24",
            amount=121,
            direction="debit",
        )
        regular = Transaction(
            txn_date=date(2026, 9, 6),
            description="BEERBAZAAR JERUSALEM",
            amount=38,
            direction="debit",
        )
        session.add_all([slice_, regular])
        session.commit()
        assert slice_.installment_date == date(2026, 9, 20)
        assert regular.installment_date is None

        slice_.txn_date = date(2026, 8, 31)
        slice_.details = "תשלום 2 מתוך 4"
        session.commit()
        assert slice_.installment_date == date(2026, 9, 30)


def test_backfill_dates_existing_installment_rows(client):
    from sqlalchemy import text

    import expense_tracker.db as db
    from expense_tracker.db.migrations import _backfill_installment_dates
    from expense_tracker.models import Transaction

    with db.get_session() as session:
        txn = Transaction(
            txn_date=date(2024, 12, 19),
            description="דינמיקה מול הים אילת",
            details="תשלום 21 מתוך 24",
            amount=114.54,
            direction="debit",
        )
        session.add(txn)
        session.commit()
        tid = txn.id
        session.execute(text("UPDATE transactions SET installment_date = NULL"))
        session.commit()

    _backfill_installment_dates()

    with db.get_session() as session:
        assert session.get(Transaction, tid).installment_date == date(2026, 8, 19)


def test_manual_date_edit_moves_slice_to_new_month(client):
    hdr = {"X-Requested-With": "XMLHttpRequest"}
    created = client.post(
        "/transactions",
        json={
            "description": "KSP אקספרס-גמא",
            "details": "תשלום 3 מתוך 9",
            "amount": 273,
            "direction": "debit",
            "date": "2026-07-16",
        },
        headers=hdr,
    )
    tid = created.get_json()["id"]

    september = client.get("/?view=expenses&date_from=2026-09").get_data(as_text=True)
    assert "KSP" in september
    assert "16/09/26" in september

    client.patch(f"/transactions/{tid}", json={"date": "2026-06-16"}, headers=hdr)

    august = client.get("/?view=expenses&date_from=2026-08").get_data(as_text=True)
    assert "KSP" in august
    assert "16/08/26" in august
