"""Customers, reference catalogue, global search, paginated inventory/orders and the extended analytics."""
from __future__ import annotations

import math

import pytest
from .helpers import AuthedClient
from sqlalchemy import create_engine, text

from app.db import upgrade_schema


# ------------------------------------------------------------------ catalogue
def test_catalog_is_loaded_from_the_sourced_file(client):
    src = client.get("/api/catalog/source").json()
    assert src["rows_loaded"] > 4000 and src["manifest_found"]
    assert "ODbL" in src["licence"] or "Open Database" in src["licence"]
    assert src["retrieved_on"] == "2026-11-10" and src["limitations"]


def test_catalog_search_filters_and_pagination(client):
    r = client.get("/api/catalog", params={"q": "amul butter", "page_size": 5}).json()
    assert r["total"] >= 1 and all("amul" in (i["name"] + i["brand"]).lower() for i in r["items"])
    assert all(i["provenance"] == "transformed" and i["ean"].isdigit() for i in r["items"])
    cats = client.get("/api/catalog/facets").json()
    assert cats["total"] == sum(c["count"] for c in cats["categories"])
    one = cats["categories"][0]["name"]
    page1 = client.get("/api/catalog", params={"category": one, "page_size": 10}).json()
    page2 = client.get("/api/catalog", params={"category": one, "page_size": 10, "page": 2}).json()
    assert page1["total"] == cats["categories"][0]["count"]
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})
    assert client.get("/api/catalog", params={"page_size": 100000}).json()["page_size"] == 100


def test_catalog_has_no_price_field_anywhere(client):
    item = client.get("/api/catalog", params={"page_size": 1}).json()["items"][0]
    detail = client.get(f"/api/catalog/{item['id']}").json()
    for d in (item, detail):
        assert not [k for k in d if "price" in k or k in ("mrp", "stock")]


def test_import_needs_a_shop_price_and_creates_a_sellable_product(client):
    item = client.get("/api/catalog", params={"q": "tata salt", "page_size": 1}).json()["items"][0]
    assert client.post(f"/api/catalog/{item['id']}/import", json={"stock": 5}).status_code == 422  # no price: refused
    r = client.post(f"/api/catalog/{item['id']}/import", json={"price_paise": 2800, "stock": 12, "reorder_level": 3})
    assert r.status_code == 201
    p = r.json()
    assert p["source"] == "off_india" and p["price_basis"] == "shop" and p["ean"] == item["ean"]
    assert p["source_ref"].endswith(item["ean"]) and p["unit"] == "pack" and p["aliases"]
    assert client.post(f"/api/catalog/{item['id']}/import", json={"price_paise": 2800}).status_code == 409
    assert client.post("/api/catalog/99999999/import", json={"price_paise": 100}).status_code == 404
    got = client.get("/api/catalog", params={"q": item["ean"]}).json()["items"][0]
    assert got["in_shop"] is True


def test_imported_branded_item_can_be_ordered_by_voice_text(client):
    item = client.get("/api/catalog", params={"q": "amul butter", "page_size": 1}).json()["items"][0]
    client.post(f"/api/catalog/{item['id']}/import", json={"price_paise": 6000, "stock": 20})
    r = client.post("/api/text/turn", json={"text": "ek amul butter"}).json()
    assert r["cart"]["lines"] and r["cart"]["lines"][0]["name_en"].lower().startswith("amul butter")
    assert r["cart"]["total_paise"] == 6000


def test_importing_does_not_hijack_generic_words(client):
    for q in ("amul", "tata", "parle", "britannia", "maggi"):
        for it in client.get("/api/catalog", params={"q": q, "page_size": 30}).json()["items"]:
            client.post(f"/api/catalog/{it['id']}/import", json={"price_paise": 1000, "stock": 5})
    r = client.post("/api/text/turn", json={"text": "2 kilo chawal aur 1 litre doodh"}).json()
    names = [l["name_en"] for l in r["cart"]["lines"]]
    assert names == ["Rice", "Milk"] and r["cart"]["total_paise"] == 2 * 5800 + 5600
    assert client.post("/api/text/turn", json={"text": "hello how are you"}).json()["cart"]["lines"] == []


# ------------------------------------------------------------------ products / inventory
def test_curated_products_are_labelled_demo(client):
    p = client.get("/api/inventory", params={"page_size": 100}).json()
    curated = [i for i in p["items"] if i["source"] == "curated"]
    assert len(curated) == 65 and all(i["price_basis"] == "demo" for i in curated)
    assert all(i["cost_paise"] is None for i in curated)  # a cost is something only the shopkeeper knows


def test_editing_a_price_marks_it_as_the_shops_own(client):
    pid = client.get("/api/products").json()[0]["id"]
    assert client.get(f"/api/products/{pid}").json()["price_basis"] == "demo"
    client.patch(f"/api/products/{pid}", json={"price_paise": 6100})
    assert client.get(f"/api/products/{pid}").json()["price_basis"] == "shop"


def test_inventory_pagination_sorting_search_and_counts(client):
    r = client.get("/api/inventory", params={"page_size": 10, "sort": "value"}).json()
    assert r["total"] == 65 and len(r["items"]) == 10 and r["counts"]["all"] == 65
    values = [i["stock_value_paise"] for i in r["items"]]
    assert values == sorted(values, reverse=True)
    assert sum(r["counts"][k] for k in ("ok", "low", "out")) == 65
    low = client.get("/api/inventory", params={"status": "low", "page_size": 100}).json()
    assert low["total"] == r["counts"]["low"] and all(i["stock_status"] == "low" for i in low["items"])
    assert low["counts"]["all"] == 65  # tab counts stay stable while a status filter is active
    q = client.get("/api/inventory", params={"q": "basmati"}).json()
    assert q["total"] >= 1 and all("basmati" in i["name_en"].lower() for i in q["items"])
    assert client.get("/api/inventory", params={"page": 0, "page_size": 0}).json()["page"] == 1


# ------------------------------------------------------------------ customers
def test_customer_list_stats_match_orders(client):
    r = client.get("/api/customers", params={"sort": "spent", "page_size": 50}).json()
    assert r["total"] == 8 and all(c["is_synthetic"] for c in r["items"])
    spent = [c["spent_paise"] for c in r["items"]]
    assert spent == sorted(spent, reverse=True) and spent[0] > 0
    top = r["items"][0]
    orders = client.get("/api/orders", params={"customer_id": top["id"], "limit": 100}).json()
    assert orders["total"] >= top["orders"]  # includes cancelled orders; stats exclude them
    live = [o for o in client.get("/api/orders", params={"customer_id": top["id"], "limit": 100}).json()["items"] if o["status"] != "cancelled"]
    assert sum(o["total_paise"] for o in live) == top["spent_paise"] if orders["total"] <= 100 else True


def test_customer_detail_has_top_products_and_languages(client):
    cid = client.get("/api/customers").json()["items"][0]["id"]
    d = client.get(f"/api/customers/{cid}").json()
    assert d["top_products"] and d["language_mix"]
    assert d["top_products"] == sorted(d["top_products"], key=lambda x: -x["revenue_paise"])
    assert client.get("/api/customers/99999").status_code == 404


def test_customer_crud_and_validation(client):
    r = client.post("/api/customers", json={"name": "  Ramesh Patel ", "phone": "+91 98765 43210", "language": "gu"})
    assert r.status_code == 201
    c = r.json()
    assert c["name"] == "Ramesh Patel" and c["is_synthetic"] is False and c["orders"] == 0
    assert client.post("/api/customers", json={"name": "", "phone": ""}).status_code == 422
    assert client.post("/api/customers", json={"name": "X", "phone": "<script>"}).status_code == 422
    assert client.post("/api/customers", json={"name": "X", "language": "fr"}).status_code == 422
    assert client.patch(f"/api/customers/{c['id']}", json={"notes": "Pays monthly"}).json()["notes"] == "Pays monthly"
    assert client.get("/api/customers", params={"q": "ramesh", "include_synthetic": False}).json()["total"] == 1
    client.patch(f"/api/customers/{c['id']}", json={"is_active": False})
    assert client.get("/api/customers", params={"q": "ramesh"}).json()["total"] == 0


def test_order_placed_for_a_selected_customer_is_linked(client):
    c = client.post("/api/customers", json={"name": "Meena Shah", "language": "hi"}).json()
    r = client.post("/api/text/turn", json={"text": "2 kilo chawal", "customer_id": c["id"]}).json()
    sid = r["session_id"]
    client.post("/api/text/turn", json={"text": "bas itna hi", "session_id": sid})
    done = client.post("/api/text/turn", json={"text": "haan", "session_id": sid}).json()
    assert done["order"]["customer_id"] == c["id"] and done["order"]["customer_name"] == "Meena Shah"
    d = client.get(f"/api/customers/{c['id']}").json()
    assert d["orders"] == 1 and d["spent_paise"] == 11600
    assert client.get("/api/orders", params={"customer_id": c["id"]}).json()["total"] == 1


def test_unknown_customer_id_falls_back_to_walk_in(client):
    r = client.post("/api/text/turn", json={"text": "1 kilo chawal", "customer_id": 99999}).json()
    sid = r["session_id"]
    client.post("/api/text/turn", json={"text": "bas", "session_id": sid})
    done = client.post("/api/text/turn", json={"text": "yes", "session_id": sid}).json()
    assert done["order"]["customer_name"] == "Walk-in customer" and done["order"]["customer_id"] is None


# ------------------------------------------------------------------ search / orders filters
def test_global_search_groups_results(client):
    r = client.get("/api/search", params={"q": "milk"}).json()
    assert r["products"] and any("milk" in p["title"].lower() for p in r["products"])
    assert r["catalog_total"] > 0
    assert client.get("/api/search", params={"q": "a"}).json()["products"] == []  # too short
    c = client.get("/api/search", params={"q": "Demo Customer"}).json()
    assert c["customers"] and c["orders"]


def test_order_search_by_code_number_and_customer(client):
    first = client.get("/api/orders", params={"limit": 1}).json()["items"][0]
    by_code = client.get("/api/orders", params={"q": first["code"]}).json()
    assert first["id"] in [o["id"] for o in by_code["items"]]
    by_name = client.get("/api/orders", params={"q": first["customer_name"], "limit": 100}).json()
    assert by_name["total"] >= 1 and all(o["customer_name"] == first["customer_name"] for o in by_name["items"])
    cheap = client.get("/api/orders", params={"sort": "total_low", "limit": 5}).json()["items"]
    assert [o["total_paise"] for o in cheap] == sorted(o["total_paise"] for o in cheap)


# ------------------------------------------------------------------ analytics
def test_sales_series_grains_add_up(client):
    day = client.get("/api/analytics/sales", params={"grain": "day", "periods": 30}).json()
    assert len(day["series"]) == 30 and day["totals"]["orders"] == sum(p["orders"] for p in day["series"])
    ov = client.get("/api/analytics/overview", params={"days": 30}).json()
    assert day["totals"]["revenue_paise"] == ov["kpis"]["revenue_paise"]  # one source of truth
    week = client.get("/api/analytics/sales", params={"grain": "week", "periods": 8}).json()
    assert len(week["series"]) == 8 and all(p["period"] for p in week["series"])
    from datetime import date
    assert all(date.fromisoformat(p["period"]).weekday() == 0 for p in week["series"])  # weeks start on Monday
    assert week["series"][-1]["partial"] is True
    month = client.get("/api/analytics/sales", params={"grain": "month", "periods": 3}).json()
    assert len(month["series"]) == 3 and all(p["period"].endswith("-01") for p in month["series"])
    assert client.get("/api/analytics/sales", params={"grain": "bogus"}).json()["grain"] == "day"
    none = client.get("/api/analytics/sales", params={"include_synthetic": False}).json()
    assert none["totals"]["orders"] == 0  # a fresh install has no real orders: nothing is invented


def test_inventory_summary_valuation_matches_products(client):
    s = client.get("/api/analytics/inventory").json()
    items = client.get("/api/inventory", params={"page_size": 100}).json()["items"]
    assert s["valuation_retail_paise"] == sum(i["stock_value_paise"] for i in items)
    assert s["valuation_cost_paise"] is None and s["products_with_cost"] == 0
    assert s["price_basis"]["demo"] == 65
    assert s["stock_health"]["low"] == len(s["low_stock"]) and s["stock_health"]["out"] == len(s["out_of_stock"])
    assert sum(c["retail_paise"] for c in s["by_category"]) == s["valuation_retail_paise"]
    pid = items[0]["id"]
    client.patch(f"/api/products/{pid}", json={"cost_paise": 100})
    s2 = client.get("/api/analytics/inventory").json()
    assert s2["products_with_cost"] == 1 and s2["valuation_cost_paise"] > 0


def test_demand_insights_are_internally_consistent(client):
    d = client.get("/api/analytics/demand", params={"days": 30}).json()
    assert "Not a forecast" in d["method"] and d["products"]
    for r in d["products"]:
        assert abs(r["velocity_per_day"] - r["units_sold"] / 30) < 0.001
        if r["days_of_cover"] is not None:
            assert abs(r["days_of_cover"] - r["stock"] / (r["units_sold"] / 30)) <= 0.05 + 1e-9  # velocity itself is shown rounded
        assert r["suggested_reorder_qty"] >= 0
    assert all(r["status"] == "stockout_risk" for r in d["stockout_risk"])
    revs = [r["revenue_paise"] for r in d["products"]]
    assert revs == sorted(revs, reverse=True)


# ------------------------------------------------------------------ schema upgrade
def test_upgrade_adds_missing_columns_to_a_v1_database(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, sku VARCHAR(40), name_en VARCHAR(120))"))
        c.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, total_paise INTEGER)"))
        c.execute(text("CREATE TABLE sessions (id VARCHAR(40) PRIMARY KEY)"))
        c.execute(text("INSERT INTO products VALUES (1, 'A', 'Old product')"))
    added = upgrade_schema(eng)
    assert "products.brand" in added and "orders.customer_id" in added and "sessions.customer_id" in added
    with eng.connect() as c:
        row = c.execute(text("SELECT name_en, brand, source, price_basis FROM products")).one()
    assert row == ("Old product", "", "manual", "shop")  # old rows keep their data and get honest defaults
    assert upgrade_schema(eng) == []  # idempotent
    eng.dispose()


def test_sales_series_allows_enough_periods_for_a_full_comparison(client):
    """The Analytics page compares the last N complete periods with the N before, plus one in-progress period."""
    for grain, want in (("day", 61), ("week", 25), ("month", 25)):
        got = client.get("/api/analytics/sales", params={"grain": grain, "periods": want}).json()
        assert len(got["series"]) == want, grain
    # and it still stops somewhere sensible
    assert len(client.get("/api/analytics/sales", params={"grain": "day", "periods": 5000}).json()["series"]) == 366


def test_demand_trend_is_withheld_when_the_earlier_window_has_no_history(client):
    """The demo data covers about 31 days. A 30-day window therefore has no real 'earlier 30 days' to compare with, and
    showing +6000% would be arithmetic dressed up as insight. A 7-day window does have one."""
    wide = client.get("/api/analytics/demand", params={"days": 30}).json()
    assert wide["previous_window"]["comparable"] is False
    assert all(r["trend_pct"] is None for r in wide["products"])
    assert not wide["rising"] and not wide["falling"]
    short = client.get("/api/analytics/demand", params={"days": 7}).json()
    assert short["previous_window"] == {"days": 7, "days_with_orders": short["previous_window"]["days_with_orders"], "comparable": True}
    assert short["previous_window"]["days_with_orders"] >= 4
    assert any(r["trend_pct"] is not None for r in short["products"])
    # A product that sold very little in the earlier week can honestly show a huge percentage (that is arithmetic on a small base, not a defect), and the
    # seeded demo orders land differently depending on the hour the test runs (found when a run crossed midnight IST: 0.25 kg of okra then 15.75 kg).
    # So the invariants are: finite numbers, and the "rising" / "falling" lists only ever hold products with enough units sold to mean something.
    assert all(math.isfinite(r["trend_pct"]) for r in short["products"] if r["trend_pct"] is not None)
    assert all(r["units_sold"] >= 3 for r in short["rising"] + short["falling"])


# ------------------------------------------------------------------ longer demo history (the default for a fresh install)
@pytest.fixture
def long_client(make_app):
    with AuthedClient(make_app(demo_history_days=120)) as c:
        yield c


def test_default_demo_history_is_long_enough_for_weekly_monthly_and_30_day_comparisons():
    from app.config import Settings
    assert Settings(_env_file=None).demo_history_days == 120


def test_long_history_gives_a_real_earlier_window_and_fills_the_monthly_chart(long_client):
    d = long_client.get("/api/analytics/demand", params={"days": 30}).json()
    assert d["previous_window"]["comparable"] is True and d["previous_window"]["days_with_orders"] >= 28
    assert any(r["trend_pct"] is not None for r in d["products"])
    assert all(abs(r["trend_pct"]) < 1000 for r in d["products"] if r["trend_pct"] is not None)
    month = long_client.get("/api/analytics/sales", params={"grain": "month", "periods": 5}).json()["series"]
    assert len(month) == 5 and sum(1 for p in month if p["orders"] > 0) >= 4
    day = long_client.get("/api/analytics/sales", params={"grain": "day", "periods": 61}).json()["series"]
    assert sum(1 for p in day if p["orders"] > 0) >= 60 and day[-1]["partial"] is True
    # every generated order is still labelled synthetic: a longer history is still not real sales
    assert long_client.get("/api/analytics/sales", params={"include_synthetic": False}).json()["totals"]["orders"] == 0


def test_only_the_period_containing_today_is_flagged_as_unfinished(client):
    """Regression: the in-progress DAY used to be reported as complete, so half a day was charted and compared as a whole one."""
    day = client.get("/api/analytics/sales", params={"grain": "day", "periods": 5}).json()["series"]
    assert [p["partial"] for p in day] == [False, False, False, False, True]
    for grain in ("week", "month"):
        s = client.get("/api/analytics/sales", params={"grain": grain, "periods": 4}).json()["series"]
        assert [p["partial"] for p in s] == [False, False, False, True], grain


@pytest.mark.parametrize("now_utc", [
    "2026-11-08 06:00:00",   # a Sunday morning IST: the week ends tonight, so it is still unfinished
    "2026-11-30 10:00:00",   # the last day of a month
    "2026-11-09 19:00:00",   # 00:30 IST on Tuesday 10 Nov, i.e. IST is already a day ahead of UTC
])
def test_unfinished_flags_hold_on_week_and_month_boundaries(client, monkeypatch, now_utc):
    from datetime import datetime, timedelta
    from app.services import analytics
    fixed = datetime.fromisoformat(now_utc)
    monkeypatch.setattr(analytics, "utcnow", lambda: fixed)
    today = (fixed + timedelta(minutes=330)).date()
    for grain in ("day", "week", "month"):
        s = client.get("/api/analytics/sales", params={"grain": grain, "periods": 3}).json()["series"]
        assert [p["partial"] for p in s] == [False, False, True], (grain, today)
        assert s[-1]["period"] <= today.isoformat()
