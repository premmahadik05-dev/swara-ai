from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..models import Product, StockMovement
from ..nlu.units import quantize_qty


class InventoryError(Exception):
    pass


def serialize_product(p: Product) -> dict:
    status = "out" if p.stock <= 0 else "low" if p.stock <= p.reorder_level else "ok"
    return {
        "id": p.id, "sku": p.sku, "name_en": p.name_en, "name_gu": p.name_gu, "name_hi": p.name_hi,
        "category": p.category, "unit": p.unit, "price_paise": p.price_paise, "stock": float(p.stock),
        "reorder_level": float(p.reorder_level),
        "pack_size": float(p.pack_size) if p.pack_size is not None else None, "pack_size_unit": p.pack_size_unit,
        "aliases": list(p.aliases or []), "default_for": list(p.default_for or []),
        "is_active": p.is_active, "stock_status": status,
        "brand": p.brand or "", "ean": p.ean, "source": p.source, "source_ref": p.source_ref,
        "price_basis": p.price_basis, "cost_paise": p.cost_paise,
        "stock_value_paise": int((Decimal(p.stock) * p.price_paise).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
        "updated_at": p.updated_at.isoformat() + "Z",
    }


def list_products(db: Session, q: Optional[str] = None, category: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
    stmt = select(Product).where(Product.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name_en.ilike(like), Product.sku.ilike(like), Product.name_gu.like(like), Product.name_hi.like(like)))
    if category:
        stmt = stmt.where(Product.category == category)
    rows = [serialize_product(p) for p in db.scalars(stmt.order_by(Product.category, Product.name_en))]
    if status in ("low", "out", "ok"):
        rows = [r for r in rows if r["stock_status"] == status]
    return rows


def restock(db: Session, product_id: int, qty: Decimal) -> Product:
    if qty <= 0:
        raise InventoryError("restock quantity must be positive")
    p = db.get(Product, product_id)
    if p is None:
        raise InventoryError("product not found")
    q = quantize_qty(qty)
    p.stock = Decimal(p.stock) + q
    db.add(StockMovement(product_id=p.id, delta=q, reason="restock"))
    db.commit()
    return p


def clean_aliases(values: list[str]) -> list[str]:
    out, seen = [], set()
    for v in values:
        v = (v or "").strip()
        if v and len(v) <= 80 and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out[:60]


_SORTS = {
    "name": (Product.name_en,), "category": (Product.category, Product.name_en), "stock": (Product.stock, Product.name_en),
    "price": (Product.price_paise.desc(), Product.name_en), "value": ((Product.stock * Product.price_paise).desc(), Product.name_en),
    "status": (case((Product.stock <= 0, 0), (Product.stock <= Product.reorder_level, 1), else_=2), Product.name_en),
}


def _inventory_base(q: Optional[str], category: str, source: str):
    """Active products matching the search, category and source filters (shared by the Inventory list and its CSV export)."""
    base = select(Product).where(Product.is_active.is_(True))
    if q:
        for tok in q.strip().split()[:5]:
            like = f"%{tok}%"
            base = base.where(or_(Product.name_en.ilike(like), Product.sku.ilike(like), Product.brand.ilike(like),
                                  Product.ean.like(like), Product.name_gu.like(like), Product.name_hi.like(like)))
    if category:
        base = base.where(Product.category == category)
    if source in ("curated", "off_india", "manual"):
        base = base.where(Product.source == source)
    return base


def _status_filter(stmt, status: str):
    if status == "out":
        return stmt.where(Product.stock <= 0)
    if status == "low":
        return stmt.where(Product.stock > 0, Product.stock <= Product.reorder_level)
    if status == "ok":
        return stmt.where(Product.stock > Product.reorder_level)
    return stmt


def list_inventory(
    db: Session, q: Optional[str] = None, category: str = "", status: str = "", source: str = "", sort: str = "name",
    page: int = 1, page_size: int = 25,
) -> dict[str, Any]:
    """Paginated, sortable inventory with tab counts (counts ignore the status filter so tabs stay stable)."""
    base = _inventory_base(q, category, source)
    sub = base.subquery()
    counts = {"all": 0, "ok": 0, "low": 0, "out": 0}
    status_col = case((sub.c.stock <= 0, "out"), (sub.c.stock <= sub.c.reorder_level, "low"), else_="ok")
    for st, n in db.execute(select(status_col, func.count()).group_by(status_col)).all():
        counts[st] = n
        counts["all"] += n
    stmt = _status_filter(base, status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    rows = db.scalars(stmt.order_by(*_SORTS.get(sort, _SORTS["name"]), Product.id).limit(page_size).offset((page - 1) * page_size))
    return {"total": total, "page": page, "page_size": page_size, "counts": counts, "items": [serialize_product(p) for p in rows]}


EXPORT_MAX_PRODUCTS = 20_000
_STATUS_TEXT = {"ok": "In stock", "low": "Running low", "out": "Finished"}
_SOURCE_TEXT = {"curated": "Curated staple", "off_india": "Open Food Facts India", "manual": "Added by you"}


def export_inventory(db: Session, q: str = "", category: str = "", status: str = "", source: str = "", sort: str = "name") -> tuple[bytes, bool]:
    """Stock as CSV for the same filters the Inventory screen uses. Returns (file bytes, truncated)."""
    from . import export as xp
    stmt = _status_filter(_inventory_base(q or None, category, source), status)
    rows = list(db.scalars(stmt.order_by(*_SORTS.get(sort, _SORTS["name"]), Product.id).limit(EXPORT_MAX_PRODUCTS + 1)))
    header = ["SKU", "Name", "Gujarati name", "Hindi name", "Category", "Brand", "Unit", "Price (INR)", "Price basis", "Stock", "Reorder level",
              "Status", "Stock value at price (INR)", "Source"]
    out = []
    for p in rows[:EXPORT_MAX_PRODUCTS]:
        d = serialize_product(p)
        out.append([p.sku, p.name_en, p.name_gu, p.name_hi, p.category, p.brand or "", p.unit, xp.rupees(p.price_paise),
                    "Your price" if p.price_basis == "shop" else "Demo price", xp.qty(p.stock), xp.qty(p.reorder_level),
                    _STATUS_TEXT[d["stock_status"]], xp.rupees(d["stock_value_paise"]), _SOURCE_TEXT.get(p.source, p.source)])
    return xp.to_csv(header, out), len(rows) > EXPORT_MAX_PRODUCTS
