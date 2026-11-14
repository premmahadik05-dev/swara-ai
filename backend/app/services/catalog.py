"""Product views + cached lexicon.  Stock/price are read fresh each turn; the alias index is cached."""
from __future__ import annotations

from decimal import Decimal
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product
from ..nlu.lexicon import Lexicon, ProductView
from ..nlu.product_names import names_for


def to_view(p: Product) -> ProductView:
    return ProductView(
        id=p.id, sku=p.sku, name_en=p.name_en, name_gu=p.name_gu or "", name_hi=p.name_hi or "", unit=p.unit,
        price_paise=p.price_paise, stock=Decimal(p.stock), aliases=list(p.aliases or []),
        default_for=list(p.default_for or []),
        pack_size=Decimal(p.pack_size) if p.pack_size is not None else None, pack_size_unit=p.pack_size_unit,
        category=p.category or "", reorder_level=Decimal(p.reorder_level or 0), is_active=bool(p.is_active),
        names=names_for(p.sku),
    )


def load_views(db: Session, include_inactive: bool = False) -> dict[int, ProductView]:
    stmt = select(Product)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    return {p.id: to_view(p) for p in db.scalars(stmt)}


class CatalogCache:
    def __init__(self) -> None:
        self._lex: Lexicon | None = None
        self._lock = Lock()

    def invalidate(self) -> None:
        with self._lock:
            self._lex = None

    def lexicon(self, db: Session) -> Lexicon:
        with self._lock:
            if self._lex is None:
                self._lex = Lexicon(list(load_views(db).values()))
            return self._lex
