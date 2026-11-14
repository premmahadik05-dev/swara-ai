from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..deps import get_catalog, get_db
from ..models import Product, StockMovement
from ..auth import require_owner
from ..services import export as xp
from ..services import inventory as inv
from ..services.catalog import CatalogCache
from ..services.orders import low_stock_alerts

router = APIRouter(prefix="/api", tags=["inventory"])


class ProductIn(BaseModel):
    sku: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{1,39}$")
    name_en: str = Field(min_length=1, max_length=120)
    name_gu: str = Field(default="", max_length=120)
    name_hi: str = Field(default="", max_length=120)
    category: str = Field(default="", max_length=60)
    unit: Literal["kg", "l", "pack", "pc"]
    price_paise: int = Field(ge=1, le=10_000_000)
    stock: Decimal = Field(default=Decimal(0), ge=0, le=Decimal(1_000_000))
    reorder_level: Decimal = Field(default=Decimal(0), ge=0, le=Decimal(1_000_000))
    pack_size: Optional[Decimal] = Field(default=None, gt=0, le=Decimal(10_000))
    pack_size_unit: Optional[Literal["kg", "l"]] = None
    aliases: list[str] = Field(default_factory=list, max_length=60)
    default_for: list[str] = Field(default_factory=list, max_length=20)
    brand: str = Field(default="", max_length=80)
    cost_paise: Optional[int] = Field(default=None, ge=1, le=10_000_000)


class ProductPatch(BaseModel):
    name_en: Optional[str] = Field(default=None, min_length=1, max_length=120)
    name_gu: Optional[str] = Field(default=None, max_length=120)
    name_hi: Optional[str] = Field(default=None, max_length=120)
    category: Optional[str] = Field(default=None, max_length=60)
    price_paise: Optional[int] = Field(default=None, ge=1, le=10_000_000)
    reorder_level: Optional[Decimal] = Field(default=None, ge=0, le=Decimal(1_000_000))
    aliases: Optional[list[str]] = Field(default=None, max_length=60)
    is_active: Optional[bool] = None
    brand: Optional[str] = Field(default=None, max_length=80)
    cost_paise: Optional[int] = Field(default=None, ge=1, le=10_000_000)


class RestockIn(BaseModel):
    qty: Decimal = Field(gt=0, le=Decimal(100_000))


@router.get("/products")
def products(q: Optional[str] = None, category: Optional[str] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    return inv.list_products(db, q=q[:60] if q else None, category=category, status=status)


@router.get("/inventory")
def inventory_list(
    q: str = "", category: str = "", status: str = "", source: str = "", sort: str = "name",
    page: int = 1, page_size: int = 25, db: Session = Depends(get_db),
):
    """Paginated inventory for the Inventory screen (the plain /products list is kept for compatibility)."""
    return inv.list_inventory(db, q=q[:60] or None, category=category[:60], status=status, source=source, sort=sort, page=page, page_size=page_size)


@router.get("/inventory/export.csv")
def inventory_export(q: str = "", category: str = "", status: str = "", source: str = "", sort: str = "name", db: Session = Depends(get_db)):
    """Stock as CSV, filtered like the Inventory screen. Declared before /products/{id}-style routes so the path is never read as an id."""
    body, truncated = inv.export_inventory(db, q=q[:60], category=category[:60], status=status, source=source, sort=sort)
    return xp.csv_response(body, "inventory", truncated)


@router.get("/products/{product_id}")
def product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "Product not found")
    return inv.serialize_product(p)


@router.post("/products", status_code=201, dependencies=[Depends(require_owner)])
def create_product(body: ProductIn, db: Session = Depends(get_db), catalog: CatalogCache = Depends(get_catalog)):
    p = Product(
        sku=body.sku, name_en=body.name_en, name_gu=body.name_gu, name_hi=body.name_hi, category=body.category,
        unit=body.unit, price_paise=body.price_paise, stock=body.stock, reorder_level=body.reorder_level,
        pack_size=body.pack_size, pack_size_unit=body.pack_size_unit,
        aliases=inv.clean_aliases(body.aliases), default_for=inv.clean_aliases(body.default_for),
        brand=body.brand.strip(), cost_paise=body.cost_paise, source="manual", price_basis="shop",
    )
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A product with this SKU already exists")
    catalog.invalidate()
    return inv.serialize_product(p)


@router.patch("/products/{product_id}", dependencies=[Depends(require_owner)])
def patch_product(product_id: int, body: ProductPatch, db: Session = Depends(get_db), catalog: CatalogCache = Depends(get_catalog)):
    p = db.get(Product, product_id)
    if p is None:
        raise HTTPException(404, "Product not found")
    data = body.model_dump(exclude_unset=True)
    if "aliases" in data and data["aliases"] is not None:
        data["aliases"] = inv.clean_aliases(data["aliases"])
    for k, v in data.items():
        setattr(p, k, v)
    if "price_paise" in data:
        p.price_basis = "shop"  # the shopkeeper has now set this price themselves
    db.commit()
    catalog.invalidate()
    return inv.serialize_product(p)


@router.post("/products/{product_id}/restock", dependencies=[Depends(require_owner)])
def restock(product_id: int, body: RestockIn, db: Session = Depends(get_db)):
    try:
        p = inv.restock(db, product_id, body.qty)
    except inv.InventoryError as exc:
        raise HTTPException(404 if "not found" in str(exc) else 422, str(exc))
    return inv.serialize_product(p)


@router.get("/inventory/alerts")
def alerts(db: Session = Depends(get_db)):
    return low_stock_alerts(db)


@router.get("/inventory/categories")
def categories(db: Session = Depends(get_db)):
    rows = db.execute(select(Product.category, func.count(Product.id)).where(Product.is_active.is_(True)).group_by(Product.category).order_by(Product.category)).all()
    return [{"category": c, "count": n} for c, n in rows]


@router.get("/inventory/movements")
def movements(limit: int = 30, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 200)
    rows = db.execute(
        select(StockMovement, Product.name_en).join(Product, Product.id == StockMovement.product_id)
        .order_by(StockMovement.id.desc()).limit(limit)
    ).all()
    return [{"id": m.id, "product": n, "delta": float(m.delta), "reason": m.reason, "order_id": m.order_id, "created_at": m.created_at.isoformat() + "Z"} for m, n in rows]
