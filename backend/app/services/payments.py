"""Payment rules: cash, UPI and Razorpay, refunds, invoices and payment analytics.

How the pieces fit together
  * A payment belongs to one order and never changes the order: confirming an order, taking stock off the shelf and cancelling an order all work
    exactly as before, with or without a payment. Retrying a payment cannot take stock off twice because payments never touch stock.
  * The amount due is the ORDER TOTAL ON THE SERVER at the moment the payment starts. Nothing the browser sends can change it.
  * "Paid" is only ever set by (a) a person recording cash, (b) a person confirming a manual UPI payment, which stays labelled as not verified
    by a provider, or (c) Razorpay itself: a correct checkout signature followed by a lookup of the payment at Razorpay, a signed webhook, or a
    lookup of the payment at Razorpay. A message from the browser saying "paid" is not an input to anything here.
  * Every change is written to payment_events (ids, amounts and statuses, never card numbers or UPI IDs or PINs).
  * Duplicates are stopped by the database (unique idempotency keys, one pending payment per order, unique provider ids, unique webhook
    event ids) and by checks here; a repeated delivery is acknowledged and changes nothing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import PAID_STATUSES, Customer, Invoice, Order, Payment, PaymentEvent, Refund, User, utcnow
from .razorpay import RazorpayClient, RazorpayError, verify_checkout_signature, verify_webhook_signature

log = logging.getLogger("swara.payments")
IST = timedelta(hours=5, minutes=30)
METHODS = ("cash", "upi", "razorpay")
VPA_RE = re.compile(r"^[A-Za-z0-9._\-]{2,64}@[A-Za-z][A-Za-z0-9]{1,31}$")
REFERENCE_RE = re.compile(r"^[A-Za-z0-9\-_/ ]{4,40}$")
QR_MINUTES = 15  # a Razorpay dynamic QR stays valid this long (Razorpay allows 2 minutes to 2 hours)


class PaymentError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def rupees_text(paise: int) -> str:
    return f"{paise / 100:,.2f}"


# ---- audit trail ----------------------------------------------------------------------------------------------------------------------
_SAFE_KEYS = {"event", "amount", "currency", "status", "order_id", "payment_id", "refund_id", "qr_id", "method", "error_code", "error_description",
              "captured", "refund_status", "amount_refunded", "receipt", "speed_processed", "received_paise", "change_paise", "reference", "reason",
              "provider_status", "note", "refund", "kind"}


def clean_data(data: Optional[dict]) -> dict:
    """Only whitelisted, scalar fields survive: a webhook body also carries e-mail, phone, UPI IDs and card fragments, and none of that is kept."""
    out: dict[str, Any] = {}
    for k, v in (data or {}).items():
        if k in _SAFE_KEYS and isinstance(v, (str, int, float, bool)) or (k in _SAFE_KEYS and v is None):
            out[k] = v[:160] if isinstance(v, str) else v
    return out


def record(db: Session, payment: Optional[Payment], source: str, event_type: str, message: str, *, before: Optional[str] = None, after: Optional[str] = None,
           event_id: Optional[str] = None, signature_ok: Optional[bool] = None, actor: Optional[User] = None, data: Optional[dict] = None) -> PaymentEvent:
    ev = PaymentEvent(payment_id=payment.id if payment is not None else None, source=source, event_id=event_id, event_type=event_type[:48],
                      status_before=before, status_after=after, signature_ok=signature_ok, actor_id=actor.id if actor else None,
                      message=message[:240], data=clean_data(data))
    db.add(ev)
    return ev


def _set_status(db: Session, payment: Payment, new: str, source: str, event_type: str, message: str, **kw) -> None:
    old = payment.status
    payment.status = new
    payment.updated_at = utcnow()
    record(db, payment, source, event_type, message, before=old, after=new, **kw)


# ---- lookups and summaries ------------------------------------------------------------------------------------------------------------
def get_payment(db: Session, payment_id: int) -> Payment:
    p = db.get(Payment, payment_id)
    if p is None:
        raise PaymentError(404, "PAYMENT_NOT_FOUND", "Payment not found.")
    return p


def get_order(db: Session, order_id: int) -> Order:
    o = db.get(Order, order_id)
    if o is None:
        raise PaymentError(404, "ORDER_NOT_FOUND", "Order not found.")
    return o


def order_payments(db: Session, order_id: int) -> list[Payment]:
    return list(db.scalars(select(Payment).where(Payment.order_id == order_id).order_by(Payment.id.desc())))


def payment_summaries(db: Session, order_ids: list[int]) -> dict[int, dict]:
    """One small record per order for the Orders list: 'none' means no payment was ever started (every order before 2.7.0), and it is not an error."""
    out: dict[int, dict] = {i: {"status": "none", "paid_paise": 0, "refunded_paise": 0, "method": None, "payment_id": None, "pending_payment_id": None} for i in order_ids}
    if not order_ids:
        return out
    for p in db.scalars(select(Payment).where(Payment.order_id.in_(order_ids)).order_by(Payment.id)):
        s = out[p.order_id]
        if p.status in PAID_STATUSES:
            s["paid_paise"] += p.amount_paise
            s["refunded_paise"] += p.refunded_paise
            s["method"], s["payment_id"] = p.method, p.id
        elif p.status == "pending":
            s["pending_payment_id"] = p.id
        elif p.status == "failed" and s["status"] == "none":
            s["status"] = "failed"
    for s in out.values():
        if s["paid_paise"]:
            s["status"] = "refunded" if s["refunded_paise"] >= s["paid_paise"] else "partially_refunded" if s["refunded_paise"] else "paid"
        elif s["pending_payment_id"]:
            s["status"] = "pending"
    return out


def user_names(db: Session, ids: set[Optional[int]]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(ids)))}


def refundable_paise(p: Payment) -> int:
    if p.status not in ("paid", "partially_refunded"):
        return 0
    pending = sum(r.amount_paise for r in p.refunds if r.status == "pending")
    return max(0, p.amount_paise - p.refunded_paise - pending)


def verification_label(p: Payment, names: dict[int, str]) -> str:
    who = names.get(p.confirmed_by_id or 0, "")
    if p.status == "pending":
        return {"cash": "Waiting for cash", "upi": "Waiting for the customer to pay" + ("" if p.provider == "razorpay_qr" else ", not yet confirmed"), "razorpay": "Waiting for Razorpay"}[p.method]
    if p.status not in PAID_STATUSES:
        return ""
    if p.verified:
        return "Confirmed by Razorpay"
    if p.verification == "manual":
        return f"Confirmed by {who or 'a team member'}. Not verified by a payment provider"
    if p.verification == "cash":
        return f"Cash recorded by {who or 'a team member'}"
    return ""


def serialize_payment(p: Payment, names: Optional[dict[int, str]] = None, settings: Optional[Settings] = None, *, detail: bool = False, events: Optional[list] = None) -> dict:
    names = names or {}
    stale = bool(settings and p.status == "pending" and utcnow() - p.created_at > timedelta(minutes=settings.payment_pending_minutes))
    out = {
        "id": p.id, "code": p.code, "order_id": p.order_id, "order_code": p.order.code, "customer_name": p.order.customer_name,
        "order_status": p.order.status, "method": p.method, "provider": p.provider, "status": p.status,
        "amount_paise": p.amount_paise, "currency": p.currency, "amount_received_paise": p.amount_received_paise,
        "change_paise": max(0, (p.amount_received_paise or 0) - p.amount_paise) if p.method == "cash" and p.amount_received_paise else 0,
        "refunded_paise": p.refunded_paise, "refundable_paise": refundable_paise(p), "verified": p.verified, "verification": p.verification,
        "verification_label": verification_label(p, names), "reference_note": p.reference_note, "provider_method": p.provider_method,
        "provider_payment_id": p.provider_payment_id, "failure_code": p.failure_code, "failure_reason": p.failure_reason, "attention": p.attention,
        "is_synthetic": p.is_synthetic, "stale": stale, "created_at": iso(p.created_at), "paid_at": iso(p.paid_at),
        "created_by": names.get(p.created_by_id or 0), "confirmed_by": names.get(p.confirmed_by_id or 0),
    }
    if detail:
        out["provider_order_id"] = p.provider_order_id
        out["provider_qr_id"] = p.provider_qr_id
        out["qr_image_url"] = p.qr_image_url
        out["upi_payee"] = p.upi_payee
        out["refunds"] = [serialize_refund(r, names) for r in p.refunds]
        out["events"] = [serialize_event(e, names) for e in (events or [])]
    return out


def serialize_refund(r: Refund, names: Optional[dict[int, str]] = None) -> dict:
    names = names or {}
    label = ("Recorded by the owner. Not confirmed by a payment provider." if r.kind == "manual"
             else "Confirmed by Razorpay" if r.status == "processed" else "Waiting for Razorpay to confirm" if r.status == "pending" else "Razorpay did not complete this refund")
    return {"id": r.id, "code": r.code, "payment_id": r.payment_id, "kind": r.kind, "amount_paise": r.amount_paise, "status": r.status, "reason": r.reason,
            "provider_refund_id": r.provider_refund_id, "speed_processed": r.speed_processed, "failure_reason": r.failure_reason, "label": label,
            "initiated_by": names.get(r.initiated_by_id or 0), "created_at": iso(r.created_at), "processed_at": iso(r.processed_at)}


def serialize_event(e: PaymentEvent, names: Optional[dict[int, str]] = None) -> dict:
    names = names or {}
    return {"id": e.id, "source": e.source, "type": e.event_type, "message": e.message, "status_before": e.status_before, "status_after": e.status_after,
            "signature_ok": e.signature_ok, "actor": names.get(e.actor_id or 0), "created_at": iso(e.created_at)}


def payment_events(db: Session, payment_id: int) -> list[PaymentEvent]:
    return list(db.scalars(select(PaymentEvent).where(PaymentEvent.payment_id == payment_id).order_by(PaymentEvent.id)))


def payment_detail(db: Session, settings: Settings, p: Payment) -> dict:
    events = payment_events(db, p.id)
    names = user_names(db, {p.created_by_id, p.confirmed_by_id, *(r.initiated_by_id for r in p.refunds), *(e.actor_id for e in events)})
    out = serialize_payment(p, names, settings, detail=True, events=events)
    out["upi"] = upi_instructions(settings, p)
    return out


# ---- UPI ------------------------------------------------------------------------------------------------------------------------------
def valid_vpa(vpa: str) -> bool:
    return bool(VPA_RE.match((vpa or "").strip()))


def payee_name(settings: Settings) -> str:
    return (settings.upi_payee_name.strip() or settings.store_name.strip() or "Shop")[:40]


def upi_uri(settings: Settings, p: Payment) -> Optional[str]:
    """The upi:// payment link a UPI app reads from a QR. The amount, shop and bill reference are fixed here, on the server, from the stored payment."""
    vpa = (p.upi_payee or settings.upi_vpa or "").strip()
    if not valid_vpa(vpa):
        return None
    note = f"Bill {p.order.code}"
    q = f"pa={quote(vpa, safe='@')}&pn={quote(payee_name(settings), safe='')}&am={p.amount_paise / 100:.2f}&cu=INR&tn={quote(note, safe='')}&tr={quote(p.code, safe='')}"
    return "upi://pay?" + q


def upi_instructions(settings: Settings, p: Payment) -> Optional[dict]:
    if p.method != "upi":
        return None
    provider_qr = p.provider == "razorpay_qr"
    return {
        "mode": "provider" if provider_qr else "manual", "verified_by_provider": provider_qr,
        "uri": None if provider_qr else upi_uri(settings, p), "qr_image_url": p.qr_image_url if provider_qr else None,
        "payee": None if provider_qr else (p.upi_payee or settings.upi_vpa), "amount_paise": p.amount_paise, "reference": p.code, "order_code": p.order.code,
        "instructions": ("Ask the customer to scan the code with any UPI app and pay the exact amount. The payment is confirmed automatically once Razorpay reports it."
                         if provider_qr else
                         "Ask the customer to scan the code with any UPI app and pay the exact amount. This app cannot see the payment. It stays unconfirmed until you "
                         "check your bank or UPI app and confirm it here."),
    }


# ---- creating a payment ---------------------------------------------------------------------------------------------------------------
def _shop(settings: Settings) -> str:
    return settings.store_name.strip() or "SWARA AI"


def create_payment(db: Session, settings: Settings, rp: RazorpayClient, order: Order, method: str, user: User, idempotency_key: Optional[str]) -> tuple[Payment, bool]:
    """Start (or resume) a payment for an order. Returns (payment, created). The same idempotency key, or an unfinished payment of the same kind,
    returns the existing record, so a double tap or a retry never starts a second payment."""
    if method not in METHODS:
        raise PaymentError(422, "BAD_METHOD", "Choose cash, UPI or Razorpay.")
    key = (idempotency_key or "").strip() or None
    if key and not re.fullmatch(r"[A-Za-z0-9._:\-]{8,64}", key):
        raise PaymentError(422, "BAD_IDEMPOTENCY_KEY", "The idempotency key must be 8 to 64 letters, digits or . _ : - characters.")
    if key:
        same = db.scalar(select(Payment).where(Payment.idempotency_key == key))
        if same is not None:
            if same.order_id != order.id or same.method != method:
                raise PaymentError(409, "IDEMPOTENCY_CONFLICT", "That request key was already used for a different payment.")
            return same, False
    if order.status == "cancelled":
        raise PaymentError(409, "ORDER_CANCELLED", "This order was cancelled, so it cannot be paid.")
    if order.total_paise <= 0:
        raise PaymentError(409, "NOTHING_TO_PAY", "This order has no amount to pay.")
    existing = order_payments(db, order.id)
    if any(p.status in ("paid", "partially_refunded") for p in existing):
        raise PaymentError(409, "ALREADY_PAID", "This order is already paid.")
    pending = next((p for p in existing if p.status == "pending"), None)
    if pending is not None:
        if pending.method == method:
            return pending, False
        raise PaymentError(409, "PAYMENT_IN_PROGRESS", f"A {pending.method} payment ({pending.code}) is still open for this order. Cancel it first to choose another way.", payment_id=pending.id)

    provider, extra = "none", {}
    notes = {"swara_order": order.code, "shop": _shop(settings)[:60]}
    if method == "razorpay":
        if not settings.razorpay_enabled:
            raise PaymentError(409, "RAZORPAY_OFF", settings.razorpay_problem or "Razorpay is not set up.")
        provider = "razorpay"
        try:
            ro = rp.create_order(order.total_paise, f"{order.code}-{secrets.token_hex(3)}", notes)
        except RazorpayError as exc:
            raise PaymentError(502, f"RAZORPAY_{exc.code}", exc.message) from exc
        if not isinstance(ro.get("id"), str) or int(ro.get("amount", -1)) != order.total_paise:
            raise PaymentError(502, "RAZORPAY_BAD_REPLY", "Razorpay answered with an order that does not match the bill. Nothing was started.")
        extra["provider_order_id"] = ro["id"]
    elif method == "upi":
        if settings.razorpay_enabled and settings.razorpay_upi_qr:
            provider = "razorpay_qr"
            try:
                close_by = int((datetime.utcnow() + timedelta(minutes=QR_MINUTES)).timestamp())
                qr = rp.create_upi_qr(order.total_paise, f"Bill {order.code}", f"Bill {order.code} at {_shop(settings)}", close_by, notes)
            except RazorpayError as exc:
                hint = " Razorpay may not have switched UPI QR on for this account yet." if exc.code == "REJECTED" else ""
                raise PaymentError(502, f"RAZORPAY_{exc.code}", exc.message + hint) from exc
            if not isinstance(qr.get("id"), str) or int(qr.get("payment_amount", -1)) != order.total_paise:
                raise PaymentError(502, "RAZORPAY_BAD_REPLY", "Razorpay answered with a QR code that does not match the bill. Nothing was started.")
            extra["provider_qr_id"] = qr["id"]
            extra["qr_image_url"] = str(qr.get("image_url") or "")[:300] or None
        elif valid_vpa(settings.upi_vpa):
            provider = "manual"
            extra["upi_payee"] = settings.upi_vpa.strip()
        else:
            raise PaymentError(409, "UPI_NOT_SET_UP", "UPI is not set up yet. The owner can add the shop's UPI ID in Settings.")

    p = Payment(order_id=order.id, method=method, provider=provider, status="pending", amount_paise=order.total_paise, currency="INR", idempotency_key=key,
                is_synthetic=order.is_synthetic, created_by_id=user.id, **extra)
    db.add(p)
    try:
        db.flush()
    except IntegrityError:  # two taps at once: the database allows one open payment per order
        db.rollback()
        again = next((x for x in order_payments(db, order.id) if x.status == "pending"), None)
        if again is not None and again.method == method:
            return again, False
        raise PaymentError(409, "PAYMENT_IN_PROGRESS", "A payment is already open for this order.")
    record(db, p, "user", "created", f"{method} payment started for {order.code}", after="pending", actor=user,
           data={"amount": p.amount_paise, "method": method, "order_id": extra.get("provider_order_id") or extra.get("provider_qr_id")})
    db.commit()
    db.refresh(p)
    return p, True


def checkout_params(settings: Settings, p: Payment) -> dict:
    """What the browser needs to open Razorpay Checkout. The key id is public by design; the key secret is never here."""
    return {"key_id": settings.razorpay_key_id.strip(), "provider_order_id": p.provider_order_id, "amount_paise": p.amount_paise, "currency": p.currency,
            "name": _shop(settings)[:60], "description": f"Bill {p.order.code}", "mode": settings.payment_mode}


# ---- cash and manual UPI --------------------------------------------------------------------------------------------------------------
def _must_be_pending(p: Payment) -> None:
    if p.status == "paid" or p.status in ("partially_refunded", "refunded"):
        raise PaymentError(409, "ALREADY_PAID", "This payment is already recorded as paid.")
    if p.status != "pending":
        raise PaymentError(409, "NOT_PENDING", f"This payment is {p.status}. Start a new payment instead.")


def _mark_paid(db: Session, p: Payment, *, source: str, event_type: str, message: str, received: Optional[int] = None, verified: bool = False,
               verification: str = "none", actor: Optional[User] = None, provider_payment_id: Optional[str] = None, provider_method: Optional[str] = None,
               event_id: Optional[str] = None, data: Optional[dict] = None) -> None:
    others_paid = db.scalar(select(func.count()).select_from(Payment).where(Payment.order_id == p.order_id, Payment.id != p.id, Payment.status.in_(PAID_STATUSES))) or 0
    was = p.status
    p.amount_received_paise = received if received is not None else p.amount_paise
    p.verified, p.verification = verified, verification
    p.paid_at = utcnow()
    p.failure_code = p.failure_reason = None
    if actor is not None:
        p.confirmed_by_id = actor.id
    if provider_payment_id:
        p.provider_payment_id = provider_payment_id
    if provider_method:
        p.provider_method = provider_method[:16]
    if others_paid:
        p.attention = "duplicate_collection"
    elif p.order.status == "cancelled":
        p.attention = "order_cancelled"
    elif was in ("failed", "cancelled"):
        p.attention = "late_payment"
    _set_status(db, p, "paid", source, event_type, message, event_id=event_id, actor=actor, data=data)


def confirm_cash(db: Session, p: Payment, received_paise: int, user: User) -> Payment:
    if p.method != "cash":
        raise PaymentError(409, "WRONG_METHOD", "This is not a cash payment.")
    _must_be_pending(p)
    if received_paise < p.amount_paise:
        raise PaymentError(422, "CASH_SHORT", f"The customer gave ₹{rupees_text(received_paise)}, which is less than the bill of ₹{rupees_text(p.amount_paise)}.")
    if received_paise > p.amount_paise * 20 + 100_000:
        raise PaymentError(422, "CASH_TOO_MUCH", "That amount looks wrong. Check it and try again.")
    _mark_paid(db, p, source="user", event_type="cash_received", message=f"Cash received: ₹{rupees_text(received_paise)} for a bill of ₹{rupees_text(p.amount_paise)}",
               received=received_paise, verification="cash", actor=user, data={"received_paise": received_paise, "change_paise": received_paise - p.amount_paise})
    db.commit()
    return p


def confirm_manual_upi(db: Session, p: Payment, reference: str, user: User) -> Payment:
    if p.method != "upi" or p.provider != "manual":
        raise PaymentError(409, "WRONG_METHOD", "Only a manual UPI payment can be confirmed by hand. A Razorpay payment confirms itself.")
    _must_be_pending(p)
    ref = " ".join((reference or "").split())
    if not REFERENCE_RE.match(ref):
        raise PaymentError(422, "BAD_REFERENCE", "Enter the UPI reference from your bank or UPI app (4 to 40 letters or digits).")
    p.reference_note = ref
    _mark_paid(db, p, source="user", event_type="upi_confirmed_manually", message="UPI payment confirmed by hand. Not verified by a payment provider.",
               verification="manual", actor=user, data={"reference": ref})
    db.commit()
    return p


def cancel_payment(db: Session, rp: RazorpayClient, p: Payment, user: User, reason: str = "") -> Payment:
    if p.status != "pending":
        raise PaymentError(409, "NOT_PENDING", "Only a payment that is still waiting can be cancelled.")
    if p.provider == "razorpay_qr" and p.provider_qr_id and rp.enabled:
        try:  # best effort: close the QR so nobody can still pay it
            rp.close_qr(p.provider_qr_id)
        except RazorpayError:
            pass
    note = ""
    if p.provider == "razorpay":
        note = " If the customer already started paying in Razorpay Checkout, a later success will still be recorded and flagged."
    _set_status(db, p, "cancelled", "user", "cancelled", (reason or "Cancelled before it was paid.") + note, actor=user)
    db.commit()
    return p


# ---- Razorpay: confirming from Razorpay's own data -------------------------------------------------------------------------------------
def _entity_amount_ok(p: Payment, pdata: dict) -> bool:
    try:
        return int(pdata.get("amount", -1)) == p.amount_paise and str(pdata.get("currency", "INR")).upper() == p.currency
    except (TypeError, ValueError):
        return False


def apply_provider_payment(db: Session, settings: Settings, rp: RazorpayClient, p: Payment, pdata: dict, *, source: str, event_id: Optional[str] = None,
                           actor: Optional[User] = None, verification: str = "provider", may_capture: bool = True) -> str:
    """Move a payment according to a Razorpay payment record (from a lookup or a signed webhook). Returns a short word for logs and tests."""
    pid = str(pdata.get("id") or "")
    status = str(pdata.get("status") or "")
    safe = {"payment_id": pid, "status": status, "amount": pdata.get("amount") if isinstance(pdata.get("amount"), int) else None,
            "method": pdata.get("method"), "order_id": pdata.get("order_id"), "error_code": pdata.get("error_code"), "error_description": pdata.get("error_description")}
    if p.provider == "razorpay" and pdata.get("order_id") != p.provider_order_id:
        record(db, p, source, "ignored_wrong_order", "Razorpay payment belongs to a different order. Ignored.", event_id=event_id, data=safe)
        return "wrong_order"
    if status in ("captured", "authorized") and not _entity_amount_ok(p, pdata):
        p.attention = "amount_mismatch"
        record(db, p, source, "amount_mismatch", f"Razorpay reports an amount different from the bill (bill ₹{rupees_text(p.amount_paise)}). Not marked paid.", event_id=event_id, data=safe)
        return "amount_mismatch"
    other = db.scalar(select(Payment).where(Payment.provider_payment_id == pid, Payment.id != p.id)) if pid else None
    if other is not None:
        record(db, p, source, "duplicate_provider_id", "That Razorpay payment is already attached to another record. Ignored.", event_id=event_id, data=safe)
        return "duplicate"
    if status == "authorized":
        if p.status in PAID_STATUSES:
            return "already_paid"
        if not (may_capture and rp.enabled):
            record(db, p, source, "authorized", "Razorpay authorised the payment; waiting for it to be captured.", event_id=event_id, data=safe)
            return "authorized"
        try:
            captured = rp.capture_payment(pid, p.amount_paise)
        except RazorpayError as exc:
            record(db, p, source, "capture_failed", f"Could not capture the authorised payment yet: {exc.message}", event_id=event_id, data=safe)
            return "capture_failed"
        pdata, status = captured, str(captured.get("status") or "")
        if status != "captured" or not _entity_amount_ok(p, captured):
            record(db, p, source, "capture_unconfirmed", "Razorpay did not report the capture as complete.", event_id=event_id, data=safe)
            return "capture_unconfirmed"
    if status == "captured":
        if p.status in PAID_STATUSES:
            if p.provider_payment_id == pid:
                return "already_paid"
            p.attention = "duplicate_collection"
            record(db, p, source, "second_payment_captured", "Razorpay captured a second payment for this order. It was not recorded as a new payment; refund it in the Razorpay dashboard.",
                   event_id=event_id, data=safe)
            return "duplicate_collection"
        _mark_paid(db, p, source=source, event_type="paid", message="Razorpay confirmed the payment.", verified=True, verification=verification,
                   actor=actor, provider_payment_id=pid, provider_method=str(pdata.get("method") or ""), event_id=event_id, data=safe)
        return "paid"
    if status == "failed":
        if p.status in PAID_STATUSES:
            record(db, p, source, "failed_attempt_ignored", "A failed attempt was reported after the payment succeeded. Nothing changed.", event_id=event_id, data=safe)
            return "ignored"
        p.failure_code = str(pdata.get("error_code") or "")[:48] or None
        p.failure_reason = str(pdata.get("error_description") or "The payment did not go through.")[:200]
        if pid and p.provider_payment_id is None:
            p.provider_payment_id = pid
        if p.status != "failed":
            _set_status(db, p, "failed", source, "failed", "Razorpay reported the payment as failed: " + (p.failure_reason or ""), event_id=event_id, data=safe)
        return "failed"
    record(db, p, source, "provider_" + (status or "unknown"), f"Razorpay reports the payment as {status or 'unknown'}.", event_id=event_id, data=safe)
    return "pending"


def verify_checkout(db: Session, settings: Settings, rp: RazorpayClient, p: Payment, razorpay_order_id: str, razorpay_payment_id: str, signature: str, user: User) -> tuple[Payment, str]:
    """The browser's callback after Checkout. The signature proves the ids came from Razorpay, then Razorpay is asked about the payment before anything
    is marked paid. Returns (payment, notice) where notice is empty unless the answer could not be confirmed yet."""
    if p.method != "razorpay" or not p.provider_order_id:
        raise PaymentError(409, "WRONG_METHOD", "This is not a Razorpay payment.")
    secret = settings.razorpay_secret
    if not secret:
        raise PaymentError(409, "RAZORPAY_OFF", settings.razorpay_problem or "Razorpay is not set up.")
    # The order id used is the one STORED here when the payment was started; the one the browser sent only has to agree with it.
    ok = (razorpay_order_id == p.provider_order_id) and verify_checkout_signature(secret, p.provider_order_id, razorpay_payment_id, signature)
    if not ok:
        record(db, p, "checkout", "bad_signature", "The payment confirmation could not be verified. Nothing was recorded as paid.", signature_ok=False, actor=user,
               data={"payment_id": str(razorpay_payment_id)[:48]})
        db.commit()
        raise PaymentError(400, "BAD_SIGNATURE", "The payment confirmation could not be verified, so nothing was recorded as paid. If money left the customer's account, "
                                                 "check the payment in Razorpay before trying again.")
    if p.status in PAID_STATUSES and p.provider_payment_id == razorpay_payment_id:
        return p, ""  # a second delivery of the same confirmation
    record(db, p, "checkout", "signature_ok", "Checkout signature is valid. Asking Razorpay about the payment.", signature_ok=True, actor=user, data={"payment_id": razorpay_payment_id[:48]})
    try:
        pdata = rp.fetch_payment(razorpay_payment_id)
    except RazorpayError as exc:
        db.commit()
        return p, ("Razorpay's confirmation has a valid signature but Razorpay could not be asked about the payment just now (" + exc.message +
                   "). It will be confirmed when Razorpay reports it. Use Check status to try again.")
    outcome = apply_provider_payment(db, settings, rp, p, pdata, source="checkout", actor=user, verification="signature")
    db.commit()
    db.refresh(p)
    notice = {"amount_mismatch": "Razorpay reports a different amount from the bill, so the payment was not marked paid. Check it in Razorpay.",
              "wrong_order": "That Razorpay payment belongs to a different order, so it was ignored.", "duplicate": "That Razorpay payment is already recorded elsewhere.",
              "authorized": "Razorpay has authorised the payment but not captured it yet. It will show as paid once captured.",
              "capture_failed": "The payment is authorised but capturing it did not work yet. Use Check status in a moment.",
              "pending": "Razorpay has not finished the payment yet. Use Check status in a moment."}.get(outcome, "")
    return p, notice


def refresh_payment(db: Session, settings: Settings, rp: RazorpayClient, p: Payment, user: Optional[User]) -> tuple[Payment, str]:
    """Ask Razorpay where a still-pending payment stands. This is how a shop whose computer cannot receive webhooks (most can't) finds out."""
    if p.status in PAID_STATUSES or p.method == "cash" or p.provider in ("none", "manual"):
        return p, ""
    if not rp.enabled:
        raise PaymentError(409, "RAZORPAY_OFF", settings.razorpay_problem or "Razorpay is not set up.")
    try:
        if p.provider == "razorpay_qr":
            items = rp.fetch_qr_payments(p.provider_qr_id or "").get("items") or []
        elif p.provider_payment_id:
            items = [rp.fetch_payment(p.provider_payment_id)]
        else:
            items = rp.fetch_order_payments(p.provider_order_id or "").get("items") or []
    except RazorpayError as exc:
        return p, exc.message
    items = [i for i in items if isinstance(i, dict)]
    rank = {"captured": 0, "authorized": 1, "failed": 3}
    items.sort(key=lambda i: rank.get(str(i.get("status")), 2))
    if not items:
        record(db, p, "system", "checked", "Checked with Razorpay: no payment attempt yet.", actor=user)
        db.commit()
        return p, "Razorpay has no payment for this yet."
    outcome = "pending"
    for it in items[:5]:
        outcome = apply_provider_payment(db, settings, rp, p, it, source="system", actor=user, verification="provider")
        if outcome in ("paid", "already_paid"):
            break
    db.commit()
    db.refresh(p)
    return p, "" if p.status != "pending" else "Not paid yet."


# ---- webhooks -------------------------------------------------------------------------------------------------------------------------
def _find_payment_for_event(db: Session, payload: dict) -> Optional[Payment]:
    pay = ((payload.get("payment") or {}).get("entity")) or {}
    qr = ((payload.get("qr_code") or {}).get("entity")) or {}
    order = ((payload.get("order") or {}).get("entity")) or {}
    for col, val in ((Payment.provider_order_id, pay.get("order_id") or order.get("id")), (Payment.provider_qr_id, qr.get("id")), (Payment.provider_payment_id, pay.get("id"))):
        if val:
            hit = db.scalar(select(Payment).where(col == str(val)))
            if hit is not None:
                return hit
    return None


def handle_webhook(db: Session, settings: Settings, rp: RazorpayClient, raw: bytes, signature: Optional[str], event_id_header: Optional[str]) -> dict:
    """Process one Razorpay webhook. The signature is checked over the raw bytes first; a delivery with an already-seen event id is acknowledged and ignored."""
    secret = settings.razorpay_webhook_key
    if not secret:
        raise PaymentError(503, "WEBHOOK_NOT_CONFIGURED", "The webhook secret is not set on this server.")
    if not verify_webhook_signature(secret, raw, signature):
        log.warning("Razorpay webhook refused: bad signature")
        raise PaymentError(400, "BAD_SIGNATURE", "The webhook signature is not valid.")
    try:
        body = json.loads(raw.decode("utf-8"))
        assert isinstance(body, dict)
    except (ValueError, AssertionError, UnicodeDecodeError):
        raise PaymentError(400, "BAD_PAYLOAD", "The webhook body is not valid JSON.")
    event = str(body.get("event") or "")[:48]
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    event_id = (event_id_header or "").strip()[:100] or "sha256:" + hashlib.sha256(raw).hexdigest()
    if db.scalar(select(PaymentEvent.id).where(PaymentEvent.event_id == event_id)) is not None:
        return {"status": "duplicate"}
    ev = PaymentEvent(source="webhook", event_id=event_id, event_type=event or "unknown", signature_ok=True, message="Webhook received.", data={"event": event})
    db.add(ev)
    try:
        db.flush()
    except IntegrityError:  # the same event arrived twice at the same moment
        db.rollback()
        return {"status": "duplicate"}

    p = _find_payment_for_event(db, payload)
    pay = ((payload.get("payment") or {}).get("entity")) or {}
    result = "ignored"
    if event.startswith("refund."):
        result = _webhook_refund(db, event, payload, ev)
    elif p is None:
        ev.message = "No matching payment in this shop. Ignored."
    else:
        ev.payment_id, ev.status_before = p.id, p.status
        if event in ("payment.authorized", "payment.captured", "payment.failed", "order.paid", "qr_code.credited") and isinstance(pay, dict) and pay:
            result = apply_provider_payment(db, settings, rp, p, pay, source="webhook", event_id=None, verification="webhook")
            ev.message = f"{event}: {result}"
        else:
            ev.message = f"{event}: no action needed."
        ev.status_after = p.status
    db.commit()
    return {"status": "processed" if result != "ignored" else "ignored", "result": result}


def _webhook_refund(db: Session, event: str, payload: dict, ev: PaymentEvent) -> str:
    ent = ((payload.get("refund") or {}).get("entity")) or {}
    rid, rcpt = str(ent.get("id") or ""), str(ent.get("receipt") or "")
    refund = db.scalar(select(Refund).where(Refund.provider_refund_id == rid)) if rid else None
    if refund is None and rcpt:
        m = re.fullmatch(r"REF-\d{6}-(\d+)", rcpt)
        refund = db.get(Refund, int(m.group(1))) if m else None
    if refund is None:
        ev.message = f"{event}: no matching refund in this shop. Ignored."
        return "ignored"
    ev.payment_id = refund.payment_id
    status = {"refund.created": "pending", "refund.processed": "processed", "refund.failed": "failed"}.get(event)
    if status is None:
        ev.message = f"{event}: no action needed."
        return "ignored"
    if rid and refund.provider_refund_id is None:
        refund.provider_refund_id = rid
    set_refund_status(db, refund, status, source="webhook", speed=str(ent.get("speed_processed") or "") or None, reason=str(ent.get("failure_reason") or ""))
    ev.status_before, ev.status_after = refund.payment.status, refund.payment.status
    ev.message = f"{event}: refund {refund.code} is {refund.status}."
    return refund.status


# ---- refunds --------------------------------------------------------------------------------------------------------------------------
def set_refund_status(db: Session, refund: Refund, status: str, *, source: str, speed: Optional[str] = None, reason: str = "", actor: Optional[User] = None) -> None:
    """Move a refund forward. Only a provider-reported (or owner-recorded manual) 'processed' ever reduces what the customer paid; it counts once."""
    p = refund.payment
    if refund.status == status:
        return
    if refund.status == "processed":  # a processed refund is final; a late 'failed' or 'pending' report must not undo it
        record(db, p, source, "refund_report_ignored", f"Refund {refund.code} is already processed; ignored a later '{status}' report.", actor=actor)
        return
    before = p.status
    if status == "processed":
        refund.status, refund.processed_at, refund.speed_processed = "processed", utcnow(), speed or refund.speed_processed
        if p.refunded_paise + refund.amount_paise > p.amount_paise:
            p.attention = "refund_mismatch"
            refund.amount_paise = max(1, p.amount_paise - p.refunded_paise)
        p.refunded_paise += refund.amount_paise
        p.status = "refunded" if p.refunded_paise >= p.amount_paise else "partially_refunded"
        p.updated_at = utcnow()
        record(db, p, source, "refund_processed", f"Refund {refund.code} of ₹{rupees_text(refund.amount_paise)} " + ("recorded by the owner." if refund.kind == "manual" else "confirmed by Razorpay."),
               before=before, after=p.status, actor=actor, data={"refund_id": refund.provider_refund_id, "amount": refund.amount_paise, "kind": refund.kind})
    elif status == "failed":
        refund.status, refund.failure_reason = "failed", (reason or "Razorpay did not complete this refund.")[:200]
        record(db, p, source, "refund_failed", f"Refund {refund.code} failed: {refund.failure_reason}", before=before, after=p.status, actor=actor, data={"refund_id": refund.provider_refund_id})
    else:
        refund.status = "pending"
        record(db, p, source, "refund_pending", f"Refund {refund.code} is waiting for Razorpay.", before=before, after=p.status, actor=actor, data={"refund_id": refund.provider_refund_id})


def create_refund(db: Session, settings: Settings, rp: RazorpayClient, p: Payment, amount_paise: Optional[int], reason: str, user: User, idempotency_key: Optional[str]) -> tuple[Refund, bool]:
    """Start a refund (owner only; the route enforces that). Returns (refund, created). A refund is never reported as done until Razorpay says so."""
    key = (idempotency_key or "").strip() or secrets.token_hex(16)
    if not re.fullmatch(r"[A-Za-z0-9._:\-]{8,64}", key):
        raise PaymentError(422, "BAD_IDEMPOTENCY_KEY", "The idempotency key must be 8 to 64 letters, digits or . _ : - characters.")
    prior = db.scalar(select(Refund).where(Refund.idempotency_key == key))
    if prior is not None:
        if prior.payment_id != p.id:
            raise PaymentError(409, "IDEMPOTENCY_CONFLICT", "That request key was already used for a different refund.")
        return prior, False
    if p.status not in ("paid", "partially_refunded"):
        raise PaymentError(409, "NOT_REFUNDABLE", "Only a paid payment can be refunded." if p.status != "refunded" else "This payment is already fully refunded.")
    room = refundable_paise(p)
    amount = room if amount_paise is None else amount_paise
    if amount <= 0:
        raise PaymentError(409, "NOTHING_TO_REFUND", "Nothing is left to refund on this payment (a refund may still be waiting for Razorpay).")
    if amount > room:
        raise PaymentError(422, "REFUND_TOO_LARGE", f"At most ₹{rupees_text(room)} can still be refunded on this payment.")
    reason = " ".join((reason or "").split())[:200]
    if len(reason) < 3:
        raise PaymentError(422, "REASON_REQUIRED", "Write a short reason for the refund (it is kept in the audit trail).")
    kind = "provider" if p.provider in ("razorpay", "razorpay_qr") else "manual"
    if kind == "provider":
        if not rp.enabled:
            raise PaymentError(409, "RAZORPAY_OFF", settings.razorpay_problem or "Razorpay is not set up.")
        if not p.provider_payment_id:
            raise PaymentError(409, "NO_PROVIDER_PAYMENT", "This payment has no Razorpay payment id yet. Use Check status on it first.")
    r = Refund(payment_id=p.id, kind=kind, amount_paise=amount, status="pending", reason=reason, idempotency_key=key, initiated_by_id=user.id)
    db.add(r)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        prior = db.scalar(select(Refund).where(Refund.idempotency_key == key))
        if prior is not None and prior.payment_id == p.id:
            return prior, False
        raise PaymentError(409, "IDEMPOTENCY_CONFLICT", "That request key was already used for a different refund.")
    record(db, p, "user", "refund_requested", f"Refund {r.code} of ₹{rupees_text(amount)} requested: {reason}", before=p.status, after=p.status, actor=user, data={"amount": amount, "kind": kind})
    db.commit()
    if kind == "manual":
        set_refund_status(db, r, "processed", source="user", actor=user)
        db.commit()
        return r, True
    try:
        res = rp.create_refund(p.provider_payment_id or "", amount, r.code, {"swara_order": p.order.code, "swara_payment": p.code})
    except RazorpayError as exc:
        if exc.outcome_unknown:
            record(db, p, "system", "refund_unconfirmed", f"Razorpay did not answer for refund {r.code}. It is NOT assumed to have happened. Use Check status.", actor=user)
            db.commit()
            return r, True
        set_refund_status(db, r, "failed", source="system", reason=exc.message, actor=user)
        db.commit()
        return r, True
    _apply_refund_reply(db, r, res, source="system", actor=user)
    db.commit()
    return r, True


def _apply_refund_reply(db: Session, r: Refund, res: dict, *, source: str, actor: Optional[User] = None) -> None:
    rid = str(res.get("id") or "")
    if rid and r.provider_refund_id is None:
        taken = db.scalar(select(Refund.id).where(Refund.provider_refund_id == rid, Refund.id != r.id))
        if taken is None:
            r.provider_refund_id = rid
    try:
        amount_ok = int(res.get("amount", r.amount_paise)) == r.amount_paise
    except (TypeError, ValueError):
        amount_ok = False
    if not amount_ok:
        record(db, r.payment, source, "refund_amount_mismatch", f"Razorpay reports a different amount for refund {r.code}. Left pending for the owner to check.", actor=actor)
        return
    status = {"processed": "processed", "failed": "failed"}.get(str(res.get("status")), "pending")
    set_refund_status(db, r, status, source=source, speed=str(res.get("speed_processed") or "") or None, reason=str(res.get("failure_reason") or ""), actor=actor)


def refresh_refund(db: Session, rp: RazorpayClient, r: Refund, user: Optional[User]) -> tuple[Refund, str]:
    if r.kind != "provider" or r.status != "pending":
        return r, ""
    if not rp.enabled:
        raise PaymentError(409, "RAZORPAY_OFF", "Razorpay is not set up.")
    try:
        if r.provider_refund_id:
            res = rp.fetch_refund(r.provider_refund_id)
        else:  # the create call was never answered: find the refund by the receipt it was sent with
            items = rp.fetch_payment_refunds(r.payment.provider_payment_id or "").get("items") or []
            res = next((i for i in items if isinstance(i, dict) and i.get("receipt") == r.code), None)
            if res is None:
                return r, "Razorpay has no record of this refund. It was not created."
    except RazorpayError as exc:
        return r, exc.message
    _apply_refund_reply(db, r, res, source="system", actor=user)
    db.commit()
    return r, ""


# ---- history --------------------------------------------------------------------------------------------------------------------------
def _payment_filters(q: str, status: Optional[str], method: Optional[str], since: Optional[datetime], until: Optional[datetime], include_synthetic: bool, attention: bool):
    stmt = select(Payment).join(Order, Order.id == Payment.order_id)
    q = (q or "").strip()[:60]
    if q:
        like = f"%{q}%"
        conds = [Order.customer_name.ilike(like), Payment.provider_payment_id.ilike(like), Payment.provider_order_id.ilike(like), Payment.reference_note.ilike(like)]
        m = re.fullmatch(r"(?:PAY-\d{6}-)?0*(\d{1,9})", q, flags=re.I)
        if m:
            conds.append(Payment.id == int(m.group(1)))
        m2 = re.fullmatch(r"(?:(?:SW|DM)-\d{6}-)?0*(\d{1,9})", q, flags=re.I)
        if m2:
            conds.append(Payment.order_id == int(m2.group(1)))
        stmt = stmt.where(or_(*conds))
    if method in METHODS:
        stmt = stmt.where(Payment.method == method)
    if since:
        stmt = stmt.where(Payment.created_at >= since)
    if until:
        stmt = stmt.where(Payment.created_at < until)
    if not include_synthetic:
        stmt = stmt.where(Payment.is_synthetic.is_(False))
    if attention:
        stmt = stmt.where(Payment.attention.is_not(None))
    return stmt


def list_payments(db: Session, settings: Settings, *, q: str = "", status: Optional[str] = None, method: Optional[str] = None, since: Optional[datetime] = None,
                  until: Optional[datetime] = None, include_synthetic: bool = True, attention: bool = False, sort: str = "newest", limit: int = 25, offset: int = 0) -> dict:
    base = _payment_filters(q, status, method, since, until, include_synthetic, attention)
    statuses = ("pending", "paid", "failed", "cancelled", "partially_refunded", "refunded")
    counts = {s: db.scalar(select(func.count()).select_from(base.where(Payment.status == s).subquery())) or 0 for s in statuses}
    counts["all"] = sum(counts.values())
    stmt = base.where(Payment.status == status) if status in statuses else base
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {"oldest": (Payment.created_at, Payment.id), "amount_high": (Payment.amount_paise.desc(), Payment.id.desc()), "amount_low": (Payment.amount_paise, Payment.id)}.get(sort, (Payment.created_at.desc(), Payment.id.desc()))
    rows = list(db.scalars(stmt.order_by(*order).limit(limit).offset(offset)))
    names = user_names(db, {x for p in rows for x in (p.created_by_id, p.confirmed_by_id)})
    return {"total": total, "limit": limit, "offset": offset, "counts": counts, "items": [serialize_payment(p, names, settings) for p in rows]}


def ist_date(dt: datetime):
    return (dt + IST).date()


# ---- analytics ------------------------------------------------------------------------------------------------------------------------
def analytics(db: Session, *, days: int = 30, include_synthetic: bool = True) -> dict:
    """Payment figures from the payments and refunds tables, nothing else. A window with no payments shows zeros; no figure is estimated."""
    days = min(max(days, 1), 366)
    now = utcnow()
    since = now - timedelta(days=days)

    def scope(stmt):
        return stmt if include_synthetic else stmt.where(Payment.is_synthetic.is_(False))

    paid = list(db.scalars(scope(select(Payment).where(Payment.status.in_(PAID_STATUSES), Payment.paid_at >= since))))
    refunds = list(db.execute(select(Refund, Payment).join(Payment, Payment.id == Refund.payment_id).where(Refund.status == "processed", Refund.processed_at >= since)
                              .where(True if include_synthetic else Payment.is_synthetic.is_(False))))
    pending = list(db.scalars(scope(select(Payment).where(Payment.status == "pending"))))
    failed = list(db.scalars(scope(select(Payment).where(Payment.status == "failed", Payment.created_at >= since))))
    waiting_refunds = db.execute(select(func.count(), func.coalesce(func.sum(Refund.amount_paise), 0)).select_from(Refund).join(Payment, Payment.id == Refund.payment_id)
                                 .where(Refund.status == "pending").where(True if include_synthetic else Payment.is_synthetic.is_(False))).one()
    attention = db.scalar(select(func.count()).select_from(scope(select(Payment).where(Payment.attention.is_not(None))).subquery())) or 0

    by_method = {m: {"method": m, "collected_paise": 0, "count": 0} for m in METHODS}
    for p in paid:
        by_method[p.method]["collected_paise"] += p.amount_paise
        by_method[p.method]["count"] += 1
    gross = sum(p.amount_paise for p in paid)
    refunded = sum(r.amount_paise for r, _ in refunds)
    manual_upi = sum(p.amount_paise for p in paid if p.method == "upi" and p.provider == "manual")
    for m in by_method.values():
        m["share"] = round(m["collected_paise"] / gross, 4) if gross else 0.0

    today = ist_date(now)

    def blank(label: str) -> dict:
        return {"period": label, "collected_paise": 0, "count": 0, "cash_paise": 0, "upi_paise": 0, "razorpay_paise": 0}

    daily = {(today - timedelta(days=i)).isoformat(): blank((today - timedelta(days=i)).isoformat()) for i in range(min(days, 90) - 1, -1, -1)}
    weekly: dict[str, dict] = {}
    monthly: dict[str, dict] = {}
    for p in paid:
        d = ist_date(p.paid_at)
        for series, label in ((daily, d.isoformat()), (weekly, (d - timedelta(days=d.weekday())).isoformat()), (monthly, f"{d:%Y-%m}")):
            if series is daily and label not in daily:
                continue
            row = series.setdefault(label, blank(label))
            row["collected_paise"] += p.amount_paise
            row["count"] += 1
            row[f"{p.method}_paise"] += p.amount_paise
    return {
        "days": days, "since": iso(since), "includes_demo_orders": include_synthetic,
        "kpis": {
            "collected_paise": gross, "refunds_paise": refunded, "net_paise": gross - refunded, "paid_count": len(paid), "average_paise": round(gross / len(paid)) if paid else 0,
            "cash_paise": by_method["cash"]["collected_paise"], "upi_paise": by_method["upi"]["collected_paise"], "razorpay_paise": by_method["razorpay"]["collected_paise"],
            "upi_manual_paise": manual_upi, "pending_count": len(pending), "pending_paise": sum(p.amount_paise for p in pending),
            "failed_count": len(failed), "failed_paise": sum(p.amount_paise for p in failed), "refund_count": len(refunds),
            "refunds_waiting_count": int(waiting_refunds[0]), "refunds_waiting_paise": int(waiting_refunds[1]), "needs_attention": attention,
        },
        "by_method": list(by_method.values()),
        "daily": list(daily.values()), "weekly": sorted(weekly.values(), key=lambda r: r["period"]), "monthly": sorted(monthly.values(), key=lambda r: r["period"]),
    }


# ---- invoices -------------------------------------------------------------------------------------------------------------------------
def get_or_create_invoice(db: Session, settings: Settings, order: Order, user: Optional[User]) -> Invoice:
    inv = db.scalar(select(Invoice).where(Invoice.order_id == order.id))
    if inv is not None:
        return inv
    if order.status == "cancelled":
        raise PaymentError(409, "ORDER_CANCELLED", "A cancelled order has no invoice.")
    year = (order.created_at + IST).year
    for _ in range(5):  # a number is the next one in the year; a clash with a simultaneous request is retried
        seq = (db.scalar(select(func.max(Invoice.seq)).where(Invoice.year == year)) or 0) + 1
        inv = Invoice(order_id=order.id, year=year, seq=seq, number=f"INV-{year}-{seq:06d}", shop_name=_shop(settings)[:80], issued_by_id=user.id if user else None)
        db.add(inv)
        try:
            db.commit()
            return inv
        except IntegrityError:
            db.rollback()
            mine = db.scalar(select(Invoice).where(Invoice.order_id == order.id))
            if mine is not None:
                return mine
    raise PaymentError(503, "INVOICE_BUSY", "Could not reserve an invoice number. Try again.")


def serialize_invoice(db: Session, settings: Settings, order: Order, inv: Invoice) -> dict:
    payments = order_payments(db, order.id)
    paid = next((p for p in payments if p.status in PAID_STATUSES), None)
    shown = paid or (payments[0] if payments else None)
    cust = db.get(Customer, order.customer_id) if order.customer_id else None
    names = user_names(db, {shown.confirmed_by_id} if shown else set())
    subtotal = sum(i.line_total_paise for i in order.items)
    summary = payment_summaries(db, [order.id])[order.id]
    return {
        "number": inv.number, "issued_at": iso(inv.issued_at), "order_id": order.id, "order_code": order.code, "order_status": order.status,
        "shop": {"name": inv.shop_name}, "customer": {"name": order.customer_name, "phone": cust.phone if cust and cust.phone else None},
        "ordered_at": iso(order.created_at), "is_synthetic": order.is_synthetic,
        "items": [{"name": i.product_name, "qty": float(i.qty), "unit": i.unit, "unit_price_paise": i.unit_price_paise, "line_total_paise": i.line_total_paise} for i in order.items],
        "subtotal_paise": subtotal, "discount_paise": 0, "total_paise": order.total_paise,
        "payment": None if shown is None else {
            "status": summary["status"] if paid else shown.status, "method": shown.method, "provider": shown.provider, "reference": shown.code,
            "provider_payment_id": shown.provider_payment_id, "paid_at": iso(shown.paid_at), "amount_paise": shown.amount_paise, "refunded_paise": summary["refunded_paise"],
            "verified": shown.verified, "label": verification_label(shown, names)},
        "tax_note": "This invoice shows the bill total as entered by the shop. It has no tax breakdown and is not a GST tax invoice.",
    }


# ---- order cancellation and configuration ---------------------------------------------------------------------------------------------
def before_order_cancel(db: Session, order: Order, user: User) -> None:
    """Called before an order is cancelled. Money that was collected and not refunded blocks the cancellation (the owner refunds first), and a payment
    that is still waiting is closed so it cannot be paid against a cancelled bill. Orders that never had a payment are untouched."""
    held = 0
    for p in order_payments(db, order.id):
        if p.status in ("paid", "partially_refunded"):
            held += p.amount_paise - p.refunded_paise
        elif p.status == "pending":
            _set_status(db, p, "cancelled", "system", "order_cancelled", "The order was cancelled, so this open payment was closed.", actor=user)
    if held > 0:
        db.rollback()
        raise PaymentError(409, "PAID_ORDER", f"₹{rupees_text(held)} was collected for this order. Refund the payment first, then cancel the order.")
    db.flush()


def public_config(settings: Settings, *, owner: bool) -> dict:
    """What the checkout screen needs to know. Secrets never appear here, only whether they are set."""
    rp_ok = settings.razorpay_enabled
    qr_on = rp_ok and settings.razorpay_upi_qr
    manual_ok = valid_vpa(settings.upi_vpa)
    out: dict[str, Any] = {
        "mode": settings.payment_mode, "currency": "INR", "gst_configured": False,
        "methods": {
            "cash": {"available": True, "reason": None},
            "upi": {"available": qr_on or manual_ok, "mode": "provider" if qr_on else "manual" if manual_ok else None,
                    "reason": None if (qr_on or manual_ok) else "Add the shop's UPI ID in Settings to show a UPI QR code."},
            "razorpay": {"available": rp_ok, "reason": None if rp_ok else (settings.razorpay_problem or "Razorpay is not set up.")},
        },
        "razorpay": {"enabled": rp_ok, "key_id": settings.razorpay_key_id.strip() if rp_ok else None, "test_mode": settings.payment_mode == "test"},
        "pending_minutes": settings.payment_pending_minutes,
    }
    if owner:
        out["owner"] = {
            "razorpay_problem": settings.razorpay_problem, "key_secret_set": bool(settings.razorpay_secret), "webhook_secret_set": bool(settings.razorpay_webhook_key),
            "webhook_url": settings.public_url.rstrip("/") + "/api/payments/webhooks/razorpay", "upi_vpa": settings.upi_vpa, "upi_payee_name": settings.upi_payee_name,
            "upi_qr_enabled": settings.razorpay_upi_qr,
        }
    return out
