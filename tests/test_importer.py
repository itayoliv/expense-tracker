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


def _isracard_with_pending_bytes() -> bytes:
    header = [
        "תאריך רכישה",
        "שם בית עסק",
        "סכום עסקה",
        "מטבע עסקה",
        "סכום חיוב",
        "מטבע חיוב",
        "מס' שובר",
        "פירוט נוסף",
        None,
    ]
    rows = [
        ["פירוט עסקאות", None, "ספטמבר 2026", None, None, None, None, None, None],
        ["על שם בדיקה", None, None, None, None, None, None, "לחיוב ב-10.09", None],
        [None] * 9,
        ["עסקאות שטרם נקלטו", None, None, None, None, None, None, None, None],
        header,
        ["05.09.26", "Beerbazaar Jerusalem", 38, "₪", 38, "₪", None, None, None],
        [None] * 9,
        ["עסקאות למועד חיוב", None, None, None, None, None, None, None, None],
        header,
        ["06.07.26", "דינמיקה רננים", 659, "₪", 219.67, "₪", "679147477", "תשלום 3 מתוך 3", None],
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, header=False, index=False)
    return buf.getvalue()


def test_pending_rows_are_not_imported(client):
    from sqlalchemy import select

    import expense_tracker.db as db
    from expense_tracker.models import Transaction
    from expense_tracker.services.importer import PENDING_DETAILS, import_file

    parsed = parse_file(_isracard_with_pending_bytes(), "0423_09_2026.xlsx")
    assert {r["description"] for r in parsed} == {
        "Beerbazaar Jerusalem",
        "דינמיקה רננים",
    }

    with db.get_session() as session:
        result = import_file(
            session, _isracard_with_pending_bytes(), "0423_09_2026.xlsx"
        )
        stored = session.scalars(select(Transaction)).all()

    assert result["added"] == 1
    assert result["skipped"] == 1
    assert [t.description for t in stored] == ["דינמיקה רננים"]
    assert all(t.details != PENDING_DETAILS for t in stored)


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
    assert fee["direction"] == "debit"
    assert fee["amount"] == -8.3
    assert all(r["source"] == "card" for r in rows)


def _isracard_refund_bytes() -> bytes:
    rows = [
        [None] * 9,
        ["פירוט עסקאות", None, "נובמבר 2026", None, None, None, None, None, None],
        [None] * 9,
        [None] * 9,
        ["קורפוריט - זהב - 4146", None, None, None, None, None, None, "₪ 12,998.60", None],
        ["על שם בדיקה", None, None, None, None, None, None, "לחיוב ב-02.11", None],
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
        ["25.10.26", "אצל אלברטו", 15.1, "₪", 15.1, "₪", "379166413", None, None],
        ["25.10.26", "הפניקס החזר ביטוח", -1343, "₪", -1343, "₪", "391667491", None, None],
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, header=False, index=False)
    return buf.getvalue()


def test_isracard_refund_stays_negative_debit():
    rows = parse_file(_isracard_refund_bytes(), "4146_11_2026.xlsx")
    by_desc = {row["description"]: row for row in rows}
    charge = by_desc["אצל אלברטו"]
    assert charge["direction"] == "debit"
    assert charge["amount"] == 15.1
    refund = by_desc["הפניקס החזר ביטוח"]
    assert refund["txn_date"] == date(2026, 10, 25)
    assert refund["direction"] == "debit"
    assert refund["amount"] == -1343
    assert refund["account"] == "4146"


def test_isracard_refund_reduces_expenses_and_uses_rules(client):
    from sqlalchemy import select

    import expense_tracker.db as db
    from expense_tracker.models import Category, Tag, Transaction
    from expense_tracker.services.categorizer import remember_rule
    from expense_tracker.services.importer import import_file
    from expense_tracker.services.summary import build_summary

    with db.get_session() as session:
        insurance = session.scalars(
            select(Category).where(Category.name_en == "Insurance")
        ).one()
        tag = Tag(name="policy", color="#2563EB")
        session.add(tag)
        session.flush()
        remember_rule(session, "הפניקס", insurance.id, tags=[tag])
        session.commit()
        import_file(session, _isracard_refund_bytes(), "4146_11_2026.xlsx")
        refund = session.scalars(
            select(Transaction).where(Transaction.description == "הפניקס החזר ביטוח")
        ).one()
        refund_id = refund.id
        assert refund.amount == -1343
        assert refund.direction == "debit"
        assert refund.category_id == insurance.id
        assert [item.name for item in refund.tags] == ["policy"]
        summary = build_summary(
            session,
            "expenses",
            "en",
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
        )
        assert round(summary["grand_total"], 2) == -1327.9
        assert round(summary["expense_total"], 2) == -1327.9

    html = client.get(
        "/?view=expenses&date_from=2026-10&date_to=2026-10"
    ).get_data(as_text=True)
    assert "הפניקס החזר ביטוח" in html
    assert "-1,343.00" in html
    assert "Insurance" in html
    assert "policy" in html
    income = client.get(
        "/?view=income&date_from=2026-10&date_to=2026-10"
    ).get_data(as_text=True)
    assert "הפניקס החזר ביטוח" not in income

    res = client.patch(
        f"/transactions/{refund_id}",
        json={"amount": 500},
    )
    assert res.status_code == 200
    with db.get_session() as session:
        saved = session.get(Transaction, refund_id)
        assert saved is not None
        assert saved.amount == -500


def test_dashboard_month_uses_installment_slice_date(client):
    from expense_tracker.services.importer import import_file
    import expense_tracker.db as db

    with db.get_session() as session:
        import_file(session, _isracard_bytes(), "0423_09_2026.xlsx")

    # Slice N of a plan is dated תאריך רכישה + (N - 1) months; other rows keep תאריך רכישה.
    september = client.get("/?date_from=2026-09-01&view=expenses").get_data(as_text=True)
    assert "דינמיקה רננים" in september
    assert "06/09/26" in september
    assert "סמארטאייר תל אביב בע" not in september

    august = client.get("/?date_from=2026-08-01&view=expenses").get_data(as_text=True)
    assert "סמארטאייר תל אביב בע" in august
    assert "11/08/26" in august

    july = client.get("/?date_from=2026-07-01&view=expenses").get_data(as_text=True)
    assert "דינמיקה רננים" not in july
    assert "APPLE.COM/BILL" in july

    june = client.get("/?date_from=2026-06-01&view=expenses").get_data(as_text=True)
    assert "סמארטאייר תל אביב בע" not in june


def test_installment_uses_slice_date_regular_row_uses_purchase_date(client):
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
    assert "01/09/26" in september
    assert "Regular cafe" not in september

    march = client.get(
        "/?view=expenses&date_from=2026-03&date_to=2026-03"
    ).get_data(as_text=True)
    assert "A I G" not in march
    assert "Regular cafe" in march
    assert "15/03/26" in march


def _max_bytes() -> bytes:
    billing = pd.DataFrame(
        [
            ["כל המשתמשים (1)"],
            ["כל הכרטיסים (1)"],
            ["09/2026"],
            [
                "תאריך עסקה",
                "שם בית העסק",
                "קטגוריה",
                "4 ספרות אחרונות של כרטיס האשראי",
                "סוג עסקה",
                "סכום חיוב",
                "מטבע חיוב",
                "סכום עסקה מקורי",
                "מטבע עסקה מקורי",
                "תאריך חיוב",
                "הערות",
            ],
            ["10-08-2026", "מקס נתניה", "שונות", "5719", "רגילה", 6.3, "₪", 6.3, "₪", "10-09-2026", None],
            ["24-09-2026", "שולמן תכשיטים", "אופנה", "5719", "תשלומים", 343.35, "₪", 2060, "₪", "11-10-2026", "תשלום 1 מתוך 6"],
            ["10-09-2026", "ויקטורי תל מונד", "מזון וצריכה", "5719", "רגילה", -26.9, "₪", 26.9, "₪", "11-10-2026", "ביטול עסקה"],
            ["סך הכל", None, None, None, None, "322.75₪"],
        ]
    )
    pending = pd.DataFrame(
        [
            ["כל המשתמשים (1)"],
            ["11/2026"],
            [
                "תאריך עסקה",
                "שם בית העסק",
                "קטגוריה",
                "4 ספרות אחרונות של כרטיס האשראי",
                "סוג עסקה",
                "סכום חיוב",
                "מטבע חיוב",
                "סכום עסקה מקורי",
                "מטבע עסקה מקורי",
            ],
            ["11-10-2026", "סטוק", "חשמל ומחשבים", "5719", "רגילה", None, None, 27, "₪"],
            ["סך הכל", None, None, None, None, 0],
        ]
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as writer:
        billing.to_excel(writer, sheet_name="עסקאות במועד החיוב", header=False, index=False)
        pending.to_excel(writer, sheet_name="עסקאות שאושרו וטרם נקלטו", header=False, index=False)
    return buf.getvalue()


def test_max_export_parses_charges_refunds_and_skips_pending():
    from expense_tracker.services.importer.isracard import PENDING_DETAILS

    rows = parse_file(_max_bytes(), "transaction-details_export_1 - MAX.xlsx")
    by_desc = {row["description"]: row for row in rows}
    assert set(by_desc) == {"מקס נתניה", "שולמן תכשיטים", "ויקטורי תל מונד", "סטוק"}

    purchase = by_desc["מקס נתניה"]
    assert purchase["txn_date"] == date(2026, 8, 10)
    assert purchase["value_date"] == date(2026, 9, 10)
    assert purchase["amount"] == 6.3
    assert purchase["direction"] == "debit"
    assert purchase["account"] == "5719"
    assert purchase["source"] == "card"

    installment = by_desc["שולמן תכשיטים"]
    assert installment["txn_date"] == date(2026, 9, 24)
    assert installment["amount"] == 343.35
    assert installment["details"] == "תשלום 1 מתוך 6"

    refund = by_desc["ויקטורי תל מונד"]
    assert refund["direction"] == "debit"
    assert refund["amount"] == -26.9
    assert refund["details"] == "ביטול עסקה"

    assert by_desc["סטוק"]["details"] == PENDING_DETAILS
    assert by_desc["סטוק"]["amount"] == 27


def test_max_import_skips_unposted_sheet(client):
    from sqlalchemy import select

    import expense_tracker.db as db
    from expense_tracker.models import Transaction
    from expense_tracker.services.importer import import_file
    from expense_tracker.services.installments import add_months

    data = _max_bytes()
    with db.get_session() as session:
        result = import_file(session, data, "transaction-details_export_1 - MAX.xlsx")
        stored = list(session.scalars(select(Transaction)).all())
        installment = next(txn for txn in stored if "שולמן" in txn.description)

    assert result["added"] == 3
    assert result["skipped"] == 1
    assert {txn.description for txn in stored} == {
        "מקס נתניה",
        "שולמן תכשיטים",
        "ויקטורי תל מונד",
    }
    assert installment.installment_date == add_months(date(2026, 9, 24), 0)

    with db.get_session() as session:
        again = import_file(session, data, "transaction-details_export_1 - MAX.xlsx")
    assert again["added"] == 0
    assert again["skipped"] == 4
