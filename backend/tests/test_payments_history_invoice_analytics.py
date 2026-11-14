"""Payments 2.7.0: transaction history and search, invoices, and payment analytics. Every figure must come from payment and refund rows in the database."""
from __future__ import annotations

import re
import threading
from datetime import timedelta

from sqlalchemy import select

from app.models import Invoice, Payment, Refund, utcnow
from .helpers import OWNER, STAFF
from .payment_helpers import as_owner, as_staff, checkout_sig, new_order


def pay_cash(c, text="2 kilo chawal", extra=0):
    o = new_order(c, text)
    p = c.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()
    c.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"] + extra})
    return o, c.get(f"/api/payments/{p['id']}").json()


def pay_rzp(c, fake, text="2 kilo chawal"):
    o = new_order(c, text)
    p = c.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"}).json()
    pay = fake.new_payment(p["provider_order_id"], method="netbanking")
    c.post(f"/api/payments/{p['id']}/razorpay/verify", json={"razorpay_order_id": p["provider_order_id"], "razorpay_payment_id": pay["id"],
                                                             "razorpay_signature": checkout_sig(p["provider_order_id"], pay["id"])})
    return o, c.get(f"/api/payments/{p['id']}").json(), pay


# ---- history --------------------------------------------------------------------------------------------------------------------------
def test_history_lists_payments_with_references_method_amount_status_and_counts(pc, fake_rzp):
    o1, p1 = pay_cash(pc)
    o2, p2, pay2 = pay_rzp(pc, fake_rzp, "1 litre doodh")
    o3 = new_order(pc, "1 kilo cheeni")
    p3 = pc.post(f"/api/orders/{o3['id']}/payments", json={"method": "cash"}).json()
    d = pc.get("/api/payments").json()
    assert d["total"] == 3 and d["counts"]["all"] == 3 and d["counts"]["paid"] == 2 and d["counts"]["pending"] == 1 and d["counts"]["failed"] == 0
    first = d["items"][0]
    assert first["id"] == p3["id"] and {"code", "order_code", "customer_name", "method", "amount_paise", "status", "created_at", "paid_at", "verified"} <= set(first)
    assert [i["id"] for i in d["items"]] == [p3["id"], p2["id"], p1["id"]]                       # newest first
    assert [i["id"] for i in pc.get("/api/payments", params={"sort": "oldest"}).json()["items"]] == [p1["id"], p2["id"], p3["id"]]
    amounts = [i["amount_paise"] for i in pc.get("/api/payments", params={"sort": "amount_high"}).json()["items"]]
    assert amounts == sorted(amounts, reverse=True)


def test_history_filters_by_status_method_search_and_dates(pc, fake_rzp):
    o1, p1 = pay_cash(pc)
    o2, p2, pay2 = pay_rzp(pc, fake_rzp, "1 litre doodh")
    assert [i["id"] for i in pc.get("/api/payments", params={"method": "razorpay"}).json()["items"]] == [p2["id"]]
    assert [i["id"] for i in pc.get("/api/payments", params={"status": "paid", "method": "cash"}).json()["items"]] == [p1["id"]]
    for q in (p1["code"], p1["code"][-4:], o1["code"], pay2["id"], p2["provider_order_id"]):
        ids = [i["id"] for i in pc.get("/api/payments", params={"q": q}).json()["items"]]
        assert ids and (p1["id"] in ids or p2["id"] in ids), q
    assert [i["id"] for i in pc.get("/api/payments", params={"q": pay2["id"]}).json()["items"]] == [p2["id"]]
    assert pc.get("/api/payments", params={"q": "no-such-thing"}).json()["total"] == 0
    today = (utcnow() + timedelta(hours=5, minutes=30)).date()
    assert pc.get("/api/payments", params={"since": today.isoformat(), "until": today.isoformat()}).json()["total"] == 2
    assert pc.get("/api/payments", params={"since": (today + timedelta(days=1)).isoformat()}).json()["total"] == 0
    assert pc.get("/api/payments", params={"until": (today - timedelta(days=1)).isoformat()}).json()["total"] == 0
    assert pc.get("/api/payments", params={"since": "not-a-date"}).status_code == 422
    page = pc.get("/api/payments", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["limit"] == 1 and page["offset"] == 1
    assert pc.get("/api/payments", params={"limit": 0}).status_code == 422 and pc.get("/api/payments", params={"limit": 101}).status_code == 422


def test_history_can_hide_demo_orders_and_show_what_needs_attention(pc, fake_rzp):
    o, p = pay_cash(pc)
    with pc.app.state.session_factory() as db:
        db.get(Payment, p["id"]).is_synthetic = True
        db.commit()
    assert pc.get("/api/payments", params={"include_synthetic": "false"}).json()["total"] == 0
    assert pc.get("/api/payments").json()["items"][0]["is_synthetic"] is True
    assert pc.get("/api/payments", params={"attention": "true"}).json()["total"] == 0


def test_a_payment_detail_has_the_full_audit_trail_with_who_and_what(pc, fake_rzp):
    o, p = pay_cash(pc)
    as_staff(pc)
    pc.post(f"/api/payments/{p['id']}/refunds", json={"reason": "no"})                     # refused: staff
    as_owner(pc)
    pc.post(f"/api/payments/{p['id']}/refunds", json={"reason": "Customer returned the goods", "amount_paise": 100})
    d = pc.get(f"/api/payments/{p['id']}").json()
    kinds = [e["type"] for e in d["events"]]
    assert kinds == ["created", "cash_received", "refund_requested", "refund_processed"]
    assert all(e["actor"] == OWNER["full_name"] for e in d["events"]) and d["events"][1]["status_before"] == "pending" and d["events"][1]["status_after"] == "paid"
    assert d["created_by"] == OWNER["full_name"] and d["refunds"][0]["reason"] == "Customer returned the goods"


# ---- invoices -------------------------------------------------------------------------------------------------------------------------
def test_an_invoice_has_a_unique_number_the_items_totals_and_the_payment(pc):
    o, p = pay_cash(pc)
    inv = pc.get(f"/api/orders/{o['id']}/invoice").json()
    year = (utcnow() + timedelta(hours=5, minutes=30)).year
    assert re.fullmatch(rf"INV-{year}-\d{{6}}", inv["number"]) and inv["order_code"] == o["code"] and inv["issued_at"]
    assert [i["name"] for i in inv["items"]] == [i["name"] for i in o["items"]]
    assert all({"qty", "unit", "unit_price_paise", "line_total_paise"} <= set(i) for i in inv["items"])
    assert inv["subtotal_paise"] == sum(i["line_total_paise"] for i in o["items"]) == o["total_paise"] and inv["discount_paise"] == 0 and inv["total_paise"] == o["total_paise"]
    assert inv["payment"]["status"] == "paid" and inv["payment"]["method"] == "cash" and inv["payment"]["reference"] == p["code"] and inv["payment"]["paid_at"]
    assert inv["shop"]["name"] and inv["customer"]["name"] == o["customer_name"] and "Cash recorded" in inv["payment"]["label"]
    assert inv["order_status"] == "confirmed" and inv["ordered_at"]


def test_the_same_order_always_gets_the_same_invoice_number_and_numbers_do_not_repeat(pc):
    o1, _ = pay_cash(pc)
    o2, _ = pay_cash(pc, "1 litre doodh")
    a = pc.get(f"/api/orders/{o1['id']}/invoice").json()["number"]
    assert pc.get(f"/api/orders/{o1['id']}/invoice").json()["number"] == a
    b = pc.get(f"/api/orders/{o2['id']}/invoice").json()["number"]
    assert a != b and int(b[-6:]) == int(a[-6:]) + 1


def test_invoice_numbers_stay_unique_under_simultaneous_requests(pc):
    orders = [new_order(pc, "1 litre doodh") for _ in range(4)]
    from app.services import payments as svc
    results, gate = [], threading.Barrier(len(orders))

    def issue(oid):
        with pc.app.state.session_factory() as db:
            gate.wait()
            order = svc.get_order(db, oid)
            results.append(svc.get_or_create_invoice(db, pc.app.state.settings, order, None).number)

    threads = [threading.Thread(target=issue, args=(o["id"],)) for o in orders]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert len(results) == 4 and len(set(results)) == 4
    with pc.app.state.session_factory() as db:
        assert db.query(Invoice).count() == 4


def test_the_invoice_keeps_the_shop_name_it_was_issued_with(pc, monkeypatch, tmp_path):
    o, _ = pay_cash(pc)
    before = pc.get(f"/api/orders/{o['id']}/invoice").json()["shop"]["name"]
    assert pc.put("/api/settings", json={"store_name": "Brand New Name"}).status_code == 200
    assert pc.get(f"/api/orders/{o['id']}/invoice").json()["shop"]["name"] == before


def test_an_unpaid_order_has_an_invoice_that_says_so_and_a_cancelled_order_has_none(pc):
    o = new_order(pc)
    inv = pc.get(f"/api/orders/{o['id']}/invoice").json()
    assert inv["payment"] is None and inv["total_paise"] == o["total_paise"]
    p = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()
    assert pc.get(f"/api/orders/{o['id']}/invoice").json()["payment"]["status"] == "pending"
    pc.post(f"/api/payments/{p['id']}/cancel", json={})
    o2 = new_order(pc, "1 litre doodh")
    pc.post(f"/api/orders/{o2['id']}/status", json={"status": "cancelled"})
    r = pc.get(f"/api/orders/{o2['id']}/invoice")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ORDER_CANCELLED"
    assert pc.get("/api/orders/999999/invoice").status_code == 404


def test_the_invoice_shows_refunds_and_never_claims_to_be_a_gst_invoice(pc):
    o, p = pay_cash(pc)
    pc.post(f"/api/payments/{p['id']}/refunds", json={"reason": "Customer returned the goods", "amount_paise": 100})
    inv = pc.get(f"/api/orders/{o['id']}/invoice").json()
    assert inv["payment"]["refunded_paise"] == 100
    assert "not a GST tax invoice" in inv["tax_note"]
    text = str(inv).lower()
    assert "gstin" not in text and "cgst" not in text and "sgst" not in text and "igst" not in text and "tax invoice" not in text.replace("not a gst tax invoice", "")


def test_the_invoice_shows_the_customer_phone_when_there_is_one(pc):
    o, _ = pay_cash(pc)
    assert pc.get(f"/api/orders/{o['id']}/invoice").json()["customer"]["phone"] is None
    from app.models import Customer, Order
    with pc.app.state.session_factory() as db:
        c = Customer(name="Ramesh Bhai", phone="+919800011122")
        db.add(c)
        db.flush()
        db.get(Order, o["id"]).customer_id = c.id
        db.commit()
    assert pc.get(f"/api/orders/{o['id']}/invoice").json()["customer"]["phone"] == "+919800011122"


# ---- analytics ------------------------------------------------------------------------------------------------------------------------
def test_analytics_are_summed_from_real_payment_rows_by_method(pc, fake_rzp):
    o1, p1 = pay_cash(pc)
    o2, p2, _ = pay_rzp(pc, fake_rzp, "1 litre doodh")
    o3, p3 = pay_cash(pc, "1 kilo cheeni", extra=500)
    o4 = new_order(pc, "1 packet biscuit")
    pc.post(f"/api/orders/{o4['id']}/payments", json={"method": "cash"})
    k = pc.get("/api/payments/analytics").json()["kpis"]
    assert k["collected_paise"] == o1["total_paise"] + o2["total_paise"] + o3["total_paise"]             # the bill amount, not the cash handed over
    assert k["cash_paise"] == o1["total_paise"] + o3["total_paise"] and k["razorpay_paise"] == o2["total_paise"] and k["upi_paise"] == 0
    assert k["paid_count"] == 3 and k["pending_count"] == 1 and k["pending_paise"] == o4["total_paise"] and k["failed_count"] == 0 and k["average_paise"] == round(k["collected_paise"] / 3)
    a = pc.get("/api/payments/analytics").json()
    methods = {m["method"]: m for m in a["by_method"]}
    assert methods["cash"]["count"] == 2 and methods["razorpay"]["count"] == 1 and abs(sum(m["share"] for m in a["by_method"]) - 1) < 0.001
    assert abs(methods["cash"]["share"] - (k["cash_paise"] / k["collected_paise"])) < 0.0001


def test_analytics_count_failed_payments_and_only_confirmed_refunds(pc, fake_rzp):
    o1, p1 = pay_cash(pc)
    o2, p2, pay2 = pay_rzp(pc, fake_rzp, "1 litre doodh")
    pc.post(f"/api/payments/{p1['id']}/refunds", json={"reason": "Customer returned goods", "amount_paise": 300})
    pc.post(f"/api/payments/{p2['id']}/refunds", json={"reason": "Customer returned goods", "amount_paise": 200})        # Razorpay: pending
    o3 = new_order(pc, "1 kilo cheeni")
    r3 = pc.post(f"/api/orders/{o3['id']}/payments", json={"method": "razorpay"}).json()
    bad = fake_rzp.new_payment(r3["provider_order_id"], status="failed", error_description="declined")
    pc.post(f"/api/payments/{r3['id']}/razorpay/verify", json={"razorpay_order_id": r3["provider_order_id"], "razorpay_payment_id": bad["id"],
                                                               "razorpay_signature": checkout_sig(r3["provider_order_id"], bad["id"])})
    k = pc.get("/api/payments/analytics").json()["kpis"]
    assert k["refunds_paise"] == 300 and k["refund_count"] == 1 and k["refunds_waiting_count"] == 1 and k["refunds_waiting_paise"] == 200
    assert k["net_paise"] == k["collected_paise"] - 300 and k["failed_count"] == 1 and k["failed_paise"] == o3["total_paise"]


def test_analytics_trends_are_built_from_paid_times_in_india_time_and_empty_days_are_zero(pc):
    o, p = pay_cash(pc)
    a = pc.get("/api/payments/analytics", params={"days": 7}).json()
    today = (utcnow() + timedelta(hours=5, minutes=30)).date().isoformat()
    assert len(a["daily"]) == 7 and a["daily"][-1]["period"] == today and a["daily"][-1]["collected_paise"] == o["total_paise"] and a["daily"][-1]["count"] == 1
    assert all(d["collected_paise"] == 0 and d["count"] == 0 for d in a["daily"][:-1])
    assert a["weekly"] and sum(w["collected_paise"] for w in a["weekly"]) == o["total_paise"] and sum(m["collected_paise"] for m in a["monthly"]) == o["total_paise"]
    # move the payment to just before IST midnight yesterday: it must land on yesterday's India date, not today's
    with pc.app.state.session_factory() as db:
        row = db.get(Payment, p["id"])
        ist_now = utcnow() + timedelta(hours=5, minutes=30)
        row.paid_at = ist_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(minutes=1) - timedelta(hours=5, minutes=30)
        db.commit()
    a = pc.get("/api/payments/analytics", params={"days": 7}).json()
    yesterday = ((utcnow() + timedelta(hours=5, minutes=30)).date() - timedelta(days=1)).isoformat()
    assert next(d for d in a["daily"] if d["period"] == yesterday)["collected_paise"] == o["total_paise"] and a["daily"][-1]["collected_paise"] == 0


def test_analytics_window_and_demo_data_options(pc):
    o, p = pay_cash(pc)
    with pc.app.state.session_factory() as db:
        row = db.get(Payment, p["id"])
        row.paid_at = utcnow() - timedelta(days=40)
        db.commit()
    assert pc.get("/api/payments/analytics", params={"days": 30}).json()["kpis"]["collected_paise"] == 0
    assert pc.get("/api/payments/analytics", params={"days": 60}).json()["kpis"]["collected_paise"] == o["total_paise"]
    with pc.app.state.session_factory() as db:
        db.get(Payment, p["id"]).is_synthetic = True
        db.commit()
    assert pc.get("/api/payments/analytics", params={"days": 60, "include_synthetic": "false"}).json()["kpis"]["collected_paise"] == 0
    a = pc.get("/api/payments/analytics", params={"days": 60, "include_synthetic": "false"}).json()
    assert a["includes_demo_orders"] is False
    assert pc.get("/api/payments/analytics", params={"days": 0}).status_code == 422 and pc.get("/api/payments/analytics", params={"days": 400}).status_code == 422


def test_manual_upi_collections_are_reported_separately_as_unverified(make_pay_app):
    from fastapi.testclient import TestClient
    from .helpers import register
    with TestClient(make_pay_app(razorpay_key_id="", razorpay_key_secret=None, upi_vpa="patelstore@okhdfcbank")) as c:
        register(c, OWNER)
        o = new_order(c)
        p = c.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"}).json()
        c.post(f"/api/payments/{p['id']}/confirm-upi", json={"reference": "REF-98765"})
        k = c.get("/api/payments/analytics").json()["kpis"]
        assert k["upi_paise"] == o["total_paise"] and k["upi_manual_paise"] == o["total_paise"]


def test_analytics_never_include_a_payment_that_is_not_paid(pc):
    o = new_order(pc)
    p = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()
    k = pc.get("/api/payments/analytics").json()["kpis"]
    assert k["collected_paise"] == 0 and k["pending_count"] == 1
    pc.post(f"/api/payments/{p['id']}/cancel", json={})
    k = pc.get("/api/payments/analytics").json()["kpis"]
    assert k["collected_paise"] == 0 and k["pending_count"] == 0 and k["failed_count"] == 0
