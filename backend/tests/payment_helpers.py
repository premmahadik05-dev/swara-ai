"""A stand-in for Razorpay used by the payment tests.

Nothing here talks to Razorpay. FakeRazorpay is an httpx.MockTransport handler that answers the handful of REST calls the app makes, from state the test
controls. It proves the app builds the right requests and reacts correctly to the answers. It does NOT prove that Razorpay's real servers answer
this way: see docs/PAYMENT_TESTING.md for what remains unverified.

The keys below are made-up placeholders that satisfy the app's format checks (rzp_test_ prefix). They are not Razorpay credentials.
"""
from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import re
from typing import Any, Optional

import httpx

KEY_ID = "rzp_test_PLACEHOLDER01"
KEY_SECRET = "placeholder_key_secret_for_tests_only"
WEBHOOK_SECRET = "placeholder_webhook_secret_for_tests_only"
SECRETS = (KEY_SECRET, WEBHOOK_SECRET)


def hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def checkout_sig(order_id: str, payment_id: str, secret: str = KEY_SECRET) -> str:
    """What Razorpay Checkout returns: HMAC-SHA256 of 'order_id|payment_id' with the key secret (written out here on purpose, not imported from the app)."""
    return hmac_hex(secret, f"{order_id}|{payment_id}".encode())


def webhook_headers(raw: bytes, event_id: Optional[str] = None, secret: str = WEBHOOK_SECRET) -> dict:
    h = {"X-Razorpay-Signature": hmac_hex(secret, raw), "Content-Type": "application/json"}
    if event_id:
        h["X-Razorpay-Event-Id"] = event_id
    return h


class FakeRazorpay:
    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.payments: dict[str, dict] = {}
        self.refunds: dict[str, dict] = {}
        self.qrs: dict[str, dict] = {}
        self.calls: list[tuple[str, str, Any]] = []
        self.fail_next: Optional[Any] = None  # an httpx exception to raise, or (status, body) to answer with
        self.order_amount_delta = 0           # make /v1/orders answer with a different amount (a lying provider)
        self.qr_amount_delta = 0
        self.refund_status_on_create = "pending"
        self.auth_seen: list[tuple[str, str]] = []
        self._n = itertools.count(1)
        self.transport = httpx.MockTransport(self._handle)

    # -- helpers for tests
    def new_payment(self, provider_order_id: Optional[str], *, status: str = "captured", amount: Optional[int] = None, method: str = "upi", **extra) -> dict:
        n = next(self._n)
        order = self.orders.get(provider_order_id or "")
        pay = {"id": f"pay_TEST{n:06d}", "entity": "payment", "order_id": provider_order_id, "amount": amount if amount is not None else (order or {}).get("amount", 0),
               "currency": "INR", "status": status, "method": method, "captured": status == "captured", **extra}
        self.payments[pay["id"]] = pay
        return pay

    def new_qr_payment(self, qr_id: str, *, status: str = "captured", amount: Optional[int] = None) -> dict:
        qr = self.qrs[qr_id]
        pay = self.new_payment(None, status=status, amount=amount if amount is not None else qr["payment_amount"], method="upi")
        pay["qr_code_id"] = qr_id
        return pay

    def paths(self, method: str) -> list[str]:
        return [p for m, p, _ in self.calls if m == method]

    def count(self, method: str, pattern: str) -> int:
        return sum(1 for m, p, _ in self.calls if m == method and re.search(pattern, p))

    # -- the fake server
    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        auth = request.headers.get("authorization", "")
        import base64
        try:
            user, _, pw = base64.b64decode(auth.split(" ", 1)[1]).decode().partition(":")
        except Exception:
            user = pw = ""
        self.auth_seen.append((user, pw))
        if user != KEY_ID or pw != KEY_SECRET:
            return httpx.Response(401, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Authentication failed"}})
        if self.fail_next is not None:
            f, self.fail_next = self.fail_next, None
            if isinstance(f, Exception):
                raise f
            return httpx.Response(f[0], json=f[1])
        path, m = request.url.path, request.method

        if m == "POST" and path == "/v1/orders":
            n = next(self._n)
            o = {"id": f"order_TEST{n:06d}", "entity": "order", "amount": body["amount"] + self.order_amount_delta, "currency": body["currency"], "receipt": body["receipt"],
                 "status": "created", "notes": body.get("notes", {})}
            self.orders[o["id"]] = o
            return httpx.Response(200, json=o)
        if m == "GET" and (mt := re.fullmatch(r"/v1/orders/([^/]+)/payments", path)):
            return httpx.Response(200, json={"entity": "collection", "items": [p for p in self.payments.values() if p.get("order_id") == mt.group(1)]})
        if m == "GET" and (mt := re.fullmatch(r"/v1/payments/(pay_[^/]+)", path)):
            p = self.payments.get(mt.group(1))
            return httpx.Response(200, json=p) if p else httpx.Response(400, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}})
        if m == "POST" and (mt := re.fullmatch(r"/v1/payments/(pay_[^/]+)/capture", path)):
            p = self.payments.get(mt.group(1))
            if not p or p["status"] != "authorized":
                return httpx.Response(400, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "This payment has already been captured"}})
            p["status"], p["captured"] = "captured", True
            return httpx.Response(200, json=p)
        if m == "POST" and (mt := re.fullmatch(r"/v1/payments/(pay_[^/]+)/refund", path)):
            p = self.payments.get(mt.group(1))
            if not p:
                return httpx.Response(400, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}})
            n = next(self._n)
            r = {"id": f"rfnd_TEST{n:06d}", "entity": "refund", "payment_id": p["id"], "amount": body["amount"], "currency": "INR", "receipt": body.get("receipt"),
                 "status": self.refund_status_on_create, "speed_processed": "normal" if self.refund_status_on_create == "processed" else None}
            self.refunds[r["id"]] = r
            return httpx.Response(200, json=r)
        if m == "GET" and (mt := re.fullmatch(r"/v1/refunds/(rfnd_[^/]+)", path)):
            r = self.refunds.get(mt.group(1))
            return httpx.Response(200, json=r) if r else httpx.Response(400, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}})
        if m == "GET" and (mt := re.fullmatch(r"/v1/payments/(pay_[^/]+)/refunds", path)):
            return httpx.Response(200, json={"entity": "collection", "items": [r for r in self.refunds.values() if r["payment_id"] == mt.group(1)]})
        if m == "POST" and path == "/v1/payments/qr_codes":
            n = next(self._n)
            q = {"id": f"qr_TEST{n:06d}", "entity": "qr_code", "type": "upi_qr", "usage": "single_use", "fixed_amount": True,
                 "payment_amount": body["payment_amount"] + self.qr_amount_delta, "status": "active", "image_url": f"https://rzp.io/i/TEST{n:06d}", "notes": body.get("notes", {})}
            self.qrs[q["id"]] = q
            return httpx.Response(200, json=q)
        if m == "GET" and (mt := re.fullmatch(r"/v1/payments/qr_codes/(qr_[^/]+)/payments", path)):
            return httpx.Response(200, json={"entity": "collection", "items": [p for p in self.payments.values() if p.get("qr_code_id") == mt.group(1)]})
        if m == "POST" and (mt := re.fullmatch(r"/v1/payments/qr_codes/(qr_[^/]+)/close", path)):
            q = self.qrs.get(mt.group(1))
            if q:
                q["status"] = "closed"
            return httpx.Response(200, json=q or {})
        return httpx.Response(404, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "The requested URL was not found on the server"}})


def event(name: str, *, payment: Optional[dict] = None, refund: Optional[dict] = None, qr: Optional[dict] = None, order: Optional[dict] = None) -> bytes:
    payload: dict[str, Any] = {}
    if payment is not None:
        payload["payment"] = {"entity": payment}
    if refund is not None:
        payload["refund"] = {"entity": refund}
    if qr is not None:
        payload["qr_code"] = {"entity": qr}
    if order is not None:
        payload["order"] = {"entity": order}
    return json.dumps({"entity": "event", "account_id": "acc_TEST", "event": name, "contains": list(payload), "payload": payload, "created_at": 1700000000}).encode()


def new_order(c, text: str = "2 kilo chawal") -> dict:
    """A real confirmed order made through the same typed-order endpoints the shop uses (so payment tests also exercise the existing order path)."""
    sid = c.post("/api/text/turn", json={"text": text}).json()["session_id"]
    c.post("/api/text/turn", json={"text": "bas itna hi", "session_id": sid})
    order = c.post(f"/api/sessions/{sid}/confirm").json()["order"]
    assert order and order["total_paise"] > 0, order
    return order


def as_owner(c) -> None:
    from .helpers import OWNER, login
    assert login(c, OWNER).status_code == 200


def as_staff(c) -> None:
    from .helpers import STAFF, login
    assert login(c, STAFF).status_code == 200
