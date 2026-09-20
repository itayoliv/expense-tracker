"""Credit-card statement parsing and billing-month grouping."""

from __future__ import annotations

import io
from datetime import date

import pandas as pd

from expense_tracker.services.importer import parse_file


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
    from expense_tracker.services.importer import import_file
    import expense_tracker.db as db
    from expense_tracker.models import Transaction
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


def _discount_bank_bytes() -> bytes:
    rows = [
        ["עובר ושב"] + [None] * 7,
        [None] * 8,
        ["חשבון: 0140178718 | אלייב יפית"] + [None] * 7,
        [None] * 8,
        [None] * 8,
        ["תנועות אחרונות"] + [None] * 7,
        [None] * 8,
        [
            "תאריך",
            "יום ערך",
            "תיאור התנועה",
            "₪ זכות/חובה ",
            "₪ יתרה ",
            "אסמכתא",
            "עמלה",
            "ערוץ ביצוע",
        ],
        [
            "2026-08-21 00:00:00",
            "2026-08-21 00:00:00",
            "חיוב לכרטיס ויזה 6352",
            "-318.6",
            "4943.98",
            "1582",
            "",
            "סניף",
        ],
        [
            "2026-08-09 00:00:00",
            "2026-08-09 00:00:00",
            "עמל הולדינ משכורת",
            "4148.96",
            "9849.55",
            "1571",
            "",
            "יזום מחשב",
        ],
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, header=False, index=False)
    return buf.getvalue()


def _discount_cc_bytes() -> bytes:
    rows = [
        ["כרטיסי אשראי"] + [None] * 17,
        [None] * 18,
        ["חשבון: 0140178718 | אלייב יפית"] + [None] * 17,
        [None] * 18,
        [None] * 18,
        ["פירוט עסקאות - כל הכרטיסים הבנקאיים "] + [None] * 17,
        [None] * 18,
        [
            "כרטיס",
            "בית עסק",
            "תאריך עסקה",
            "סכום העסקה",
            "מנפיק",
            "סוג העסקה",
            "פירוט",
            "תאריך החיוב",
            "סכום החיוב",
        ] + [None] * 9,
        [
            "ויזה 6352",
            "Gett",
            "30/07/2026",
            "35",
            "כאל",
            "ישראל",
            "",
            "02/08/2026",
            "35",
        ] + [None] * 9,
        [
            "מאסטרכארד 5539",
            "דמי  כרטיס בנק דיסקונט",
            "09/08/2026",
            "-8.3",
            "כאל",
            "זיכוי-ישראל",
            "",
            "10/08/2026",
            "-8.3",
        ] + [None] * 9,
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, header=False, index=False)
    return buf.getvalue()


def test_discount_bank_statement_parses_signed_amounts():
    rows = parse_file(_discount_bank_bytes(), "discount_oved.xlsx")
    assert len(rows) == 2
    by_desc = {r["description"]: r for r in rows}
    assert by_desc["חיוב לכרטיס ויזה 6352"]["direction"] == "debit"
    assert by_desc["חיוב לכרטיס ויזה 6352"]["amount"] == 318.6
    assert by_desc["חיוב לכרטיס ויזה 6352"]["account"] == "0140178718"
    assert by_desc["עמל הולדינ משכורת"]["direction"] == "credit"
    assert by_desc["עמל הולדינ משכורת"]["amount"] == 4148.96
    assert all(r["source"] == "bank" for r in rows)


def test_discount_credit_card_parses_merchant_lines():
    rows = parse_file(_discount_cc_bytes(), "discount_cc.xlsx")
    assert len(rows) == 2
    by_desc = {r["description"]: r for r in rows}
    gett = by_desc["Gett"]
    assert gett["txn_date"] == date(2026, 7, 30)
    assert gett["value_date"] == date(2026, 8, 2)
    assert gett["amount"] == 35
    assert gett["direction"] == "debit"
    assert gett["account"] == "6352"
    fee = by_desc["דמי  כרטיס בנק דיסקונט"]
    assert fee["direction"] == "credit"
    assert fee["amount"] == 8.3
    assert all(r["source"] == "card" for r in rows)


def test_dashboard_month_uses_purchase_date_except_installments(client):
    from expense_tracker.services.importer import import_file
    import expense_tracker.db as db

    with db.get_session() as session:
        import_file(session, _isracard_bytes(), "0423_09_2026.xlsx")

    # Installments (תשלום X מתוך Y) follow billing date; other rows stay on purchase date.
    september = client.get("/?date_from=2026-09-01&view=expenses").get_data(as_text=True)
    assert "דינמיקה רננים" in september
    assert "סמארטאייר תל אביב בע" in september
    assert "APPLE.COM/BILL" not in september

    july = client.get("/?date_from=2026-07-01&view=expenses").get_data(as_text=True)
    assert "דינמיקה רננים" not in july
    assert "APPLE.COM/BILL" in july

    june = client.get("/?date_from=2026-06-01&view=expenses").get_data(as_text=True)
    assert "סמארטאייר תל אביב בע" not in june


def test_installment_uses_billing_date_regular_row_uses_purchase_date(client):
    hdr = {"X-Requested-With": "XMLHttpRequest"}
    created = client.post(
        "/transactions",
        json={
            "description": "A I G ביטוח חובה",
            "details": "תשלום 7 מתוך 12",
            "amount": 241.33,
            "direction": "debit",
            "date": "2026-03-01",
            "account": "4146",
        },
        headers=hdr,
    )
    assert created.status_code == 200
    other = client.post(
        "/transactions",
        json={
            "description": "Regular cafe",
            "details": "",
            "amount": 40,
            "direction": "debit",
            "date": "2026-03-15",
            "account": "4146",
        },
        headers=hdr,
    )
    assert other.status_code == 200

    from datetime import date

    from expense_tracker.db import get_session
    from expense_tracker.models import Transaction

    with get_session() as session:
        inst = session.get(Transaction, created.get_json()["id"])
        cafe = session.get(Transaction, other.get_json()["id"])
        inst.value_date = date(2026, 9, 2)
        cafe.value_date = date(2026, 9, 2)
        session.commit()

    september = client.get(
        "/?view=expenses&date_from=2026-09&date_to=2026-09"
    ).get_data(as_text=True)
    assert "A I G" in september
    assert "02/09/26" in september
    assert "Regular cafe" not in september

    march = client.get(
        "/?view=expenses&date_from=2026-03&date_to=2026-03"
    ).get_data(as_text=True)
    assert "A I G" not in march
    assert "Regular cafe" in march
    assert "15/03/26" in march
