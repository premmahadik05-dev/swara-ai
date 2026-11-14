"""End-to-end ordering conversations through the HTTP API (text fallback path = same code as voice after STT)."""
from __future__ import annotations

import pytest


def turn(client, text, sid=None):
    body = {"text": text}
    if sid:
        body["session_id"] = sid
    r = client.post("/api/text/turn", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def stock(client, sku):
    items = client.get("/api/products").json()
    return next(p for p in items if p["sku"] == sku)


def test_full_order_flow_decrements_stock_and_totals_exactly(client):
    before_rice, before_milk = float(stock(client, "RICE-REGULAR")["stock"]), float(stock(client, "MILK")["stock"])
    r = turn(client, "Bhai mujhe 2 kilo chawal aur 1 litre doodh chahiye")
    assert r["cart"]["total_paise"] == 2 * 5800 + 1 * 5600
    assert r["phase"] == "collecting" and r["order"] is None
    sid = r["session_id"]
    r = turn(client, "bas itna hi", sid)
    assert r["phase"] == "confirming" and "172" in r["reply_text"]
    r = turn(client, "haan", sid)
    assert r["phase"] == "completed" and r["order"]["total_paise"] == 17200
    assert r["order"]["code"].startswith("SW-")
    assert float(stock(client, "RICE-REGULAR")["stock"]) == before_rice - 2
    assert float(stock(client, "MILK")["stock"]) == before_milk - 1
    o = client.get(f"/api/orders/{r['order']['id']}").json()
    assert [(i["name"], i["qty"]) for i in o["items"]] == [("Rice", 2.0), ("Milk", 1.0)]


@pytest.mark.parametrize("lines,total,reply_has", [
    (["મને બે કિલો ખાંડ અને એક લિટર દૂધ જોઈએ છે"], 2 * 4600 + 5600, "₹"),
    (["भैया ढाई किलो चीनी और आधा किलो आटा दे दो"], 11500 + 2200, "₹"),
    (["2 kilo sugar and 1 liter milk please"], 2 * 4600 + 5600, "₹"),
])
def test_each_language_gets_a_reply_in_the_same_language(client, lines, total, reply_has):
    r = turn(client, lines[0])
    assert r["cart"]["total_paise"] == total
    assert reply_has in r["reply_text"]
    assert r["reply_lang"] == r["language"]


def test_reply_script_matches_language(client):
    gu = turn(client, "મને બે કિલો ખાંડ જોઈએ છે")["reply_text"]
    hi = turn(client, "मुझे दो किलो चीनी चाहिए")["reply_text"]
    assert any("઀" <= c <= "૿" for c in gu)
    assert any("ऀ" <= c <= "ॿ" for c in hi)


def test_ambiguous_dal_asks_which_one_then_resolves(client):
    r = turn(client, "ek kilo dal chahiye")
    assert r["cart"]["lines"] == [] and r["pending"] is not None
    assert r["pending"]["kind"] == "choose_product"
    r = turn(client, "moong", r["session_id"])
    assert [l["sku"] for l in r["cart"]["lines"]] == ["DAL-MOONG"]
    assert r["cart"]["total_paise"] == 12000


def test_out_of_stock_is_refused_and_nothing_is_added(client):
    r = turn(client, "ek kilo sabudana")
    assert r["cart"]["lines"] == []
    assert any(e.get("type") == "out_of_stock" for e in r["events"])


def test_partial_stock_asks_before_adding_less(client):
    r = turn(client, "5 kilo paneer")  # only 3 kg in stock
    assert r["pending"] and r["pending"]["kind"] == "confirm_partial"
    assert r["cart"]["lines"] == []
    r = turn(client, "haan", r["session_id"])
    assert [(l["sku"], float(l["qty"])) for l in r["cart"]["lines"]] == [("PANEER", 3.0)]


def test_missing_quantity_is_asked_then_filled(client):
    r = turn(client, "doodh chahiye")
    assert r["pending"]["kind"] in ("need_qty", "need_unit")
    r = turn(client, "do litre", r["session_id"])
    assert [(l["sku"], float(l["qty"])) for l in r["cart"]["lines"]] == [("MILK", 2.0)]


def test_wrong_unit_is_questioned_not_converted_silently(client):
    r = turn(client, "2 litre sugar")
    assert r["cart"]["lines"] == []
    assert r["pending"] is not None


def test_pack_conversion_kilo_of_tea_is_four_packs(client):
    r = turn(client, "1 kilo chai")
    assert [(l["sku"], float(l["qty"])) for l in r["cart"]["lines"]] == [("TEA", 4.0)]
    assert r["cart"]["total_paise"] == 4 * 12000


def test_tea_300g_is_not_silently_rounded(client):
    r = turn(client, "300 gram chai")
    assert r["cart"]["lines"] == []
    assert r["pending"] is not None


def test_cancel_creates_no_order(client):
    r = turn(client, "2 kilo sugar")
    sid = r["session_id"]
    r = turn(client, "cancel kar do", sid)
    assert r["phase"] == "cancelled" and r["order"] is None
    assert client.get("/api/orders", params={"limit": 5}).json()["total"] == client.get("/api/orders").json()["total"]


def test_remove_item(client):
    r = turn(client, "2 kilo sugar aur 1 litre milk")
    r = turn(client, "doodh hata do", r["session_id"])
    assert [l["sku"] for l in r["cart"]["lines"]] == ["SUGAR"]


def test_price_question_does_not_modify_cart(client):
    r = turn(client, "doodh ka bhav kya hai")
    assert r["cart"]["lines"] == [] and "56" in r["reply_text"]


def test_confirm_button_endpoint_matches_spoken_confirm(client):
    r = turn(client, "1 kilo sugar")
    sid = r["session_id"]
    turn(client, "bas", sid)
    r = client.post(f"/api/sessions/{sid}/confirm").json()
    assert r["order"] and r["order"]["total_paise"] == 4600


def test_stock_changed_between_cart_and_confirm_never_oversells(client):
    r = turn(client, "2 kilo garlic")  # 3.5 in stock
    sid = r["session_id"]
    turn(client, "bas", sid)
    # another customer buys 3 kg meanwhile
    other = turn(client, "3 kilo garlic")
    turn(client, "bas", other["session_id"])
    assert turn(client, "haan", other["session_id"])["order"]
    r = turn(client, "haan", sid)
    assert r["order"] is None
    assert any(e.get("type") == "stock_changed" for e in r["events"])
    assert float(stock(client, "GARLIC")["stock"]) == pytest.approx(0.5)


def test_low_stock_alert_is_raised_after_order(client):
    r = turn(client, "3 kilo garlic")
    sid = r["session_id"]
    turn(client, "bas", sid)
    r = turn(client, "haan", sid)
    assert any(a["sku"] == "GARLIC" for a in r["low_stock_alerts"])
    assert any(a["sku"] == "GARLIC" for a in client.get("/api/inventory/alerts").json())


def test_session_persists_across_requests(client):
    r = turn(client, "1 kilo sugar")
    snap = client.get(f"/api/sessions/{r['session_id']}").json()
    assert snap["cart"]["lines"] and len(snap["turns"]) == 2
    assert client.get("/api/sessions/does-not-exist").status_code == 404


def test_unintelligible_input_gets_a_helpful_reply(client):
    r = turn(client, "asdf qwer zxcv")
    assert r["cart"]["lines"] == [] and r["reply_text"]


def test_confirm_button_works_straight_after_items_are_added(client):
    """The assistant has just asked "Anything else?". Pressing Confirm must save the order on the first press: a bare
    "confirm" used to be read as a yes to that question, so nothing was saved until a second press."""
    r = turn(client, "1 kilo sugar")
    assert r["awaiting"] == "more_items" and r["order"] is None
    out = client.post(f"/api/sessions/{r['session_id']}/confirm").json()
    assert out["phase"] == "completed" and out["order"]["total_paise"] == 4600


def test_confirm_button_keeps_the_customers_language_on_the_order(client):
    """The button sends an English command; it must not turn a Gujarati order into an English one (it used to, which
    also skewed the language charts)."""
    r = turn(client, "mane 2 kilo chawal ane 1 litre doodh joie")
    assert r["language"] == "gu"
    out = client.post(f"/api/sessions/{r['session_id']}/confirm").json()
    assert out["order"] is not None and out["order"]["language"] == "gu"
    assert out["reply_lang"] == "gu"   # the confirmation is worded in Gujarati, not English
    assert client.get(f"/api/orders/{out['order']['id']}").json()["language"] == "gu"
