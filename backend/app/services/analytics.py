"""Dashboard aggregates computed from the live database (no hard-coded numbers)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ApiCall, Order, OrderItem, Product, Turn, utcnow

IST_OFFSET = timedelta(minutes=330)  # store runs on India Standard Time


def _pctl(values: list[int], p: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, round((p / 100) * (len(s) - 1))))
    return s[k]


def overview(db: Session, days: int = 30, include_synthetic: bool = True) -> dict[str, Any]:
    now_local = utcnow() + IST_OFFSET
    start_local = (now_local - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local - IST_OFFSET
    stmt = select(Order).where(Order.created_at >= start_utc)
    if not include_synthetic:
        stmt = stmt.where(Order.is_synthetic.is_(False))
    orders = list(db.scalars(stmt))
    live = [o for o in orders if o.status != "cancelled"]

    by_day: dict[str, dict[str, int]] = {}
    for i in range(days):
        d = (start_local + timedelta(days=i)).date().isoformat()
        by_day[d] = {"revenue_paise": 0, "orders": 0}
    hours = Counter()
    langs = Counter()
    channels = Counter()
    for o in live:
        local = o.created_at + IST_OFFSET
        key = local.date().isoformat()
        if key in by_day:
            by_day[key]["revenue_paise"] += o.total_paise
            by_day[key]["orders"] += 1
        hours[local.hour] += 1
        langs[o.language] += 1
        channels[o.channel] += 1

    revenue = sum(o.total_paise for o in live)
    today_key = now_local.date().isoformat()
    today = by_day.get(today_key, {"revenue_paise": 0, "orders": 0})

    # top products & categories (join on live order ids)
    live_ids = [o.id for o in live]
    top: list[dict[str, Any]] = []
    cats: dict[str, int] = defaultdict(int)
    if live_ids:
        for chunk_start in range(0, len(live_ids), 500):
            chunk = live_ids[chunk_start : chunk_start + 500]
            rows = db.execute(
                select(OrderItem.product_id, OrderItem.product_name, Product.category, Product.unit,
                       func.sum(OrderItem.line_total_paise), func.sum(OrderItem.qty))
                .join(Product, Product.id == OrderItem.product_id)
                .where(OrderItem.order_id.in_(chunk))
                .group_by(OrderItem.product_id, OrderItem.product_name, Product.category, Product.unit)
            ).all()
            for pid, name, cat, unit, rev, qty in rows:
                top.append({"product_id": pid, "name": name, "unit": unit, "revenue_paise": int(rev), "qty": float(qty)})
                cats[cat or "Other"] += int(rev)
    merged: dict[int, dict[str, Any]] = {}
    for t in top:
        m = merged.setdefault(t["product_id"], {**t, "revenue_paise": 0, "qty": 0.0})
        m["revenue_paise"] += t["revenue_paise"]
        m["qty"] += t["qty"]
    top_products = sorted(merged.values(), key=lambda r: -r["revenue_paise"])[:8]

    low = db.scalar(select(func.count(Product.id)).where(Product.is_active.is_(True), Product.stock <= Product.reorder_level)) or 0
    out_ = db.scalar(select(func.count(Product.id)).where(Product.is_active.is_(True), Product.stock <= 0)) or 0
    live_real = db.scalar(select(func.count(Order.id)).where(Order.is_synthetic.is_(False))) or 0
    return {
        "window_days": days,
        "include_synthetic": include_synthetic,
        "kpis": {
            "revenue_paise": revenue, "orders": len(live),
            "avg_basket_paise": int(revenue / len(live)) if live else 0,
            "voice_share": round(channels["voice"] / len(live), 4) if live else 0.0,
            "today_revenue_paise": today["revenue_paise"], "today_orders": today["orders"],
            "low_stock_count": int(low), "out_of_stock_count": int(out_),
            "cancelled": len(orders) - len(live),
            "non_synthetic_orders_total": int(live_real),
        },
        "sales_by_day": [{"date": d, **v} for d, v in by_day.items()],
        "top_products": top_products,
        "category_mix": sorted(({"category": c, "revenue_paise": v} for c, v in cats.items()), key=lambda r: -r["revenue_paise"]),
        "orders_by_status": [{"status": st, "orders": sum(1 for o in orders if o.status == st)} for st in ("confirmed", "fulfilled", "cancelled")],
        "orders_by_language": [{"language": k, "orders": v} for k, v in langs.most_common()],
        "orders_by_channel": [{"channel": k, "orders": v} for k, v in channels.most_common()],
        "orders_by_hour": [{"hour": h, "orders": hours.get(h, 0)} for h in range(24)],
    }


def latency(db: Session, hours: int = 24 * 7) -> dict[str, Any]:
    since = utcnow() - timedelta(hours=hours)
    calls = list(db.scalars(select(ApiCall).where(ApiCall.created_at >= since)))
    out: dict[str, Any] = {}
    for prov in ("gnani-stt", "gnani-tts", "evon"):
        rows = [c for c in calls if c.provider == prov]
        oks = [c.latency_ms for c in rows if c.ok]
        out[prov] = {
            "calls": len(rows), "ok": len(oks), "errors": len(rows) - len(oks),
            "p50_ms": int(median(oks)) if oks else None, "p95_ms": _pctl(oks, 95),
            "last_error": next((c.error_type for c in sorted(rows, key=lambda c: c.created_at, reverse=True) if not c.ok), None),
        }
    nlu = [float(t.nlu_ms) for t in db.scalars(select(Turn).where(Turn.created_at >= since, Turn.nlu_ms.is_not(None)))]
    out["nlu"] = {
        "turns": len(nlu), "p50_ms": round(median(nlu), 2) if nlu else None,
        "p95_ms": round(sorted(nlu)[max(0, round(0.95 * (len(nlu) - 1)))], 2) if nlu else None,
    }
    return out


# ---------------------------------------------------------------------------------------------------------------
# Extended business intelligence. Everything below is computed from the live tables at request time.
# ---------------------------------------------------------------------------------------------------------------
from decimal import ROUND_HALF_UP, Decimal  # noqa: E402
from datetime import date, datetime  # noqa: E402


def _local_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def _period_start(d: date, grain: str) -> date:
    if grain == "week":
        return d - timedelta(days=d.weekday())  # Monday
    if grain == "month":
        return d.replace(day=1)
    return d


def _next_period(d: date, grain: str) -> date:
    if grain == "week":
        return d + timedelta(days=7)
    if grain == "month":
        return date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return d + timedelta(days=1)


def sales_series(db: Session, grain: str = "day", periods: int = 30, include_synthetic: bool = True) -> dict[str, Any]:
    """Revenue / orders / average order value per day, ISO week (Mon-Sun) or calendar month, in IST.

    The final period is usually partial; it is flagged ``partial`` so charts can say so.
    """
    grain = grain if grain in ("day", "week", "month") else "day"
    periods = max(1, min(periods, {"day": 366, "week": 104, "month": 36}[grain]))
    today = (utcnow() + IST_OFFSET).date()
    cur = _period_start(today, grain)
    starts = [cur]
    for _ in range(periods - 1):
        if grain == "day":
            cur = cur - timedelta(days=1)
        elif grain == "week":
            cur = cur - timedelta(days=7)
        else:
            cur = (cur - timedelta(days=1)).replace(day=1)
        starts.append(cur)
    starts.reverse()
    first_utc = _local_midnight(starts[0]) - IST_OFFSET
    # only the two columns that are summed: loading whole Order objects was most of the time on a long history
    stmt = select(Order.created_at, Order.total_paise).where(Order.created_at >= first_utc, Order.status != "cancelled")
    if not include_synthetic:
        stmt = stmt.where(Order.is_synthetic.is_(False))
    buckets = {s: {"revenue_paise": 0, "orders": 0} for s in starts}
    for created_at, total_paise in db.execute(stmt):
        b = _period_start((created_at + IST_OFFSET).date(), grain)
        if b in buckets:
            buckets[b]["revenue_paise"] += total_paise
            buckets[b]["orders"] += 1
    out = []
    for s in starts:
        v = buckets[s]
        out.append({
            "period": s.isoformat(), "revenue_paise": v["revenue_paise"], "orders": v["orders"],
            "avg_basket_paise": int(v["revenue_paise"] / v["orders"]) if v["orders"] else 0,
            # a period is unfinished while the next one has not started yet; today always belongs to an unfinished period
            "partial": _next_period(s, grain) > today,
        })
    total_rev = sum(p["revenue_paise"] for p in out)
    total_orders = sum(p["orders"] for p in out)
    return {
        "grain": grain, "periods": periods, "include_synthetic": include_synthetic, "series": out,
        "totals": {"revenue_paise": total_rev, "orders": total_orders, "avg_basket_paise": int(total_rev / total_orders) if total_orders else 0},
    }


def _money(stock: Decimal, price_paise: int) -> int:
    return int((Decimal(stock) * price_paise).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def inventory_summary(db: Session, dead_days: int = 30) -> dict[str, Any]:
    """Stock valuation and health. Valuation is at the shop's selling price; cost valuation only counts products with a cost entered."""
    products = list(db.scalars(select(Product).where(Product.is_active.is_(True))))
    retail = cost = 0
    cost_cov = 0
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"retail_paise": 0, "items": 0, "units_low": 0})
    out_, low_ = [], []
    for p in products:
        v = _money(p.stock, p.price_paise)
        retail += v
        if p.cost_paise:
            cost += _money(p.stock, p.cost_paise)
            cost_cov += 1
        c = by_cat[p.category or "Other"]
        c["retail_paise"] += v
        c["items"] += 1
        row = {"product_id": p.id, "name": p.name_en, "unit": p.unit, "stock": float(p.stock), "reorder_level": float(p.reorder_level)}
        if p.stock <= 0:
            out_.append(row)
        elif p.stock <= p.reorder_level:
            low_.append(row)
            c["units_low"] += 1
    since = utcnow() - timedelta(days=dead_days)
    sold_ids = set(db.scalars(
        select(OrderItem.product_id).join(Order, Order.id == OrderItem.order_id).where(Order.created_at >= since, Order.status != "cancelled").distinct()
    ))
    dead = [p for p in products if p.stock > 0 and p.id not in sold_ids]
    dead_value = sum(_money(p.stock, p.price_paise) for p in dead)
    demo_priced = sum(1 for p in products if p.price_basis == "demo")
    return {
        "products": len(products), "valuation_retail_paise": retail,
        "valuation_cost_paise": cost if cost_cov else None, "products_with_cost": cost_cov,
        "price_basis": {"demo": demo_priced, "shop": len(products) - demo_priced},
        "by_category": sorted(({"category": k, **v} for k, v in by_cat.items()), key=lambda r: -r["retail_paise"]),
        "out_of_stock": out_, "low_stock": low_,
        "stock_health": {"ok": len(products) - len(out_) - len(low_), "low": len(low_), "out": len(out_)},
        "no_sales": {"days": dead_days, "items": len(dead), "retail_paise": dead_value,
                     "top": [{"product_id": p.id, "name": p.name_en, "retail_paise": _money(p.stock, p.price_paise)}
                             for p in sorted(dead, key=lambda p: -_money(p.stock, p.price_paise))[:6]]},
    }


def demand_insights(db: Session, days: int = 30, include_synthetic: bool = True, limit: int = 40) -> dict[str, Any]:
    """Per-product sales velocity and stock cover from the last `days` days vs the `days` before them.

    Simple trailing averages, not a forecast model: velocity = units sold / days; cover = stock / velocity.
    """
    days = max(7, min(days, 90))
    now = utcnow()
    win_start, prev_start = now - timedelta(days=days), now - timedelta(days=2 * days)
    base = (
        select(OrderItem.product_id, func.sum(OrderItem.qty), func.sum(OrderItem.line_total_paise))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status != "cancelled")
        .group_by(OrderItem.product_id)
    )
    if not include_synthetic:
        base = base.where(Order.is_synthetic.is_(False))
    cur = {pid: (Decimal(q), int(r)) for pid, q, r in db.execute(base.where(Order.created_at >= win_start))}
    prev = {pid: Decimal(q) for pid, q, _r in db.execute(base.where(Order.created_at >= prev_start, Order.created_at < win_start))}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.is_active.is_(True)))}
    # A "vs earlier" figure is only meaningful if the earlier window really has sales history. A shop (or a demo) that
    # started recording last month would otherwise show +6000%, which is arithmetic, not insight. Require orders on at
    # least half of the earlier window's days; otherwise withhold every trend and say why.
    prev_orders = select(Order.created_at).where(Order.status != "cancelled", Order.created_at >= prev_start, Order.created_at < win_start)
    if not include_synthetic:
        prev_orders = prev_orders.where(Order.is_synthetic.is_(False))
    prev_days = {(t + IST_OFFSET).date() for t in db.scalars(prev_orders)}
    comparable = len(prev_days) >= days * 0.5
    rows = []
    for pid, (qty, rev) in cur.items():
        p = products.get(pid)
        if p is None:
            continue
        velocity = float(qty) / days
        cover = float(p.stock) / velocity if velocity > 0 else None
        pq = prev.get(pid)
        trend = round((float(qty) - float(pq)) / float(pq) * 100, 1) if comparable and pq and pq > 0 else None
        target = Decimal(str(velocity * 14))  # 14 days of cover is the suggested level; a rule of thumb, shown as such
        need = max(Decimal(0), target - Decimal(p.stock))
        step = Decimal("0.5") if p.unit in ("kg", "l") else Decimal(1)
        suggest = (need / step).to_integral_value(rounding="ROUND_CEILING") * step if need > 0 else Decimal(0)
        status = "stockout_risk" if cover is not None and cover < 3 else "overstocked" if cover is not None and cover > 60 else "ok"
        rows.append({
            "product_id": pid, "name": p.name_en, "category": p.category, "unit": p.unit, "units_sold": float(qty),
            "revenue_paise": rev, "velocity_per_day": round(velocity, 3), "stock": float(p.stock),
            "days_of_cover": round(cover, 1) if cover is not None else None, "trend_pct": trend,
            "suggested_reorder_qty": float(suggest), "status": status,
        })
    rows.sort(key=lambda r: -r["revenue_paise"])
    risk = sorted((r for r in rows if r["status"] == "stockout_risk"), key=lambda r: r["days_of_cover"] or 0)
    movers_up = sorted((r for r in rows if r["trend_pct"] is not None and r["units_sold"] >= 3), key=lambda r: -r["trend_pct"])[:5]
    movers_down = sorted((r for r in rows if r["trend_pct"] is not None and r["units_sold"] >= 3), key=lambda r: r["trend_pct"])[:5]
    return {
        "window_days": days, "include_synthetic": include_synthetic,
        "previous_window": {"days": days, "days_with_orders": len(prev_days), "comparable": comparable},
        "method": "Trailing average of units sold per day over the window. Not a forecast. Suggested reorder tops stock up to 14 days of cover.",
        "products": rows[:limit], "stockout_risk": risk[:8], "rising": movers_up, "falling": movers_down,
    }


def stock_movement(db: Session, days: int = 30, limit: int = 60) -> dict[str, Any]:
    """What happened to each product's stock in the last ``days`` days, from the stock ledger (``stock_movements``).

    opening = current - (added + returned - sold - written_off). Only real movements are in the ledger: orders confirmed, cancelled
    or restocked in the app. Generated demo orders never touched the shelf and are not in it, so they do not appear here.
    ``in_paise`` / ``out_paise`` value each day's movements at today's selling price, because kilos and packs cannot be added up.
    """
    from ..models import StockMovement

    days = max(1, min(days, 365))
    today = (utcnow() + IST_OFFSET).date()
    first = today - timedelta(days=days - 1)
    since_utc = _local_midnight(first) - IST_OFFSET
    products = {p.id: p for p in db.scalars(select(Product).where(Product.is_active.is_(True)))}
    agg: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    daily = {first + timedelta(days=i): {"in_paise": 0, "out_paise": 0} for i in range(days)}
    n_moves = 0
    for pid, reason, delta, created_at in db.execute(
        select(StockMovement.product_id, StockMovement.reason, StockMovement.delta, StockMovement.created_at).where(StockMovement.created_at >= since_utc)
    ):
        p = products.get(pid)
        if p is None:
            continue
        n_moves += 1
        delta = Decimal(delta)
        a = agg[pid]
        if reason == "order":
            a["sold"] += -delta
        elif reason == "cancel":
            a["returned"] += delta
        elif reason == "restock":
            a["added"] += delta
        elif delta >= 0:
            a["added"] += delta
        else:
            a["written_off"] += -delta
        d = (created_at + IST_OFFSET).date()
        if d in daily:
            v = _money(abs(delta), p.price_paise)
            daily[d]["in_paise" if delta > 0 else "out_paise"] += v
    rows = []
    for pid, a in agg.items():
        p = products[pid]
        current = Decimal(p.stock)
        net = a["added"] + a["returned"] - a["sold"] - a["written_off"]
        status = "out" if current <= 0 else "low" if current <= Decimal(p.reorder_level) else "ok"
        rows.append({
            "product_id": pid, "name": p.name_en, "category": p.category, "unit": p.unit,
            "opening": float(current - net), "added": float(a["added"]), "returned": float(a["returned"]), "sold": float(a["sold"]),
            "written_off": float(a["written_off"]), "current": float(current), "reorder_level": float(p.reorder_level), "status": status,
        })
    rows.sort(key=lambda r: (-r["sold"], r["name"]))
    return {
        "window_days": days, "movements": n_moves, "products_moved": len(rows), "products_total": len(products),
        "rows": rows[:limit], "truncated": len(rows) > limit,
        "series": [{"date": d.isoformat(), **v} for d, v in sorted(daily.items())],
        "totals": {"in_paise": sum(v["in_paise"] for v in daily.values()), "out_paise": sum(v["out_paise"] for v in daily.values())},
        "method": "From the stock ledger: orders confirmed, cancelled or restocked in the app. Opening stock is today's stock with the window's movements taken back out. Generated demo orders never touched the shelf and are not counted.",
    }
