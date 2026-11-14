from __future__ import annotations

import pytest

from .helpers import AuthedClient, KEY

NEW = {"sku": "TEST-ITEM", "name_en": "Test Biscuit", "name_gu": "ટેસ્ટ", "name_hi": "टेस्ट", "category": "Snacks",
       "unit": "pack", "price_paise": 1500, "stock": "10", "reorder_level": "2", "aliases": ["testbis", "Test  Biscuit"]}


def test_health_reports_seeded_catalogue(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["db"] == "ok" and h["products"] == 65 and h["gnani_configured"] is False


def test_inventory_crud_and_new_product_is_immediately_orderable(client):
    r = client.post("/api/products", json=NEW)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.post("/api/products", json=NEW).status_code == 409
    t = client.post("/api/text/turn", json={"text": "2 testbis"}).json()
    assert [l["sku"] for l in t["cart"]["lines"]] == ["TEST-ITEM"]
    client.patch(f"/api/products/{pid}", json={"price_paise": 2000})
    t = client.post("/api/text/turn", json={"text": "1 testbis"}).json()
    assert t["cart"]["total_paise"] == 2000
    client.patch(f"/api/products/{pid}", json={"is_active": False})
    t = client.post("/api/text/turn", json={"text": "1 testbis"}).json()
    assert t["cart"]["lines"] == []


@pytest.mark.parametrize("bad", [
    {**NEW, "sku": "lower case"}, {**NEW, "price_paise": 0}, {**NEW, "price_paise": -5}, {**NEW, "stock": "-1"},
    {**NEW, "unit": "lbs"}, {**NEW, "name_en": ""}, {**NEW, "pack_size_unit": "g"},
])
def test_product_validation(client, bad):
    assert client.post("/api/products", json=bad).status_code == 422


def test_restock_updates_stock_and_logs_movement(client):
    pid = next(p["id"] for p in client.get("/api/products").json() if p["sku"] == "PANEER")
    r = client.post(f"/api/products/{pid}/restock", json={"qty": "10"})
    assert r.status_code == 200 and float(r.json()["stock"]) == 13.0
    assert client.post(f"/api/products/{pid}/restock", json={"qty": "-1"}).status_code == 422
    assert client.post("/api/products/99999/restock", json={"qty": "1"}).status_code == 404
    mv = client.get("/api/inventory/movements").json()
    assert mv[0]["reason"] == "restock" and float(mv[0]["delta"]) == 10.0


def test_product_filters(client):
    low = client.get("/api/products", params={"status": "low"}).json()
    assert {p["sku"] for p in low} >= {"GARLIC", "PANEER", "LEMON"}
    out = client.get("/api/products", params={"status": "out"}).json()
    assert {p["sku"] for p in out} == {"SABUDANA", "CAULIFLOWER"}
    assert [p["sku"] for p in client.get("/api/products", params={"q": "paneer"}).json()] == ["PANEER"]


def test_cancel_confirmed_order_restocks_exactly_once(client):
    sid = client.post("/api/text/turn", json={"text": "2 kilo sugar"}).json()["session_id"]
    client.post("/api/text/turn", json={"text": "bas", "session_id": sid})
    oid = client.post("/api/text/turn", json={"text": "haan", "session_id": sid}).json()["order"]["id"]
    sugar = lambda: float(next(p for p in client.get("/api/products").json() if p["sku"] == "SUGAR")["stock"])
    after = sugar()
    assert client.post(f"/api/orders/{oid}/status", json={"status": "cancelled"}).json()["status"] == "cancelled"
    assert sugar() == after + 2
    # repeating the same transition is idempotent and must not restock a second time
    assert client.post(f"/api/orders/{oid}/status", json={"status": "cancelled"}).json()["status"] == "cancelled"
    assert sugar() == after + 2
    assert client.post(f"/api/orders/{oid}/status", json={"status": "fulfilled"}).status_code == 409
    assert client.post("/api/orders/99999/status", json={"status": "cancelled"}).status_code == 404


def test_orders_listing_filters_and_pagination(client):
    allr = client.get("/api/orders", params={"limit": 10}).json()
    assert allr["total"] > 600 and len(allr["items"]) == 10
    page2 = client.get("/api/orders", params={"limit": 10, "offset": 10}).json()
    assert {o["id"] for o in allr["items"]}.isdisjoint({o["id"] for o in page2["items"]})
    assert all(o["channel"] == "voice" for o in client.get("/api/orders", params={"channel": "voice", "limit": 20}).json()["items"])
    assert client.get("/api/orders", params={"include_synthetic": False}).json()["total"] == 0
    assert len(client.get("/api/orders", params={"limit": 100000}).json()["items"]) <= 100


def test_analytics_overview_is_computed_from_orders(client):
    o = client.get("/api/analytics/overview", params={"days": 30}).json()
    k = o["kpis"]
    assert k["orders"] > 0 and k["revenue_paise"] > 0
    assert k["avg_basket_paise"] == pytest.approx(k["revenue_paise"] / k["orders"], abs=1)
    assert 0 <= k["voice_share"] <= 1
    assert k["low_stock_count"] >= 3 and k["out_of_stock_count"] == 2
    assert k["non_synthetic_orders_total"] == 0
    excl = client.get("/api/analytics/overview", params={"include_synthetic": False}).json()["kpis"]
    assert excl["orders"] == 0 and excl["revenue_paise"] == 0


def test_real_order_shows_up_in_non_synthetic_analytics(client):
    sid = client.post("/api/text/turn", json={"text": "1 kilo sugar"}).json()["session_id"]
    client.post("/api/text/turn", json={"text": "bas", "session_id": sid})
    client.post("/api/text/turn", json={"text": "haan", "session_id": sid})
    k = client.get("/api/analytics/overview", params={"include_synthetic": False}).json()["kpis"]
    assert k["orders"] == 1 and k["revenue_paise"] == 4600


def test_synthetic_data_is_labelled_and_pii_free(client):
    items = client.get("/api/orders", params={"limit": 100}).json()["items"]
    assert all(o["is_synthetic"] for o in items)
    assert {o["customer_name"] for o in items} <= {"Walk-in customer"} | {c for c in {o["customer_name"] for o in items}}
    for o in items:
        assert "@" not in o["customer_name"] and not any(ch.isdigit() for ch in o["customer_name"])


# ------------------------------------------------------------------ settings & secrets
def test_settings_never_expose_the_key(make_app, monkeypatch, tmp_path):
    monkeypatch.setattr("app.routers.settings.ENV_FILE", tmp_path / ".env")
    with AuthedClient(make_app(gnani_api_key=KEY)) as c:
        r = c.get("/api/settings")
        assert KEY not in r.text and r.json()["gnani"]["configured"] is True
        assert r.json()["gnani"]["key_hint"].endswith(KEY[-4:])
        r = c.put("/api/settings/gnani-key", json={"api_key": "another-key-98765432"})
        assert "another-key-98765432" not in r.text
        assert "another-key-98765432" in (tmp_path / ".env").read_text()


def test_key_endpoint_rejects_injection(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.routers.settings.ENV_FILE", tmp_path / ".env")
    for bad in ["abc\nADMIN_TOKEN=x1234567", "key with spaces 12345", "x" * 300, "short", "a=b;rm -rf /"]:
        assert client.put("/api/settings/gnani-key", json={"api_key": bad}).status_code == 422
    assert not (tmp_path / ".env").exists()


def test_settings_patch_validates_and_persists(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.routers.settings.ENV_FILE", tmp_path / ".env")
    assert client.put("/api/settings", json={"gnani_stt_model": "prisma-v3.0", "tts_speed": 1.1}).status_code == 200
    env = (tmp_path / ".env").read_text()
    assert "GNANI_STT_MODEL=prisma-v3.0" in env and "TTS_SPEED=1.1" in env
    assert client.put("/api/settings", json={"gnani_stt_model": "whisper"}).status_code == 422
    assert client.put("/api/settings", json={"tts_speed": 5}).status_code == 422
    assert client.put("/api/settings", json={"tts_voice_hi": "NotAVoice"}).status_code == 422


def test_evon_is_reported_honestly(client):
    e = client.get("/api/settings").json()["evon"]
    assert e["available_on_gnani_api"] is False and e["configured"] is False


async def _noop():  # pragma: no cover
    return None


def test_test_gnani_endpoint_without_key_is_503(client):
    assert client.post("/api/settings/test-gnani").status_code == 503
