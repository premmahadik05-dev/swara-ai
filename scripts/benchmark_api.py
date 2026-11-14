"""Measure local HTTP latency of the order pipeline WITHOUT calling Gnani (text channel only).
   python scripts/benchmark_api.py --email you@example.com --password ... [--base http://localhost:8000] [--n 200]
(or set BENCH_EMAIL and BENCH_PASSWORD). Every page behind the sign-in needs an account, and the run PLACES REAL ORDERS (about n/4 of them, which
take stock), so point it at a throw-away database, never at a shop's own data.
Writes eval/results/api_latency.json. These are numbers for THIS machine and THIS server process only; they say nothing about
Gnani speech latency (use scripts/verify_gnani.py and the Live screen for that)."""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path

import httpx

SENTENCES = [
    "mane 2 kilo chawal ane 1 litre doodh joie", "bhai 2 kilo cheeni aur ek packet bread dena", "ek kilo dal chahiye",
    "do kilo aloo aur dhai sau gram tamatar", "બે કિલો ખાંડ અને એક કિલો લોટ", "half kilo paneer and one dozen eggs",
    "sabudana hai kya", "तीन पैकेट बिस्कुट और एक लीटर तेल",
]


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def summarise(xs: list[float]) -> dict:
    return {"n": len(xs), "p50_ms": round(pct(xs, 50), 2), "p95_ms": round(pct(xs, 95), 2), "max_ms": round(max(xs), 2), "mean_ms": round(statistics.mean(xs), 2)}


def timed(fn) -> float:
    t = time.perf_counter()
    r = fn()
    dt = (time.perf_counter() - t) * 1000
    r.raise_for_status()
    return dt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--email", default=os.environ.get("BENCH_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("BENCH_PASSWORD"))
    a = ap.parse_args()
    if not (a.email and a.password):
        raise SystemExit("Give --email and --password (or BENCH_EMAIL / BENCH_PASSWORD) of an account on a throw-away database.")
    out: dict = {"machine": f"{platform.system()} {platform.release()} Python {platform.python_version()}", "base": a.base, "n": a.n, "note": "Local loopback HTTP, signed-in session, no Gnani calls."}
    with httpx.Client(base_url=a.base, timeout=30, headers={"Origin": a.base}) as c:
        c.get("/api/health").raise_for_status()
        login = c.post("/api/auth/login", json={"email": a.email, "password": a.password, "remember": False})
        login.raise_for_status()
        c.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        for s in SENTENCES:  # warm-up
            c.post("/api/text/parse", json={"text": s})
        out["text_parse"] = summarise([timed(lambda i=i: c.post("/api/text/parse", json={"text": SENTENCES[i % len(SENTENCES)]})) for i in range(a.n)])
        turn, confirm = [], []
        for i in range(a.n // 4):
            sid = c.post("/api/sessions").json()["session_id"]
            turn.append(timed(lambda: c.post("/api/text/turn", json={"text": "2 kilo chawal aur 1 litre doodh", "session_id": sid})))
            turn.append(timed(lambda: c.post("/api/text/turn", json={"text": "bas itna hi", "session_id": sid})))
            confirm.append(timed(lambda: c.post(f"/api/sessions/{sid}/confirm")))
        out["text_turn"] = summarise(turn)
        out["confirm_order_with_stock_update"] = summarise(confirm)
        out["analytics_overview_30d"] = summarise([timed(lambda: c.get("/api/analytics/overview", params={"days": 30})) for _ in range(a.n // 4)])
        out["inventory_list"] = summarise([timed(lambda: c.get("/api/products")) for _ in range(a.n // 4)])
        # the endpoints behind the Analytics, Orders and Catalogue pages
        out["analytics_sales_daily_61"] = summarise([timed(lambda: c.get("/api/analytics/sales", params={"grain": "day", "periods": 61})) for _ in range(a.n // 4)])
        out["analytics_sales_monthly_25"] = summarise([timed(lambda: c.get("/api/analytics/sales", params={"grain": "month", "periods": 25})) for _ in range(a.n // 4)])
        out["analytics_demand_30d"] = summarise([timed(lambda: c.get("/api/analytics/demand", params={"days": 30})) for _ in range(a.n // 4)])
        out["analytics_inventory_summary"] = summarise([timed(lambda: c.get("/api/analytics/inventory")) for _ in range(a.n // 4)])
        out["orders_page_20"] = summarise([timed(lambda: c.get("/api/orders", params={"limit": 20})) for _ in range(a.n // 4)])
        out["orders_search"] = summarise([timed(lambda: c.get("/api/orders", params={"q": "Demo Customer", "limit": 20})) for _ in range(a.n // 4)])
        out["catalogue_search"] = summarise([timed(lambda: c.get("/api/catalog", params={"q": "parle", "page_size": 24})) for _ in range(a.n // 4)])
        out["global_search"] = summarise([timed(lambda: c.get("/api/search", params={"q": "milk"})) for _ in range(a.n // 4)])
        out["analytics_stock_movement_30d"] = summarise([timed(lambda: c.get("/api/analytics/stock-movement", params={"days": 30})) for _ in range(a.n // 4)])
        out["evaluation_summary"] = summarise([timed(lambda: c.get("/api/evaluation")) for _ in range(a.n // 4)])
        out["orders_in_database"] = c.get("/api/orders", params={"limit": 1}).json().get("total")
    p = Path(__file__).resolve().parent.parent / "eval" / "results" / "api_latency.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
