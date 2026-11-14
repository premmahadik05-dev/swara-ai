"""Take real screenshots of the running app (SWARA AI is light only) at desktop, tablet and phone sizes.

    python scripts/take_screenshots.py [base_url] [--out DIR] [--only desktop|tablet|phone] [--pages a,b]
                                       [--email E] [--name N] [--signup] [--landing]

The app needs an account now. Give --email and put the password in the SWARA_SHOT_PASSWORD environment variable (never on the command
line). Add --signup the first time, against a fresh database, to create that account through the real sign-up page; later runs sign in.
--landing writes the five optimised WebP pictures the public landing page shows (frontend/public/shots/) instead of the documentation set.

Needs: pip install playwright pillow && playwright install chromium   (or an installed Chrome at /usr/bin/google-chrome).
The Order desk shots use the TEXT channel, so they work without a Gnani key; voice screens show their honest 'no key' state.
Also reports every console error/warning and every failed or 4xx/5xx network request it saw, so a clean run means something."""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VIEWPORTS = {
    "desktop": dict(viewport={"width": 1440, "height": 900}, device_scale_factor=1),
    "tablet": dict(viewport={"width": 820, "height": 1180}, device_scale_factor=1, has_touch=True),
    "phone": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True),
}
VISITOR_PAGES = [("landing", "/"), ("sign-in", "/sign-in"), ("sign-up", "/sign-up"), ("forgot-password", "/forgot-password")]
PAGES = [
    ("dashboard", "/dashboard"), ("orders", "/orders"), ("orders-drawer", "/orders?open=1"), ("customers", "/customers"),
    ("customer-drawer", "/customers?open=1"), ("inventory", "/inventory"), ("catalogue", "/catalogue"), ("catalogue-drawer", "/catalogue?open=1"),
    ("analytics", "/analytics"), ("ai-performance", "/performance"), ("voice-diagnostics", "/diagnostics"), ("live", "/live"), ("noise-lab", "/noise"), ("settings", "/settings"), ("account", "/account"),
]
LANDING_SHOTS = [("dashboard", "/dashboard"), ("order-desk", "/order"), ("orders", "/orders"), ("inventory", "/inventory"), ("analytics", "/analytics")]


def shoot(page, path: Path, viewport: dict, full: bool = True) -> None:
    """Screenshot a page. For a full-page shot the browser window is first made as tall as the page, so layout that is sized to the
    window (the sidebar is 100vh and sticky) fills the whole picture the way it does for a person who scrolls."""
    if not full:
        page.screenshot(path=str(path))
        return
    if viewport["width"] < 1000:   # phones and tablets have no sticky sidebar, and resizing an emulated mobile window changes its layout
        page.screenshot(path=str(path), full_page=True)
        return
    h = page.evaluate("Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)")
    if h and h <= 16000:   # Chromium takes a viewport this tall; above it the page is captured with full_page instead (the sticky sidebar then stops at the window height)
        page.set_viewport_size({"width": viewport["width"], "height": max(viewport["height"], int(h))})
        page.wait_for_timeout(250)
        page.screenshot(path=str(path))
        page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
    else:
        page.screenshot(path=str(path), full_page=True)


def authenticate(page, base: str, email: str, password: str, name: str, signup: bool) -> None:
    """Sign in (or create the account first) through the real pages, so a run also proves the forms work in a browser."""
    if signup:
        page.goto(base + "/sign-up", wait_until="networkidle")
        page.get_by_label("Full name").fill(name)
        page.get_by_label("E-mail address").fill(email)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_label("Confirm password", exact=True).fill(password)
        page.get_by_role("checkbox", name=re.compile("I accept")).check()
        page.get_by_role("button", name="Create account").click()
        page.get_by_role("button", name="Open the dashboard").click()
    else:
        page.goto(base + "/sign-in", wait_until="networkidle")
        page.get_by_label("E-mail address").fill(email)
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_url("**/dashboard", timeout=15000)
    page.wait_for_load_state("networkidle")


def order_desk_conversation(page, base: str) -> None:
    """A real multi-turn text conversation against the real backend, so the bill on screen was built by the engine."""
    page.goto(base + "/order", wait_until="networkidle")
    box = page.get_by_label("Or type the order")
    for sentence in ["mane 2 kilo chawal ane 1 litre doodh joie", "sabudana hai kya"]:
        box.fill(sentence)
        page.get_by_role("button", name="Send").click()
        page.wait_for_timeout(1000)


def landing_pictures(browser, a, problems: list[str]) -> None:
    """The pictures on the public landing page: real screens of the running app at 1440x900 as WebP."""
    from PIL import Image

    dest = ROOT / "frontend" / "public" / "shots"
    dest.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(locale="en-IN", viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page = ctx.new_page()
    page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    authenticate(page, a.base, a.email, os.environ["SWARA_SHOT_PASSWORD"], a.name, a.signup)
    for name, path in LANDING_SHOTS:
        if name == "order-desk":
            order_desk_conversation(page, a.base)
        else:
            page.goto(a.base + path, wait_until="networkidle")
        if name == "dashboard":   # a shop owner who has finished (or dismissed) the setup list sees the numbers first; hide it the way they would
            hide = page.get_by_role("button", name="Hide the setup checklist")
            if hide.count():
                hide.click()
                page.wait_for_timeout(300)
        page.evaluate("window.scrollTo(0, 0)")   # typing into the order box can scroll the page; the picture starts at the top
        page.wait_for_timeout(900)
        png = dest / f"{name}.png"
        page.screenshot(path=str(png))
        Image.open(png).convert("RGB").save(dest / f"{name}.webp", "WEBP", quality=82, method=6)
        png.unlink()
        print("landing picture", name, (dest / f"{name}.webp").stat().st_size // 1024, "KB")
    ctx.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="http://localhost:8000")
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    ap.add_argument("--only", choices=list(VIEWPORTS))
    ap.add_argument("--pages", help="comma separated page names to limit the run")
    ap.add_argument("--email", default=os.environ.get("SWARA_SHOT_EMAIL", ""), help="account to sign in with (or create, with --signup)")
    ap.add_argument("--name", default="Ramesh Patel", help="full name used when creating the account")
    ap.add_argument("--signup", action="store_true", help="create the account through the sign-up page in the first browser window")
    ap.add_argument("--landing", action="store_true", help="only write the landing-page pictures (WebP) to frontend/public/shots/")
    a = ap.parse_args()
    if not a.email or not os.environ.get("SWARA_SHOT_PASSWORD"):
        sys.exit("Give --email (or SWARA_SHOT_EMAIL) and set SWARA_SHOT_PASSWORD in the environment.")
    password = os.environ["SWARA_SHOT_PASSWORD"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    want = set(a.pages.split(",")) if a.pages else None

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        if a.landing:
            landing_pictures(browser, a, problems)
            browser.close()
            for line in sorted(set(problems)):
                print("  problem:", line)
            return
        need_signup = a.signup
        for vp_name, vp in VIEWPORTS.items():
            if a.only and vp_name != a.only:
                continue
            ctx = browser.new_context(locale="en-IN", **vp)
            # The pictures in docs/ show the generated demo history, labelled as such in the app. Since 2.6 the Demo data switch starts off for a shop
            # that has recorded orders (this throw-away database has a few, from demo_activity.py), so the person's own choice is set here, the way the switch would.
            ctx.add_init_script("try { localStorage.setItem('swara.includeDemo', '1') } catch (e) {}")
            page = ctx.new_page()
            tag = vp_name
            page.on("console", lambda m, t=tag: problems.append(f"[{t}] console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e, t=tag: problems.append(f"[{t}] pageerror: {e}"))
            page.on("requestfailed", lambda r, t=tag: problems.append(f"[{t}] request failed: {r.url} {r.failure}"))
            page.on("response", lambda r, t=tag: problems.append(f"[{t}] HTTP {r.status}: {r.url}") if r.status >= 400 else None)

            # what a visitor sees before signing in
            for name, path in VISITOR_PAGES:
                if want and name not in want:
                    continue
                page.goto(a.base + path, wait_until="networkidle")
                page.wait_for_timeout(700)
                shoot(page, out / f"{vp_name}-{name}.png", vp["viewport"], full=(name != "landing" or vp_name != "desktop"))
                print("saved", tag, name)
                if name == "landing" and vp_name == "desktop":
                    sec = page.locator("#security")
                    sec.scroll_into_view_if_needed()
                    page.wait_for_timeout(300)
                    sec.screenshot(path=str(out / f"{vp_name}-landing-security.png"))
                    print("saved", tag, "landing-security")
            authenticate(page, a.base, a.email, password, a.name, need_signup)
            need_signup = False
            if not want or "order-desk" in want:
                order_desk_conversation(page, a.base)
                shoot(page, out / f"{vp_name}-order-desk.png", vp["viewport"])
            for name, path in PAGES:
                if want and name not in want:
                    continue
                page.goto(a.base + path, wait_until="networkidle")
                page.wait_for_timeout(700)
                shoot(page, out / f"{vp_name}-{name}.png", vp["viewport"], full=not name.endswith("drawer"))   # a drawer is shown as a person sees it: the window, not the whole page
                print("saved", tag, name)
                if name == "orders-drawer" and vp_name == "desktop":
                    # What the browser's print window would show for this bill: the page in print state, rendered with print media.
                    page.evaluate("document.body.classList.add('printing-bill')")
                    page.emulate_media(media="print")
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(out / f"{vp_name}-print-bill.png"))
                    page.emulate_media(media="screen")
                    page.evaluate("document.body.classList.remove('printing-bill')")
                    print("saved", tag, "print-bill")
            ctx.close()
        browser.close()
    # The same 404 for a missing favicon etc. would be noise; show unique lines.
    uniq = sorted(set(problems))
    print("\nproblems seen:" if uniq else "\nno console errors, failed requests or HTTP errors seen")
    for line in uniq:
        print(" ", line)


if __name__ == "__main__":
    main()
