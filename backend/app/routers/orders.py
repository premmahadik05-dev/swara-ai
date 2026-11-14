from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..languages import LANGUAGES
from ..models import Order
from ..auth import require_owner
from ..services import export as xp
from ..services import orders as order_svc
from ..services import payments as pay_svc
from ..auth import Principal, require_user

router = APIRouter(prefix="/api", tags=["orders"])


class StatusIn(BaseModel):
    status: Literal["fulfilled", "cancelled"]


STATUSES = ("confirmed", "fulfilled", "cancelled")
EXPORT_MAX_ORDERS = 20_000


def _order_filters(q: str, customer_id: Optional[int], language: Optional[str], channel: Optional[str], include_synthetic: bool):
    """The WHERE part shared by the Orders list and its CSV export, so the file always holds exactly what the screen filtered to."""
    stmt = select(Order)
    q = (q or "").strip()[:60]
    if q:
        m = re.fullmatch(r"(?:(?:SW|DM)-\d{6}-)?0*(\d{1,9})", q, flags=re.I)   # DM- was the prefix before the rename; old codes still resolve
        like = f"%{q}%"
        cond = Order.customer_name.ilike(like)
        stmt = stmt.where(or_(cond, Order.id == int(m.group(1))) if m else cond)
    if customer_id is not None:
        stmt = stmt.where(Order.customer_id == customer_id)
    if language in LANGUAGES:
        stmt = stmt.where(Order.language == language)
    if channel in ("voice", "text"):
        stmt = stmt.where(Order.channel == channel)
    if not include_synthetic:
        stmt = stmt.where(Order.is_synthetic.is_(False))
    return stmt


_SORT = {"oldest": (Order.created_at, Order.id), "total_high": (Order.total_paise.desc(), Order.id.desc()),
         "total_low": (Order.total_paise, Order.id)}


@router.get("/orders")
def list_orders(
    status: Optional[str] = None, channel: Optional[str] = None, include_synthetic: bool = True,
    q: str = "", customer_id: Optional[int] = None, language: Optional[str] = None, sort: str = "newest",
    limit: int = 25, offset: int = 0, db: Session = Depends(get_db),
):
    limit, offset = min(max(limit, 1), 100), max(offset, 0)
    stmt = _order_filters(q, customer_id, language, channel, include_synthetic)
    # per-status counts honour every filter except status itself, so the tabs can show how many orders each would list
    by_status = {
        st: db.scalar(select(func.count()).select_from(stmt.where(Order.status == st).subquery())) or 0
        for st in ("confirmed", "fulfilled", "cancelled")
    }
    counts = {**by_status, "all": sum(by_status.values())}
    if status in ("confirmed", "fulfilled", "cancelled"):
        stmt = stmt.where(Order.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.order_by(*_SORT.get(sort, (Order.created_at.desc(), Order.id.desc()))).limit(limit).offset(offset)))
    paid = pay_svc.payment_summaries(db, [o.id for o in rows])  # additive: status "none" for every order that never had a payment (all orders before 2.7.0)
    return {"total": total, "limit": limit, "offset": offset, "counts": counts, "items": [{**order_svc.serialize_order(o), "payment": paid[o.id]} for o in rows]}


@router.get("/orders/export.csv")
def export_orders(
    status: Optional[str] = None, channel: Optional[str] = None, include_synthetic: bool = True,
    q: str = "", customer_id: Optional[int] = None, language: Optional[str] = None, sort: str = "newest", db: Session = Depends(get_db),
):
    """Orders as CSV, one row per bill line, for the same filters the Orders screen uses. Declared before /orders/{order_id}."""
    stmt = _order_filters(q, customer_id, language, channel, include_synthetic)
    if status in STATUSES:
        stmt = stmt.where(Order.status == status)
    rows = list(db.scalars(stmt.order_by(*_SORT.get(sort, (Order.created_at.desc(), Order.id.desc()))).limit(EXPORT_MAX_ORDERS + 1)))
    truncated = len(rows) > EXPORT_MAX_ORDERS
    header = ["Bill", "Date (IST)", "Status", "Customer", "Taken by", "Language", "Item", "Quantity", "Unit", "Rate (INR)", "Amount (INR)", "Bill total (INR)", "Demo data"]
    out = []
    for o in rows[:EXPORT_MAX_ORDERS]:
        common = [o.code, xp.ist(o.created_at), o.status, o.customer_name, "Voice" if o.channel == "voice" else "Typed", o.language]
        for i in o.items:
            out.append([*common, i.product_name, xp.qty(i.qty), i.unit, xp.rupees(i.unit_price_paise), xp.rupees(i.line_total_paise), xp.rupees(o.total_paise), "Yes" if o.is_synthetic else "No"])
    return xp.csv_response(xp.to_csv(header, out), "orders", truncated)


@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if o is None:
        raise HTTPException(404, "Order not found")
    return {**order_svc.serialize_order(o), "payment": pay_svc.payment_summaries(db, [o.id])[o.id]}


@router.post("/orders/{order_id}/status", dependencies=[Depends(require_owner)])
def change_status(order_id: int, body: StatusIn, db: Session = Depends(get_db), p: Principal = Depends(require_user)):
    if body.status == "cancelled":
        order = db.get(Order, order_id)
        if order is not None and order.status == "confirmed":
            pay_svc.before_order_cancel(db, order, p.user)  # money collected and not refunded blocks it; a still-open payment is closed
    try:
        o = order_svc.set_status(db, order_id, body.status)
    except order_svc.OrderError as exc:
        raise HTTPException(404 if "not found" in str(exc) else 409, str(exc))
    return {**order_svc.serialize_order(o), "payment": pay_svc.payment_summaries(db, [o.id])[o.id]}
