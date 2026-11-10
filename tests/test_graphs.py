"""Category monthly graph."""

from datetime import date


def _id_by_name_en(client, name_en: str) -> int:
    cats = client.get("/api/categories").get_json()["categories"]
    return next(c["id"] for c in cats if c["name_en"] == name_en)


def _add(client, description, amount, day, category_id, details=""):
    res = client.post(
        "/transactions",
        json={
            "description": description,
            "details": details,
            "amount": amount,
            "direction": "debit",
            "date": day,
            "category_id": category_id,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert res.status_code == 200
    return res.get_json()["id"]


def test_graphs_nav_and_monthly_totals(client):
    page = client.get("/graphs")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Graphs" in html
    assert 'href="/graphs?' in html
    assert f'value="{date.today():%Y-%m}"' in html

    fuel_id = _id_by_name_en(client, "Fuel and transport")
    shopping_id = _id_by_name_en(client, "Shopping")
    _add(client, "Paz January", 100, "2026-01-05", fuel_id)
    _add(client, "Paz January again", 40, "2026-01-20", fuel_id)
    _add(client, "Paz March", 25, "2026-03-02", fuel_id)
    _add(client, "Mall", 80, "2026-01-08", shopping_id)
    ignored = _add(client, "Ignored fuel", 999, "2026-02-01", fuel_id)
    patched = client.patch(
        f"/transactions/{ignored}",
        json={"ignored": True, "ignore_reason": "duplicate"},
    )
    assert patched.status_code == 200

    shown = client.get(
        f"/graphs?category_id={fuel_id}&date_from=&date_to="
    ).get_data(as_text=True)
    assert "Fuel and transport" in shown
    assert "Jan 2026" in shown
    assert "140.00" in shown
    assert "Feb 2026" in shown
    assert "0.00" in shown
    assert "Mar 2026" in shown
    assert "25.00" in shown
    assert "165.00" in shown
    assert "55.00" in shown
    assert "Monthly average" in shown
    assert "999" not in shown
    assert "80.00" not in shown


def test_graphs_uses_installment_month(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    _add(
        client,
        "KSP",
        50,
        "2026-01-16",
        fuel_id,
        details="תשלום 3 מתוך 3",
    )
    shown = client.get(
        f"/graphs?category_id={fuel_id}&date_from=&date_to="
    ).get_data(as_text=True)
    assert "Mar 2026" in shown
    assert "50.00" in shown
    assert "Jan 2026" not in shown


def test_graphs_date_range_and_payments(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    _add(client, "Paz", 30, "2026-02-05", fuel_id)
    _add(client, "KSP", 70, "2026-03-10", fuel_id, details="תשלום 1 מתוך 2")
    _add(client, "Paz May", 11, "2026-05-01", fuel_id)

    shown = client.get(
        f"/graphs?category_id={fuel_id}&date_from=2026-01&date_to=2026-04"
    ).get_data(as_text=True)
    assert 'value="2026-01"' in shown
    assert 'value="2026-04"' in shown
    assert "Jan 2026" in shown
    assert "Apr 2026" in shown
    assert "May 2026" not in shown
    assert "1 / 1" in shown
    assert "70.00" in shown
    assert "2 / 1" in shown
    assert "100.00" in shown
    assert "25.00" in shown
    assert "Installment payments" in shown


def test_graphs_defaults_to_current_month(client):
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    today = date.today()
    _add(client, "This month", 15, today.isoformat(), fuel_id)
    _add(client, "Last year", 99, date(today.year - 1, today.month, 1).isoformat(), fuel_id)

    shown = client.get(f"/graphs?category_id={fuel_id}").get_data(as_text=True)
    assert f'value="{today:%Y-%m}"' in shown
    assert "15.00" in shown
    assert "99.00" not in shown


def test_graphs_hebrew_label(client):
    client.set_cookie("lang", "he")
    page = client.get("/graphs")
    assert "גרפים" in page.get_data(as_text=True)
    fuel_id = _id_by_name_en(client, "Fuel and transport")
    _add(client, "Paz", 10, "2026-10-04", fuel_id)
    shown = client.get(
        f"/graphs?category_id={fuel_id}&date_from=&date_to="
    ).get_data(as_text=True)
    assert "אוק 2026" in shown
