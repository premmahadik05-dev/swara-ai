"""Customer list, detail and per-customer statistics, all computed from the orders table."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Customer, Order, OrderItem

UTC_Z = "Z"


def _stats_subquery():
    return (
        select(
            Order.customer_id.label("cid"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total_paise), 0).label("spent"),
            func.max(Order.created_at).label("last_at"),
        )
        .where(Order.status != "cancelled", Order.customer_id.is_not(None))
        .group_by(Order.customer_id)
        .subquery()
    )


def serialize(c: Customer, orders: int = 0, spent: int = 0, last_at=None) -> dict[str, Any]:
    return {
        "id": c.id, "name": c.name, "phone": c.phone, "language": c.language, "notes": c.notes,
        "is_synthetic": c.is_synthetic, "is_active": c.is_active, "created_at": c.created_at.isoformat() + UTC_Z,
        "orders": int(orders or 0), "spent_paise": int(spent or 0),
        "avg_basket_paise": int(spent / orders) if orders else 0,
        "last_order_at": (last_at.isoformat() + UTC_Z) if last_at else None,
    }


def _filtered(q: str, include_synthetic: bool):
    """Customers with their order statistics, filtered like the Customers screen (shared by the list and the CSV export)."""
    st = _stats_subquery()
    stmt = select(Customer, st.c.orders, st.c.spent, st.c.last_at).outerjoin(st, st.c.cid == Customer.id).where(Customer.is_active.is_(True))
    if not include_synthetic:
        stmt = stmt.where(Customer.is_synthetic.is_(False))
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.like(like)))
    return st, stmt


def _order_by(st, sort: str):
    return {
        "name": (Customer.name,),
        "spent": (func.coalesce(st.c.spent, 0).desc(), Customer.name),
        "orders": (func.coalesce(st.c.orders, 0).desc(), Customer.name),
        "recent": (st.c.last_at.is_(None), st.c.last_at.desc(), Customer.name),
    }.get(sort, (Customer.name,))


def list_customers(
    db: Session, q: str = "", sort: str = "recent", include_synthetic: bool = True, page: int = 1, page_size: int = 20,
) -> dict[str, Any]:
    st, stmt = _filtered(q, include_synthetic)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    rows = db.execute(stmt.order_by(*_order_by(st, sort), Customer.id).limit(page_size).offset((page - 1) * page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [serialize(c, o, s, la) for c, o, s, la in rows]}


EXPORT_MAX_CUSTOMERS = 20_000


def export_customers(db: Session, q: str = "", sort: str = "recent", include_synthetic: bool = True) -> tuple[bytes, bool]:
    """Customers as CSV for the same filters the Customers screen uses. Returns (file bytes, truncated)."""
    from . import export as xp
    st, stmt = _filtered(q, include_synthetic)
    rows = db.execute(stmt.order_by(*_order_by(st, sort), Customer.id).limit(EXPORT_MAX_CUSTOMERS + 1)).all()
    langs = {"gu": "Gujarati", "hi": "Hindi", "en": "English", "hinglish": "Hinglish"}
    header = ["Name", "Phone", "Preferred language", "Orders", "Total spent (INR)", "Average bill (INR)", "Last order (IST)", "Notes", "Demo data"]
    out = []
    for c, o, spent, last_at in rows[:EXPORT_MAX_CUSTOMERS]:
        n = int(o or 0)
        out.append([c.name, c.phone, langs.get(c.language, ""), n, xp.rupees(int(spent or 0)), xp.rupees(int(int(spent or 0) / n) if n else 0),
                    xp.ist(last_at), c.notes, "Yes" if c.is_synthetic else "No"])
    return xp.to_csv(header, out), len(rows) > EXPORT_MAX_CUSTOMERS


def detail(db: Session, customer_id: int) -> Optional[dict[str, Any]]:
    c = db.get(Customer, customer_id)
    if c is None:
        return None
    row = db.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.total_paise), 0), func.max(Order.created_at))
        .where(Order.customer_id == c.id, Order.status != "cancelled")
    ).one()
    out = serialize(c, row[0], row[1], row[2])
    top = db.execute(
        select(OrderItem.product_id, OrderItem.product_name, OrderItem.unit, func.sum(OrderItem.qty), func.sum(OrderItem.line_total_paise))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.customer_id == c.id, Order.status != "cancelled")
        .group_by(OrderItem.product_id, OrderItem.product_name, OrderItem.unit)
        .order_by(func.sum(OrderItem.line_total_paise).desc()).limit(5)
    ).all()
    langs = db.execute(
        select(Order.language, func.count(Order.id)).where(Order.customer_id == c.id, Order.status != "cancelled").group_by(Order.language)
    ).all()
    out["top_products"] = [{"product_id": pid, "name": n, "unit": u, "qty": float(q), "revenue_paise": int(r)} for pid, n, u, q, r in top]
    out["language_mix"] = sorted(({"language": l, "orders": n} for l, n in langs), key=lambda x: -x["orders"])
    return out
