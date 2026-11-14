"""Demo data for a fresh install. What is real and what is not:

* products  : the 65 staples are CURATED by hand (generic names, placeholder prices flagged ``price_basis='demo'``).
* customers : synthetic ("Demo Customer A-H"), flagged ``is_synthetic``. No real person is represented.
* orders    : ~120 days (configurable, DEMO_HISTORY_DAYS) of SYNTHETIC orders flagged ``is_synthetic=True``; the dashboard can exclude them.
* catalogue : REAL product identities (barcode, brand, pack size) from Open Food Facts India, loaded from
              data/processed/catalog_off_india.csv, with no prices. See docs/DATA.md.
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from .config import REPO_ROOT
from .models import CatalogItem, Customer, Order, OrderItem, Product, utcnow
from .nlu.units import line_total_paise
from .seed_data import CATALOG, SYNTHETIC_CUSTOMERS

# relative popularity of SKUs in demo baskets
_POPULAR = {
    "MILK": 10, "SUGAR": 7, "RICE-REGULAR": 6, "ATTA": 6, "ONION": 6, "POTATO": 6, "TOMATO": 5, "SALT": 3,
    "TEA": 5, "BREAD": 5, "EGGS": 5, "OIL-GROUNDNUT": 4, "DAL-TOOR": 4, "BISC-GLUCOSE": 5, "NOODLES": 4,
    "CURD": 4, "BUTTER": 2, "TURMERIC": 2, "SOAP-BATH": 3, "CHIPS": 3, "COLD-DRINK": 3, "POHA": 3, "GHEE": 2,
}
_LANG_MIX = [("gu", 40), ("hinglish", 25), ("en", 20), ("hi", 15)]
_HOUR_WEIGHTS = {7: 3, 8: 8, 9: 9, 10: 6, 11: 3, 12: 2, 13: 2, 14: 1, 15: 2, 16: 4, 17: 8, 18: 10, 19: 9, 20: 5, 21: 2}


def seed_products(db: Session) -> int:
    n = 0
    for c in CATALOG:
        if db.scalar(select(Product.id).where(Product.sku == c["sku"])):
            continue
        db.add(Product(
            sku=c["sku"], name_en=c["name_en"], name_gu=c["name_gu"], name_hi=c["name_hi"], category=c["category"],
            unit=c["unit"], price_paise=int(round(c["price"] * 100)), stock=Decimal(str(c["stock"])),
            reorder_level=Decimal(str(c["reorder_level"])), aliases=c["aliases"], default_for=c["default_for"],
            pack_size=Decimal(c["pack_size"]) if c["pack_size"] else None, pack_size_unit=c["pack_size_unit"],
            source="curated", price_basis="demo",
        ))
        n += 1
    db.commit()
    return n


def seed_customers(db: Session) -> int:
    """Synthetic demo customers; also links older demo orders (matched by name) so upgraded databases get customer history."""
    n = 0
    for name in SYNTHETIC_CUSTOMERS:
        if db.scalar(select(Customer.id).where(Customer.name == name, Customer.is_synthetic.is_(True))):
            continue
        db.add(Customer(name=name, is_synthetic=True, language="", notes="Synthetic demo customer"))
        n += 1
    db.flush()
    for c in db.scalars(select(Customer).where(Customer.is_synthetic.is_(True))):
        db.execute(update(Order).where(Order.customer_id.is_(None), Order.customer_name == c.name, Order.is_synthetic.is_(True)).values(customer_id=c.id))
    db.commit()
    return n


CATALOG_CSV = REPO_ROOT / "data" / "processed" / "catalog_off_india.csv"


def seed_catalog(db: Session, path=CATALOG_CSV) -> int:
    """Load the reference catalogue (real OFF-derived rows, no prices). Idempotent; skipped if the file is absent."""
    if not path.exists() or db.scalar(select(func.count(CatalogItem.id))):
        return 0
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(dict(
                ean=r["ean"], name=r["name"][:160], name_raw=r["name_raw"][:240], brand=r["brand"][:80], category=r["category"],
                pack_size=Decimal(r["pack_size"]), pack_unit=r["pack_unit"], pack_label=r["pack_label"],
                quantity_raw=r["quantity_raw"][:40], off_categories_raw=r["off_categories_raw"][:400],
                last_modified=r["last_modified"], source_id=r["source_id"], provenance=r["provenance"],
                transforms=r["transforms"][:160], split=r["split"],
            ))
    if rows:
        db.execute(insert(CatalogItem), rows)   # one bulk INSERT: 5,000+ rows through the ORM one by one made every app start (and every test) slow
    db.commit()
    return len(rows)


def _qty_for(unit: str, price_paise: int, rng: random.Random) -> Decimal:
    if unit in ("kg", "l"):
        choices = [0.25, 0.5, 1, 1, 1.5, 2, 2, 3, 5] if price_paise < 15000 else [0.1, 0.25, 0.25, 0.5, 1]
        return Decimal(str(rng.choice(choices)))
    return Decimal(rng.choice([1, 1, 2, 2, 3, 4, 6]))


def seed_orders(db: Session, days: int = 120, seed: int = 42) -> int:
    if db.scalar(select(func.count(Order.id)).where(Order.is_synthetic.is_(True))):
        return 0
    rng = random.Random(seed)
    products = list(db.scalars(select(Product)))
    cust_id = {c.name: c.id for c in db.scalars(select(Customer).where(Customer.is_synthetic.is_(True)))}
    weights = [_POPULAR.get(p.sku, 1) for p in products]
    langs, lw = zip(*_LANG_MIX)
    hours, hw = zip(*_HOUR_WEIGHTS.items())
    # The shop runs on IST: pick business hours in local time, store UTC (what the rest of the app expects).
    ist = timedelta(minutes=330)
    now_local = utcnow() + ist
    today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    created = 0
    for d in range(days, -1, -1):  # d == 0 is today: only orders that already "happened"
        day = today - timedelta(days=d)
        base = 22 + (8 if day.weekday() in (5, 6) else 0)  # busier weekends
        for _ in range(rng.randint(base - 6, base + 8)):
            n_items = rng.choices([1, 2, 3, 4, 5, 6], weights=[8, 22, 28, 22, 12, 8])[0]
            picked: dict[int, Product] = {}
            while len(picked) < n_items:
                p = rng.choices(products, weights=weights)[0]
                picked[p.id] = p
            when_local = day + timedelta(hours=rng.choices(hours, weights=hw)[0], minutes=rng.randint(0, 59))
            if when_local > now_local:
                continue
            when = when_local - ist
            # draw in the same order as v1.0 so the seeded demo data stays identical for a given seed
            status = "cancelled" if rng.random() < 0.04 else "fulfilled"
            channel = "voice" if rng.random() < 0.6 else "text"
            language = rng.choices(langs, weights=lw)[0]
            cname = rng.choice(SYNTHETIC_CUSTOMERS)
            order = Order(
                status=status, channel=channel, language=language,
                customer_name=cname, customer_id=cust_id.get(cname), is_synthetic=True, created_at=when,
            )
            total = 0
            for p in picked.values():
                q = _qty_for(p.unit, p.price_paise, rng)
                lt = line_total_paise(p.price_paise, q)
                total += lt
                order.items.append(OrderItem(
                    product_id=p.id, product_name=p.name_en, qty=q, unit=p.unit,
                    unit_price_paise=p.price_paise, line_total_paise=lt,
                ))
            order.total_paise = total
            db.add(order)
            created += 1
        db.flush()
    db.commit()
    return created


def seed_all(db: Session, history_days: int = 120) -> dict[str, int]:
    products = seed_products(db)
    customers = seed_customers(db)
    orders = seed_orders(db, days=max(7, min(int(history_days), 366)))
    catalog = seed_catalog(db)
    return {"products": products, "customers": customers, "orders": orders, "catalog_items": catalog}
