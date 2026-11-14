"""Payments 2.7.0: cash, manual UPI, one-payment-per-order rules, owner and staff permissions, and backward compatibility with orders that have no payment.

Every provider answer in these tests is simulated (see payment_helpers.FakeRazorpay). Nothing here moves money or contacts Razorpay.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Order, Payment, PaymentEvent, Product
from .helpers import OWNER, STAFF, login
from .payment_helpers import as_owner, as_staff, new_order

VPA = "patelstore@okhdfcbank"


def start(c, order_id, method="cash", key=None, expect=(200, 201)):
    r = c.post(f"/api/orders/{order_id}/payments", json={"method": method, **({"idempotency_key": key} if key else {})})
    assert r.status_code in expect, r.text
    return r


def stock_map(pc):
    app = pc.app
    with app.state.session_factory() as db:
        return {p.id: p.stock for p in db.scalars(select(Product))}


# ---- orders that never had a payment -------------------------------------------------------------------------------------
def test_an_order_with_no_payment_still_works_exactly_as_before(pc):
    o = new_order(pc)
    got = pc.get(f"/api/orders/{o['id']}").json()
    assert got["payment"]["status"] == "none" and got["payment"]["paid_paise"] == 0
    listed = next(i for i in pc.get("/api/orders").json()["items"] if i["id"] == o["id"])
    assert listed["payment"]["status"] == "none"
    assert pc.post(f"/api/orders/{o['id']}/status", json={"status": "fulfilled"}).json()["status"] == "fulfilled"
    assert pc.get(f"/api/orders/{o['id']}/payments").json()["items"] == []


def test_seeded_demo_orders_have_no_payment_and_no_payment_figures_are_invented(pc):
    items = pc.get("/api/orders", params={"limit": 100}).json()["items"]
    assert items and all(i["payment"]["status"] == "none" for i in items)
    a = pc.get("/api/payments/analytics").json()["kpis"]
    assert a["collected_paise"] == 0 and a["paid_count"] == 0 and a["pending_count"] == 0 and a["refunds_paise"] == 0
    assert pc.get("/api/payments").json()["total"] == 0


def test_cancelling_an_order_with_no_payment_restocks_as_before(pc):
    before = stock_map(pc)
    o = new_order(pc)
    assert stock_map(pc) != before
    assert pc.post(f"/api/orders/{o['id']}/status", json={"status": "cancelled"}).json()["status"] == "cancelled"
    assert stock_map(pc) == before


# ---- cash -------------------------------------------------------------------------------------------------------------------
def test_cash_is_pending_until_a_person_records_it_and_stores_who_and_when(pc):
    o = new_order(pc)
    as_staff(pc)
    p = start(pc, o["id"], "cash", expect=(201,)).json()
    assert p["status"] == "pending" and p["method"] == "cash" and p["amount_paise"] == o["total_paise"] and p["paid_at"] is None
    assert p["code"].startswith("PAY-") and p["verified"] is False and p["verification_label"] == "Waiting for cash"
    paid = pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"]}).json()
    assert paid["status"] == "paid" and paid["paid_at"] and paid["confirmed_by"] == STAFF["full_name"] and paid["verification"] == "cash"
    assert paid["amount_received_paise"] == o["total_paise"] and paid["change_paise"] == 0
    assert "Cash recorded by Test Staff" in paid["verification_label"] and paid["verified"] is False
    assert pc.get(f"/api/orders/{o['id']}").json()["payment"]["status"] == "paid"


def test_cash_records_the_amount_received_and_the_change(pc):
    o = new_order(pc)
    p = start(pc, o["id"]).json()
    paid = pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"] + 5000}).json()
    assert paid["amount_received_paise"] == o["total_paise"] + 5000 and paid["change_paise"] == 5000 and paid["amount_paise"] == o["total_paise"]


def test_cash_less_than_the_bill_is_refused_and_the_payment_stays_pending(pc):
    o = new_order(pc)
    p = start(pc, o["id"]).json()
    r = pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"] - 1})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "CASH_SHORT"
    assert pc.get(f"/api/payments/{p['id']}").json()["status"] == "pending"
    assert pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": 0}).status_code == 422
    assert pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"] * 50 + 10**6}).json()["detail"]["code"] == "CASH_TOO_MUCH"


def test_recording_cash_twice_does_not_record_it_twice(pc):
    o = new_order(pc)
    p = start(pc, o["id"]).json()
    assert pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"]}).status_code == 200
    again = pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"]})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ALREADY_PAID"
    with pc.app.state.session_factory() as db:
        events = [e.event_type for e in db.scalars(select(PaymentEvent).where(PaymentEvent.payment_id == p["id"]))]
    assert events.count("cash_received") == 1


# ---- one payment at a time, and never twice -------------------------------------------------------------------------------------------
def test_the_same_idempotency_key_returns_the_same_payment(pc):
    o = new_order(pc)
    a = start(pc, o["id"], "cash", key="key-abcdef-0001", expect=(201,))
    b = start(pc, o["id"], "cash", key="key-abcdef-0001", expect=(200,))
    assert a.json()["id"] == b.json()["id"]
    clash = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "upi", "idempotency_key": "key-abcdef-0001"})
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    other = new_order(pc, "1 litre doodh")
    assert pc.post(f"/api/orders/{other['id']}/payments", json={"method": "cash", "idempotency_key": "key-abcdef-0001"}).json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash", "idempotency_key": "short"}).json()["detail"]["code"] == "BAD_IDEMPOTENCY_KEY"


def test_asking_again_while_a_payment_is_open_returns_it_and_another_method_is_refused(pc):
    o = new_order(pc)
    a = start(pc, o["id"], "cash", expect=(201,)).json()
    assert start(pc, o["id"], "cash", expect=(200,)).json()["id"] == a["id"]
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PAYMENT_IN_PROGRESS" and r.json()["detail"]["payment_id"] == a["id"]
    assert pc.post(f"/api/payments/{a['id']}/cancel", json={"reason": "Customer will pay by card instead"}).json()["status"] == "cancelled"
    assert start(pc, o["id"], "razorpay", expect=(201,)).json()["method"] == "razorpay"


def test_the_database_itself_allows_only_one_open_payment_per_order(pc):
    o = new_order(pc)
    with pc.app.state.session_factory() as db:
        for _ in range(2):
            db.add(Payment(order_id=o["id"], method="cash", provider="none", status="pending", amount_paise=o["total_paise"]))
        with pytest.raises(IntegrityError):
            db.commit()


def test_the_database_refuses_nonsense_amounts_and_duplicate_provider_ids(pc):
    o = new_order(pc)
    with pc.app.state.session_factory() as db:
        db.add(Payment(order_id=o["id"], method="cash", provider="none", status="pending", amount_paise=0))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Payment(order_id=o["id"], method="cash", provider="none", status="paid", amount_paise=100, refunded_paise=101))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Payment(order_id=o["id"], method="razorpay", provider="razorpay", status="failed", amount_paise=100, provider_payment_id="pay_X1"))
        db.add(Payment(order_id=o["id"], method="razorpay", provider="razorpay", status="failed", amount_paise=100, provider_payment_id="pay_X1"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_a_paid_order_cannot_be_paid_again(pc):
    o = new_order(pc)
    p = start(pc, o["id"]).json()
    pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"]})
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ALREADY_PAID"


def test_a_cancelled_order_cannot_be_paid_and_a_cancelled_payment_cannot_be_recorded(pc):
    o = new_order(pc)
    pc.post(f"/api/orders/{o['id']}/status", json={"status": "cancelled"})
    assert pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()["detail"]["code"] == "ORDER_CANCELLED"
    o2 = new_order(pc, "1 litre doodh")
    p = start(pc, o2["id"]).json()
    pc.post(f"/api/payments/{p['id']}/cancel", json={})
    r = pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o2["total_paise"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "NOT_PENDING"


def test_the_amount_due_is_the_server_side_order_total_whatever_the_browser_sends(pc):
    o = new_order(pc)
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash", "amount_paise": 1, "total_paise": 1, "amount": 1})
    assert r.status_code == 201 and r.json()["amount_paise"] == o["total_paise"]


def test_unknown_method_order_and_payment(pc):
    o = new_order(pc)
    assert pc.post(f"/api/orders/{o['id']}/payments", json={"method": "bitcoin"}).json()["detail"]["code"] == "BAD_METHOD"
    assert pc.post("/api/orders/999999/payments", json={"method": "cash"}).status_code == 404
    assert pc.get("/api/payments/999999").status_code == 404
    assert pc.post("/api/payments/999999/cash", json={"received_paise": 100}).status_code == 404


def test_payment_attempts_and_retries_never_change_stock(pc, fake_rzp):
    before = stock_map(pc)
    o = new_order(pc)
    after_order = stock_map(pc)
    assert after_order != before
    p = start(pc, o["id"], "cash").json()
    start(pc, o["id"], "cash")
    pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": 1})                       # refused
    pc.post(f"/api/payments/{p['id']}/cancel", json={})
    r = start(pc, o["id"], "razorpay", expect=(201,)).json()
    pc.post(f"/api/payments/{r['id']}/razorpay/verify", json={"razorpay_order_id": r["provider_order_id"], "razorpay_payment_id": "pay_x", "razorpay_signature": "bad"})
    pc.post(f"/api/payments/{r['id']}/cancel", json={})
    c = start(pc, o["id"], "cash", expect=(201,)).json()
    pc.post(f"/api/payments/{c['id']}/cash", json={"received_paise": o["total_paise"]})
    assert stock_map(pc) == after_order
    with pc.app.state.session_factory() as db:
        assert db.scalar(select(Order).where(Order.id == o["id"])).status == "confirmed"


def test_a_voice_channel_order_is_paid_the_same_way(pc):
    from decimal import Decimal
    from app.nlu.dialogue import CartLine
    from app.services import orders as order_svc
    from app.services.catalog import load_views
    with pc.app.state.session_factory() as db:
        views = load_views(db)
        pid = next(iter(views))
        order, _ = order_svc.create_order(db, [CartLine(product_id=pid, qty=Decimal("1"))], views, session_id=None, channel="voice", language="hi")
        oid, total = order.id, order.total_paise
    p = start(pc, oid, "cash", expect=(201,)).json()
    paid = pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": total}).json()
    assert paid["status"] == "paid" and paid["order_id"] == oid
    assert pc.get(f"/api/orders/{oid}").json()["channel"] == "voice"


# ---- manual UPI -----------------------------------------------------------------------------------------------------------------------
def test_upi_needs_the_shops_upi_id_first(make_pay_app):
    with TestClient(make_pay_app(razorpay_key_id="", razorpay_key_secret=None)) as c:
        from .helpers import register
        register(c, OWNER)
        o = new_order(c)
        r = c.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "UPI_NOT_SET_UP"
        cfg = c.get("/api/payments/config").json()
        assert cfg["methods"]["upi"]["available"] is False and cfg["methods"]["razorpay"]["available"] is False and cfg["methods"]["cash"]["available"] is True


@pytest.fixture
def upi_client(make_pay_app):
    with TestClient(make_pay_app(razorpay_key_id="", razorpay_key_secret=None, upi_vpa=VPA, upi_payee_name="Patel Store")) as c:
        from .helpers import login, register
        register(c, OWNER)
        c.cookies.clear(); c.headers.pop("X-CSRF-Token", None)
        register(c, STAFF)
        c.cookies.clear(); c.headers.pop("X-CSRF-Token", None)
        login(c, OWNER)
        yield c


def test_manual_upi_shows_the_amount_reference_and_is_labelled_unverified(upi_client):
    c = upi_client
    o = new_order(c)
    p = start(c, o["id"], "upi", expect=(201,)).json()
    u = p["upi"]
    assert u["mode"] == "manual" and u["verified_by_provider"] is False and u["payee"] == VPA and u["reference"] == p["code"] and u["order_code"] == o["code"]
    q = parse_qs(urlparse(u["uri"]).query)
    assert u["uri"].startswith("upi://pay?") and q["pa"] == [VPA] and q["pn"] == ["Patel Store"] and q["cu"] == ["INR"] and q["tr"] == [p["code"]]
    assert q["am"] == [f"{o['total_paise'] / 100:.2f}"] and "Bill" in q["tn"][0] and o["code"] in q["tn"][0]
    assert "cannot see the payment" in u["instructions"] and p["status"] == "pending" and p["verified"] is False
    assert "not yet confirmed" in p["verification_label"]


def test_manual_upi_is_never_paid_until_a_person_confirms_it_with_a_reference(upi_client):
    c = upi_client
    o = new_order(c)
    p = start(c, o["id"], "upi").json()
    assert c.get(f"/api/payments/{p['id']}").json()["status"] == "pending"               # time passing or reloading changes nothing
    assert c.post(f"/api/payments/{p['id']}/refresh").json()["status"] == "pending"
    for bad in ("", "  ", "ab", "x" * 41, "<script>"):
        r = c.post(f"/api/payments/{p['id']}/confirm-upi", json={"reference": bad})
        assert r.status_code == 422, bad
    as_staff(c)
    done = c.post(f"/api/payments/{p['id']}/confirm-upi", json={"reference": "UPI 4012 3456 7890"}).json()
    assert done["status"] == "paid" and done["verified"] is False and done["verification"] == "manual" and done["reference_note"] == "UPI 4012 3456 7890"
    assert done["confirmed_by"] == STAFF["full_name"] and "Not verified by a payment provider" in done["verification_label"]
    assert c.post(f"/api/payments/{p['id']}/confirm-upi", json={"reference": "UPI 4012 3456 7890"}).json()["detail"]["code"] == "ALREADY_PAID"


def test_a_cash_payment_cannot_be_confirmed_as_upi_and_the_reverse(upi_client):
    c = upi_client
    o = new_order(c)
    cash = start(c, o["id"], "cash").json()
    assert c.post(f"/api/payments/{cash['id']}/confirm-upi", json={"reference": "REF12345"}).json()["detail"]["code"] == "WRONG_METHOD"
    c.post(f"/api/payments/{cash['id']}/cancel", json={})
    upi = start(c, o["id"], "upi").json()
    assert c.post(f"/api/payments/{upi['id']}/cash", json={"received_paise": o["total_paise"]}).json()["detail"]["code"] == "WRONG_METHOD"


def test_owner_can_set_the_upi_id_in_settings_and_bad_ids_are_refused(make_pay_app):
    with TestClient(make_pay_app(razorpay_key_id="", razorpay_key_secret=None)) as c:
        from .helpers import register
        register(c, OWNER)
        assert c.put("/api/settings", json={"upi_vpa": "not a vpa"}).status_code == 422
        assert c.put("/api/settings", json={"upi_vpa": "evil@x\nGNANI_API_KEY=hacked"}).status_code == 422
        r = c.put("/api/settings", json={"upi_vpa": VPA, "upi_payee_name": "Patel Store"})
        assert r.status_code == 200 and r.json()["payments"]["methods"]["upi"]["available"] is True
        assert r.json()["payments"]["owner"]["upi_vpa"] == VPA
        o = new_order(c)
        assert c.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"}).json()["upi"]["payee"] == VPA
        assert c.put("/api/settings", json={"upi_vpa": ""}).json()["payments"]["methods"]["upi"]["available"] is False


# ---- permissions ----------------------------------------------------------------------------------------------------------------------
def test_staff_can_take_payments_but_not_refund_or_see_analytics_or_change_settings(pc):
    o = new_order(pc)
    as_staff(pc)
    p = start(pc, o["id"], "cash", expect=(201,)).json()
    assert pc.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"]}).status_code == 200
    assert pc.get("/api/payments").status_code == 200 and pc.get(f"/api/payments/{p['id']}").status_code == 200 and pc.get(f"/api/orders/{o['id']}/invoice").status_code == 200
    r = pc.post(f"/api/payments/{p['id']}/refunds", json={"reason": "customer returned goods"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "OWNER_ONLY"
    assert pc.get("/api/payments/analytics").status_code == 403
    assert pc.put("/api/settings", json={"upi_vpa": VPA}).status_code == 403
    assert pc.post("/api/refunds/1/refresh").status_code == 403
    cfg = pc.get("/api/payments/config").json()
    assert "owner" not in cfg                                  # webhook address and which secrets are set are for the owner
    as_owner(pc)
    assert "owner" in pc.get("/api/payments/config").json()


def test_nothing_in_the_payment_api_works_without_signing_in(make_pay_app):
    with TestClient(make_pay_app()) as c:
        for method, url, body in (
            ("get", "/api/payments", None), ("get", "/api/payments/config", None), ("get", "/api/payments/analytics", None), ("get", "/api/payments/1", None),
            ("get", "/api/orders/1/payments", None), ("get", "/api/orders/1/invoice", None), ("post", "/api/orders/1/payments", {"method": "cash"}),
            ("post", "/api/payments/1/cash", {"received_paise": 100}), ("post", "/api/payments/1/confirm-upi", {"reference": "REF12345"}),
            ("post", "/api/payments/1/razorpay/verify", {"razorpay_order_id": "o", "razorpay_payment_id": "p", "razorpay_signature": "s"}),
            ("post", "/api/payments/1/refresh", None), ("post", "/api/payments/1/cancel", {}), ("post", "/api/payments/1/refunds", {"reason": "abc"}),
            ("post", "/api/refunds/1/refresh", None),
        ):
            r = getattr(c, method)(url, **({"json": body} if body is not None else {}))
            assert r.status_code == 401, (method, url, r.status_code)


def test_writes_need_the_csrf_token(pc):
    o = new_order(pc)
    token = pc.headers.pop("X-CSRF-Token")
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "CSRF_FAILED"
    pc.headers["X-CSRF-Token"] = token
    assert pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).status_code == 201
