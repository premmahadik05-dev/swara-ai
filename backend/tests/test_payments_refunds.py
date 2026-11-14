"""Payments 2.7.0: refunds. Owner only, never reported as done before the provider confirms, never twice, never more than was paid.

Razorpay's answers are simulated by FakeRazorpay: these tests prove how the app reacts to each answer, not how Razorpay really behaves.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Payment, Refund
from .helpers import OWNER
from .payment_helpers import as_owner, as_staff, event, new_order, webhook_headers

WEBHOOK = "/api/payments/webhooks/razorpay"


def paid_cash(c, text="2 kilo chawal"):
    o = new_order(c, text)
    p = c.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()
    c.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"]})
    return o, c.get(f"/api/payments/{p['id']}").json()


def paid_rzp(c, fake, text="2 kilo chawal"):
    o = new_order(c, text)
    p = c.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"}).json()
    pay = fake.new_payment(p["provider_order_id"], method="upi")
    from .payment_helpers import checkout_sig
    c.post(f"/api/payments/{p['id']}/razorpay/verify", json={"razorpay_order_id": p["provider_order_id"], "razorpay_payment_id": pay["id"],
                                                             "razorpay_signature": checkout_sig(p["provider_order_id"], pay["id"])})
    got = c.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "paid", got
    return o, got, pay


def refund(c, pid, reason="Customer returned the goods", **kw):
    return c.post(f"/api/payments/{pid}/refunds", json={"reason": reason, **kw})


def deliver(c, name, **kw):
    raw = event(name, **kw)
    return c.post(WEBHOOK, content=raw, headers=webhook_headers(raw, f"evt_{name}_{len(raw)}_{id(kw)}"))


# ---- cash and manual refunds ------------------------------------------------------------------------------------------------------------
def test_owner_refunds_a_cash_payment_in_full_and_it_is_labelled_as_not_provider_confirmed(pc):
    o, p = paid_cash(pc)
    r = refund(pc, p["id"])
    assert r.status_code == 201
    d = r.json()
    assert d["kind"] == "manual" and d["status"] == "processed" and d["amount_paise"] == o["total_paise"] and d["code"].startswith("REF-")
    assert d["label"] == "Recorded by the owner. Not confirmed by a payment provider." and d["initiated_by"] == OWNER["full_name"]
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "refunded" and got["refunded_paise"] == o["total_paise"] and got["refundable_paise"] == 0
    assert pc.get(f"/api/orders/{o['id']}").json()["payment"]["status"] == "refunded"
    assert [x["code"] for x in got["refunds"]] == [d["code"]]
    assert {"refund_requested", "refund_processed"} <= {e["type"] for e in got["events"]}


def test_partial_refunds_add_up_and_cannot_pass_what_was_paid(pc):
    o, p = paid_cash(pc)
    total = o["total_paise"]
    first = refund(pc, p["id"], amount_paise=total // 4).json()
    assert first["payment"]["status"] == "partially_refunded" and first["payment"]["refunded_paise"] == total // 4
    assert pc.get(f"/api/orders/{o['id']}").json()["payment"]["status"] == "partially_refunded"
    too_much = refund(pc, p["id"], amount_paise=total)
    assert too_much.status_code == 422 and too_much.json()["detail"]["code"] == "REFUND_TOO_LARGE"
    rest = refund(pc, p["id"]).json()                                   # no amount: whatever is left
    assert rest["amount_paise"] == total - total // 4 and rest["payment"]["status"] == "refunded"
    again = refund(pc, p["id"])
    assert again.status_code == 409 and again.json()["detail"]["code"] == "NOT_REFUNDABLE"
    assert pc.get(f"/api/payments/{p['id']}").json()["refunded_paise"] == total


def test_refund_rules_reason_amount_and_state(pc):
    o = new_order(pc)
    pending = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()
    assert refund(pc, pending["id"]).json()["detail"]["code"] == "NOT_REFUNDABLE"
    pc.post(f"/api/payments/{pending['id']}/cash", json={"received_paise": o["total_paise"]})
    assert refund(pc, pending["id"], reason="x").json()["detail"]["code"] == "REASON_REQUIRED"
    assert refund(pc, pending["id"], reason="  ").status_code == 422
    assert pc.post(f"/api/payments/{pending['id']}/refunds", json={"reason": "valid reason", "amount_paise": 0}).status_code == 422
    assert pc.post(f"/api/payments/{pending['id']}/refunds", json={"reason": "valid reason", "amount_paise": -5}).status_code == 422
    assert pc.post(f"/api/payments/{pending['id']}/refunds", json={}).status_code == 422


def test_the_same_refund_request_twice_makes_one_refund(pc):
    o, p = paid_cash(pc)
    a = refund(pc, p["id"], amount_paise=o["total_paise"] // 2, idempotency_key="refund-key-0001")
    b = refund(pc, p["id"], amount_paise=o["total_paise"] // 2, idempotency_key="refund-key-0001")
    assert a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"]
    assert pc.get(f"/api/payments/{p['id']}").json()["refunded_paise"] == o["total_paise"] // 2
    _, p2 = paid_cash(pc, "1 litre doodh")
    clash = refund(pc, p2["id"], idempotency_key="refund-key-0001")
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert refund(pc, p2["id"], idempotency_key="no").json()["detail"]["code"] == "BAD_IDEMPOTENCY_KEY"


def test_staff_cannot_refund_and_a_failed_attempt_changes_nothing(pc):
    o, p = paid_cash(pc)
    as_staff(pc)
    r = refund(pc, p["id"])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "OWNER_ONLY"
    as_owner(pc)
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "paid" and got["refunds"] == []


# ---- Razorpay refunds -------------------------------------------------------------------------------------------------------------------
def test_a_razorpay_refund_is_pending_until_razorpay_confirms_and_the_payment_stays_paid(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"]).json()
    assert d["kind"] == "provider" and d["status"] == "pending" and d["provider_refund_id"].startswith("rfnd_") and d["label"] == "Waiting for Razorpay to confirm"
    sent = next(b for m, path, b in fake_rzp.calls if path.endswith("/refund"))
    assert sent["amount"] == o["total_paise"] and sent["receipt"] == d["code"]
    assert next(path for m, path, b in fake_rzp.calls if path.endswith("/refund")) == f"/v1/payments/{pay['id']}/refund"
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "paid" and got["refunded_paise"] == 0 and got["refundable_paise"] == 0       # money on its way is spoken for, but nothing is "refunded" yet
    assert pc.get(f"/api/orders/{o['id']}").json()["payment"]["status"] == "paid"


def test_the_refund_becomes_refunded_only_when_razorpay_reports_it_processed(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"]).json()
    ent = fake_rzp.refunds[d["provider_refund_id"]]
    ent["status"], ent["speed_processed"] = "processed", "normal"
    assert deliver(pc, "refund.processed", refund=ent).json()["result"] == "processed"
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "refunded" and got["refunded_paise"] == o["total_paise"]
    assert got["refunds"][0]["status"] == "processed" and got["refunds"][0]["speed_processed"] == "normal" and got["refunds"][0]["label"] == "Confirmed by Razorpay"
    again = deliver(pc, "refund.processed", refund=dict(ent, note="redelivered"))                  # a different body = a different delivery
    assert pc.get(f"/api/payments/{p['id']}").json()["refunded_paise"] == o["total_paise"]
    assert again.status_code == 200


def test_the_same_refund_webhook_twice_counts_the_money_once(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"], amount_paise=o["total_paise"] // 2).json()
    ent = dict(fake_rzp.refunds[d["provider_refund_id"]], status="processed")
    raw = event("refund.processed", refund=ent)
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw, "evt_r1")).json()["result"] == "processed"
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw, "evt_r1")).json()["status"] == "duplicate"
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw, "evt_r2")).status_code == 200
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["refunded_paise"] == o["total_paise"] // 2 and got["status"] == "partially_refunded"


def test_check_status_on_a_refund_asks_razorpay_and_applies_it_once(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"]).json()
    r = pc.post(f"/api/refunds/{d['id']}/refresh").json()
    assert r["status"] == "pending"
    fake_rzp.refunds[d["provider_refund_id"]]["status"] = "processed"
    assert pc.post(f"/api/refunds/{d['id']}/refresh").json()["status"] == "processed"
    assert pc.post(f"/api/refunds/{d['id']}/refresh").json()["status"] == "processed"
    assert pc.get(f"/api/payments/{p['id']}").json()["refunded_paise"] == o["total_paise"]


def test_an_instantly_processed_refund_is_recorded_as_processed(pc, fake_rzp):
    fake_rzp.refund_status_on_create = "processed"
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"]).json()
    assert d["status"] == "processed" and pc.get(f"/api/payments/{p['id']}").json()["status"] == "refunded"


def test_a_failed_refund_is_shown_as_failed_and_can_be_tried_again(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"]).json()
    ent = dict(fake_rzp.refunds[d["provider_refund_id"]], status="failed", failure_reason="Bank rejected the refund")
    assert deliver(pc, "refund.failed", refund=ent).json()["result"] == "failed"
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "paid" and got["refunded_paise"] == 0 and got["refunds"][0]["status"] == "failed" and got["refunds"][0]["failure_reason"] == "Bank rejected the refund"
    assert got["refundable_paise"] == o["total_paise"]
    assert refund(pc, p["id"]).status_code == 201


def test_a_late_failed_or_pending_report_cannot_undo_a_processed_refund(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"]).json()
    ent = fake_rzp.refunds[d["provider_refund_id"]]
    deliver(pc, "refund.processed", refund=dict(ent, status="processed"))
    deliver(pc, "refund.failed", refund=dict(ent, status="failed"))
    deliver(pc, "refund.created", refund=dict(ent, status="created"))
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "refunded" and got["refunded_paise"] == o["total_paise"] and got["refunds"][0]["status"] == "processed"


def test_a_pending_refund_blocks_a_second_refund_of_the_same_money(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    assert refund(pc, p["id"]).status_code == 201
    second = refund(pc, p["id"])
    assert second.status_code == 409 and second.json()["detail"]["code"] == "NOTHING_TO_REFUND"
    assert refund(pc, p["id"], amount_paise=1).json()["detail"]["code"] == "REFUND_TOO_LARGE"
    assert fake_rzp.count("POST", r"/refund$") == 1


def test_a_refund_for_part_leaves_the_rest_refundable_while_it_is_pending(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    half = o["total_paise"] // 2
    assert refund(pc, p["id"], amount_paise=half).status_code == 201
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["refundable_paise"] == o["total_paise"] - half
    assert refund(pc, p["id"], amount_paise=o["total_paise"] - half).status_code == 201


def test_when_razorpay_does_not_answer_the_refund_is_not_assumed_done_and_can_be_found_by_receipt(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    fake_rzp.fail_next = httpx.ReadTimeout("no answer")
    d = refund(pc, p["id"]).json()
    assert d["status"] == "pending" and d["provider_refund_id"] is None
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["refunded_paise"] == 0 and "refund_unconfirmed" in [e["type"] for e in got["events"]]
    msg = pc.post(f"/api/refunds/{d['id']}/refresh").json()
    assert msg["status"] == "pending" and "not created" in msg["notice"]
    # the request had in fact reached Razorpay: the refund exists there under our receipt code
    fake_rzp.refunds["rfnd_FOUND"] = {"id": "rfnd_FOUND", "entity": "refund", "payment_id": pay["id"], "amount": o["total_paise"], "receipt": d["code"], "status": "processed"}
    found = pc.post(f"/api/refunds/{d['id']}/refresh").json()
    assert found["status"] == "processed" and found["provider_refund_id"] == "rfnd_FOUND"
    assert pc.get(f"/api/payments/{p['id']}").json()["status"] == "refunded"


@pytest.mark.parametrize("fail", [(400, {"error": {"description": "The refund amount is greater than the payment"}}), (500, {}), httpx.ConnectError("down")])
def test_a_refund_razorpay_rejects_or_cannot_receive_is_recorded_without_touching_the_payment(pc, fake_rzp, fail):
    o, p, pay = paid_rzp(pc, fake_rzp)
    fake_rzp.fail_next = fail
    d = refund(pc, p["id"]).json()
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["refunded_paise"] == 0 and got["status"] == "paid" and d["status"] in ("failed", "pending")


def test_a_razorpay_reply_with_a_different_refund_amount_is_not_applied(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    orig = fake_rzp._handle

    def odd(request):
        res = orig(request)
        if request.url.path.endswith("/refund"):
            body = res.json()
            body["amount"], body["status"] = body["amount"] - 1, "processed"
            return httpx.Response(200, json=body)
        return res
    pc.app.state.razorpay._transport = httpx.MockTransport(odd)
    d = refund(pc, p["id"]).json()
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert d["status"] == "pending" and got["refunded_paise"] == 0 and got["status"] == "paid"
    assert "refund_amount_mismatch" in [e["type"] for e in got["events"]]


def test_a_razorpay_refund_needs_razorpay_to_be_set_up_and_a_provider_payment_id(make_pay_app, fake_rzp):
    app = make_pay_app()
    with TestClient(app) as c:
        from .helpers import register
        register(c, OWNER)
        o, p, pay = paid_rzp(c, fake_rzp)
        with app.state.session_factory() as db:
            row = db.get(Payment, p["id"])
            row.provider_payment_id = None
            db.commit()
        assert refund(c, p["id"]).json()["detail"]["code"] == "NO_PROVIDER_PAYMENT"
        with app.state.session_factory() as db:
            row = db.get(Payment, p["id"])
            row.provider_payment_id = pay["id"]
            db.commit()
        app.state.settings.razorpay_key_secret = None
        assert refund(c, p["id"]).json()["detail"]["code"] == "RAZORPAY_OFF"


# ---- cancelling after a refund -------------------------------------------------------------------------------------------------------------
def test_an_order_can_be_cancelled_once_its_payment_is_fully_refunded_and_stock_comes_back(pc):
    from .test_payments_cash_upi import stock_map
    before = stock_map(pc)
    o, p = paid_cash(pc)
    blocked = pc.post(f"/api/orders/{o['id']}/status", json={"status": "cancelled"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "PAID_ORDER"
    refund(pc, p["id"])
    assert pc.post(f"/api/orders/{o['id']}/status", json={"status": "cancelled"}).json()["status"] == "cancelled"
    assert stock_map(pc) == before


def test_a_partly_refunded_order_is_still_blocked_from_cancelling(pc):
    o, p = paid_cash(pc)
    refund(pc, p["id"], amount_paise=o["total_paise"] // 2)
    assert pc.post(f"/api/orders/{o['id']}/status", json={"status": "cancelled"}).json()["detail"]["code"] == "PAID_ORDER"


def test_refund_rows_cannot_exceed_the_payment_in_the_database(pc):
    from sqlalchemy.exc import IntegrityError
    o, p = paid_cash(pc)
    with pc.app.state.session_factory() as db:
        row = db.get(Payment, p["id"])
        row.refunded_paise = row.amount_paise + 1
        with pytest.raises(IntegrityError):
            db.commit()


# ---- refund webhooks in less common orders ---------------------------------------------------------------------------------------------
def test_a_refund_webhook_that_arrives_before_the_create_call_was_answered_is_matched_by_receipt(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    fake_rzp.fail_next = httpx.ReadTimeout("no answer")
    d = refund(pc, p["id"]).json()
    assert d["provider_refund_id"] is None
    ent = {"id": "rfnd_FROM_WEBHOOK", "entity": "refund", "payment_id": pay["id"], "amount": o["total_paise"], "receipt": d["code"], "status": "processed", "speed_processed": "normal"}
    assert deliver(pc, "refund.processed", refund=ent).json()["result"] == "processed"
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "refunded" and got["refunds"][0]["provider_refund_id"] == "rfnd_FROM_WEBHOOK"


def test_refund_webhooks_for_unknown_refunds_or_unused_event_types_change_nothing(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"]).json()
    ent = fake_rzp.refunds[d["provider_refund_id"]]
    assert deliver(pc, "refund.processed", refund={"id": "rfnd_NOBODY", "receipt": "REF-000000-9999", "status": "processed", "amount": 1}).json()["status"] == "ignored"
    assert deliver(pc, "refund.processed", refund={"id": "rfnd_NOBODY2", "receipt": "something else", "status": "processed", "amount": 1}).json()["status"] == "ignored"
    assert deliver(pc, "refund.speed_changed", refund=ent).json()["status"] == "ignored"
    assert deliver(pc, "refund.created", refund=ent).json()["status"] in ("ignored", "processed")
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["status"] == "paid" and got["refunded_paise"] == 0 and got["refunds"][0]["status"] == "pending"


def test_a_processed_refund_larger_than_what_is_left_is_capped_and_flagged(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"], amount_paise=o["total_paise"] // 2).json()
    with pc.app.state.session_factory() as db:                                            # money was already refunded elsewhere (e.g. in the Razorpay dashboard)
        row = db.get(Payment, p["id"])
        row.refunded_paise = o["total_paise"] - 10
        db.commit()
    ent = dict(fake_rzp.refunds[d["provider_refund_id"]], status="processed")
    deliver(pc, "refund.processed", refund=ent)
    got = pc.get(f"/api/payments/{p['id']}").json()
    assert got["refunded_paise"] == o["total_paise"] and got["status"] == "refunded" and got["attention"] == "refund_mismatch"
    assert got["refunds"][0]["amount_paise"] == 10


def test_refreshing_a_refund_when_razorpay_is_unreachable_keeps_it_pending(pc, fake_rzp):
    o, p, pay = paid_rzp(pc, fake_rzp)
    d = refund(pc, p["id"]).json()
    fake_rzp.fail_next = httpx.ConnectError("offline")
    r = pc.post(f"/api/refunds/{d['id']}/refresh").json()
    assert r["status"] == "pending" and "Could not reach Razorpay" in r["notice"]
    assert pc.post("/api/refunds/999999/refresh").status_code == 404
    cash_o, cash_p = paid_cash(pc, "1 litre doodh")
    c = refund(pc, cash_p["id"]).json()
    assert pc.post(f"/api/refunds/{c['id']}/refresh").json()["status"] == "processed"      # a manual refund has nothing to ask Razorpay
