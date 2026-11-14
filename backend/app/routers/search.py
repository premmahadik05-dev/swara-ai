from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import CatalogItem, Customer, Order, Product

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def global_search(q: str = "", limit: int = 5, db: Session = Depends(get_db)):
    """Command-bar search across products, customers, orders and the reference catalogue."""
    q = q.strip()[:60]
    limit = min(max(limit, 1), 10)
    if len(q) < 2:
        return {"query": q, "products": [], "customers": [], "orders": [], "catalog": []}
    like = f"%{q}%"
    products = db.scalars(
        select(Product).where(Product.is_active.is_(True), or_(
            Product.name_en.ilike(like), Product.sku.ilike(like), Product.brand.ilike(like), Product.ean.like(like),
            Product.name_gu.like(like), Product.name_hi.like(like))).order_by(Product.name_en).limit(limit)
    )
    customers = db.scalars(
        select(Customer).where(Customer.is_active.is_(True), or_(Customer.name.ilike(like), Customer.phone.like(like))).order_by(Customer.name).limit(limit)
    )
    m = re.fullmatch(r"(?:(?:SW|DM)-\d{6}-)?0*(\d{1,9})", q, flags=re.I)   # DM- was the prefix before the rename; old codes still resolve
    ocond = Order.customer_name.ilike(like)
    orders = db.scalars(select(Order).where(or_(ocond, Order.id == int(m.group(1))) if m else ocond).order_by(Order.created_at.desc()).limit(limit))
    cat = db.scalars(select(CatalogItem).where(or_(CatalogItem.name.ilike(like), CatalogItem.brand.ilike(like), CatalogItem.ean.like(like))).order_by(CatalogItem.name).limit(limit))
    cat_total = db.scalar(select(func.count(CatalogItem.id)).where(or_(CatalogItem.name.ilike(like), CatalogItem.brand.ilike(like), CatalogItem.ean.like(like)))) or 0
    return {
        "query": q,
        "products": [{"id": p.id, "title": p.name_en, "subtitle": f"{p.category} · {p.sku}"} for p in products],
        "customers": [{"id": c.id, "title": c.name, "subtitle": "Demo customer" if c.is_synthetic else (c.phone or "Customer")} for c in customers],
        "orders": [{"id": o.id, "title": o.code, "subtitle": f"{o.customer_name} · {o.status}"} for o in orders],
        "catalog": [{"id": c.id, "title": c.name, "subtitle": f"{c.brand or 'Unbranded'} · {c.pack_label}"} for c in cat],
        "catalog_total": int(cat_total),
    }
