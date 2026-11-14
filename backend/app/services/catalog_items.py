"""Reference catalogue (Open Food Facts India) -> shop inventory.

The catalogue has product identities but NO prices. A shopkeeper imports a row and supplies their own selling price
and opening stock; only then does it become a sellable ``Product``. Spoken aliases are generated conservatively so that
importing branded items cannot make generic words like "milk" or "rice" ambiguous.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import CatalogItem, Product

# words that carry no brand/product identity in a spoken order
_FILLER = {
    "the", "and", "with", "of", "pack", "packet", "pouch", "bottle", "pet", "original", "classic", "regular", "pure",
    "premium", "fresh", "new", "special", "flavour", "flavoured", "flavor", "flavored", "ltr", "ml", "gm", "gms", "kg",
    "gram", "grams", "litre", "liter", "rs", "mrp", "plain", "natural", "super", "best", "good",
}
_GENERIC_ALONE = {
    "milk", "rice", "atta", "flour", "sugar", "salt", "oil", "ghee", "tea", "coffee", "dal", "biscuit", "biscuits", "butter",
    "curd", "bread", "water", "juice", "noodles", "chips", "paneer", "masala", "powder", "honey", "jam", "sauce", "pickle",
}
# words used while ordering or chatting; an alias made only of these could hijack a normal sentence
_CONVERSATIONAL = {
    "hello", "hi", "hey", "thank", "thanks", "you", "your", "please", "yes", "no", "ok", "okay", "bhai", "bhaiya", "bhaiyya",
    "kaka", "uncle", "aunty", "bas", "haan", "han", "nahi", "nahin", "cancel", "confirm", "order", "add", "remove", "bill",
    "total", "want", "give", "need", "one", "two", "three", "half", "more", "less", "what", "how", "are", "very", "much",
}
_TOKEN = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower().replace("’", "'"))


def _strip_size(name: str) -> str:
    """Remove a trailing/embedded pack-size such as '1kg', '500 ml', '200 g' from a product name."""
    return re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kg|kgs|g|gm|gms|gr|gram|grams|l|ltr|litre|liter|ml|pcs?|pieces?)\b\.?", " ", name, flags=re.I)


def display_name(item: CatalogItem | dict) -> str:
    brand = (item["brand"] if isinstance(item, dict) else item.brand).strip()
    name = (item["name"] if isinstance(item, dict) else item.name).strip()
    label = (item["pack_label"] if isinstance(item, dict) else item.pack_label).strip()
    base = name if (not brand or name.lower().startswith(brand.lower())) else f"{brand} {name}"
    base = re.sub(r"\s+", " ", _strip_size(base)).strip(" -,.")
    full = f"{base} {label}".strip()
    return full[:120]


def make_aliases(brand: str, name: str, taken: Optional[set[str]] = None) -> list[str]:
    """Spoken names for an imported item: the full name and brand + first product words.

    Never emits a generic word alone ("milk"), never a single token shorter than 4 letters, and skips anything
    already used by another product (``taken``, lower-case), so existing orders keep resolving exactly as before.
    """
    taken = taken or set()
    clean = re.sub(r"\s+", " ", _strip_size(name)).strip()
    b_tokens = [t for t in _tokens(brand) if not t.isdigit()]
    n_tokens = [t for t in _tokens(clean) if t not in _FILLER and not t.isdigit()]
    rest = [t for t in n_tokens if t not in b_tokens]
    candidates: list[str] = []
    if b_tokens or rest:
        candidates.append(" ".join(b_tokens + rest))
    if b_tokens and rest:
        candidates.append(" ".join(b_tokens + rest[:2]))
        candidates.append(" ".join(b_tokens + rest[:1]))
    if b_tokens and not rest:
        candidates.append(" ".join(b_tokens))
    out: list[str] = []
    for c in candidates:
        c = c.strip()
        words = c.split()
        if not c or len(c) > 60 or c in out or c.lower() in taken:
            continue
        if len(words) == 1 and (len(c) < 4 or c in _GENERIC_ALONE):
            continue
        if sum(ch.isalpha() for ch in c) < 6 or all(w in _CONVERSATIONAL or w in _FILLER for w in words):
            continue
        out.append(c)
    return out[:6]


def to_dict(c: CatalogItem, imported_eans: Optional[set[str]] = None) -> dict:
    return {
        "id": c.id, "ean": c.ean, "name": c.name, "brand": c.brand, "category": c.category,
        "pack_size": float(c.pack_size), "pack_unit": c.pack_unit, "pack_label": c.pack_label,
        "display_name": display_name(c), "last_modified": c.last_modified, "source_id": c.source_id,
        "provenance": c.provenance, "in_shop": bool(imported_eans and c.ean in imported_eans),
    }


def search(
    db: Session, q: str = "", category: str = "", brand: str = "", unit: str = "", sort: str = "name",
    page: int = 1, page_size: int = 24,
) -> dict:
    stmt = select(CatalogItem)
    for tok in _tokens(q)[:6]:
        like = f"%{tok}%"
        stmt = stmt.where(or_(CatalogItem.name.ilike(like), CatalogItem.brand.ilike(like), CatalogItem.ean.like(like)))
    if category:
        stmt = stmt.where(CatalogItem.category == category)
    if brand:
        stmt = stmt.where(func.lower(CatalogItem.brand) == brand.lower())
    if unit in ("kg", "l", "pc"):
        stmt = stmt.where(CatalogItem.pack_unit == unit)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {"name": (CatalogItem.name,), "brand": (CatalogItem.brand, CatalogItem.name),
             "recent": (CatalogItem.last_modified.desc(), CatalogItem.name)}.get(sort, (CatalogItem.name,))
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    rows = list(db.scalars(stmt.order_by(*order, CatalogItem.id).limit(page_size).offset((page - 1) * page_size)))
    imported = set(db.scalars(select(Product.ean).where(Product.ean.in_([r.ean for r in rows])))) if rows else set()
    return {"total": total, "page": page, "page_size": page_size, "items": [to_dict(r, imported) for r in rows]}


def facets(db: Session) -> dict:
    cats = db.execute(select(CatalogItem.category, func.count()).group_by(CatalogItem.category).order_by(func.count().desc())).all()
    brands = db.execute(
        select(CatalogItem.brand, func.count()).where(CatalogItem.brand != "").group_by(CatalogItem.brand)
        .order_by(func.count().desc(), CatalogItem.brand).limit(40)
    ).all()
    total = db.scalar(select(func.count(CatalogItem.id))) or 0
    return {"total": total, "categories": [{"name": c, "count": n} for c, n in cats], "brands": [{"name": b, "count": n} for b, n in brands]}


class ImportError_(Exception):
    """Raised for a rejected import (unknown id, already in the shop)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def import_to_shop(
    db: Session, catalog_id: int, price_paise: int, stock: Decimal, reorder_level: Decimal, cost_paise: Optional[int],
) -> Product:
    item = db.get(CatalogItem, catalog_id)
    if item is None:
        raise ImportError_("NOT_FOUND", "Catalogue item not found")
    if db.scalar(select(Product.id).where(Product.ean == item.ean)):
        raise ImportError_("ALREADY_IMPORTED", "This product is already in your shop")
    # An alias already used by another product is normally skipped, so that existing orders keep resolving exactly as before.
    # The exception is a PACK FAMILY: another imported product of the same brand (Amul ghee 500 g and Amul ghee 1 l). Both may
    # answer to "amul ghee"; the parser then sees two candidates and the dialogue asks which pack, instead of quietly handing
    # over whichever pack happened to be imported first.
    taken: set[str] = set()
    brand_l = (item.brand or "").strip().lower()
    for aliases, other_brand, other_source in db.execute(select(Product.aliases, Product.brand, Product.source)):
        same_family = bool(brand_l) and (other_brand or "").strip().lower() == brand_l and other_source == "off_india"
        if not same_family:
            taken.update(a.lower() for a in (aliases or []))
    name = display_name(item)
    p = Product(
        sku=f"EAN-{item.ean}", name_en=name, name_gu="", name_hi="", category=item.category, unit="pack",
        price_paise=price_paise, stock=stock, reorder_level=reorder_level, cost_paise=cost_paise,
        pack_size=Decimal(item.pack_size) if item.pack_unit in ("kg", "l") else None,
        pack_size_unit=item.pack_unit if item.pack_unit in ("kg", "l") else None,
        aliases=make_aliases(item.brand, item.name, taken), default_for=[],
        brand=item.brand, ean=item.ean, source="off_india", source_ref=f"{item.source_id}:{item.ean}", price_basis="shop",
    )
    db.add(p)
    db.commit()
    return p
