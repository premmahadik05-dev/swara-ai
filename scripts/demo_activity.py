"""Put a little REAL activity through a running SWARA AI server, so charts and tables built from the stock ledger have something genuine to show.

   python scripts/demo_activity.py --base http://localhost:8000 --email you@example.com --password ... [--json out.json]

What it does, through the same API the screens use: signs in, imports a few catalogue products at prices typed here (labelled demo prices),
places six typed orders in six languages (each goes through the dialogue and the confirm button, so it takes stock exactly like a real order),
restocks two items and cancels one order. It then reads back the product list, the orders and the stock-movement report.

With --payments it also puts version 2.7 payments through the same API (no Razorpay, nothing is sent to any provider): one cash payment, one UPI QR confirmed by hand,
one cash payment with a part refund, one UPI payment left waiting, and one order left with no payment record. It then tries to cancel the paid order (the app must refuse),
asks twice for an invoice (the number must not change), and checks that no payment step changed any product's stock. The payment history, analytics and the invoice are
read back into the --json file under "payments". The shop's UPI ID used is a made-up one.

Use a THROW-AWAY database. These are real writes: the orders take stock and stay in the database. The sentences are written by the
author of the parser, so this shows the plumbing works, not how well the parser understands strangers.
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

# (language hint, sentence). Each is a one-line order; the confirm button then ends the bill and saves it.
ORDERS = [
    ("hinglish", "2 kilo chawal aur 1 litre doodh"),
    ("en", "two kilos of sugar and one packet of bread"),
    ("hi", "मुझे दो किलो आटा और आधा किलो चीनी चाहिए"),
    ("gu", "બે કિલો ખાંડ અને એક લીટર દૂધ"),
    ("mr", "मला दोन किलो साखर आणि अर्धा किलो तांदूळ"),
    ("ta", "அரை கிலோ அரிசி"),
]
# catalogue search -> price in paise typed by "the shopkeeper" for this demo, and opening stock
IMPORTS = [("parle-g", 1000, 24), ("amul ghee", 62000, 6), ("maggi", 1400, 40), ("tata salt", 2800, 30)]


def put_payments(c: httpx.Client, placed: list[dict]) -> dict | None:
    """Real payments through the API on the confirmed orders just placed. Returns what was read back, for the report."""
    if len(placed) < 6:
        print("note: fewer than six orders were saved, so the payment steps were skipped", file=sys.stderr)
        return None
    inv_before = {i["id"]: i["stock"] for i in c.get("/api/inventory", params={"page_size": 100}).json()["items"]}
    moves_before = c.get("/api/analytics/stock-movement", params={"days": 30}).json()["movements"]
    c.put("/api/settings", json={"upi_vpa": "patelstore@okhdfcbank", "upi_payee_name": "Patel Kirana Store"}).raise_for_status()
    steps: list[dict] = []

    def start(order: dict, method: str) -> dict:
        r = c.post(f"/api/orders/{order['id']}/payments", json={"method": method, "idempotency_key": f"demo-{order['id']}-{method}"})
        r.raise_for_status()
        return r.json()

    def note(order: dict, what: str, pay: dict) -> None:
        steps.append({"order": order["code"], "what": what, "payment": pay.get("code"), "status": pay.get("status")})

    cash_order, upi_order, refund_order, waiting_order, bare_order = placed[0], placed[2], placed[3], placed[4], placed[5]
    # 1. cash, with change
    p = start(cash_order, "cash")
    given = (cash_order["total_paise"] // 5000 + 1) * 5000
    r = c.post(f"/api/payments/{p['id']}/cash", json={"received_paise": given}); r.raise_for_status()
    note(cash_order, "Cash recorded", r.json())
    # 2. UPI QR for the shop's own ID, confirmed by a person (not verified by any provider)
    p = start(upi_order, "upi")
    r = c.post(f"/api/payments/{p['id']}/confirm-upi", json={"reference": "DEMO-REF-0001"}); r.raise_for_status()
    note(upi_order, "UPI QR confirmed by hand", r.json())
    # 3. cash, then a part refund recorded by the owner
    p = start(refund_order, "cash")
    r = c.post(f"/api/payments/{p['id']}/cash", json={"received_paise": refund_order["total_paise"]}); r.raise_for_status()
    refund_pay = r.json()
    rf = c.post(f"/api/payments/{p['id']}/refunds", json={"amount_paise": 1000, "reason": "Item returned", "idempotency_key": f"demo-refund-{refund_order['id']}"}); rf.raise_for_status()
    refund_pay = c.get(f"/api/payments/{p['id']}").json()
    note(refund_order, "Cash recorded, then Rs 10 refunded by the owner", refund_pay)
    # 4. UPI QR shown, nobody has confirmed it: stays waiting
    p = start(waiting_order, "upi")
    note(waiting_order, "UPI QR shown, left waiting", p)
    steps.append({"order": bare_order["code"], "what": "No payment recorded", "payment": None, "status": "none"})

    # a paid order cannot be cancelled while collected money has not been refunded
    cancel = c.post(f"/api/orders/{refund_order['id']}/status", json={"status": "cancelled"})
    cancel_info = {"http_status": cancel.status_code, "code": (cancel.json().get("detail") or {}).get("code") if cancel.status_code >= 400 else None}
    # the invoice number is issued once and stays
    inv1 = c.get(f"/api/orders/{cash_order['id']}/invoice"); inv1.raise_for_status()
    inv2 = c.get(f"/api/orders/{cash_order['id']}/invoice"); inv2.raise_for_status()
    # stock is moved by orders only
    inv_after = {i["id"]: i["stock"] for i in c.get("/api/inventory", params={"page_size": 100}).json()["items"]}
    moves_after = c.get("/api/analytics/stock-movement", params={"days": 30}).json()["movements"]
    return {
        "upi_vpa": "patelstore@okhdfcbank",
        "steps": steps,
        "cancel_paid_order": cancel_info,
        "invoice": inv1.json(),
        "invoice_number_stable": inv1.json()["number"] == inv2.json()["number"],
        "stock_unchanged": {"products_compared": len(inv_before), "all_same": inv_before == inv_after, "movements_before": moves_before, "movements_after": moves_after},
        "config": c.get("/api/payments/config").json(),
        "history": c.get("/api/payments", params={"limit": 100, "include_synthetic": "true"}).json(),
        "analytics": c.get("/api/payments/analytics", params={"days": 30, "include_synthetic": "true"}).json(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--json", help="write what was read back to this file")
    ap.add_argument("--payments", action="store_true", help="also put payments through (cash, a hand-confirmed UPI QR, a part refund) and read back the history, analytics and an invoice")
    a = ap.parse_args()
    with httpx.Client(base_url=a.base, timeout=30, headers={"Origin": a.base}) as c:
        r = c.post("/api/auth/login", json={"email": a.email, "password": a.password, "remember": False})
        r.raise_for_status()
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]

        imported = []
        for query, price, stock in IMPORTS:
            hits = c.get("/api/catalog", params={"q": query, "page_size": 1}).json()["items"]
            if not hits:
                continue
            res = c.post(f"/api/catalog/{hits[0]['id']}/import", json={"price_paise": price, "stock": stock, "reorder_level": 5})
            if res.status_code == 201:
                imported.append(res.json())

        placed = []
        for lang, text in ORDERS:
            sid = c.post("/api/text/turn", json={"text": text, "language": lang}).json()["session_id"]
            out = c.post(f"/api/sessions/{sid}/confirm").json()
            if out.get("order"):
                placed.append(out["order"])
        if len(placed) < len(ORDERS):
            print(f"note: {len(ORDERS) - len(placed)} of {len(ORDERS)} sentences did not end in a saved order", file=sys.stderr)

        shelf = {i["name_en"]: i for i in c.get("/api/inventory", params={"page_size": 100}).json()["items"]}
        restocked = 0
        for name, qty in (("Rice", 10), ("Sugar", 5)):
            if name in shelf:
                c.post(f"/api/products/{shelf[name]['id']}/restock", json={"qty": qty}).raise_for_status()
                restocked += 1
        if len(placed) >= 2:
            c.post(f"/api/orders/{placed[1]['id']}/status", json={"status": "cancelled"}).raise_for_status()

        payments = put_payments(c, placed) if a.payments else None
        data = {
            "base": a.base,
            "imported": [{"name": p.get("name_en"), "brand": p.get("brand"), "pack_size": p.get("pack_size"), "pack_size_unit": p.get("pack_size_unit")} for p in imported],
            "orders_placed": [{"id": o["id"], "code": o["code"], "language": o["language"], "total_paise": o["total_paise"]} for o in placed],
            "inventory": c.get("/api/inventory", params={"page_size": 100}).json()["items"],
            "orders": c.get("/api/orders", params={"limit": 100}).json()["items"],
            "stock_movement": c.get("/api/analytics/stock-movement", params={"days": 30}).json(),
            "overview": c.get("/api/analytics/overview", params={"days": 30}).json(),
        }
        if payments is not None:
            data["payments"] = payments
    print(f"imported {len(imported)} products, placed {len(placed)} orders, restocked {restocked} items, cancelled 1 order; "
          f"{data['stock_movement']['movements']} stock movements recorded")
    if "payments" in data:
        pm = data["payments"]
        print(f"payments: {len(pm['history']['items'])} recorded, cancel of a paid order answered HTTP {pm['cancel_paid_order']['http_status']} {pm['cancel_paid_order']['code']}, "
              f"invoice {pm['invoice']['number']} stable={pm['invoice_number_stable']}, stock unchanged by payments={pm['stock_unchanged']['all_same']}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
