"""Payments 2.7.0: security properties. Secrets stay on the server, nothing is trusted from the browser, replays and duplicates change nothing,
live mode is never switched on by itself, and the Content-Security-Policy opens up for Razorpay only while Razorpay is on."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.security import csp
from .helpers import OWNER
from .payment_helpers import KEY_ID, KEY_SECRET, SECRETS, WEBHOOK_SECRET, checkout_sig, event, new_order, webhook_headers

ROOT = Path(__file__).resolve().parents[2]
WEBHOOK = "/api/payments/webhooks/razorpay"


# ---- placeholders and the shipped files --------------------------------------------------------------------------------------------------
def test_env_example_has_only_empty_placeholders_for_payments_and_keeps_the_gnani_lines():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    lines = {m.group(1): m.group(2) for m in re.finditer(r"^([A-Z_0-9]+)=(.*)$", text, flags=re.M)}
    assert lines["RAZORPAY_KEY_ID"] == "" and lines["RAZORPAY_KEY_SECRET"] == "" and lines["RAZORPAY_WEBHOOK_SECRET"] == "" and lines["PAYMENT_MODE"] == "test"
    assert lines["GNANI_API_KEY"] == "your_gnani_api_key_here" and lines["GNANI_BASE_URL"] == "https://api.vachana.ai" and lines["GNANI_TTS_MODEL"] == "timbre-v2.5"
    assert not re.search(r"rzp_(test|live)_[A-Za-z0-9]{6,}", text) and "live" not in lines["PAYMENT_MODE"]


# What the browser's code must never contain. Two field names are allowed because they are yes/no answers from the server, not secrets:
# key_secret_set and webhook_secret_set (the Settings card says "Set on the server (never shown)" or "Not set"). The placeholder keys the tests use
# (rzp_test_PLACEHOLDER01) are made up and cannot be a real key id.
SECRET_NAME = re.compile(r"key_secret(?!_set\b)|webhook_secret(?!_set\b)|KEY_SECRET|WEBHOOK_SECRET")
KEY_VALUE = re.compile(r"rzp_(test|live)_(?!PLACEHOLDER)[A-Za-z0-9]{6,}")


def test_the_frontend_guard_recognises_what_it_looks_for():
    """A guard that matches nothing passes forever; check it fires on each kind of leak and lets the two yes/no fields and the made-up test key through."""
    for leak in ("const key_secret = 'x'", "webhook_secret: string", "process.env.RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET=abc"):
        assert SECRET_NAME.search(leak), leak
    for leak in ("rzp_test_AbCdEf123456", "rzp_live_9f8e7d6c5b4a"):
        assert KEY_VALUE.search(leak), leak
    for fine in ("key_secret_set: boolean", "o.webhook_secret_set ? 'Set' : 'Not set'"):
        assert not SECRET_NAME.search(fine), fine
    assert not KEY_VALUE.search("rzp_test_PLACEHOLDER01")


def test_no_razorpay_credential_or_secret_name_appears_in_frontend_source():
    """The browser bundle may know the PUBLIC key id from the server's answer, never a secret value or the name of one."""
    hits = []
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".css", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        is_test = ".test." in path.name or "test" in path.relative_to(ROOT / "frontend" / "src").parts[:1]   # tests and fixtures may mention env-var names in server messages
        if KEY_VALUE.search(text) or (not is_test and SECRET_NAME.search(text)):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
    dist = ROOT / "frontend" / "dist"
    if dist.is_dir():
        for path in dist.rglob("*.js"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert not SECRET_NAME.search(text) and not KEY_VALUE.search(text), path.name


def test_no_credential_is_hardcoded_anywhere_in_the_backend():
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"rzp_(test|live)_[A-Za-z0-9]{6,}", src), path
        assert not re.search(r"""(?i)(secret|password|token)\s*=\s*["'][A-Za-z0-9_\-]{16,}["']""", src), path


def test_the_default_configuration_has_razorpay_off_in_test_mode():
    s = Settings(_env_file=None)
    assert s.payment_mode == "test" and s.razorpay_enabled is False and s.razorpay_secret is None and s.razorpay_webhook_key is None


def test_secrets_are_hidden_when_settings_are_printed():
    s = Settings(_env_file=None, razorpay_key_id=KEY_ID, razorpay_key_secret=KEY_SECRET, razorpay_webhook_secret=WEBHOOK_SECRET)
    shown = repr(s) + str(s.model_dump())
    for secret in SECRETS:
        assert secret not in shown


# ---- nothing leaks in responses or logs ----------------------------------------------------------------------------------------------------
def test_secrets_never_appear_in_logs_even_when_razorpay_refuses_the_key(pc, fake_rzp, caplog):
    caplog.set_level(logging.DEBUG)
    o = new_order(pc)
    pc.app.state.settings.razorpay_key_secret = type(pc.app.state.settings.razorpay_key_secret)("a-wrong-secret-value")
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "RAZORPAY_AUTH_FAILED"
    pc.app.state.settings.razorpay_key_secret = type(pc.app.state.settings.razorpay_key_secret)(KEY_SECRET)
    p = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"}).json()
    pay = fake_rzp.new_payment(p["provider_order_id"])
    pc.post(f"/api/payments/{p['id']}/razorpay/verify", json={"razorpay_order_id": p["provider_order_id"], "razorpay_payment_id": pay["id"], "razorpay_signature": "bad"})
    raw = event("payment.captured", payment=pay)
    pc.post(WEBHOOK, content=raw, headers={"X-Razorpay-Signature": "bad"})
    pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw))
    everything = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (*SECRETS, "a-wrong-secret-value"):
        assert secret not in everything


def test_the_audit_trail_stores_ids_and_amounts_but_never_a_signature_or_secret(pc, fake_rzp):
    o = new_order(pc)
    p = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"}).json()
    pay = fake_rzp.new_payment(p["provider_order_id"])
    sig = checkout_sig(p["provider_order_id"], pay["id"])
    pc.post(f"/api/payments/{p['id']}/razorpay/verify", json={"razorpay_order_id": p["provider_order_id"], "razorpay_payment_id": pay["id"], "razorpay_signature": sig})
    from sqlalchemy import select
    from app.models import PaymentEvent
    with pc.app.state.session_factory() as db:
        blob = json.dumps([[e.message, e.data] for e in db.scalars(select(PaymentEvent))])
    assert sig not in blob and not any(s in blob for s in SECRETS)


# ---- nothing is trusted from the browser ---------------------------------------------------------------------------------------------------
def test_a_browser_claim_of_success_cannot_mark_anything_paid(pc, fake_rzp):
    """There is no endpoint that accepts 'paid' from the browser; the only ways in are a signature plus Razorpay's own record, a signed webhook, or a person."""
    o = new_order(pc)
    p = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"}).json()
    for body in ({"status": "paid"}, {"paid": True}, {"razorpay_payment_id": "pay_x"}, {"success": True, "razorpay_order_id": p["provider_order_id"]}):
        for path in (f"/api/payments/{p['id']}", f"/api/payments/{p['id']}/razorpay/verify", f"/api/payments/{p['id']}/refresh"):
            pc.post(path, json=body)
            pc.put(path, json=body)
            pc.patch(path, json=body)
    assert pc.get(f"/api/payments/{p['id']}").json()["status"] == "pending"
    assert pc.post(f"/api/payments/{p['id']}/razorpay/verify", json={"razorpay_order_id": p["provider_order_id"], "razorpay_payment_id": "pay_NOTREAL0001",
                                                                       "razorpay_signature": checkout_sig(p["provider_order_id"], "pay_NOTREAL0001")}).json()["status"] == "pending"


def test_a_genuinely_signed_payment_that_razorpay_does_not_know_is_not_marked_paid(pc, fake_rzp):
    """Even a correct signature is not enough: Razorpay is asked, and an unknown payment id answers with an error."""
    o = new_order(pc)
    p = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay"}).json()
    r = pc.post(f"/api/payments/{p['id']}/razorpay/verify", json={"razorpay_order_id": p["provider_order_id"], "razorpay_payment_id": "pay_NOTREAL0001",
                                                                   "razorpay_signature": checkout_sig(p["provider_order_id"], "pay_NOTREAL0001")})
    assert r.status_code == 200 and r.json()["status"] == "pending" and "notice" in r.json()


def test_a_signature_for_one_payment_cannot_be_replayed_to_mark_another_paid(pc, fake_rzp):
    o1, o2 = new_order(pc), new_order(pc, "1 litre doodh")
    p1 = pc.post(f"/api/orders/{o1['id']}/payments", json={"method": "razorpay"}).json()
    p2 = pc.post(f"/api/orders/{o2['id']}/payments", json={"method": "razorpay"}).json()
    pay1 = fake_rzp.new_payment(p1["provider_order_id"])
    ok = pc.post(f"/api/payments/{p1['id']}/razorpay/verify", json={"razorpay_order_id": p1["provider_order_id"], "razorpay_payment_id": pay1["id"],
                                                                      "razorpay_signature": checkout_sig(p1["provider_order_id"], pay1["id"])})
    assert ok.json()["status"] == "paid"
    replay = pc.post(f"/api/payments/{p2['id']}/razorpay/verify", json={"razorpay_order_id": p1["provider_order_id"], "razorpay_payment_id": pay1["id"],
                                                                          "razorpay_signature": checkout_sig(p1["provider_order_id"], pay1["id"])})
    assert replay.status_code == 400 and pc.get(f"/api/payments/{p2['id']}").json()["status"] == "pending"


def test_a_captured_event_replayed_against_a_different_order_is_ignored(pc, fake_rzp):
    o1, o2 = new_order(pc), new_order(pc, "1 litre doodh")
    p1 = pc.post(f"/api/orders/{o1['id']}/payments", json={"method": "razorpay"}).json()
    p2 = pc.post(f"/api/orders/{o2['id']}/payments", json={"method": "razorpay"}).json()
    pay = fake_rzp.new_payment(p1["provider_order_id"])
    raw = event("payment.captured", payment=pay)
    pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw, "evt_x"))
    assert pc.get(f"/api/payments/{p1['id']}").json()["status"] == "paid" and pc.get(f"/api/payments/{p2['id']}").json()["status"] == "pending"
    # the same payment id reported for the second order's provider order id: it is already attached to payment 1
    clash = dict(pay, order_id=p2["provider_order_id"], amount=o2["total_paise"])
    raw2 = event("payment.captured", payment=clash)
    r = pc.post(WEBHOOK, content=raw2, headers=webhook_headers(raw2, "evt_y"))
    assert r.status_code == 200 and r.json()["result"] == "duplicate"
    assert pc.get(f"/api/payments/{p2['id']}").json()["status"] == "pending"


def test_every_amount_checked_comes_from_the_server_side_order_total(pc, fake_rzp):
    o = new_order(pc)
    p = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "razorpay", "amount_paise": 1}).json()
    assert p["amount_paise"] == o["total_paise"] == fake_rzp.orders[p["provider_order_id"]]["amount"]
    underpaid = fake_rzp.new_payment(p["provider_order_id"], amount=1)
    raw = event("payment.captured", payment=underpaid)
    assert pc.post(WEBHOOK, content=raw, headers=webhook_headers(raw, "e1")).json()["result"] == "amount_mismatch"
    assert pc.get(f"/api/payments/{p['id']}").json()["status"] == "pending"


# ---- permissions on the open webhook route ---------------------------------------------------------------------------------------------------
def test_the_webhook_is_the_only_payment_route_without_a_session_and_it_needs_the_signature(make_pay_app):
    with TestClient(make_pay_app()) as c:
        paths = c.get("/openapi.json").json()["paths"]
        for path, methods in paths.items():
            if "payment" in path or "refund" in path or "invoice" in path:
                for m in methods:
                    r = getattr(c, m)(path.replace("{payment_id}", "1").replace("{order_id}", "1").replace("{refund_id}", "1"), **({"json": {}} if m != "get" else {}))
                    if path == "/api/payments/webhooks/razorpay":
                        assert r.status_code == 400, (m, path)                  # reachable, but refused without a valid signature
                    else:
                        assert r.status_code == 401, (m, path, r.status_code)


# ---- live mode and the browser's permissions --------------------------------------------------------------------------------------------
def test_live_mode_never_turns_on_by_itself(make_pay_app, tmp_path):
    for i, kw in enumerate(({}, {"razorpay_key_id": "rzp_live_PLACEHOLDER01"})):
        with TestClient(make_pay_app(database_url=f"sqlite:///{tmp_path / f'm{i}.db'}", **kw)) as c:
            from .helpers import register
            register(c, OWNER)
            cfg = c.get("/api/payments/config").json()
            assert cfg["mode"] == "test"
            assert cfg["razorpay"]["enabled"] is bool(not kw)                   # live keys while the mode is test: refused, not silently used


def test_content_security_policy_allows_razorpay_only_when_razorpay_is_on():
    off, on = csp("localhost:8000"), csp("localhost:8000", razorpay=True)
    assert "razorpay" not in off and "frame-src" not in off and "script-src 'self'" in off
    assert "script-src 'self' https://checkout.razorpay.com" in on and "frame-src https://api.razorpay.com https://checkout.razorpay.com" in on
    assert "https://lumberjack.razorpay.com" in on and "default-src 'self'" in on and "object-src 'none'" in on and "frame-ancestors 'none'" in on
    assert "'unsafe-inline'" not in on.split("script-src")[1].split(";")[0] and "unsafe-eval" not in on


def test_response_headers_follow_whether_razorpay_is_on(make_pay_app):
    with TestClient(make_pay_app()) as on, TestClient(make_pay_app(razorpay_key_id="", razorpay_key_secret=None)) as off:
        a, b = on.get("/api/health"), off.get("/api/health")
        assert "checkout.razorpay.com" in a.headers["permissions-policy"] and "payment=()" in b.headers["permissions-policy"]
        assert a.headers["cross-origin-opener-policy"] == "same-origin-allow-popups" and b.headers["cross-origin-opener-policy"] == "same-origin"
        assert "microphone=(self)" in a.headers["permissions-policy"] and "camera=()" in a.headers["permissions-policy"]


def test_payment_responses_are_not_cached(pc):
    o = new_order(pc)
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"})
    assert r.headers["cache-control"] == "no-store" and pc.get("/api/payments").headers["cache-control"] == "no-store"


def test_a_payment_request_from_another_website_is_refused(pc):
    o = new_order(pc)
    r = pc.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "BAD_ORIGIN"


def test_the_gnani_settings_are_untouched_by_the_payment_module(pc):
    s = pc.app.state.settings
    assert s.gnani_base_url == "https://api.vachana.ai" and s.gnani_tts_model == "timbre-v2.5"
    cfg = pc.get("/api/settings").json()
    assert "gnani" in cfg and cfg["gnani"]["configured"] is False and "payments" in cfg
    assert not any(k.startswith("razorpay") for k in cfg["gnani"])
