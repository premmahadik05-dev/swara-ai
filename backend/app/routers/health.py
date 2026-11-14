from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import brand
from ..config import Settings
from ..deps import get_db
from ..models import Product

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    s = request.app.state.settings
    return {
        "app": brand.NAME, "status": "ok", "db": "ok", "products": db.scalar(select(func.count(Product.id))) or 0,
        "gnani_configured": s.gnani_configured, "version": request.app.version,
        "store_name": s.store_name,
        # True while the shop still carries the built-in demo name. The dashboard's setup checklist reads this; it never guesses from the text.
        "store_name_is_default": s.store_name == Settings.model_fields["store_name"].default,
    }
