"""Payments 2.7.0: Razorpay in TEST mode (simulated provider), checkout signature verification, webhooks, replays, duplicates, amount mismatches.

The provider is FakeRazorpay. A passing test shows that this app builds the right requests, checks signatures correctly and refuses to mark a payment
paid on anything but a verified answer. It is not proof that Razorpay's servers answer in exactly this shape.
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.models import Payment, PaymentEvent
from app.services.razorpay import verify_checkout_signature, verify_webhook_signature
from .helpers import OWNER
from .payment_helpers import KEY_ID, KEY_SECRET, SECRETS, WEBHOOK_SECRET, checkout_sig, event, hmac_hex, new_order, webhook_headers

WEBHOOK = "/api/payments/webhooks/razorpay"


def rzp(c, order, expect=(200, 201)):
    r = c.post(f"/api/orders/{order['id']}/payments", json={"method": "razorpay"})
    assert r.status_code in expect, r.text
    return r.json()


def verify(c, p, payment_id, sig=None, order_id=None):
    return c.post(f"/api/payments/{p['id']}/razorpay/verify", json={
        "razorpay_order_id": order_id or p["provider_order_id"], "razorpay_payment_id": payment_id,
        "razorpay_signature": sig if sig is not None else checkout_sig(order_id or p["provider_order_id"], payment_id)})


def hook(c, raw, event_id="evt_1", headers=None):
    return c.post(WEBHOOK, content=raw, headers=headers or webhook_headers(raw, event_id))


def state(c, p):
    return c.get(f"/api/payments/{p['id']}").json()


def event_types(c, p):
    return [e["type"] for e in state(c, p)["events"]]


# ---- configuration --------------------------------------------------------------------------------------------------------------------
def test_razorpay_is_off_until_keys_are_set_and_never_switches_on_by_itself(make_pay_app):
    with TestClient(make_pay_app(razorpay_key_id="", razorpay_key_secret=None, razorpay_webhook_secret=None)) as c:
        from .helpers import register
        register(c, OWNER)
        o = new_order(c)
        r = c.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "RAZORPAY_OFF"
        cfg = c.get("/api/payments/config").json()
        assert cfg["mode"] == "test" and cfg["razorpay"]["enabled"] is False and cfg["razorpay"]["key_id"] is None
        assert cfg["owner"]["key_secret_set"] is False and cfg["owner"]["webhook_secret_set"] is False


@pytest.mark.parametrize("kw,fragment", [
    (dict(razorpay_key_id="your_key_id_here", razorpay_key_secret="your_secret_here"), "placeholder"),
    (dict(razorpay_key_id="rzp_live_PLACEHOLDER01"), "rzp_test_"),
    (dict(payment_mode="live"), "rzp_live_"),
    (dict(razorpay_key_secret=None), "RAZORPAY_KEY_SECRET"),
])
def test_razorpay_stays_off_for_bad_or_mismatched_keys(make_pay_app, kw, fragment):
    with TestClient(make_pay_app(**kw)) as c:
        from .helpers import register
        register(c, OWNER)
        cfg = c.get("/api/payments/config").json()
        assert cfg["razorpay"]["enabled"] is False and fragment.lower() in (cfg["owner"]["razorpay_problem"] or "").lower()


def test_the_default_mode_is_test_and_unknown_modes_are_refused():
    assert Settings(_env_file=None).payment_mode == "test"
    with pytest.raises(ValueError):
        Settings(_env_file=None, payment_mode="production")
    assert Settings(_env_file=None, payment_mode="LIVE").payment_mode == "live"


def test_live_mode_works_only_with_live_keys_and_is_never_implied_by_test_keys(make_pay_app):
    with TestClient(make_pay_app(payment_mode="live", razorpay_key_id="rzp_live_PLACEHOLDER01")) as c:
        from .helpers import register
        register(c, OWNER)
        assert c.get("/api/payments/config").json()["mode"] == "live"
        assert c.get("/api/payments/config").json()["razorpay"]["test_mode"] is False


# ---- creating the Razorpay order --------------------------------------------------------------------------------------------------------
def test_the_razorpay_order_is_made_on_the_server_for_the_server_side_total(pc, fake_rzp):
    o = new_order(pc)
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay", "amount_paise": 100})
    p = r.json()
    assert r.status_code == 201 and p["status"] == "pending" and p["provider_order_id"].startswith("order_")
    sent = next(b for m, path, b in fake_rzp.calls if path == "/v1/orders")
    assert sent["amount"] == o["total_paise"] and sent["currency"] == "INR" and sent["receipt"].startswith(o["code"])
    assert p["checkout"] == {"key_id": KEY_ID, "provider_order_id": p["provider_order_id"], "amount_paise": o["total_paise"], "currency": "INR",
                             "name": p["checkout"]["name"], "description": f"Bill {o['code']}", "mode": "test"}
    assert fake_rzp.auth_seen and all(a == (KEY_ID, KEY_SECRET) for a in fake_rzp.auth_seen)   # the server authenticates; the browser gets only the key id


def test_no_secret_appears_in_any_payment_response(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    bodies = [json.dumps(p), verify(pc, p, pay["id"]).text, pc.get("/api/payments").text, pc.get(f"/api/payments/{p['id']}").text, pc.get("/api/payments/config").text,
              pc.get("/api/settings").text, pc.get(f"/api/orders/{o['id']}/invoice").text, pc.get("/api/payments/analytics").text]
    for text in bodies:
        for secret in SECRETS:
            assert secret not in text


def test_a_second_tap_returns_the_open_razorpay_payment_and_does_not_create_another_provider_order(pc, fake_rzp):
    o = new_order(pc)
    a = rzp(pc, o)
    b = rzp(pc, o, expect=(200,))
    assert a["id"] == b["id"] and a["provider_order_id"] == b["provider_order_id"] and fake_rzp.count("POST", r"/v1/orders$") == 1
    assert b["checkout"]["provider_order_id"] == a["provider_order_id"]


def test_a_provider_order_with_the_wrong_amount_is_refused_and_nothing_is_started(pc, fake_rzp):
    o = new_order(pc)
    fake_rzp.order_amount_delta = 100
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "RAZORPAY_BAD_REPLY"
    assert pc.get(f"/api/orders/{o['id']}/payments").json()["items"] == []


@pytest.mark.parametrize("fail,code", [(httpx.ConnectError("down"), "RAZORPAY_NETWORK"), (httpx.ReadTimeout("slow"), "RAZORPAY_TIMEOUT"),
                                        ((401, {"error": {"description": "x"}}), "RAZORPAY_AUTH_FAILED"), ((429, {}), "RAZORPAY_RATE_LIMITED"),
                                        ((500, {}), "RAZORPAY_PROVIDER_ERROR"), ((400, {"error": {"description": "Amount is too low"}}), "RAZORPAY_REJECTED")])
def test_provider_errors_are_reported_plainly_and_leave_no_payment_behind(pc, fake_rzp, fail, code):
    o = new_order(pc)
    fake_rzp.fail_next = fail
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == code and r.json()["detail"]["message"]
    assert pc.get(f"/api/orders/{o['id']}/payments").json()["items"] == []
    assert start_ok(pc, o)


def start_ok(pc, o):
    return pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"}).status_code == 201   # and it works again afterwards


# ---- the checkout callback ------------------------------------------------------------------------------------------------------------
def test_a_correct_signature_then_razorpays_own_record_marks_the_payment_paid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], method="card")
    r = verify(pc, p, pay["id"])
    d = r.json()
    assert r.status_code == 200 and d["status"] == "paid" and d["verified"] is True and d["verification"] == "signature" and d["provider_payment_id"] == pay["id"]
    assert d["provider_method"] == "card" and d["paid_at"] and d["verification_label"] == "Confirmed by Razorpay" and not d.get("notice")
    assert fake_rzp.count("GET", rf"/v1/payments/{pay['id']}$") == 1           # Razorpay was asked, the browser's word was not enough
    assert pc.get(f"/api/orders/{o['id']}").json()["payment"]["status"] == "paid"
    assert event_types(pc, p) == ["created", "signature_ok", "paid"]


def test_a_wrong_signature_is_refused_and_nothing_is_marked_paid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    r = verify(pc, p, pay["id"], sig="0" * 64)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "BAD_SIGNATURE"
    assert state(pc, p)["status"] == "pending"
    assert fake_rzp.count("GET", r"/v1/payments/") == 0                    # a bad signature never even reaches the provider lookup
    ev = state(pc, p)["events"][-1]
    assert ev["type"] == "bad_signature" and ev["signature_ok"] is False
    assert verify(pc, p, pay["id"], sig="").status_code in (400, 422)


def test_the_signature_must_be_for_the_stored_order_not_the_one_the_browser_names(pc, fake_rzp):
    o1, o2 = new_order(pc), new_order(pc, "1 litre doodh")
    p1 = rzp(pc, o1)
    p2 = rzp(pc, o2)
    pay2 = fake_rzp.new_payment(p2["provider_order_id"])
    # a genuine payment + signature for order 2 presented against order 1's payment record
    r = verify(pc, p1, pay2["id"], sig=checkout_sig(p2["provider_order_id"], pay2["id"]), order_id=p2["provider_order_id"])
    assert r.status_code == 400 and state(pc, p1)["status"] == "pending"
    # and the right order id with a signature made for another payment id
    r = verify(pc, p2, pay2["id"], sig=checkout_sig(p2["provider_order_id"], "pay_other"))
    assert r.status_code == 400 and state(pc, p2)["status"] == "pending"
    assert verify(pc, p2, pay2["id"]).json()["status"] == "paid"           # the genuine pair works


def test_a_signature_made_with_the_wrong_secret_is_refused(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    assert verify(pc, p, pay["id"], sig=checkout_sig(p["provider_order_id"], pay["id"], secret="somebody-elses-secret")).status_code == 400
    assert verify(pc, p, pay["id"], sig=checkout_sig(p["provider_order_id"], pay["id"], secret=WEBHOOK_SECRET)).status_code == 400   # the webhook secret is not the key secret


def test_presenting_the_same_confirmation_twice_records_one_payment(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    assert verify(pc, p, pay["id"]).json()["status"] == "paid"
    again = verify(pc, p, pay["id"])
    assert again.status_code == 200 and again.json()["status"] == "paid"
    assert event_types(pc, p).count("paid") == 1
    assert pc.get(f"/api/orders/{o['id']}/payments").json()["summary"]["paid_paise"] == o["total_paise"]


def test_a_valid_signature_for_a_payment_razorpay_says_is_for_a_different_amount_is_not_marked_paid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], amount=o["total_paise"] - 100)
    r = verify(pc, p, pay["id"])
    d = r.json()
    assert d["status"] == "pending" and d["attention"] == "amount_mismatch" and "different amount" in d["notice"]
    assert "amount_mismatch" in event_types(pc, p)


def test_a_payment_that_belongs_to_another_razorpay_order_is_ignored(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment("order_SOMEONE_ELSES", amount=o["total_paise"])
    d = verify(pc, p, pay["id"]).json()
    assert d["status"] == "pending" and "different order" in d["notice"]


def test_an_authorised_payment_is_captured_for_the_exact_amount_then_paid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], status="authorized", method="card")
    d = verify(pc, p, pay["id"]).json()
    assert d["status"] == "paid" and fake_rzp.payments[pay["id"]]["status"] == "captured"
    cap = next(b for m, path, b in fake_rzp.calls if path.endswith("/capture"))
    assert cap == {"amount": o["total_paise"], "currency": "INR"}


def test_if_capture_fails_the_payment_stays_pending_with_a_plain_message(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], status="authorized")
    orig = fake_rzp._handle

    def flaky(request):
        if request.url.path.endswith("/capture"):
            return httpx.Response(500, json={})
        return orig(request)
    pc.app.state.razorpay._transport = httpx.MockTransport(flaky)
    d = verify(pc, p, pay["id"]).json()
    assert d["status"] == "pending" and "capturing" in d["notice"]
    assert "capture_failed" in event_types(pc, p)


def test_when_razorpay_cannot_be_asked_a_valid_signature_alone_does_not_mark_paid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    fake_rzp.fail_next = httpx.ConnectError("offline")
    d = verify(pc, p, pay["id"]).json()
    assert d["status"] == "pending" and "could not be asked" in d["notice"]
    d = pc.post(f"/api/payments/{p['id']}/refresh").json()                    # later, Check status finds it
    assert d["status"] == "paid" and d["verified"] is True and d["verification"] == "provider"


def test_a_failed_payment_is_recorded_as_failed_and_the_shop_can_try_again(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], status="failed", error_code="BAD_REQUEST_ERROR", error_description="Payment declined by the bank")
    d = verify(pc, p, pay["id"]).json()
    assert d["status"] == "failed" and d["failure_reason"] == "Payment declined by the bank" and d["failure_code"] == "BAD_REQUEST_ERROR" and d["paid_at"] is None
    assert pc.get(f"/api/orders/{o['id']}").json()["payment"]["status"] == "failed"
    assert pc.get("/api/payments", params={"status": "failed"}).json()["total"] == 1
    retry = rzp(pc, o, expect=(201,))
    assert retry["id"] != p["id"] and retry["status"] == "pending"
    assert pc.get(f"/api/orders/{o['id']}").json()["payment"]["status"] == "pending"


def test_a_pending_payment_is_checked_by_asking_razorpay_and_stays_pending_if_unpaid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    d = pc.post(f"/api/payments/{p['id']}/refresh").json()
    assert d["status"] == "pending" and "no payment" in d["notice"].lower()
    created = fake_rzp.new_payment(p["provider_order_id"], status="created")
    d = pc.post(f"/api/payments/{p['id']}/refresh").json()
    assert d["status"] == "pending"
    created["status"], created["captured"] = "captured", True
    d = pc.post(f"/api/payments/{p['id']}/refresh").json()
    assert d["status"] == "paid" and d["verified"] is True and d["provider_payment_id"] == created["id"]


def test_cancelling_a_waiting_razorpay_payment_then_a_later_success_is_recorded_and_flagged(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    assert pc.post(f"/api/payments/{p['id']}/cancel", json={}).json()["status"] == "cancelled"
    pay = fake_rzp.new_payment(p["provider_order_id"])
    raw = event("payment.captured", payment=pay)
    assert hook(pc, raw).json()["result"] == "paid"
    d = state(pc, p)
    assert d["status"] == "paid" and d["attention"] == "late_payment"
    assert pc.get("/api/payments", params={"attention": "true"}).json()["total"] == 1


# ---- webhooks -------------------------------------------------------------------------------------------------------------------------
def test_a_signed_captured_event_marks_the_payment_paid_without_any_signed_in_user(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    pc.cookies.clear()
    pc.headers.pop("X-CSRF-Token", None)                                 # Razorpay has no session and no CSRF token
    r = hook(pc, event("payment.captured", payment=pay))
    assert r.status_code == 200 and r.json() == {"status": "processed", "result": "paid"}
    from .helpers import login
    login(pc, OWNER)
    d = state(pc, p)
    assert d["status"] == "paid" and d["verified"] is True and d["verification"] == "webhook" and d["provider_payment_id"] == pay["id"]


def test_a_webhook_with_a_bad_or_missing_signature_is_refused_and_changes_nothing(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    raw = event("payment.captured", payment=pay)
    for headers in ({"X-Razorpay-Signature": "0" * 64}, {}, {"X-Razorpay-Signature": hmac_hex("wrong-secret", raw)}, {"X-Razorpay-Signature": hmac_hex(KEY_SECRET, raw)}):
        r = pc.post(WEBHOOK, content=raw, headers={"Content-Type": "application/json", **headers})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "BAD_SIGNATURE"
    tampered = raw.replace(b'"captured"', b'"captured" ')
    assert pc.post(WEBHOOK, content=tampered, headers=webhook_headers(raw)).status_code == 400   # signature of the original does not fit a changed body
    assert state(pc, p)["status"] == "pending"
    with pc.app.state.session_factory() as db:
        assert db.scalar(select(PaymentEvent).where(PaymentEvent.source == "webhook")) is None


def test_webhooks_are_refused_when_no_webhook_secret_is_set(make_pay_app, fake_rzp):
    with TestClient(make_pay_app(razorpay_webhook_secret=None)) as c:
        raw = event("payment.captured", payment=fake_rzp.new_payment("order_x", amount=100))
        r = c.post(WEBHOOK, content=raw, headers=webhook_headers(raw))
        assert r.status_code == 503 and r.json()["detail"]["code"] == "WEBHOOK_NOT_CONFIGURED"


def test_the_same_webhook_delivered_twice_is_processed_once(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    raw = event("payment.captured", payment=pay)
    assert hook(pc, raw, "evt_same").json()["status"] == "processed"
    second = hook(pc, raw, "evt_same")
    assert second.status_code == 200 and second.json() == {"status": "duplicate"}
    assert event_types(pc, p).count("paid") == 1
    with pc.app.state.session_factory() as db:
        assert len(db.scalars(select(PaymentEvent).where(PaymentEvent.event_id == "evt_same")).all()) == 1


def test_a_redelivery_with_a_new_event_id_after_payment_changes_nothing(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    raw = event("payment.captured", payment=pay)
    assert hook(pc, raw, "evt_a").json()["result"] == "paid"
    assert hook(pc, raw, "evt_b").json()["result"] == "already_paid"
    assert event_types(pc, p).count("paid") == 1 and pc.get("/api/payments").json()["counts"]["paid"] == 1


def test_a_webhook_without_an_event_id_header_is_still_deduplicated_by_its_content(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    raw = event("payment.captured", payment=pay)
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw)).json()["status"] == "processed"
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw)).json()["status"] == "duplicate"


def test_an_old_failure_replayed_after_success_does_not_undo_it(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    failed_attempt = dict(pay, id="pay_EARLIER_ATTEMPT", status="failed", error_code="X", error_description="declined")
    assert hook(pc, event("payment.captured", payment=pay), "evt_1").json()["result"] == "paid"
    assert hook(pc, event("payment.failed", payment=failed_attempt), "evt_2").json()["result"] == "ignored"
    d = state(pc, p)
    assert d["status"] == "paid" and d["provider_payment_id"] == pay["id"]


def test_failed_then_captured_events_end_paid_and_captured_then_failed_stay_paid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    first = fake_rzp.new_payment(p["provider_order_id"], status="failed", error_description="Card declined")
    assert hook(pc, event("payment.failed", payment=first), "e1").json()["result"] == "failed"
    assert state(pc, p)["status"] == "failed" and state(pc, p)["failure_reason"] == "Card declined"
    second = fake_rzp.new_payment(p["provider_order_id"])
    assert hook(pc, event("payment.captured", payment=second), "e2").json()["result"] == "paid"
    assert state(pc, p)["status"] == "paid" and state(pc, p)["failure_reason"] is None and state(pc, p)["attention"] == "late_payment"


def test_a_second_captured_payment_for_a_paid_order_is_flagged_not_recorded_twice(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    a = fake_rzp.new_payment(p["provider_order_id"])
    b = fake_rzp.new_payment(p["provider_order_id"])
    assert hook(pc, event("payment.captured", payment=a), "e1").json()["result"] == "paid"
    assert hook(pc, event("payment.captured", payment=b), "e2").json()["result"] == "duplicate_collection"
    d = state(pc, p)
    assert d["status"] == "paid" and d["provider_payment_id"] == a["id"] and d["attention"] == "duplicate_collection"
    assert pc.get(f"/api/orders/{o['id']}/payments").json()["summary"]["paid_paise"] == o["total_paise"]


def test_a_webhook_amount_that_differs_from_the_bill_is_not_marked_paid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], amount=o["total_paise"] + 1)
    assert hook(pc, event("payment.captured", payment=pay)).json()["result"] == "amount_mismatch"
    d = state(pc, p)
    assert d["status"] == "pending" and d["attention"] == "amount_mismatch"


def test_a_webhook_for_something_this_shop_does_not_know_is_acknowledged_and_ignored(pc, fake_rzp):
    pay = fake_rzp.new_payment("order_UNKNOWN", amount=1000)
    r = hook(pc, event("payment.captured", payment=pay))
    assert r.status_code == 200 and r.json()["status"] == "ignored"
    assert hook(pc, event("payout.processed"), "e9").status_code == 200


def test_webhook_bodies_that_are_not_json_or_are_too_large_are_refused(pc):
    raw = b"not json at all"
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw)).json()["detail"]["code"] == "BAD_PAYLOAD"
    raw = b"[1,2,3]"
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw)).json()["detail"]["code"] == "BAD_PAYLOAD"
    big = b'{"event":"x","pad":"' + b"a" * (300 * 1024) + b'"}'
    assert pc.post(WEBHOOK, content=big, headers=webhook_headers(big)).status_code == 413


def test_personal_data_in_a_webhook_is_not_stored(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], email="customer@example.com", contact="+919800000000", vpa="customer@okhdfcbank",
                               card={"last4": "4242", "network": "Visa"}, notes={"x": "y"})
    assert hook(pc, event("payment.captured", payment=pay)).status_code == 200
    with pc.app.state.session_factory() as db:
        blob = json.dumps([[e.message, e.data] for e in db.scalars(select(PaymentEvent))])
    for needle in ("customer@example.com", "9800000000", "customer@okhdfcbank", "4242", "Visa"):
        assert needle not in blob


def test_the_webhook_works_without_the_browser_origin_rules_getting_in_the_way(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    raw = event("payment.captured", payment=fake_rzp.new_payment(p["provider_order_id"]))
    r = pc.post(WEBHOOK, content=raw, headers={**webhook_headers(raw), "Origin": "https://evil.example"})
    assert r.status_code == 403                                  # a browser from another site is still refused, as for every API write
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw)).status_code == 200   # Razorpay's server sends no Origin


# ---- signature functions, on their own ------------------------------------------------------------------------------------------------
def test_signature_functions_follow_razorpays_documented_construction_and_reject_junk():
    sig = hmac_hex("s3cret", b"order_1|pay_1")
    assert verify_checkout_signature("s3cret", "order_1", "pay_1", sig)
    assert verify_checkout_signature("s3cret", "order_1", "pay_1", sig.upper()) is True    # hex case is not part of the value: same bytes, same signature
    for junk in ("", None, 5, sig[:-1], sig + "0", "zz" * 32):
        assert verify_checkout_signature("s3cret", "order_1", "pay_1", junk) is False
    assert verify_checkout_signature("", "order_1", "pay_1", sig) is False
    body = b'{"event":"x"}'
    assert verify_webhook_signature("w", body, hmac_hex("w", body))
    assert not verify_webhook_signature("w", body, hmac_hex("w", body + b" "))
    assert not verify_webhook_signature(None, body, hmac_hex("w", body)) and not verify_webhook_signature("w", body, None)


# ---- razorpay UPI QR (dynamic, provider-verified) ---------------------------------------------------------------------------------------
@pytest.fixture
def qc(make_pay_app):
    with TestClient(make_pay_app(razorpay_upi_qr=True)) as c:
        from .helpers import register
        register(c, OWNER)
        yield c


def test_with_razorpay_qr_on_upi_shows_a_provider_qr_and_waits_for_razorpay(qc, fake_rzp):
    o = new_order(qc)
    p = qc.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"}).json()
    assert p["provider"] == "razorpay_qr" and p["provider_qr_id"].startswith("qr_") and p["upi"]["mode"] == "provider" and p["upi"]["verified_by_provider"] is True
    assert p["upi"]["qr_image_url"].startswith("https://") and p["upi"]["uri"] is None and "confirmed automatically" in p["upi"]["instructions"]
    sent = next(b for m, path, b in fake_rzp.calls if path == "/v1/payments/qr_codes")
    assert sent["payment_amount"] == o["total_paise"] and sent["fixed_amount"] is True and sent["usage"] == "single_use" and sent["type"] == "upi_qr"
    assert qc.post(f"/api/payments/{p['id']}/confirm-upi", json={"reference": "REF12345"}).json()["detail"]["code"] == "WRONG_METHOD"
    assert qc.get(f"/api/payments/{p['id']}").json()["status"] == "pending"


def test_a_qr_payment_is_confirmed_by_the_provider_via_check_status_or_webhook(qc, fake_rzp):
    o = new_order(qc)
    p = qc.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"}).json()
    assert qc.post(f"/api/payments/{p['id']}/refresh").json()["status"] == "pending"
    pay = fake_rzp.new_qr_payment(p["provider_qr_id"])
    d = qc.post(f"/api/payments/{p['id']}/refresh").json()
    assert d["status"] == "paid" and d["verified"] is True and d["provider_method"] == "upi" and d["verification_label"] == "Confirmed by Razorpay"
    o2 = new_order(qc, "1 litre doodh")
    p2 = qc.post(f"/api/orders/{o2['id']}/payments", json={"method": "upi"}).json()
    pay2 = fake_rzp.new_qr_payment(p2["provider_qr_id"])
    raw = event("qr_code.credited", payment=pay2, qr=fake_rzp.qrs[p2["provider_qr_id"]])
    assert hook(qc, raw).json()["result"] == "paid"
    assert qc.get(f"/api/payments/{p2['id']}").json()["status"] == "paid"


def test_a_qr_payment_of_the_wrong_amount_is_not_marked_paid(qc, fake_rzp):
    o = new_order(qc)
    p = qc.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"}).json()
    fake_rzp.new_qr_payment(p["provider_qr_id"], amount=o["total_paise"] - 1)
    d = qc.post(f"/api/payments/{p['id']}/refresh").json()
    assert d["status"] == "pending" and d["attention"] == "amount_mismatch"


def test_a_qr_reply_with_the_wrong_amount_starts_nothing_and_a_rejected_qr_says_why(qc, fake_rzp):
    o = new_order(qc)
    fake_rzp.qr_amount_delta = 1
    r = qc.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "RAZORPAY_BAD_REPLY"
    fake_rzp.qr_amount_delta = 0
    fake_rzp.fail_next = (400, {"error": {"description": "QR codes are not enabled for this account"}})
    r = qc.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"})
    assert r.status_code == 502 and "not enabled" in r.json()["detail"]["message"] and "switched UPI QR on" in r.json()["detail"]["message"]
    assert qc.get(f"/api/orders/{o['id']}/payments").json()["items"] == []


def test_cancelling_a_qr_payment_closes_the_qr(qc, fake_rzp):
    o = new_order(qc)
    p = qc.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"}).json()
    assert qc.post(f"/api/payments/{p['id']}/cancel", json={}).json()["status"] == "cancelled"
    assert fake_rzp.qrs[p["provider_qr_id"]]["status"] == "closed"


# ---- cancelling the order ---------------------------------------------------------------------------------------------------------------
def test_cancelling_an_order_closes_its_open_payment_and_a_late_success_is_flagged(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    assert pc.post(f"/api/orders/{o['id']}/status", json={"status": "cancelled"}).json()["status"] == "cancelled"
    assert state(pc, p)["status"] == "cancelled" and "order_cancelled" in event_types(pc, p)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    assert hook(pc, event("payment.captured", payment=pay)).json()["result"] == "paid"
    assert state(pc, p)["attention"] == "order_cancelled"


def test_a_paid_order_cannot_be_cancelled_until_it_is_refunded(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"])
    verify(pc, p, pay["id"])
    r = pc.post(f"/api/orders/{o['id']}/status", json={"status": "cancelled"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PAID_ORDER"
    assert pc.get(f"/api/orders/{o['id']}").json()["status"] == "confirmed"
    assert pc.post(f"/api/orders/{o['id']}/status", json={"status": "fulfilled"}).json()["status"] == "fulfilled"   # fulfilling a paid order is fine


# ---- less common paths ----------------------------------------------------------------------------------------------------------------
def test_an_authorised_event_is_captured_by_the_server_and_then_paid(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], status="authorized", method="card")
    assert hook(pc, event("payment.authorized", payment=pay)).json()["result"] == "paid"
    assert fake_rzp.payments[pay["id"]]["status"] == "captured" and state(pc, p)["status"] == "paid"


def test_the_start_of_a_double_tap_race_returns_the_payment_the_other_tap_made(pc, monkeypatch):
    """Two taps at the same moment both see 'no open payment'; the database's one-open-payment rule stops the second and it gets the first one back."""
    from app.services import payments as svc
    o = new_order(pc)
    first = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()
    real = svc.order_payments
    calls = {"n": 0}

    def blind_once(db, order_id):
        calls["n"] += 1
        return [] if calls["n"] == 1 else real(db, order_id)
    monkeypatch.setattr(svc, "order_payments", blind_once)
    with pc.app.state.session_factory() as db:
        order = svc.get_order(db, o["id"])
        user = db.scalar(select(__import__("app.models", fromlist=["User"]).User))
        again, created = svc.create_payment(db, pc.app.state.settings, pc.app.state.razorpay, order, "cash", user, None)
    assert created is False and again.id == first["id"]
    with pc.app.state.session_factory() as db:
        assert db.query(Payment).filter(Payment.order_id == o["id"]).count() == 1


def test_an_order_with_nothing_to_pay_is_refused(pc):
    o = new_order(pc)
    from app.models import Order
    with pc.app.state.session_factory() as db:
        db.get(Order, o["id"]).total_paise = 0
        db.commit()
    assert pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()["detail"]["code"] == "NOTHING_TO_PAY"


def test_verify_and_refresh_refuse_the_wrong_kind_of_payment_or_a_switched_off_razorpay(pc, fake_rzp):
    o = new_order(pc)
    cash = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()
    r = pc.post(f"/api/payments/{cash['id']}/razorpay/verify", json={"razorpay_order_id": "o", "razorpay_payment_id": "p", "razorpay_signature": "s"})
    assert r.json()["detail"]["code"] == "WRONG_METHOD"
    assert pc.post(f"/api/payments/{cash['id']}/refresh").json()["status"] == "pending"          # nothing to ask Razorpay about a cash payment
    pc.post(f"/api/payments/{cash['id']}/cancel", json={})
    p = rzp(pc, o)
    saved = pc.app.state.settings.razorpay_key_secret
    pc.app.state.settings.razorpay_key_secret = None
    assert pc.post(f"/api/payments/{p['id']}/razorpay/verify", json={"razorpay_order_id": p["provider_order_id"], "razorpay_payment_id": "pay_x",
                                                                       "razorpay_signature": "s"}).json()["detail"]["code"] == "RAZORPAY_OFF"
    assert pc.post(f"/api/payments/{p['id']}/refresh").json()["detail"]["code"] == "RAZORPAY_OFF"
    pc.app.state.settings.razorpay_key_secret = saved


def test_check_status_after_a_failed_attempt_looks_the_payment_up_by_its_own_id(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], status="failed", error_description="declined")
    assert verify(pc, p, pay["id"]).json()["status"] == "failed"
    pay["status"], pay["captured"] = "captured", True                                    # the bank retried and it went through
    d = pc.post(f"/api/payments/{p['id']}/refresh").json()
    assert d["status"] == "paid" and d["attention"] == "late_payment"
    assert fake_rzp.count("GET", rf"/v1/payments/{pay['id']}$") >= 2


def test_check_status_reports_razorpay_being_unreachable_without_changing_anything(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    fake_rzp.fail_next = httpx.ConnectError("offline")
    d = pc.post(f"/api/payments/{p['id']}/refresh").json()
    assert d["status"] == "pending" and "Could not reach Razorpay" in d["notice"]


def test_a_qr_that_cannot_be_closed_still_cancels_the_payment(qc, fake_rzp):
    o = new_order(qc)
    p = qc.post(f"/api/orders/{o['id']}/payments", json={"method": "upi"}).json()
    fake_rzp.fail_next = httpx.ConnectError("offline")
    assert qc.post(f"/api/payments/{p['id']}/cancel", json={}).json()["status"] == "cancelled"


def test_events_that_need_no_action_are_recorded_and_acknowledged(pc, fake_rzp):
    o = new_order(pc)
    p = rzp(pc, o)
    pay = fake_rzp.new_payment(p["provider_order_id"], status="created")
    r = hook(pc, event("payment.dispute.created", payment=pay), "e_disp")
    assert r.status_code == 200 and r.json()["status"] == "ignored" and state(pc, p)["status"] == "pending"
    assert hook(pc, event("payment.authorized", payment=dict(pay, status="created")), "e_auth").status_code == 200
