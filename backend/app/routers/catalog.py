from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import REPO_ROOT
from ..deps import get_catalog, get_db
from ..models import CatalogItem
from ..auth import require_owner
from ..services import catalog_items as svc
from ..services import inventory as inv
from ..services.catalog import CatalogCache

router = APIRouter(prefix="/api/catalog", tags=["catalogue"])


class ImportIn(BaseModel):
    price_paise: int = Field(ge=1, le=10_000_000, description="The shop's own selling price per pack, in paise")
    stock: Decimal = Field(default=Decimal(0), ge=0, le=Decimal(1_000_000))
    reorder_level: Decimal = Field(default=Decimal(0), ge=0, le=Decimal(1_000_000))
    cost_paise: Optional[int] = Field(default=None, ge=1, le=10_000_000)


@router.get("")
def list_catalog(
    q: str = "", category: str = "", brand: str = "", unit: str = "", sort: str = "name",
    page: int = 1, page_size: int = 24, db: Session = Depends(get_db),
):
    return svc.search(db, q=q[:80], category=category[:60], brand=brand[:80], unit=unit, sort=sort, page=page, page_size=page_size)


@router.get("/facets")
def catalog_facets(db: Session = Depends(get_db)):
    return svc.facets(db)


@router.get("/source")
def catalog_source(db: Session = Depends(get_db)):
    """Where the catalogue came from, read from data/sources/MANIFEST.json (written by the fetch script)."""
    total = db.scalar(select(func.count(CatalogItem.id))) or 0
    manifest = REPO_ROOT / "data" / "sources" / "MANIFEST.json"
    info: dict = {"rows_loaded": total, "manifest_found": manifest.exists()}
    if manifest.exists():
        src = json.loads(manifest.read_text(encoding="utf-8"))["sources"][0]
        info.update({
            "id": src["id"], "title": src["title"], "origin": src["origin"]["name"], "origin_url": src["origin"]["url"],
            "licence": f'{src["origin"]["licence_database"]}; contents: {src["origin"]["licence_contents"]}',
            "attribution": src["origin"]["attribution"], "retrieved_on": src["retrieved_on"],
            "snapshot_date": src["snapshot_date_from_filename"], "raw_rows": src["rows"], "limitations": src["limitations"],
        })
    return info


@router.get("/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    c = db.get(CatalogItem, item_id)
    if c is None:
        raise HTTPException(404, "Catalogue item not found")
    return {**svc.to_dict(c), "name_raw": c.name_raw, "quantity_raw": c.quantity_raw, "off_categories_raw": c.off_categories_raw,
            "transforms": c.transforms.split("|") if c.transforms else [], "split": c.split,
            "suggested_aliases": svc.make_aliases(c.brand, c.name)}


@router.post("/{item_id}/import", status_code=201, dependencies=[Depends(require_owner)])
def import_item(item_id: int, body: ImportIn, db: Session = Depends(get_db), catalog: CatalogCache = Depends(get_catalog)):
    try:
        p = svc.import_to_shop(db, item_id, body.price_paise, body.stock, body.reorder_level, body.cost_paise)
    except svc.ImportError_ as exc:
        raise HTTPException(404 if exc.code == "NOT_FOUND" else 409, {"code": exc.code, "message": str(exc)})
    catalog.invalidate()
    return inv.serialize_product(p)
