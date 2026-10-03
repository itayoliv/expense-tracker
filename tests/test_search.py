"""Dashboard search across description, details, custom description, and tags."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

import expense_tracker.db as db
from expense_tracker.models import Category, Tag, Transaction
from expense_tracker.services.summary import build_summary


def _seed_search_rows(session) -> int:
    category = session.scalars(select(Category).limit(1)).one()
    tag = Tag(name="Fuel", color="#336699")
    session.add(tag)
    session.flush()
    rows = [
        Transaction(
            txn_date=date(2026, 8, 1),
            description="Fuel station",
            amount=10,
            direction="debit",
            category_id=category.id,
        ),
        Transaction(
            txn_date=date(2026, 8, 2),
            description="Shop",
            details="fuel note",
            amount=20,
            direction="debit",
            category_id=category.id,
        ),
        Transaction(
            txn_date=date(2026, 8, 3),
            description="Market",
            custom_description="My fuel",
            amount=30,
            direction="debit",
            category_id=category.id,
        ),
        Transaction(
            txn_date=date(2026, 8, 4),
            description="Garage",
            amount=40,
            direction="debit",
            category_id=category.id,
            tags=[tag],
        ),
        Transaction(
            txn_date=date(2026, 8, 5),
            description="Coffee",
            amount=100,
            direction="debit",
            category_id=category.id,
        ),
    ]
    session.add_all(rows)
    session.commit()
    return category.id


def test_summary_search_keeps_matching_fields_only(client):
    with db.get_session() as session:
        category_id = _seed_search_rows(session)
        summary = build_summary(
            session,
            "expenses",
            "en",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
            query="fuel",
        )

    category = next(
        item for item in summary["categories"] if item["category_id"] == category_id
    )
    assert category["total"] == 100
    assert {txn["description"] for txn in category["txns"]} == {
        "Fuel station",
        "Shop",
        "Market",
        "Garage",
    }
    assert summary["grand_total"] == 100
    assert summary["expense_total"] == 100


def test_txn_search_labels_each_field_and_skips_non_matches(client):
    with db.get_session() as session:
        _seed_search_rows(session)

    res = client.get("/api/txn-search?q=fuel&view=expenses&date_from=2026-08&date_to=2026-08")
    assert res.status_code == 200
    options = res.get_json()["options"]
    by_field = {item["field"]: item["text"] for item in options}
    assert by_field["description"] == "Fuel station"
    assert by_field["details"] == "fuel note"
    assert by_field["custom_description"] == "My fuel"
    assert by_field["tag"] == "Fuel"
    assert all("coffee" not in item["text"].casefold() for item in options)


def test_dashboard_keeps_search_query_in_the_input(client):
    html = client.get("/?view=expenses&q=fuel").get_data(as_text=True)
    assert 'id="txn-search"' in html
    assert 'value="fuel"' in html
    assert 'id="btn-apply-search"' in html
