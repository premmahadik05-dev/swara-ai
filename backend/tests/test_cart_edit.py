"""Manual cart editing (the order desk's +/- buttons and item search)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _first(client: TestClient, name: str) -> dict:
    items = client.get("/api/inventory", params={"q": name, "page_size": 5}).json()["items"]
    return next(i for i in items if i["name_en"].lower().startswith(name.lower()))


def _session(client: TestClient) -> str:
    return client.post("/api/sessions").json()["session_id"]


def test_add_set_remove_line_updates_total(client: TestClient):
    sid = _session(client)
    sugar = _first(client, "Sugar")
    r = client.post(f"/api/sessions/{sid}/cart", json={"product_id": sugar["id"], "qty": "2", "mode": "add"})
    assert r.status_code == 200
    cart = r.json()["cart"]
    assert [l["qty"] for l in cart["lines"]] == ["2.000"]
    assert cart["total_paise"] == 2 * sugar["price_paise"]
    r = client.post(f"/api/sessions/{sid}/cart", json={"product_id": sugar["id"], "qty": "1.5", "mode": "add"}).json()
    assert r["cart"]["lines"][0]["qty"] == "3.500"
    r = client.post(f"/api/sessions/{sid}/cart", json={"product_id": sugar["id"], "qty": "1", "mode": "set"}).json()
    assert r["cart"]["lines"][0]["qty"] == "1.000"
    r = client.post(f"/api/sessions/{sid}/cart", json={"product_id": sugar["id"], "qty": "0", "mode": "set"}).json()
    assert r["cart"]["lines"] == [] and r["cart"]["total_paise"] == 0


def test_more_than_stock_is_refused_not_clamped(client: TestClient):
    sid = _session(client)
    sugar = _first(client, "Sugar")
    r = client.post(f"/api/sessions/{sid}/cart", json={"product_id": sugar["id"], "qty": str(sugar["stock"] + 5)})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NOT_ENOUGH_STOCK"
    assert client.get(f"/api/sessions/{sid}").json()["cart"]["lines"] == []


def test_unknown_product_and_unknown_session(client: TestClient):
    sid = _session(client)
    assert client.post(f"/api/sessions/{sid}/cart", json={"product_id": 999999, "qty": "1"}).status_code == 404
    assert client.post("/api/sessions/nosuchsession/cart", json={"product_id": 1, "qty": "1"}).status_code == 404


def test_pack_items_need_whole_numbers(client: TestClient):
    sid = _session(client)
    packs = [p for p in client.get("/api/inventory", params={"page_size": 100}).json()["items"] if p["unit"] in ("pack", "pc") and p["stock"] >= 2]
    assert packs, "seed has pack/piece items"
    r = client.post(f"/api/sessions/{sid}/cart", json={"product_id": packs[0]["id"], "qty": "1.5"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "WHOLE_NUMBER"


def test_edit_then_confirm_creates_order_and_reduces_stock(client: TestClient):
    sid = _session(client)
    sugar = _first(client, "Sugar")
    client.post(f"/api/sessions/{sid}/cart", json={"product_id": sugar["id"], "qty": "2", "mode": "add"})
    out = client.post(f"/api/sessions/{sid}/confirm").json()
    assert out["order"] and out["order"]["total_paise"] == 2 * sugar["price_paise"]
    after = _first(client, "Sugar")
    assert after["stock"] == pytest.approx(sugar["stock"] - 2)
    # closed order cannot be edited any more
    r = client.post(f"/api/sessions/{sid}/cart", json={"product_id": sugar["id"], "qty": "1"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ORDER_CLOSED"


def test_negative_or_absurd_quantity_rejected(client: TestClient):
    sid = _session(client)
    assert client.post(f"/api/sessions/{sid}/cart", json={"product_id": 1, "qty": "-1"}).status_code == 422
    assert client.post(f"/api/sessions/{sid}/cart", json={"product_id": 1, "qty": "100000"}).status_code == 422


def test_confirm_can_attach_a_customer(client: TestClient):
    cid = client.post("/api/customers", json={"name": "Kiran Shah", "phone": "98250 11111", "language": "gu"}).json()["id"]
    sid = _session(client)
    sugar = _first(client, "Sugar")
    client.post(f"/api/sessions/{sid}/cart", json={"product_id": sugar["id"], "qty": "1", "mode": "add"})
    out = client.post(f"/api/sessions/{sid}/confirm", json={"customer_id": cid}).json()
    assert out["order"]["customer_id"] == cid and out["order"]["customer_name"] == "Kiran Shah"
    assert client.get(f"/api/customers/{cid}").json()["orders"] == 1


def test_orders_list_reports_status_counts_for_the_tabs(client: TestClient):
    r = client.get("/api/orders", params={"limit": 5}).json()
    c = r["counts"]
    assert c["all"] == c["confirmed"] + c["fulfilled"] + c["cancelled"] == client.get("/api/orders", params={"limit": 1}).json()["total"]
    only = client.get("/api/orders", params={"limit": 5, "status": "cancelled"}).json()
    assert only["total"] == c["cancelled"] and only["counts"] == c  # counts ignore the status filter itself
    voice = client.get("/api/orders", params={"limit": 5, "channel": "voice"}).json()["counts"]
    assert voice["all"] <= c["all"]
