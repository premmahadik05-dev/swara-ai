"""Razorpay REST client and signature checks. No Razorpay SDK: plain httpx (already a dependency), so nothing new to install.

Rules this module keeps:
  * The key secret and the webhook secret are read from the settings, used to sign or authenticate, and never put in a log line,
    an error message, a response or an exception text.
  * Every call has a time limit. A request that was SENT and got no answer is reported as ``outcome_unknown`` and is never repeated here:
    the caller decides (a refund, for instance, is looked up again, not sent twice).
  * Provider error text is shortened and passed on so the owner can read it; request bodies are never logged.

Endpoints used (Razorpay API v1): POST /v1/orders, GET /v1/payments/{id}, POST /v1/payments/{id}/capture, POST /v1/payments/{id}/refund,
GET /v1/refunds/{id}, GET /v1/payments/{id}/refunds, POST /v1/payments/qr_codes, GET /v1/payments/qr_codes/{id}, GET /v1/payments/qr_codes/{id}/payments.
Only the test-mode behaviour of these shapes is relevant to this release, and none of it could be exercised against Razorpay itself from the
build environment: the tests use a mock transport (see docs/PAYMENT_TESTING.md).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Optional

import httpx

from ..config import Settings

log = logging.getLogger("swara.razorpay")


class RazorpayError(Exception):
    """A failed or unanswered Razorpay call. ``code`` is stable and safe to show; ``message`` is for the owner; the secret is never in either."""

    def __init__(self, code: str, message: str, *, status: Optional[int] = None, outcome_unknown: bool = False, provider_code: str = ""):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.outcome_unknown = outcome_unknown  # the request may have reached Razorpay: do not assume it did not happen
        self.provider_code = provider_code


# ---- signatures ----------------------------------------------------------------------------------------------------------------------
def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def checkout_signature(secret: str, provider_order_id: str, provider_payment_id: str) -> str:
    """What Razorpay signs after a Checkout payment: HMAC-SHA256 of "order_id|payment_id" with the key secret, as hex."""
    return _hmac_hex(secret, f"{provider_order_id}|{provider_payment_id}".encode("utf-8"))


def _same(a: Any, b: str) -> bool:
    return isinstance(a, str) and hmac.compare_digest(a.strip().lower().encode("utf-8"), b.lower().encode("utf-8"))


def verify_checkout_signature(secret: str, provider_order_id: str, provider_payment_id: str, signature: Any) -> bool:
    """Constant-time check of the signature the browser handed back. The order id must be the one STORED on the server, never one the browser sent."""
    if not secret or not provider_order_id or not provider_payment_id:
        return False
    return _same(signature, checkout_signature(secret, provider_order_id, provider_payment_id))


def verify_webhook_signature(secret: Optional[str], raw_body: bytes, signature: Any) -> bool:
    """Constant-time check of X-Razorpay-Signature: HMAC-SHA256 of the RAW request body with the webhook secret, as hex. False when no secret is set."""
    if not secret or not raw_body:
        return False
    return _same(signature, _hmac_hex(secret, raw_body))


# ---- client --------------------------------------------------------------------------------------------------------------------------
def _short(text: Any, n: int = 200) -> str:
    return " ".join(str(text or "").split())[:n]


class RazorpayClient:
    def __init__(self, settings: Settings, transport: Optional[httpx.BaseTransport] = None):
        self.settings = settings
        self._transport = transport  # tests pass httpx.MockTransport; production leaves it None

    @property
    def enabled(self) -> bool:
        return self.settings.razorpay_enabled

    def _call(self, method: str, path: str, *, json: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        s = self.settings
        if not s.razorpay_enabled:
            raise RazorpayError("NOT_CONFIGURED", s.razorpay_problem or "Razorpay is not set up.")
        timeout = httpx.Timeout(s.razorpay_timeout_s, connect=5.0)
        try:
            with httpx.Client(base_url=s.razorpay_base_url.rstrip("/"), auth=(s.razorpay_key_id.strip(), (s.razorpay_secret or "").strip()),
                              timeout=timeout, transport=self._transport, headers={"User-Agent": "swara-ai/2.7"}) as client:
                res = client.request(method, path, json=json, params=params)
        except httpx.ConnectError as exc:  # never reached Razorpay: safe to try again
            raise RazorpayError("NETWORK", "Could not reach Razorpay. Check the internet connection and try again.") from exc
        except httpx.ConnectTimeout as exc:
            raise RazorpayError("NETWORK", "Could not reach Razorpay. Check the internet connection and try again.") from exc
        except httpx.TimeoutException as exc:  # sent, no answer: it may have happened
            raise RazorpayError("TIMEOUT", "Razorpay did not answer in time. Nothing is assumed: check the payment again in a moment.", outcome_unknown=True) from exc
        except httpx.HTTPError as exc:
            raise RazorpayError("NETWORK", "The connection to Razorpay failed. Try again.", outcome_unknown=True) from exc
        try:
            body = res.json()
        except ValueError:
            body = {}
        if res.status_code >= 400:
            err = body.get("error") if isinstance(body, dict) else None
            err = err if isinstance(err, dict) else {}
            desc, pcode = _short(err.get("description")) or f"Razorpay answered HTTP {res.status_code}.", _short(err.get("code"), 48)
            if res.status_code == 401:
                raise RazorpayError("AUTH_FAILED", "Razorpay refused the key. Check RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env.", status=401, provider_code=pcode)
            if res.status_code == 429:
                raise RazorpayError("RATE_LIMITED", "Razorpay is asking us to slow down. Try again in a minute.", status=429, provider_code=pcode)
            if res.status_code >= 500:
                raise RazorpayError("PROVIDER_ERROR", "Razorpay had a problem on its side. Try again shortly.", status=res.status_code, outcome_unknown=True, provider_code=pcode)
            raise RazorpayError("REJECTED", desc, status=res.status_code, provider_code=pcode)
        if not isinstance(body, dict):
            raise RazorpayError("PROVIDER_ERROR", "Razorpay sent a reply this app cannot read.", status=res.status_code, outcome_unknown=True)
        return body

    # -- orders and payments
    def create_order(self, amount_paise: int, receipt: str, notes: dict[str, str]) -> dict:
        return self._call("POST", "/v1/orders", json={"amount": int(amount_paise), "currency": "INR", "receipt": receipt[:40], "notes": notes})

    def fetch_payment(self, payment_id: str) -> dict:
        return self._call("GET", f"/v1/payments/{payment_id}")

    def fetch_order_payments(self, order_id: str) -> dict:
        return self._call("GET", f"/v1/orders/{order_id}/payments")

    def capture_payment(self, payment_id: str, amount_paise: int) -> dict:
        return self._call("POST", f"/v1/payments/{payment_id}/capture", json={"amount": int(amount_paise), "currency": "INR"})

    # -- refunds
    def create_refund(self, payment_id: str, amount_paise: int, receipt: str, notes: dict[str, str]) -> dict:
        return self._call("POST", f"/v1/payments/{payment_id}/refund", json={"amount": int(amount_paise), "receipt": receipt[:40], "notes": notes})

    def fetch_refund(self, refund_id: str) -> dict:
        return self._call("GET", f"/v1/refunds/{refund_id}")

    def fetch_payment_refunds(self, payment_id: str) -> dict:
        return self._call("GET", f"/v1/payments/{payment_id}/refunds")

    # -- dynamic UPI QR (needs to be switched on for the account by Razorpay)
    def create_upi_qr(self, amount_paise: int, name: str, description: str, close_by: int, notes: dict[str, str]) -> dict:
        return self._call("POST", "/v1/payments/qr_codes", json={
            "type": "upi_qr", "name": name[:40], "usage": "single_use", "fixed_amount": True, "payment_amount": int(amount_paise),
            "description": description[:120], "close_by": int(close_by), "notes": notes})

    def fetch_qr(self, qr_id: str) -> dict:
        return self._call("GET", f"/v1/payments/qr_codes/{qr_id}")

    def fetch_qr_payments(self, qr_id: str) -> dict:
        return self._call("GET", f"/v1/payments/qr_codes/{qr_id}/payments")

    def close_qr(self, qr_id: str) -> dict:
        return self._call("POST", f"/v1/payments/qr_codes/{qr_id}/close")
