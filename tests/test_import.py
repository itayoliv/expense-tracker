"""Import dropzone UI tests."""

from __future__ import annotations


def test_dashboard_includes_import_dropzone(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="import-dropzone"' in html
    assert 'id="import-file"' in html
    assert 'multiple' in html
    assert 'class="dropzone"' in html
    js = client.get("/static/js/import.js").get_data(as_text=True)
    assert "bindImportDropzone" in js
    assert "assignFiles" in js
    css = client.get("/static/css/app.css").get_data(as_text=True)
    assert ".dropzone" in css
    assert ".empty-import" in css


def test_empty_dashboard_shows_inline_dropzone(client):
    html = client.get("/").get_data(as_text=True)
    assert 'class="empty-import"' in html
    assert 'id="empty-import-dropzone"' in html
    assert 'id="empty-import-file"' in html
    assert "No transactions yet." not in html


def test_dashboard_with_data_hides_inline_dropzone(client):
    created = client.post(
        "/transactions",
        json={
            "description": "Coffee",
            "amount": 12.5,
            "direction": "debit",
            "date": "2026-08-01",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert created.status_code == 200
    html = client.get("/").get_data(as_text=True)
    assert 'class="empty-import"' not in html
    assert 'id="empty-import-dropzone"' not in html
    assert 'id="import-dropzone"' in html
    assert 'class="money"' in html
    assert 'class="money-num"' in html
    assert "12.50" in html


def test_income_view_without_credits_does_not_look_unimported(client):
    created = client.post(
        "/transactions",
        json={
            "description": "Coffee",
            "amount": 12.5,
            "direction": "debit",
            "date": "2026-08-01",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert created.status_code == 200
    html = client.get("/?view=income&month=2026-08").get_data(as_text=True)
    assert 'class="empty-import"' not in html
    assert "No income in this month." in html
    assert "Coffee" not in html


def test_dashboard_defaults_to_current_month(client):
    from datetime import date

    today = date.today()
    current_day = f"{today.year:04d}-{today.month:02d}-10"
    if today.month == 1:
        other_day = f"{today.year - 1:04d}-12-15"
    else:
        other_day = f"{today.year:04d}-{today.month - 1:02d}-15"

    client.post(
        "/transactions",
        json={
            "description": "ThisMonth",
            "amount": 11,
            "direction": "debit",
            "date": current_day,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    client.post(
        "/transactions",
        json={
            "description": "OtherMonth",
            "amount": 22,
            "direction": "debit",
            "date": other_day,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    html = client.get("/").get_data(as_text=True)
    assert "ThisMonth" in html
    assert "OtherMonth" not in html
    current_key = f"{today.year:04d}-{today.month:02d}"
    assert f'value="{current_key}"' in html
    assert "selected" in html


def test_all_months_shows_every_expense(client):
    from datetime import date

    today = date.today()
    current_day = f"{today.year:04d}-{today.month:02d}-10"
    if today.month == 1:
        other_day = f"{today.year - 1:04d}-12-15"
    else:
        other_day = f"{today.year:04d}-{today.month - 1:02d}-15"

    client.post(
        "/transactions",
        json={
            "description": "ThisMonth",
            "amount": 11,
            "direction": "debit",
            "date": current_day,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    client.post(
        "/transactions",
        json={
            "description": "OtherMonth",
            "amount": 22,
            "direction": "debit",
            "date": other_day,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    html = client.get("/?month=all").get_data(as_text=True)
    assert "ThisMonth" in html
    assert "OtherMonth" in html
    assert 'value="all"' in html
    assert 'id="empty-import-dropzone"' not in html


def test_import_accepts_multiple_files(client):
    from io import BytesIO

    from sqlalchemy import func, select

    import db
    from models import Transaction
    from tests.test_importer import _isracard_bytes

    payload = _isracard_bytes()
    res = client.post(
        "/import",
        data={
            "view": "expenses",
            "file": [
                (BytesIO(payload), "0423_09_2026.xlsx"),
                (BytesIO(payload), "0423_08_2026.xlsx"),
            ],
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert res.status_code == 200
    with db.get_session() as session:
        count = session.scalar(select(func.count()).select_from(Transaction))
    assert count == 3
    html = client.get("/?month=all").get_data(as_text=True)
    assert "דינמיקה רננים" in html


def test_unsorted_banner_shows_details_newest_first(client):
    hdr = {"X-Requested-With": "XMLHttpRequest"}
    client.post(
        "/transactions",
        json={
            "description": "OldShop",
            "details": "installment 1",
            "account": "0423",
            "amount": 10,
            "direction": "debit",
            "date": "2026-08-01",
        },
        headers=hdr,
    )
    client.post(
        "/transactions",
        json={
            "description": "NewShop",
            "details": "recurring",
            "account": "0423",
            "amount": 20,
            "direction": "debit",
            "date": "2026-08-15",
        },
        headers=hdr,
    )
    html = client.get("/?month=2026-08&view=expenses").get_data(as_text=True)
    assert 'id="unsorted-banner"' in html
    assert 'id="unsorted-search"' in html
    assert html.find("NewShop") < html.find("OldShop")
    assert "15/08/26" in html
    assert "01/08/26" in html
    assert "recurring" in html
    assert "installment 1" in html
    js = client.get("/static/js/transactions.js").get_data(as_text=True)
    assert "unsorted-search" in js


def test_dashboard_shows_source_badges(client):
    from sqlalchemy import select

    import db
    from importer import import_file
    from models import Transaction
    from tests.test_importer import _bank_csv_bytes, _isracard_bytes

    hdr = {"X-Requested-With": "XMLHttpRequest"}
    client.post(
        "/transactions",
        json={
            "description": "Cash coffee",
            "amount": 12,
            "direction": "debit",
            "date": "2026-08-01",
        },
        headers=hdr,
    )
    with db.get_session() as session:
        import_file(session, _isracard_bytes(), "0423_09_2026.xlsx")
        import_file(session, _bank_csv_bytes(), "hapoalim.csv")

    expenses = client.get("/?month=all&view=expenses").get_data(as_text=True)
    assert 'source-badge source-manual' in expenses
    assert "Manual" in expenses
    assert 'source-badge source-card' in expenses
    assert "Credit card" in expenses
    assert 'source-badge source-bank' in expenses
    assert "Bank" in expenses

    with db.get_session() as session:
        kinds = {txn.source for txn in session.scalars(select(Transaction)).all()}
    assert kinds == {"manual", "card", "bank"}


def test_unsorted_search_placeholder_is_hebrew(client):
    hdr = {"X-Requested-With": "XMLHttpRequest"}
    client.post(
        "/transactions",
        json={
            "description": "Shop",
            "amount": 10,
            "direction": "debit",
            "date": "2026-08-01",
        },
        headers=hdr,
    )
    client.set_cookie("lang", "he")
    html = client.get("/?month=2026-08&view=expenses").get_data(as_text=True)
    assert "חיפוש לפי תאריך, תיאור או סכום" in html
    assert "Search by date, description, or amount" not in html
