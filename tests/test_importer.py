"""Credit-card statement parsing and billing-month grouping."""

from __future__ import annotations

import io
from datetime import date

import pandas as pd

from importer import parse_file


def _isracard_bytes() -> bytes:
    rows = [
        [None] * 9,
        ["פירוט עסקאות", None, "ספטמבר 2026", None, None, None, None, None, None],
        [None] * 9,
        [None] * 9,
        ["קורפוריט - זהב - 0423", None, None, None, None, None, None, "₪ 1,241.35", None],
        ["על שם בדיקה", None, None, None, None, None, None, "לחיוב ב-10.09", None],
        [None] * 9,
        [None] * 9,
        [None] * 9,
        [None] * 9,
        [None] * 9,
        ["עסקאות למועד חיוב", None, None, None, None, None, None, None, None],
        [
            "תאריך רכישה",
            "שם בית עסק",
            "סכום עסקה",
            "מטבע עסקה",
            "סכום חיוב",
            "מטבע חיוב",
            "מס' שובר",
            "פירוט נוסף",
            None,
        ],
        ["06.07.26", "דינמיקה רננים", 659, "₪", 219.67, "₪", "679147477", "תשלום 3 מתוך 3", None],
        ["11.06.26", "סמארטאייר תל אביב בע", 4717.62, "₪", 471.76, "₪", "517293838", "תשלום 3 מתוך 10", None],
        [None] * 9,
        ["עסקאות בחיוב מחוץ למועד", None, None, None, None, None, None, None, None],
        [
            "תאריך רכישה",
            "שם בית עסק",
            "סכום עסקה",
            "מטבע עסקה",
            "סכום חיוב",
            "מטבע חיוב",
            "מס' שובר",
            "פירוט נוסף",
            "חיוב בחשבון הבנק",
        ],
        ["30.07.26", "APPLE.COM/BILL", 11.9, "₪", 11.9, "₪", "837708589", "הוראת קבע", "02.09.26"],
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, header=False, index=False)
    return buf.getvalue()


def test_credit_card_uses_statement_month_not_purchase_month():
    rows = parse_file(_isracard_bytes(), "0423_09_2026.xlsx")
    by_desc = {r["description"]: r for r in rows}
    assert set(by_desc) == {"דינמיקה רננים", "סמארטאייר תל אביב בע", "APPLE.COM/BILL"}

    dynamika = by_desc["דינמיקה רננים"]
    assert dynamika["txn_date"] == date(2026, 7, 6)
    assert dynamika["value_date"] == date(2026, 9, 10)
    assert dynamika["amount"] == 219.67

    smartair = by_desc["סמארטאייר תל אביב בע"]
    assert smartair["txn_date"] == date(2026, 6, 11)
    assert smartair["value_date"] == date(2026, 9, 10)

    apple = by_desc["APPLE.COM/BILL"]
    assert apple["txn_date"] == date(2026, 7, 30)
    assert apple["value_date"] == date(2026, 9, 2)
    assert all(row["source"] == "card" for row in rows)


def _bank_csv_bytes() -> bytes:
    return (
        "Date,Description,Debit,Credit\n"
        "2026-08-01,ATM withdrawal,50,\n"
        "2026-08-02,Salary,,1000\n"
    ).encode("utf-8")


def test_bank_statement_rows_are_marked_bank():
    rows = parse_file(_bank_csv_bytes(), "hapoalim.csv")
    assert rows
    assert all(row["source"] == "bank" for row in rows)


def test_reimport_updates_billing_date(client, tmp_path):
    from importer import import_file
    import db
    from models import Transaction
    from sqlalchemy import select

    data = _isracard_bytes()
    with db.get_session() as session:
        first = import_file(session, data, "0423_09_2026.xlsx")
    assert first["added"] == 3

    with db.get_session() as session:
        dynamika = session.scalars(
            select(Transaction).where(Transaction.description == "דינמיקה רננים")
        ).one()
        dynamika.value_date = dynamika.txn_date
        session.commit()

    with db.get_session() as session:
        second = import_file(session, data, "0423_09_2026.xlsx")
        dynamika = session.scalars(
            select(Transaction).where(Transaction.description == "דינמיקה רננים")
        ).one()
    assert second["added"] == 0
    assert second["skipped"] == 3
    assert dynamika.value_date == date(2026, 9, 10)


def test_dashboard_month_uses_billing_date(client):
    from importer import import_file
    import db

    with db.get_session() as session:
        import_file(session, _isracard_bytes(), "0423_09_2026.xlsx")

    html = client.get("/?month=2026-09&view=expenses").get_data(as_text=True)
    assert "דינמיקה רננים" in html
    assert "סמארטאייר תל אביב בע" in html
    assert "APPLE.COM/BILL" in html

    july = client.get("/?month=2026-07&view=expenses").get_data(as_text=True)
    assert "דינמיקה רננים" not in july
