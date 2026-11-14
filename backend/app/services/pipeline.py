"""One conversational turn: text in -> dialogue -> (optional) order commit -> persisted reply.

This is the single code path shared by typed input, uploaded/recorded audio (after Gnani STT)
and the realtime WebSocket, so all three behave identically.
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ConversationSession, Customer, Turn
from ..nlu.dialogue import DialogState, DialogueManager, Outcome, cart_view
from ..nlu.lexicon import ProductView
from . import orders as order_svc
from .catalog import CatalogCache, load_views

MAX_TEXT = 600


def new_session_id() -> str:
    return uuid.uuid4().hex[:20]


def get_or_create_session(db: Session, session_id: Optional[str]) -> ConversationSession:
    if session_id:
        s = db.get(ConversationSession, session_id)
        if s:
            return s
    s = ConversationSession(id=session_id or new_session_id(), state=DialogState().to_dict())
    db.add(s)
    db.flush()
    return s


def _parse_summary(outcome: Outcome, products: dict[int, ProductView]) -> dict[str, Any]:
    p = outcome.parse
    lines = []
    for ln in p.lines:
        cands = [{"id": i, "sku": products[i].sku, "name": products[i].name_en} for i in ln.product_ids if i in products]
        lines.append({
            "spoken": ln.spoken,
            "candidates": cands,
            "resolved": len(cands) == 1,
            "qty": None if ln.qty is None else float(ln.qty),
            "unit": ln.unit,
            "qty_ambiguous": ln.qty_ambiguous,
            "match_kind": ln.match_kind,
            "match_score": round(ln.match_score, 1),
            "assumed_default": ln.assumed_default,
            "unknown_term": ln.unknown_term,
        })
    return {
        "intent": p.intent, "language": p.language, "script": p.script, "normalized": p.normalized,
        "cues": {k: v[:3] for k, v in p.cues.items()}, "lines": lines,
    }


def _pending_summary(state: DialogState, products: dict[int, ProductView]) -> Optional[dict[str, Any]]:
    if not state.queue:
        return None
    q = state.queue[0]
    return {
        "kind": q.kind,
        "product": products[q.product_id].name_en if q.product_id in products else None,
        "options": [{"id": i, "name": products[i].name_en} for i in q.options if i in products],
        "remaining": len(state.queue),
    }


def process_turn(
    db: Session, catalog: CatalogCache, text: str, *, session_id: Optional[str] = None,
    input_mode: str = "text", stt_ms: Optional[int] = None, customer_name: str = "Walk-in customer",
    customer_id: Optional[int] = None, keep_language: bool = False, language_hint: Optional[str] = None,
    timing_in: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """``timing_in`` carries the stage times measured before this call (validate_ms, stt_ms); they are stored with the reply so the
    owner's diagnostics can show where the time went for every spoken turn."""
    t_all = time.perf_counter()
    text = (text or "").strip()[:MAX_TEXT]
    sess = get_or_create_session(db, session_id)
    if customer_id is not None and customer_id != sess.customer_id:
        cust = db.get(Customer, customer_id)
        if cust is not None and cust.is_active:
            sess.customer_id = cust.id
    linked = db.get(Customer, sess.customer_id) if sess.customer_id else None
    if linked is not None:
        customer_name, customer_id = linked.name, linked.id
    else:
        customer_id = None
    state = DialogState.from_dict(sess.state)
    products = load_views(db)
    dm = DialogueManager(catalog.lexicon(db))

    t0 = time.perf_counter()
    outcome = dm.handle(text, state, products, keep_language=keep_language, language_hint=language_hint)
    nlu_ms = round((time.perf_counter() - t0) * 1000, 2)

    order_dict: Optional[dict[str, Any]] = None
    alerts: list[dict] = []
    reply = outcome.reply
    state = outcome.state
    if outcome.commit:
        try:
            order, alerts = order_svc.create_order(
                db, state.cart, products, session_id=sess.id,
                channel="voice" if input_mode in ("voice", "stream") else "text",
                language=state.language, customer_name=customer_name, customer_id=customer_id,
            )
            reply = dm.after_commit(state, order.id, order.total_paise, products)
            order_dict = order_svc.serialize_order(order)
            final_cart = cart_view(DialogState(cart=list(state.cart)), products)
            outcome.events.append({"type": "order_created", "order_id": order.id})
        except order_svc.InsufficientStock as exc:
            products = load_views(db)  # fresh stock
            reply = dm.after_commit_failed(state, exc.shortages, products)
            outcome.events.append({"type": "stock_changed", "products": list(exc.shortages)})
            final_cart = None
        view = final_cart if order_dict else cart_view(state, products)
    else:
        view = cart_view(state, products)

    sess.state = state.to_dict()
    sess.language = state.language
    process_ms = round((time.perf_counter() - t_all) * 1000, 2)   # everything above: session, dialogue, stock and order commit; not the final turn-log write
    timing: dict[str, Any] = {**(timing_in or {}), "nlu_ms": nlu_ms, "db_ms": round(max(0.0, process_ms - nlu_ms), 2), "process_ms": process_ms, "mode": input_mode}
    timing["server_ms"] = round(sum(float(timing.get(k) or 0) for k in ("validate_ms", "stt_ms", "process_ms")), 2)   # sum of the server-side stages so far
    cust = Turn(
        session_id=sess.id, role="customer", text=text, language=outcome.parse.language, input_mode=input_mode,
        stt_ms=stt_ms, nlu_ms=Decimal(str(nlu_ms)), detail={"parse": _parse_summary(outcome, products)},
    )
    asst = Turn(
        session_id=sess.id, role="assistant", text=reply, language=outcome.reply_lang, input_mode=input_mode,
        detail={"events": outcome.events, "phase": state.phase, "timing": timing},
    )
    db.add_all([cust, asst])
    db.commit()

    return {
        "session_id": sess.id,
        "transcript": text,
        "language": outcome.parse.language,
        "reply_text": reply,
        "reply_lang": outcome.reply_lang,
        "phase": state.phase,
        "awaiting": state.awaiting,
        "pending": _pending_summary(state, products),
        "cart": view,
        "parse": _parse_summary(outcome, products),
        "events": outcome.events,
        "order": order_dict,
        "low_stock_alerts": alerts,
        "timings": {"stt_ms": stt_ms, "nlu_ms": nlu_ms, "tts_ms": None, **{k: timing[k] for k in ("validate_ms", "db_ms", "process_ms", "server_ms") if k in timing}},
        "customer_turn_id": cust.id,
        "assistant_turn_id": asst.id,
    }


def no_speech_turn(db: Session, session_id: Optional[str], reply: str, reply_lang: str, *, stt_ms: Optional[int] = None,
                   timing_in: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The reply to a recording in which nothing was heard ("I did not catch that"). It is stored as a normal assistant turn, so the voice can be
    fetched for it like any other reply, and it carries the open bill unchanged, so the order desk can draw it without special cases."""
    sess = get_or_create_session(db, session_id)
    state = DialogState.from_dict(sess.state)
    products = load_views(db)
    timing = {**(timing_in or {}), "mode": "voice"}
    timing["server_ms"] = round(sum(float(timing.get(k) or 0) for k in ("validate_ms", "stt_ms")), 2)
    asst = Turn(session_id=sess.id, role="assistant", text=reply, language=reply_lang, input_mode="voice",
                detail={"events": [{"type": "no_speech"}], "phase": state.phase, "timing": timing})
    db.add(asst)
    db.commit()
    return {
        "session_id": sess.id, "transcript": "", "language": reply_lang, "reply_text": reply, "reply_lang": reply_lang, "no_speech": True,
        "phase": state.phase, "awaiting": state.awaiting, "pending": _pending_summary(state, products), "cart": cart_view(state, products),
        "events": [{"type": "no_speech"}], "order": None, "low_stock_alerts": [],
        "timings": {"stt_ms": stt_ms, "nlu_ms": 0, "tts_ms": None, **{k: timing[k] for k in ("validate_ms", "server_ms") if k in timing}},
        "assistant_turn_id": asst.id, "audio": None,
    }


def parse_only(db: Session, catalog: CatalogCache, text: str, language_hint: Optional[str] = None) -> dict[str, Any]:
    """Stateless preview used by the landing-page demo: nothing is stored or reserved."""
    products = load_views(db)
    dm = DialogueManager(catalog.lexicon(db))
    t0 = time.perf_counter()
    outcome = dm.handle(text.strip()[:MAX_TEXT], DialogState(), products, language_hint=language_hint)
    nlu_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "transcript": text,
        "language": outcome.parse.language,
        "reply_text": outcome.reply,
        "reply_lang": outcome.reply_lang,
        "parse": _parse_summary(outcome, products),
        "cart": cart_view(outcome.state, products),
        "pending": _pending_summary(outcome.state, products),
        "timings": {"nlu_ms": nlu_ms},
    }


def attach_audio(db: Session, turn_id: int, audio_id: str, tts_ms: int, cached: bool = False) -> Optional[dict[str, Any]]:
    """Record the spoken reply for an assistant turn and add its time to the turn's timing. Returns the updated timing (None if no such turn).
    Safe to call twice for the same turn: the speech time is added only once."""
    t = db.get(Turn, turn_id)
    if t is None:
        return None
    t.audio_id, t.tts_ms = audio_id, tts_ms
    d = dict(t.detail or {})
    tm = dict(d.get("timing") or {})
    if "tts_ms" not in tm:
        tm["tts_ms"] = tts_ms
        tm["server_ms"] = round(float(tm.get("server_ms") or 0) + (tts_ms or 0), 2)
    tm["tts_cached"] = bool(cached)
    d["timing"] = tm
    t.detail = d
    db.commit()
    return tm


CLIENT_TIMING_KEYS = ("capture_ms", "end_to_reply_ms", "end_to_audio_ms", "upload_bytes")


def record_client_timing(db: Session, turn_id: int, values: dict[str, Any]) -> bool:
    """Store what the browser measured for this turn (time from the end of speech to the reply on screen and to the voice starting).
    These are reported by the browser, so they are kept apart from the server's own stage times."""
    t = db.get(Turn, turn_id)
    if t is None or t.role != "assistant":
        return False
    d = dict(t.detail or {})
    d["client"] = {**(d.get("client") or {}), **{k: v for k, v in values.items() if v is not None}}
    t.detail = d
    db.commit()
    return True


def serialize_turn(t: Turn) -> dict[str, Any]:
    return {
        "id": t.id, "role": t.role, "text": t.text, "language": t.language, "input_mode": t.input_mode,
        "stt_ms": t.stt_ms, "nlu_ms": float(t.nlu_ms) if t.nlu_ms is not None else None, "tts_ms": t.tts_ms,
        "audio_id": t.audio_id, "detail": t.detail or {}, "created_at": t.created_at.isoformat() + "Z",
    }


def session_snapshot(db: Session, session_id: str) -> Optional[dict[str, Any]]:
    s = db.get(ConversationSession, session_id)
    if s is None:
        return None
    state = DialogState.from_dict(s.state)
    products = load_views(db)
    return {
        "session_id": s.id, "phase": state.phase, "awaiting": state.awaiting, "language": s.language, "customer_id": s.customer_id,
        "cart": cart_view(state, products), "pending": _pending_summary(state, products),
        "turns": [serialize_turn(t) for t in s.turns],
        "created_at": s.created_at.isoformat() + "Z", "updated_at": s.updated_at.isoformat() + "Z",
    }


def list_sessions(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.scalars(select(ConversationSession).order_by(ConversationSession.updated_at.desc()).limit(limit))
    out = []
    for s in rows:
        st = DialogState.from_dict(s.state)
        out.append({
            "session_id": s.id, "phase": st.phase, "language": s.language, "turns": len(s.turns),
            "items": len(st.cart), "updated_at": s.updated_at.isoformat() + "Z",
            "preview": next((t.text for t in s.turns if t.role == "customer"), ""),
        })
    return out


class CartError(Exception):
    """A manual cart edit that cannot be applied (unknown item, not enough stock, order already placed)."""

    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


def edit_cart(
    db: Session, session_id: str, product_id: int, qty: Decimal, mode: str = "set",
) -> dict[str, Any]:
    """Change the open bill by hand (the +/- buttons and item search on the order desk).

    Uses the same stock rules as the spoken path: a quantity above the shelf stock is refused, never clamped silently.
    ``qty`` of 0 with mode ``set`` removes the line.
    """
    from ..nlu.dialogue import CartLine
    from ..nlu.units import is_whole, quantize_qty

    sess = db.get(ConversationSession, session_id)
    if sess is None:
        raise CartError("NOT_FOUND", "Session not found", 404)
    state = DialogState.from_dict(sess.state)
    if state.phase in ("completed", "cancelled"):
        raise CartError("ORDER_CLOSED", "This order is already closed. Start a new customer first.")
    if state.queue:
        raise CartError("QUESTION_PENDING", "Answer the assistant's question first, then change the bill.")
    products = load_views(db)
    p = products.get(product_id)
    if p is None or not p.is_active:
        raise CartError("UNKNOWN_PRODUCT", "That item is not in this shop.", 404)
    existing = next((c for c in state.cart if c.product_id == product_id), None)
    have = existing.qty if existing else Decimal(0)
    target = quantize_qty(have + qty if mode == "add" else qty)
    if target < 0:
        target = Decimal(0)
    if target > 0:
        if p.unit in ("pack", "pc") and not is_whole(target):
            raise CartError("WHOLE_NUMBER", f"{p.name_en} is sold in whole {p.unit}s.", 422)
        if target > p.stock:
            left = f"{p.stock.normalize():f}" if p.stock > 0 else "none"
            raise CartError("NOT_ENOUGH_STOCK", f"Only {left} {p.unit} of {p.name_en} in stock.")
        if existing:
            existing.qty = target
        else:
            state.cart.append(CartLine(p.id, target, False))
    elif existing:
        state.cart.remove(existing)
    if state.phase == "confirming":
        state.awaiting = "confirm_order" if state.cart else None
        if not state.cart:
            state.phase = "collecting"
    sess.state = state.to_dict()
    db.commit()
    return {
        "session_id": sess.id, "phase": state.phase, "awaiting": state.awaiting,
        "pending": _pending_summary(state, products), "cart": cart_view(state, products),
    }
