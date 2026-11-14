"""Payments API: cash, UPI and Razorpay for an existing order, history, refunds, invoices and payment analytics.

Who may do what:
  * Owner and staff: start a payment, record cash, confirm a manual UPI payment, check a payment's status, cancel a payment that is still waiting,
    read the history and a payment's detail, open an invoice.
  * Owner only: refunds, payment analytics, and the UPI ID in Settings.
  * Nobody signed in: only the Razorpay webhook, and it is accepted only with a valid signature over the raw body.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import Principal, require_owner, require_user
from ..deps import get_db
from ..security import rate_limit
from ..services import payments as svc
from ..services.payments import PaymentError

router = APIRouter(prefix="/api", tags=["payments"])
webhooks = APIRouter(prefix="/api/payments/webhooks", tags=["payments"])
WEBHOOK_MAX_BYTES = 256 * 1024


async def payment_error_handler(_request: Request, exc: PaymentError) -> JSONResponse:
    return JSONResponse({"detail": {"code": exc.code, "message": exc.message, **exc.extra}}, status_code=exc.status)


def _rp(request: Request):
    return request.app.state.razorpay


def _settings(request: Request):
    return request.app.state.settings


def _ist_start(day: Optional[date]) -> Optional[datetime]:
    """Midnight India time at the start of ``day``, as the naive UTC the database uses."""
    return datetime(day.year, day.month, day.day) - svc.IST if day else None


def _reply(db: Session, request: Request, p, **extra) -> dict:
    out = svc.payment_detail(db, _settings(request), p)
    if p.method == "razorpay" and p.status == "pending":
        out["checkout"] = svc.checkout_params(_settings(request), p)
    out.update({k: v for k, v in extra.items() if v})
    return out


# ---- bodies ---------------------------------------------------------------------------------------------------------------------------
class CreatePaymentIn(BaseModel):
    method: str = Field(max_length=12)
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


class CashIn(BaseModel):
    received_paise: int = Field(ge=1, le=100_000_000)


class UpiConfirmIn(BaseModel):
    reference: str = Field(min_length=1, max_length=60)


class VerifyIn(BaseModel):
    razorpay_order_id: str = Field(min_length=1, max_length=64)
    razorpay_payment_id: str = Field(min_length=1, max_length=64)
    razorpay_signature: str = Field(min_length=1, max_length=128)


class CancelIn(BaseModel):
    reason: str = Field(default="", max_length=120)


class RefundIn(BaseModel):
    amount_paise: Optional[int] = Field(default=None, ge=1, le=100_000_000)
    reason: str = Field(min_length=1, max_length=200)
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


# ---- configuration --------------------------------------------------------------------------------------------------------------------
@router.get("/payments/config")
def payments_config(request: Request, p: Principal = Depends(require_user)):
    """Which ways of paying are available right now. Owners also see whether the secrets are set (never their values) and the webhook address."""
    return svc.public_config(_settings(request), owner=p.user.role == "owner")


# ---- history --------------------------------------------------------------------------------------------------------------------------
@router.get("/payments")
def list_payments(request: Request, status: Optional[str] = None, method: Optional[str] = None, q: str = "", since: Optional[date] = None, until: Optional[date] = None,
                  include_synthetic: bool = True, attention: bool = False, sort: str = "newest", limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db), _p: Principal = Depends(require_user)):
    """Payments, newest first. ``since`` and ``until`` are India dates (inclusive). The counts per status honour every filter except status."""
    return svc.list_payments(db, _settings(request), q=q, status=status, method=method, since=_ist_start(since),
                             until=_ist_start(until + timedelta(days=1)) if until else None, include_synthetic=include_synthetic, attention=attention,
                             sort=sort, limit=limit, offset=offset)


@router.get("/payments/analytics", dependencies=[Depends(require_owner)])
def payment_analytics(days: int = Query(30, ge=1, le=366), include_synthetic: bool = True, db: Session = Depends(get_db)):
    """Owner only. Every figure is summed from the payments and refunds tables; a period with no payments shows zero."""
    return svc.analytics(db, days=days, include_synthetic=include_synthetic)


@router.get("/payments/{payment_id}")
def get_payment(payment_id: int, request: Request, db: Session = Depends(get_db), _p: Principal = Depends(require_user)):
    return _reply(db, request, svc.get_payment(db, payment_id))


@router.get("/orders/{order_id}/payments")
def order_payments(order_id: int, request: Request, db: Session = Depends(get_db), _p: Principal = Depends(require_user)):
    order = svc.get_order(db, order_id)
    rows = svc.order_payments(db, order.id)
    names = svc.user_names(db, {x for p in rows for x in (p.created_by_id, p.confirmed_by_id)})
    return {"order_id": order.id, "order_code": order.code, "total_paise": order.total_paise, "summary": svc.payment_summaries(db, [order.id])[order.id],
            "items": [svc.serialize_payment(p, names, _settings(request)) for p in rows]}


# ---- starting and finishing a payment -------------------------------------------------------------------------------------------------
@router.post("/orders/{order_id}/payments", status_code=201, dependencies=[Depends(rate_limit)])
def start_payment(order_id: int, body: CreatePaymentIn, request: Request, response: Response, db: Session = Depends(get_db), p: Principal = Depends(require_user)):
    """Start a payment for the order's server-side total. Sending the same ``idempotency_key`` again, or asking again while a payment of the same kind
    is still open, returns that payment (HTTP 200) instead of starting a second one."""
    order = svc.get_order(db, order_id)
    pay, created = svc.create_payment(db, _settings(request), _rp(request), order, body.method, p.user, body.idempotency_key)
    if not created:
        response.status_code = 200
    return _reply(db, request, pay)


@router.post("/payments/{payment_id}/cash", dependencies=[Depends(rate_limit)])
def record_cash(payment_id: int, body: CashIn, request: Request, db: Session = Depends(get_db), p: Principal = Depends(require_user)):
    pay = svc.confirm_cash(db, svc.get_payment(db, payment_id), body.received_paise, p.user)
    return _reply(db, request, pay)


@router.post("/payments/{payment_id}/confirm-upi", dependencies=[Depends(rate_limit)])
def confirm_upi(payment_id: int, body: UpiConfirmIn, request: Request, db: Session = Depends(get_db), p: Principal = Depends(require_user)):
    """A person confirms a manual UPI payment after checking their bank or UPI app. It stays labelled as not verified by a payment provider."""
    pay = svc.confirm_manual_upi(db, svc.get_payment(db, payment_id), body.reference, p.user)
    return _reply(db, request, pay)


@router.post("/payments/{payment_id}/razorpay/verify", dependencies=[Depends(rate_limit)])
def verify_razorpay(payment_id: int, body: VerifyIn, request: Request, db: Session = Depends(get_db), p: Principal = Depends(require_user)):
    """The browser reports what Checkout returned. This does not trust it: the signature is checked with the key secret and Razorpay is then asked about the
    payment before anything is marked paid."""
    pay, notice = svc.verify_checkout(db, _settings(request), _rp(request), svc.get_payment(db, payment_id), body.razorpay_order_id, body.razorpay_payment_id,
                                      body.razorpay_signature, p.user)
    return _reply(db, request, pay, notice=notice)


@router.post("/payments/{payment_id}/refresh", dependencies=[Depends(rate_limit)])
def refresh_payment(payment_id: int, request: Request, db: Session = Depends(get_db), p: Principal = Depends(require_user)):
    """Ask Razorpay where a waiting payment stands. A shop whose computer cannot receive webhooks finds out this way."""
    pay, notice = svc.refresh_payment(db, _settings(request), _rp(request), svc.get_payment(db, payment_id), p.user)
    return _reply(db, request, pay, notice=notice)


@router.post("/payments/{payment_id}/cancel", dependencies=[Depends(rate_limit)])
def cancel_payment(payment_id: int, request: Request, body: CancelIn = CancelIn(), db: Session = Depends(get_db), p: Principal = Depends(require_user)):
    pay = svc.cancel_payment(db, _rp(request), svc.get_payment(db, payment_id), p.user, body.reason)
    return _reply(db, request, pay)


# ---- refunds (owner only) -------------------------------------------------------------------------------------------------------------
@router.post("/payments/{payment_id}/refunds", status_code=201, dependencies=[Depends(rate_limit)])
def start_refund(payment_id: int, body: RefundIn, request: Request, response: Response, db: Session = Depends(get_db), p: Principal = Depends(require_owner)):
    """Owner only. A Razorpay payment is refunded through Razorpay and stays 'waiting' until Razorpay confirms; a cash or manual UPI payment is recorded as
    refunded by the owner and labelled as not confirmed by a provider. Leave ``amount_paise`` out to refund what is left."""
    pay = svc.get_payment(db, payment_id)
    refund, created = svc.create_refund(db, _settings(request), _rp(request), pay, body.amount_paise, body.reason, p.user, body.idempotency_key)
    if not created:
        response.status_code = 200
    db.refresh(pay)
    return {**svc.serialize_refund(refund, svc.user_names(db, {refund.initiated_by_id})), "payment": svc.serialize_payment(pay, svc.user_names(db, {pay.created_by_id, pay.confirmed_by_id}), _settings(request))}


@router.post("/refunds/{refund_id}/refresh", dependencies=[Depends(rate_limit)])
def refresh_refund(refund_id: int, request: Request, db: Session = Depends(get_db), p: Principal = Depends(require_owner)):
    from ..models import Refund
    r = db.get(Refund, refund_id)
    if r is None:
        raise PaymentError(404, "REFUND_NOT_FOUND", "Refund not found.")
    r, notice = svc.refresh_refund(db, _rp(request), r, p.user)
    return {**svc.serialize_refund(r, svc.user_names(db, {r.initiated_by_id})), "notice": notice or None}


# ---- invoices -------------------------------------------------------------------------------------------------------------------------
@router.get("/orders/{order_id}/invoice")
def get_invoice(order_id: int, request: Request, db: Session = Depends(get_db), p: Principal = Depends(require_user)):
    """The invoice for an order. The first time it is opened it is given the next number; after that it always returns the same one."""
    order = svc.get_order(db, order_id)
    inv = svc.get_or_create_invoice(db, _settings(request), order, p.user)
    return svc.serialize_invoice(db, _settings(request), order, inv)


# ---- the Razorpay webhook (no session: the signature is the credential) -------------------------------------------------------------------
@webhooks.post("/razorpay", include_in_schema=True)
async def razorpay_webhook(request: Request):
    """Razorpay calls this with a signed event. The signature is checked over the exact bytes received before anything is read. Answers 200 for an event it
    has already handled (so Razorpay stops retrying), 400 for a bad signature."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > WEBHOOK_MAX_BYTES:
        raise PaymentError(413, "PAYLOAD_TOO_LARGE", "The webhook body is too large.")
    raw = await request.body()
    if len(raw) > WEBHOOK_MAX_BYTES:
        raise PaymentError(413, "PAYLOAD_TOO_LARGE", "The webhook body is too large.")
    sig, event_id = request.headers.get("x-razorpay-signature"), request.headers.get("x-razorpay-event-id")

    def work() -> dict:  # database and (for a capture) a call to Razorpay: kept off the event loop
        with request.app.state.session_factory() as db:
            return svc.handle_webhook(db, _settings(request), _rp(request), raw, sig, event_id)

    return await run_in_threadpool(work)
