"""Take real screenshots of the version 2.7 payment screens, from a running app that already has some confirmed orders (for example after scripts/demo_activity.py).

    SWARA_SHOT_PASSWORD=... python scripts/take_payment_screenshots.py [base_url] --email OWNER [--out DIR]

It signs in through the real sign-in page as the shop owner, then uses the app's own API from that signed-in page to put a handful of payments on
existing confirmed orders (cash, a hand-confirmed UPI QR, one partial refund), leaves one order unpaid, and photographs: the payment window (choose a way, the
UPI QR, a finished payment), the payments list, a payment with a refund, payment analytics, the invoice and its print layout, and the Payments card in Settings,
at desktop and phone width. No Razorpay keys are needed, nothing is sent to Razorpay, and the figures in the pictures come from those records only.

This changes the database it is pointed at (it adds payments, a UPI ID and a refund). Run it against a throw-away database, never the shop's own.
The shop's UPI ID used here is a made-up one for the pictures."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from take_screenshots import ROOT, VIEWPORTS, authenticate, shoot   # noqa: E402

JF = """async ([method, url, body]) => {
  const s = await (await fetch('/api/auth/session')).json();
  const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': s.csrf_token || '' }, body: body ? JSON.stringify(body) : undefined });
  let j = null; try { j = await r.json() } catch (e) {}
  return { status: r.status, json: j };
}"""


def seed(page) -> dict:
    """Put payments on real confirmed orders through the app's own API. Returns the ids the pictures need."""
    r = page.evaluate(JF, ["PUT", "/api/settings", {"upi_vpa": "patelstore@okhdfcbank", "upi_payee_name": "Patel Kirana Store"}])
    assert r["status"] == 200, r
    orders = page.evaluate("fetch('/api/orders?limit=40&sort=newest&status=confirmed&include_synthetic=false').then(r => r.json())")["items"]
    free = [o for o in orders if o["payment"]["status"] == "none"]
    if len(free) < 3:
        sys.exit(f"Need at least 3 confirmed orders without a payment, found {len(free)}. Run scripts/demo_activity.py first.")
    made: list[dict] = []
    for i, o in enumerate(free[:-1][:5]):
        method = "cash" if i % 2 == 0 else "upi"
        s = page.evaluate(JF, ["POST", f"/api/orders/{o['id']}/payments", {"method": method, "idempotency_key": f"shots-{o['id']}-{method}"}])
        assert s["status"] in (200, 201), s
        pid = s["json"]["id"]
        if method == "cash":
            c = page.evaluate(JF, ["POST", f"/api/payments/{pid}/cash", {"received_paise": (o["total_paise"] // 5000 + 1) * 5000}])
        else:
            c = page.evaluate(JF, ["POST", f"/api/payments/{pid}/confirm-upi", {"reference": f"UTR40{o['id']:07d}"}])
        assert c["status"] == 200, c
        made.append({"order": o["id"], "payment": pid, "method": method})
    refund_target = made[0]
    rf = page.evaluate(JF, ["POST", f"/api/payments/{refund_target['payment']}/refunds", {"amount_paise": 1000, "reason": "Item returned", "idempotency_key": "shots-refund-1"}])
    assert rf["status"] in (200, 201), rf
    return {"paid": made, "refunded_payment": refund_target["payment"], "paid_order": made[1]["order"], "unpaid_order": free[-1]["id"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="http://localhost:8000")
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    ap.add_argument("--email", default=os.environ.get("SWARA_SHOT_EMAIL", ""))
    a = ap.parse_args()
    if not a.email or not os.environ.get("SWARA_SHOT_PASSWORD"):
        sys.exit("Give --email (or SWARA_SHOT_EMAIL) and set SWARA_SHOT_PASSWORD in the environment.")
    password = os.environ["SWARA_SHOT_PASSWORD"]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    ids: dict | None = None

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        for vp_name in ("desktop", "phone"):
            vp = VIEWPORTS[vp_name]
            ctx = browser.new_context(locale="en-IN", **vp)
            ctx.add_init_script("try { localStorage.setItem('swara.includeDemo', '1') } catch (e) {}")
            page = ctx.new_page()
            page.on("console", lambda m, t=vp_name: problems.append(f"[{t}] console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e, t=vp_name: problems.append(f"[{t}] pageerror: {e}"))
            page.on("requestfailed", lambda r, t=vp_name: problems.append(f"[{t}] request failed: {r.url} {r.failure}"))
            page.on("response", lambda r, t=vp_name: problems.append(f"[{t}] HTTP {r.status}: {r.url}") if r.status >= 400 else None)
            authenticate(page, a.base, a.email, password, "Ramesh Patel", False)
            if ids is None:
                ids = seed(page)
                print("seeded", len(ids["paid"]), "payments and one refund")

            # the payment window on the order that has no payment yet: choose a way, then the shop's own UPI QR
            page.goto(f"{a.base}/orders?open={ids['unpaid_order']}", wait_until="networkidle")
            page.get_by_role("button", name="Take payment").click()
            dlg = page.get_by_role("dialog", name="Take payment"); dlg.get_by_role("radiogroup").wait_for(timeout=8000)
            page.wait_for_timeout(400)
            dlg.screenshot(path=str(out / f"{vp_name}-payment-choose.png")); print("saved", vp_name, "payment-choose")
            dlg.get_by_role("radio", name="UPI QR code").click(); dlg.get_by_role("button", name="Continue").click()
            dlg.locator("svg.qr-svg").wait_for(timeout=8000); page.wait_for_timeout(400)
            dlg.screenshot(path=str(out / f"{vp_name}-payment-upi-qr.png")); print("saved", vp_name, "payment-upi-qr")
            page.keyboard.press("Escape")
            # leave the order unpaid again for the next pass: a waiting payment that is cancelled stays in its history as cancelled
            op = page.evaluate("(id) => fetch('/api/orders/' + id + '/payments').then(r => r.json())", ids["unpaid_order"])
            if op["summary"]["pending_payment_id"]:
                assert page.evaluate(JF, ["POST", f"/api/payments/{op['summary']['pending_payment_id']}/cancel", {"reason": "Screenshots"}])["status"] == 200

            for name, path in [("payments", "/payments"), ("payment-detail", f"/payments/{ids['refunded_payment']}"),
                               ("payment-analytics", "/payment-analytics"), ("invoice", f"/invoices/{ids['paid_order']}")]:
                page.goto(a.base + path, wait_until="networkidle"); page.wait_for_timeout(900)
                shoot(page, out / f"{vp_name}-{name}.png", vp["viewport"]); print("saved", vp_name, name)
                if name == "invoice" and vp_name == "desktop":
                    # what the browser's print window shows for this invoice: the page in print state, rendered with print media
                    page.evaluate("document.body.classList.add('printing-invoice')")
                    page.emulate_media(media="print"); page.wait_for_timeout(300)
                    page.screenshot(path=str(out / f"{vp_name}-print-invoice.png"))
                    page.emulate_media(media="screen"); page.evaluate("document.body.classList.remove('printing-invoice')")
                    print("saved", vp_name, "print-invoice")
            if vp_name == "desktop":
                page.goto(a.base + "/settings", wait_until="networkidle"); page.wait_for_timeout(700)
                card = page.locator(".card", has=page.get_by_role("heading", name="Payments", exact=True))
                card.scroll_into_view_if_needed(); card.screenshot(path=str(out / "desktop-payment-settings.png")); print("saved", vp_name, "payment-settings")
            ctx.close()
        browser.close()
    for line in sorted(set(problems)):
        print("  problem:", line)


if __name__ == "__main__":
    main()
