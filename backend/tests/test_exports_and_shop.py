"""CSV exports (orders, stock, customers) and the owner-editable shop name."""
from __future__ import annotations

import csv
import io

import pytest

from app.config import Settings
from app.routers.settings import _env_value, _write_env, clean_store_name


def rows_of(resp) -> list[list[str]]:
    assert resp.status_code == 200, resp.text
    text = resp.content.decode("utf-8")
    assert text.startswith("﻿"), "starts with a byte-order mark so Excel reads Gujarati and Hindi correctly"
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


# ------------------------------------------------------------------ orders
def test_orders_export_matches_the_screen_filters(client):
    r = client.get("/api/orders/export.csv", params={"language": "gu"})
    assert r.headers["content-type"].startswith("text/csv") and r.headers["cache-control"] == "no-store"
    assert r.headers["content-disposition"].startswith('attachment; filename="swara-orders-') and r.headers["content-disposition"].endswith('.csv"')
    rows = rows_of(r)
    header, body = rows[0], rows[1:]
    assert header[:3] == ["Bill", "Date (IST)", "Status"] and "Demo data" in header
    col = {h: i for i, h in enumerate(header)}
    total = client.get("/api/orders", params={"language": "gu", "limit": 1}).json()["total"]
    assert total > 0
    assert len({r_[col["Bill"]] for r_ in body}) == total, "one bill per order the list shows"
    assert {r_[col["Language"]] for r_ in body} == {"gu"}
    assert {r_[col["Demo data"]] for r_ in body} == {"Yes"}, "generated orders are labelled in the file too"


def test_orders_export_lines_add_up_to_the_bill_total(client):
    rows = rows_of(client.get("/api/orders/export.csv", params={"channel": "text", "status": "fulfilled"}))
    col = {h: i for i, h in enumerate(rows[0])}
    bills: dict[str, tuple[float, float]] = {}
    for r_ in rows[1:]:
        s, t = bills.get(r_[col["Bill"]], (0.0, float(r_[col["Bill total (INR)"]])))
        bills[r_[col["Bill"]]] = (s + float(r_[col["Amount (INR)"]]), t)
    assert bills and all(abs(s - t) < 0.005 for s, t in bills.values())


def test_orders_export_can_leave_out_demo_data(client):
    rows = rows_of(client.get("/api/orders/export.csv", params={"include_synthetic": "false"}))
    assert len(rows) == 1, "a fresh shop has only generated orders, so only the header row is left"


def test_orders_export_dates_are_indian_time(client):
    rows = rows_of(client.get("/api/orders/export.csv", params={"sort": "newest"}))
    api_first = client.get("/api/orders", params={"limit": 1}).json()["items"][0]
    assert rows[1][0] == api_first["code"]
    from datetime import datetime, timedelta
    utc = datetime.fromisoformat(api_first["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
    assert rows[1][1] == (utc + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ inventory
def test_inventory_export_filters_like_the_screen(client):
    low = client.get("/api/inventory", params={"status": "low", "page_size": 100}).json()
    rows = rows_of(client.get("/api/inventory/export.csv", params={"status": "low"}))
    col = {h: i for i, h in enumerate(rows[0])}
    assert len(rows) - 1 == low["total"] > 0
    assert {r_[col["Status"]] for r_ in rows[1:]} == {"Running low"}
    assert {r_[col["Name"]] for r_ in rows[1:]} == {p["name_en"] for p in low["items"]}
    everything = rows_of(client.get("/api/inventory/export.csv"))
    assert len(everything) - 1 == client.get("/api/inventory", params={"page_size": 1}).json()["total"]
    first = everything[1]
    p = client.get("/api/inventory", params={"page_size": 1}).json()["items"][0]
    assert float(first[col["Price (INR)"]]) == pytest.approx(p["price_paise"] / 100)
    assert float(first[col["Stock value at price (INR)"]]) == pytest.approx(p["stock_value_paise"] / 100)
    assert first[col["Price basis"]] in {"Your price", "Demo price"}


def test_inventory_export_keeps_gujarati_and_hindi_names(client):
    rows = rows_of(client.get("/api/inventory/export.csv"))
    col = {h: i for i, h in enumerate(rows[0])}
    assert any(r_[col["Gujarati name"]] for r_ in rows[1:]) and any(r_[col["Hindi name"]] for r_ in rows[1:])


# ------------------------------------------------------------------ spreadsheet formula injection
def test_text_that_looks_like_a_formula_is_exported_as_text(client):
    evil = ["=HYPERLINK(\"http://evil.example\",\"click\")", "+SUM(1+1)", "-2+3", "@SUM(A1)"]
    for i, name in enumerate(evil):
        assert client.post("/api/products", json={"sku": f"EVIL-{i}", "name_en": name, "unit": "pc", "price_paise": 100}).status_code == 201
        assert client.post("/api/customers", json={"name": name, "notes": name}).status_code == 201
    inv = rows_of(client.get("/api/inventory/export.csv", params={"q": "EVIL"}))
    names = {r_[1] for r_ in inv[1:]}
    assert names == {"'" + n for n in evil}, "each name keeps its text and gains a leading apostrophe, so no cell starts with = + - or @"
    cust = rows_of(client.get("/api/customers/export.csv", params={"include_synthetic": "false"}))
    assert {r_[0] for r_ in cust[1:]} == {"'" + n for n in evil}
    assert {r_[7] for r_ in cust[1:]} == {"'" + n for n in evil}
    for table in (inv, cust):
        assert not [c for r_ in table[1:] for c in r_ if c and c[0] in "=+-@"], "no exported cell starts with a formula character"


def test_numbers_are_not_quoted_and_quotes_commas_survive(client):
    assert client.post("/api/customers", json={"name": 'Mehta, "Raju" & Sons', "phone": "+91 98765 43210"}).status_code == 201
    cust = rows_of(client.get("/api/customers/export.csv", params={"include_synthetic": "false"}))
    row = next(r_ for r_ in cust[1:] if r_[0].startswith("Mehta"))
    assert row[0] == 'Mehta, "Raju" & Sons'
    assert row[1] == "'+91 98765 43210", "a phone number that begins with + is text, not a formula"
    assert row[3] == "0" and row[4] == "0.00"


# ------------------------------------------------------------------ customers + access
def test_customers_export_works_for_the_owner(client):
    assert client.get("/api/customers/export.csv").status_code == 200


def test_customers_export_refuses_staff(staff):
    r = staff.get("/api/customers/export.csv")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "OWNER_ONLY"


def test_customers_export_refuses_visitors(anon):
    assert anon.get("/api/customers/export.csv").status_code == 401


@pytest.mark.parametrize("path", ["/api/orders/export.csv", "/api/inventory/export.csv"])
def test_orders_and_stock_exports_need_a_sign_in_but_not_ownership(staff, path):
    assert staff.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/api/orders/export.csv", "/api/inventory/export.csv"])
def test_orders_and_stock_exports_refuse_visitors(anon, path):
    assert anon.get(path).status_code == 401


def test_customers_export_columns_and_totals(client):
    rows = rows_of(client.get("/api/customers/export.csv"))
    col = {h: i for i, h in enumerate(rows[0])}
    api = client.get("/api/customers", params={"page_size": 100, "sort": "name"}).json()
    assert len(rows) - 1 == api["total"]
    by_name = {c["name"]: c for c in api["items"]}
    for r_ in rows[1:]:
        c = by_name.get(r_[col["Name"]])
        if c:
            assert int(r_[col["Orders"]]) == c["orders"] and float(r_[col["Total spent (INR)"]]) == pytest.approx(c["spent_paise"] / 100)


# ------------------------------------------------------------------ shop name
@pytest.fixture
def env_file(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    monkeypatch.setattr("app.routers.settings.ENV_FILE", path)
    return path


def test_the_owner_can_rename_the_shop_and_everything_shows_it(client, env_file):
    before = client.get("/api/health").json()
    assert "demo" in before["store_name"].lower() and before["store_name_is_default"] is True   # the built-in demo name, labelled as such
    r = client.put("/api/settings", json={"store_name": "  Shah   Kirana & Stores  "})
    assert r.status_code == 200 and r.json()["store_name"] == "Shah Kirana & Stores"
    after = client.get("/api/health").json()
    assert after["store_name"] == "Shah Kirana & Stores" and after["store_name_is_default"] is False
    assert client.get("/api/settings").json()["store_name"] == "Shah Kirana & Stores"


def test_a_shop_name_survives_a_restart(client, env_file):
    for name in ("Shah Kirana & Stores", "શાહ કરિયાણા સ્ટોર", "पटेल किराना (नवरंगपुरा)", "M/S Ravi's #1? no", None):
        if name is None:
            continue
        try:
            clean = clean_store_name(name)
        except ValueError:
            continue
        r = client.put("/api/settings", json={"store_name": clean})
        assert r.status_code == 200
        assert Settings(_env_file=str(env_file)).store_name == clean, f"{clean!r} must read back from .env exactly"


@pytest.mark.parametrize("bad", ["", " ", "x", "a" * 81, "#$%", "Shop\nGNANI_API_KEY=stolen1234", "Shop #1", "Shop \"quoted\"", "Shop ${HOME}", "Shop \\ slash", "<b>Shop</b>", "Shop;rm", "Shop‮evil"])
def test_a_bad_shop_name_is_refused_and_nothing_is_written(client, env_file, bad):
    r = client.put("/api/settings", json={"store_name": bad})
    assert r.status_code == 422
    assert not env_file.exists()
    assert "demo" in client.get("/api/health").json()["store_name"].lower()


def test_staff_cannot_rename_the_shop(staff, env_file):
    r = staff.put("/api/settings", json={"store_name": "Mine now"})
    assert r.status_code == 403 and not env_file.exists()


def test_env_values_are_quoted_only_when_they_need_to_be(tmp_path, monkeypatch):
    assert _env_value("prisma-v2.5") == "prisma-v2.5" and _env_value("1.1") == "1.1"
    assert _env_value("Shah Kirana") == '"Shah Kirana"'
    monkeypatch.setattr("app.routers.settings.ENV_FILE", tmp_path / ".env")
    (tmp_path / ".env").write_text("GNANI_STT_MODEL=prisma-v2.5\nSTORE_NAME=old\n", encoding="utf-8")
    _write_env({"STORE_NAME": "New Name & Co", "TTS_SPEED": "1.1"})
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert text.splitlines() == ['GNANI_STT_MODEL=prisma-v2.5', 'STORE_NAME="New Name & Co"', "TTS_SPEED=1.1"]
