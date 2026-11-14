"""Order creation with atomic stock decrement, status changes and low-stock alerts."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Product, StockMovement
from ..nlu.dialogue import CartLine
from ..nlu.lexicon import ProductView
from ..nlu.units import line_total_paise, quantize_qty


class InsufficientStock(Exception):
    def __init__(self, shortages: dict[int, Decimal]):
        super().__init__("insufficient stock")
        self.shortages = shortages  # product_id -> currently available


class OrderError(Exception):
    pass


def create_order(
    db: Session, cart: list[CartLine], products: dict[int, ProductView], *,
    session_id: Optional[str], channel: str, language: str, customer_name: str = "Walk-in customer",
    customer_id: Optional[int] = None,
) -> tuple[Order, list[dict]]:
    """Create an order and decrement stock atomically.

    Each line is protected by ``UPDATE ... WHERE stock >= qty`` so two concurrent orders
    can never oversell.  If any line fails, lines already decremented are put back.
    """
    if not cart:
        raise OrderError("empty cart")
    done: list[tuple[int, Decimal]] = []
    shortages: dict[int, Decimal] = {}
    for line in cart:
        q = quantize_qty(line.qty)
        res = db.execute(
            update(Product).where(Product.id == line.product_id, Product.stock >= q, Product.is_active.is_(True))
            .values(stock=Product.stock - q)
        )
        if res.rowcount == 1:
            done.append((line.product_id, q))
        else:
            cur = db.scalar(select(Product.stock).where(Product.id == line.product_id))
            shortages[line.product_id] = Decimal(cur or 0)
    if shortages:
        for pid, q in done:  # compensate
            db.execute(update(Product).where(Product.id == pid).values(stock=Product.stock + q))
        db.commit()
        raise InsufficientStock(shortages)

    order = Order(session_id=session_id, status="confirmed", channel=channel, language=language, customer_name=customer_name, customer_id=customer_id)
    total = 0
    for line in cart:
        p = products[line.product_id]
        q = quantize_qty(line.qty)
        lt = line_total_paise(p.price_paise, q)
        total += lt
        order.items.append(OrderItem(
            product_id=p.id, product_name=p.name_en, qty=q, unit=p.unit,
            unit_price_paise=p.price_paise, line_total_paise=lt,
        ))
    order.total_paise = total
    db.add(order)
    db.flush()
    for pid, q in done:
        db.add(StockMovement(product_id=pid, delta=-q, reason="order", order_id=order.id))
    db.commit()
    alerts = low_stock_alerts(db, [pid for pid, _ in done])
    return order, alerts


def low_stock_alerts(db: Session, product_ids: Optional[list[int]] = None) -> list[dict]:
    stmt = select(Product).where(Product.is_active.is_(True), Product.stock <= Product.reorder_level)
    if product_ids is not None:
        stmt = stmt.where(Product.id.in_(product_ids))
    out = []
    for p in db.scalars(stmt.order_by(Product.stock)):
        out.append({
            "product_id": p.id, "sku": p.sku, "name": p.name_en, "unit": p.unit,
            "stock": float(p.stock), "reorder_level": float(p.reorder_level),
            "severity": "out" if p.stock <= 0 else "low",
        })
    return out


def set_status(db: Session, order_id: int, new_status: str) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise OrderError("order not found")
    if new_status not in ("fulfilled", "cancelled"):
        raise OrderError("status must be fulfilled or cancelled")
    if order.status == new_status:
        return order
    if order.status != "confirmed":
        raise OrderError(f"cannot change a {order.status} order")
    if new_status == "cancelled":
        for it in order.items:
            db.execute(update(Product).where(Product.id == it.product_id).values(stock=Product.stock + it.qty))
            db.add(StockMovement(product_id=it.product_id, delta=it.qty, reason="cancel", order_id=order.id))
    order.status = new_status
    db.commit()
    return order


def serialize_order(o: Order) -> dict:
    return {
        "id": o.id, "code": o.code, "status": o.status, "channel": o.channel, "language": o.language,
        "customer_name": o.customer_name, "customer_id": o.customer_id, "total_paise": o.total_paise, "is_synthetic": o.is_synthetic,
        "created_at": o.created_at.isoformat() + "Z", "session_id": o.session_id,
        "items": [
            {"product_id": i.product_id, "name": i.product_name, "qty": float(i.qty), "unit": i.unit,
             "unit_price_paise": i.unit_price_paise, "line_total_paise": i.line_total_paise}
            for i in o.items
        ],
    }
