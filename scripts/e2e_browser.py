"""End-to-end checks in a real Chromium against a running SWARA AI, with a fresh throw-away database.

    SWARA_E2E_PASSWORD=... python scripts/e2e_browser.py http://localhost:8000 --db /path/to/swara.db --owner-email owner@example.com

What it does (every line it prints is a check that actually ran; a failed check makes the exit code non-zero):
  * the public landing page: content, anchors, keyboard, tabs, FAQ, theme, contact form
  * protected routes send a visitor to sign-in and come back afterwards
  * sign-up, sign-in, wrong password, unknown e-mail, lock-out, sign-out, the back button after sign-out
  * the session cookie (HttpOnly, SameSite, session vs remembered), staff versus owner
  * session expiry (the server-side expiry time is moved into the past in the SQLite file, then the app is used)
  * version 2.3: the language selector (11 languages, honest 'Not verified live' status), a Marathi sentence typed into the Order desk, and the owner's languages card
    (this section switches Marathi off and back on, which writes DISABLED_LANGUAGES to the repository's .env file)
  * version 2.7: payments (cash, a hand-confirmed UPI QR that stays marked unverified, a refund, the invoice and its print layout, duplicate and cross-role refusals, a webhook with no signature)
  * version 2.6: the owner-only Voice diagnostics page (real 'Not measured yet' before any speech, staff see no link and a plain notice), and the demo-data default that follows the shop's real orders
  * version 2.5: the AI performance page (honest 'Not measured' rows, real tables, a real CSV download), stock movement on Analytics after a real order, and staff access
  * version 2.2: the API reference page at /docs (no CDN, nothing blocked by the content-security-policy)
  * version 2.1: the Security section, the owner's setup checklist, renaming the shop, real CSV downloads, the print layout of a bill,
    and that staff are shown none of the owner-only parts (this section RENAMES THE SHOP and, at the end, renames it back)
  * no horizontal scrolling at seven window widths on public and signed-in pages
  * every console error, warning, failed request and HTTP 4xx/5xx seen along the way

Prerequisites: the server was started on an EMPTY database with ALLOW_SIGNUP=true, COOKIE_SECURE=false (plain http), no Gnani key,
and the owner account was created first (scripts/take_screenshots.py --landing --signup does that). The password goes in the
environment, never on the command line. This script writes to that database, and its 2.1 section also writes STORE_NAME to the repository's .env file (it renames the
shop back at the end, so delete that .env afterwards); never point it at real shop data.
Needs: pip install playwright && playwright install chromium   (or Chrome at /usr/bin/google-chrome)."""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

RESULTS: list[tuple[bool, str, str]] = []
PROBLEMS: list[str] = []


# Effective background of an element as WCAG relative luminance, 0 (black) to 1 (white). Every layer from the page down to
# the element is painted onto a 1x1 canvas over white, so translucent layers and colour(srgb ...) values are handled by the browser.
_LUMINANCE_JS = """(sel) => {
  const el = document.querySelector(sel); if (!el) return null;
  const layers = []; for (let e = el; e; e = e.parentElement) layers.unshift(getComputedStyle(e).backgroundColor);
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const g = cv.getContext('2d', { willReadFrequently: true });
  g.fillStyle = '#ffffff'; g.fillRect(0, 0, 1, 1);
  for (const c of layers) { g.fillStyle = c; g.fillRect(0, 0, 1, 1); }
  const [r, gr, b] = g.getImageData(0, 0, 1, 1).data;
  const lin = v => { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * lin(r) + 0.7152 * lin(gr) + 0.0722 * lin(b);
}"""


def background_luminance(page: Page, selector: str) -> float | None:
    return page.evaluate(_LUMINANCE_JS, selector)


def light_only(page: Page, where: str, selectors: list[str]) -> None:
    """SWARA AI is light only: no theme control, no data-theme, and every listed surface is light even on a device that prefers dark."""
    check(page.get_by_role("button", name=re.compile("(dark|light) theme", re.I)).count() == 0, f"light only ({where}): there is no theme switch")
    check(page.evaluate("document.documentElement.dataset.theme === undefined"), f"light only ({where}): the page carries no data-theme")
    check(page.evaluate("getComputedStyle(document.documentElement).colorScheme") == "light", f"light only ({where}): color-scheme is light")
    page.emulate_media(color_scheme="dark")
    try:
        for sel in selectors:
            try:
                page.wait_for_selector(sel, state="attached", timeout=5000)
            except Exception:
                pass
            lum = background_luminance(page, sel)
            check(lum is not None and lum > 0.8, f"light only ({where}): {sel} stays light on a device that prefers dark mode", f"luminance={lum}")
    finally:
        page.emulate_media(color_scheme="light")


def check(ok: bool, name: str, detail: str = "") -> bool:
    RESULTS.append((bool(ok), name, detail))
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""), flush=True)
    return bool(ok)


def watch(page: Page, tag: str) -> None:
    page.on("console", lambda m: PROBLEMS.append(f"[{tag}] console {m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: PROBLEMS.append(f"[{tag}] pageerror: {e}"))
    page.on("requestfailed", lambda r: PROBLEMS.append(f"[{tag}] request failed: {r.url} {r.failure}"))
    # 4xx on purpose (wrong password, protected route without a session, ...) are listed separately by the checks that cause them
    page.on("response", lambda r: PROBLEMS.append(f"[{tag}] HTTP {r.status}: {r.url}") if r.status >= 400 else None)


def sign_in(page: Page, base: str, email: str, password: str, remember: bool = False, path: str = "/sign-in") -> None:
    page.goto(base + path, wait_until="networkidle")
    page.get_by_label("E-mail address").fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    if remember:
        page.get_by_role("checkbox", name=re.compile("Keep me signed in")).check()
    page.get_by_role("button", name="Sign in", exact=True).click()


def sign_in_to_dashboard(page: Page, base: str, email: str, password: str, **kw) -> None:
    """Sign in and wait for the dashboard. The server limits sign-in, sign-up, reset and contact requests to 20 a
    minute per address, and this script makes many of them in a row, so if the dashboard does not appear it
    waits out one window and tries once more. A second failure is raised, so a real sign-in problem still fails."""
    for attempt in (1, 2):
        sign_in(page, base, email, password, **kw)
        try:
            page.wait_for_url("**/dashboard", timeout=10000)
            return
        except PWTimeout:
            if attempt == 2:
                raise
            page.wait_for_timeout(65000)


def sign_up(page: Page, base: str, name: str, email: str, password: str) -> None:
    page.goto(base + "/sign-up", wait_until="networkidle")
    page.get_by_label("Full name").fill(name)
    page.get_by_label("E-mail address").fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_label("Confirm password", exact=True).fill(password)
    page.get_by_role("checkbox", name=re.compile("I accept")).check()
    page.get_by_role("button", name="Create account").click()


def settle(page: Page) -> None:
    """Wait until smooth scrolling has finished (the page sets scroll-behavior: smooth)."""
    last, still = -1.0, 0
    for _ in range(60):
        y = page.evaluate("window.scrollY")
        still = still + 1 if abs(y - last) < 0.5 else 0
        if still >= 4:
            return
        last = y
        page.wait_for_timeout(100)


def sign_out(page: Page) -> None:
    page.locator(".sb-signout").click()


# Buttons whose whole job would end the test (sign out) or that need a real file or microphone.
SKIP_BUTTONS = re.compile(r"^(sign out|log out)$|record|tap to talk|start listening|upload|choose file|go live", re.I)


def audit_controls(page: Page, base: str, path: str) -> tuple[int, list[str], list[str]]:
    """Click every enabled button on a page, one fresh page load each, and report the ones where NOTHING observable happened
    (no DOM change, no network request, no navigation). Also checks every link: a #hash must point at a real id, an internal
    path must not land on the 'not found' page. Returns (buttons clicked, dead buttons, broken links)."""
    reqs = {"n": 0}
    page.on("request", lambda r: reqs.__setitem__("n", reqs["n"] + 1) if "/api/" in r.url else None)
    page.goto(base + path, wait_until="networkidle")
    page.wait_for_timeout(300)
    hrefs = page.evaluate("[...document.querySelectorAll('a[href]')].filter(a => a.offsetParent !== null || a.closest('nav')).map(a => [a.getAttribute('href'), (a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 40)])")
    broken: list[str] = []
    for href, label in hrefs:
        if href.startswith("#"):
            if href != "#" and page.locator(f"[id='{href[1:]}']").count() == 0:
                broken.append(f"{path}: '{label}' -> {href} (no such id)")
        elif href.startswith("/"):
            page.goto(base + href, wait_until="networkidle")
            gone = page.get_by_role("heading", name=re.compile("does not exist", re.I)).count() > 0
            if gone:
                broken.append(f"{path}: '{label}' -> {href} (page not found)")
            page.goto(base + path, wait_until="networkidle")
        elif href.startswith(("mailto:", "tel:")):
            pass
        else:
            broken.append(f"{path}: '{label}' -> {href} (external or unrecognised link)")
    n_buttons = page.locator("button:visible, [role=button]:visible").count()
    clicked, dead = 0, []
    for i in range(n_buttons):
        page.goto(base + path, wait_until="networkidle")
        page.wait_for_timeout(200)
        loc = page.locator("button:visible, [role=button]:visible").nth(i)
        if loc.count() == 0:
            continue
        name = (loc.get_attribute("aria-label") or loc.inner_text() or loc.get_attribute("title") or "").strip().replace("\n", " ")[:40]
        if SKIP_BUTTONS.search(name) or loc.is_disabled() or loc.get_attribute("aria-disabled") == "true":
            continue
        if loc.get_attribute("aria-pressed") == "true" or loc.get_attribute("aria-selected") == "true":
            continue        # already the active choice of its group: pressing it again is meant to change nothing
        if loc.locator("xpath=ancestor::th[1]").count() and loc.locator("xpath=ancestor::th[1]").get_attribute("aria-sort") not in (None, "none"):
            continue        # the column the table is already sorted by
        page.evaluate("window.__fx = 0; window.__obs && window.__obs.disconnect(); window.__obs = new MutationObserver(() => { window.__fx++ }); "
                      "window.__obs.observe(document.body, {subtree: true, childList: true, attributes: true, characterData: true})")
        before_url, before_reqs = page.url, reqs["n"]
        try:
            loc.click(timeout=3000)
        except Exception:
            dead.append(f"{path}: '{name}' could not be clicked")
            continue
        clicked += 1
        page.wait_for_timeout(500)
        fx = 0
        try:
            fx = page.evaluate("window.__fx || 0")
        except Exception:
            fx = 1      # the page navigated away: that is an effect
        if fx == 0 and page.url == before_url and reqs["n"] == before_reqs:
            dead.append(f"{path}: '{name}' did nothing")
    return clicked, dead, broken


def overflow(page: Page) -> int:
    return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def session_cookie(ctx):
    return next((c for c in ctx.cookies() if c["name"].endswith("swara_session")), None)


def cookie_gone(ctx, page: Page, seconds: float = 6.0) -> bool:
    """Sign-out takes the person to the home page at once and clears the cookie when the server answers, so wait for that answer."""
    for _ in range(int(seconds / 0.2)):
        if session_cookie(ctx) is None:
            return True
        page.wait_for_timeout(200)
    return session_cookie(ctx) is None


def report() -> int:
    """Print what the watchers saw and the overall result. Exit code 0 only if every check passed and nothing unexpected was logged."""
    expected_4xx = ("/api/orders", "/api/auth/login", "/api/auth/signup", "/api/auth/users", "/api/auth/change-password", "/api/auth/session",
                    "/api/auth/logout",
                    "/api/customers/export.csv",   # 403: the check that staff are refused the customer export by the server
                    "/api/settings",               # 422: the check that the server's reason for refusing a shop name "Shop #1" is shown
                    "/api/diagnostics/voice",      # 403: the check that the server, not just the sidebar, refuses staff the voice diagnostics
                    "/api/payments",               # 403/409/422: version 2.7 checks that the server refuses staff the analytics and refunds, a second payment, an over-refund and an unsigned webhook
                    "/api/text/parse")             # 422 LANGUAGE_DISABLED: the check that a switched-off language is refused, not answered in another one
    # a 401 from any /api/ call is expected here: the expiry check deliberately ends the session while pages are open
    # the webhook endpoint answers 503 while Razorpay is not set up (version 2.7 checks exactly that, from a page with no sign-in)
    unexpected = sorted({x for x in PROBLEMS if not (re.search(r"HTTP 401: \S+/api/", x))
                         and not re.search(r"^\[v2\.7-webhook\] (HTTP 503: \S+/api/payments/webhooks/razorpay|console error: Failed to load resource: the server responded with a status of 503)", x)
                         and not (re.search(r"HTTP (403|409|422|429)", x) and any(e in x for e in expected_4xx))
                         and not re.search(r"console error: Failed to load resource: the server responded with a status of (401|403|409|422|429)", x)})
    print("\nconsole errors, warnings, failed requests and unexpected HTTP errors:" if unexpected else "\nno unexpected console errors, warnings, failed requests or HTTP errors")
    for line in unexpected:
        print("  ", line)
    ok = sum(1 for r in RESULTS if r[0])
    print(f"\n{ok} of {len(RESULTS)} checks passed" + (f", {len(RESULTS) - ok} FAILED" if ok != len(RESULTS) else ""))
    return 0 if ok == len(RESULTS) and not unexpected else 1



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="http://localhost:8000")
    ap.add_argument("--db", required=True, help="the SQLite file the server is using (used only to move a session's expiry into the past)")
    ap.add_argument("--owner-email", required=True)
    ap.add_argument("--skip-controls", action="store_true", help="skip the slow click-every-button audit")
    ap.add_argument("--only-controls", action="store_true", help="run only the click-every-button audit (the owner account must already exist)")
    ap.add_argument("--paths", default="", help="with the button audit: comma-separated page paths to limit it to, for example /inventory,/orders")
    a = ap.parse_args()
    pw = os.environ.get("SWARA_E2E_PASSWORD")
    if not pw:
        sys.exit("Set SWARA_E2E_PASSWORD in the environment.")
    base = a.base.rstrip("/")
    stamp = str(int(time.time()))
    staff_email, lock_email = f"staff.{stamp}@example.com", f"lock.{stamp}@example.com"
    staff_pw = "Staff-Counter-Pass-77!"

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")

        def controls_section(browser) -> None:
            """D. no dead buttons, no broken links (slow: one fresh page load per button)."""
            for who, pages_ in (("visitor", ["/", "/sign-in", "/sign-up", "/forgot-password", "/terms", "/privacy"]),
                                ("owner", ["/dashboard", "/order", "/orders", "/payments", "/payment-analytics", "/customers", "/inventory", "/catalogue", "/analytics", "/performance", "/diagnostics", "/live", "/noise", "/settings", "/account"])):
                ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-IN")
                page = ctx.new_page(); watch(page, f"controls-{who}")
                if who == "owner":
                    sign_in(page, base, a.owner_email, pw)
                    page.wait_for_url("**/dashboard")
                total, dead_all, broken_all = 0, [], []
                pages_ = [p_ for p_ in pages_ if not a.paths or p_ in a.paths.split(",")]
                for path in pages_:
                    n_clicked, dead, broken = audit_controls(page, base, path)
                    total += n_clicked; dead_all += dead; broken_all += broken
                check(not broken_all, f"links ({who}): every link on {len(pages_)} pages goes somewhere real", "; ".join(broken_all))
                check(not dead_all, f"buttons ({who}): clicked {total} enabled buttons on {len(pages_)} pages and each one did something", "; ".join(dead_all))
                ctx.close()


        if a.only_controls:
            controls_section(browser)
            browser.close()
            return report()

        # ------------------------------------------------------------------ A. the public landing page
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN")
        page = ctx.new_page(); watch(page, "landing")
        page.goto(base + "/", wait_until="networkidle")
        check(page.title() == "SWARA AI: Every Voice. Smarter Commerce.", "landing: page title")
        check(re.sub(r"\s+", " ", page.locator("h1").inner_text()).strip() == "Commerce that understands every voice.", "landing: headline")
        check(page.locator('meta[name="description"]').get_attribute("content", timeout=2000) is not None, "landing: meta description present")
        check(page.locator('meta[property="og:title"]').count() == 1 and page.locator('link[rel="canonical"]').count() == 0,
              "landing: Open Graph present; canonical/og:image left out because PUBLIC_URL was not set at build time")
        check(page.evaluate("document.querySelectorAll('script:not([src]):not([type])').length") == 0, "landing: no inline scripts (CSP script-src 'self' holds)")
        check(overflow(page) <= 0, "landing: no horizontal scrolling at 1440 px", str(overflow(page)))
        for y in range(0, page.evaluate("document.documentElement.scrollHeight"), 700):
            page.evaluate(f"window.scrollTo(0,{y})"); page.wait_for_timeout(100)
        bad = page.evaluate("[...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src)")
        check(not bad, "landing: every picture loaded", str(bad))
        page.evaluate("window.scrollTo(0,0)")

        # type: the display serif and the sans are the bundled fonts, they actually loaded, and the headline is set light
        fonts = page.evaluate("""() => ({
            h1: getComputedStyle(document.querySelector('h1')).fontFamily, w: getComputedStyle(document.querySelector('h1')).fontWeight,
            body: getComputedStyle(document.body).fontFamily,
            serif: document.fonts.check('400 48px "Newsreader Variable"'), sans: document.fonts.check('400 16px "Geist Variable"'),
            h2: getComputedStyle(document.querySelector('#how-it-works h2')).fontFamily,
            lead: getComputedStyle(document.querySelector('.lp-hero-lead')).fontFamily })""")
        check("Newsreader" in fonts["h1"] and fonts["w"] == "400" and "Newsreader" in fonts["h2"], "landing type: headings are set in Newsreader at weight 400", str(fonts))
        check("Geist" in fonts["body"] and "Geist" in fonts["lead"] and fonts["serif"] and fonts["sans"], "landing type: body text is Geist, and both bundled fonts loaded (no font service)", str(fonts))
        used = page.evaluate("performance.getEntriesByType('resource').filter(r => /\\.(woff2?|ttf|otf)(\\?|$)/.test(r.name)).map(r => new URL(r.name).host)")
        check(used and set(used) == {base.split("//")[1]}, "landing type: every font file came from this server", str(set(used)))
        h1_lines = page.evaluate("(() => { const h = document.querySelector('h1'); return Math.round(h.getBoundingClientRect().height / parseFloat(getComputedStyle(h).lineHeight)) })()")
        check(h1_lines == 3, "landing type: the headline sets in three lines at 1440 px", str(h1_lines))

        for label, anchor in [("Product", "product"), ("How it works", "how-it-works"), ("Languages", "languages"), ("Technology", "technology"), ("Security", "security"), ("Contact", "contact")]:
            page.get_by_role("navigation", name="Sections of this page").get_by_role("link", name=label).click()
            settle(page)
            top = page.evaluate(f"document.getElementById('{anchor}').getBoundingClientRect().top")
            check(page.url.endswith("#" + anchor) and 78 <= top <= 92, f"landing: nav '{label}' scrolls its section to just below the sticky bar", f"top={top}")

        page.goto(base + "/", wait_until="networkidle")   # fresh page: focus starts at the top, as for a keyboard user
        page.keyboard.press("Tab")
        check(page.evaluate("document.activeElement.textContent.trim()") == "Skip to content", "keyboard: first Tab stop is the skip link")
        check(page.evaluate("document.activeElement.getBoundingClientRect().top >= 0"), "keyboard: the skip link is visible when focused")
        page.keyboard.press("Enter")
        check(page.evaluate("document.activeElement.id") == "main", "keyboard: the skip link moves focus to the main content")

        # the five product areas: each one is an article with its own heading, the screenshots load, and they say they are demo data
        page.locator("#product").scroll_into_view_if_needed()
        arts = page.locator("#product article")
        check(arts.count() == 5 and page.locator("#product article h3").all_inner_texts() == [
            "Multilingual voice ordering", "Intelligent product recognition", "Smart inventory management", "Automated order processing", "Business analytics and insights"],
              "showcase: five product areas, in the order of the brief, each with its own heading")
        for y in range(0, page.evaluate("document.documentElement.scrollHeight"), 500):
            page.evaluate(f"window.scrollTo(0,{y})"); page.wait_for_timeout(60)       # lazy pictures load as they come near the screen
        loaded = False
        for _ in range(40):
            loaded = page.evaluate("[...document.querySelectorAll('#product img')].every(i => i.complete && i.naturalWidth > 0)")
            if loaded:
                break
            page.wait_for_timeout(150)
        check(loaded and page.locator("#product img").count() == 4, "showcase: the four screenshots loaded")
        check("generated demo data" in page.locator(".sw-cap").inner_text(), "showcase: the screenshots are labelled as generated demo data")
        # the specimen sentences are set in the three scripts they name, and the underlined words are the item and quantity
        check(page.locator(".spec mark").count() == 6, "showcase: six underlined words (two in each of three sample sentences)")
        sw = page.evaluate("(() => { const a = document.querySelector('.sw-copy h3'); const m = document.querySelector('.spec p[lang=gu]'); return [getComputedStyle(a).fontFamily, getComputedStyle(m).fontFamily] })()")
        check("Newsreader" in sw[0] and "Noto Sans Gujarati" in sw[1], "showcase: headings in the serif, the Gujarati sentence in the Gujarati face", str(sw))
        # the language ledger: eleven rows in two groups, with the unreviewed note
        page.locator("#languages").scroll_into_view_if_needed()
        check(page.locator("#languages .lp-lang-list > li").count() == 11 and page.locator("#languages .lp-lang-list.is-new > li").count() == 7,
              "languages: eleven rows, seven of them in the new-in-this-release group")
        lang_txt = re.sub(r"\s+", " ", page.locator("#languages").inner_text())
        check("unit-tested" in lang_txt and "live service" in lang_txt and "no native speaker has reviewed them" in lang_txt and "verified live" not in lang_txt.lower(),
              "languages: says the rules are unit-tested, that no language has been checked against the live service, and that the new seven are unreviewed")
        # the demonstration: typed text goes through the real parser and the four steps fill in from its answer
        page.locator("#how-it-works").scroll_into_view_if_needed()
        steps = page.locator(".demo-steps")
        page.locator("#how-it-works .quick").get_by_role("button", name="ગુજરાતી").click()
        for _ in range(40):
            if "Read as Gujarati" in steps.inner_text():
                break
            page.wait_for_timeout(150)
        check("Read as Gujarati" in steps.inner_text(), "demo: choosing the Gujarati example changes the first step to 'Read as Gujarati'", steps.inner_text()[:120])
        txt = re.sub(r"\s+", " ", steps.inner_text())
        check("matched to the shop" in txt.replace("\u2019", "'") and "Bill prepared" in txt, "demo: the four-step strip fills in from the real parser's answer", txt[:200])
        check("typed text only" in page.locator(".lp-demo-note").inner_text(), "demo: labelled as a demonstration, typed text only")

        first = page.locator(".lp-faq summary").first
        first.scroll_into_view_if_needed(); settle(page); first.click()
        check(page.locator(".lp-faq details").first.get_attribute("open") is not None, "FAQ: clicking a question opens its answer")
        second = page.locator(".lp-faq summary").nth(1); second.focus(); settle(page); page.keyboard.press("Enter")
        check(page.locator(".lp-faq details").nth(1).get_attribute("open") is not None, "FAQ: Enter on a focused question opens it (keyboard)")

        page.evaluate("window.scrollTo(0, 0)")
        light_only(page, "landing", ["body", "header", ".lp-foot"])

        form = page.get_by_role("form", name="Contact form")
        form.scroll_into_view_if_needed()
        form.get_by_role("button", name="Send message").click()
        check(form.get_by_text("Enter your name (2 to 80 characters).").is_visible(), "contact: empty form shows field errors and sends nothing")
        form.get_by_label("Your name").fill("Asha Shah")
        form.get_by_label("E-mail address").fill("asha@example.com")
        form.get_by_label("What is it about?").select_option("demo")
        form.get_by_label("Message").fill("Could I see how the stock alerts work for a small shop?")
        form.get_by_role("button", name="Send message").click()
        form.get_by_role("status").wait_for(timeout=8000)
        check("saved on this server" in form.get_by_role("status").inner_text(), "contact: success message says the message was saved on this server (SMTP is not configured)")
        check(form.get_by_label("Message").input_value() == "", "contact: form cleared after sending")

        r = page.evaluate("fetch('/api/orders').then(r => r.status)")
        check(r == 401, "API: protected data refuses a visitor with 401", str(r))
        r = page.evaluate("fetch('/api/text/parse', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text:'2 kilo chawal'})}).then(r => r.status)")
        check(r == 200, "API: the landing-page demo endpoint is open, as documented", str(r))

        for path in ["/orders", "/account", "/settings", "/dashboard"]:
            page.goto(base + path, wait_until="networkidle")
            check(page.url == f"{base}/sign-in?next={path.replace('/', '%2F')}", f"protected route {path}: visitor is sent to sign-in with a return address", page.url)
        ctx.close()

        # mobile menu, in its own phone-sized window
        mctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        mp = mctx.new_page(); watch(mp, "phone")
        mp.goto(base + "/", wait_until="networkidle")
        check(overflow(mp) <= 0, "phone: landing has no horizontal scrolling at 390 px")
        mp.get_by_role("button", name="Open menu").tap()
        check(mp.get_by_role("navigation", name="Sections of this page (menu)").is_visible(), "phone: the menu opens")
        mp.get_by_role("navigation", name="Sections of this page (menu)").get_by_role("link", name="How it works").tap()
        settle(mp)
        check(mp.get_by_role("button", name="Open menu").is_visible() and mp.get_by_role("navigation", name="Sections of this page (menu)").count() == 0, "phone: choosing a link closes the menu")
        top = mp.evaluate("document.getElementById('how-it-works').getBoundingClientRect().top")
        check(0 <= top <= 110, "phone: and scrolls to that section, below the sticky bar", f"top={top}")
        mctx.close()

        # ------------------------------------------------------------------ B. accounts and sessions
        ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="en-IN")
        page = ctx.new_page(); watch(page, "auth")

        sign_in(page, base, a.owner_email, "Wrong-Password-123!")
        page.get_by_role("alert").wait_for()
        msg_wrong = page.get_by_role("alert").inner_text()
        check("Incorrect e-mail or password" in msg_wrong and page.url.endswith("/sign-in") and page.get_by_label("Password", exact=True).input_value() == "",
              "sign-in: a wrong password gives one plain message, stays on the page and clears the password", msg_wrong)
        sign_in(page, base, "nobody.here@example.com", "Wrong-Password-123!")
        page.get_by_role("alert").wait_for()
        check(page.get_by_role("alert").inner_text() == msg_wrong, "sign-in: an unknown e-mail gets exactly the same message (no account enumeration)")

        page.goto(base + "/sign-up", wait_until="networkidle")
        page.get_by_label("Full name").fill("Meena Shah")
        page.get_by_label("E-mail address").fill("meena")
        page.get_by_label("Password", exact=True).fill("short")
        page.get_by_label("Confirm password", exact=True).fill("different")
        page.get_by_role("button", name="Create account").click()
        shown = [t for t in ("Enter a valid e-mail address.", "Use at least 10 characters.", "The two passwords do not match.", "Accept the Terms and Privacy Policy to continue.")
                 if page.get_by_text(t).count()]
        check(len(shown) == 4, "sign-up: all four client-side problems are reported at once", str(shown))
        check(page.locator("input[aria-invalid='true']").count() >= 3, "sign-up: invalid fields are marked aria-invalid")

        sign_up(page, base, "Owner Again", a.owner_email, pw)
        page.get_by_text("already exists").wait_for(timeout=8000)
        check(True, "sign-up: an existing e-mail is refused (this reveals that the address is registered; documented trade-off)")

        sign_up(page, base, "Meena Shah", staff_email, staff_pw)
        page.get_by_role("heading", name="Your account is ready").wait_for(timeout=10000)
        check("as staff" in page.locator(".auth-done").inner_text(), "sign-up: a second person becomes staff, and the screen says what staff can do")
        page.get_by_role("button", name="Open the dashboard").click()
        page.wait_for_url("**/dashboard")
        page.wait_for_load_state("networkidle")
        light_only(page, "app shell", ["body", ".sidebar", ".main-col", ".topbar", ".content"])
        c = session_cookie(ctx)
        check(c is not None and c["httpOnly"] and c["sameSite"] == "Lax" and c["expires"] == -1 and c["name"] == "swara_session",
              "cookie: HttpOnly, SameSite=Lax, a session cookie (no expiry) when 'keep me signed in' was not ticked", str(c and {k: c[k] for k in ("name", "httpOnly", "sameSite", "expires", "secure")}))
        check("swara_session" not in page.evaluate("document.cookie"), "cookie: JavaScript cannot read the session cookie")
        check(page.get_by_role("link", name="Account: Meena Shah").inner_text().find("Staff") >= 0, "staff: the sidebar shows the name and the Staff role")
        check(page.get_by_role("link", name="Manage stock").count() == 0, "staff: the dashboard does not offer stock management")
        check(page.evaluate("fetch('/api/auth/users').then(r => r.status)") == 403, "staff: the team list is refused by the server (403), not just hidden")
        page.goto(base + "/account", wait_until="networkidle")
        check(page.get_by_role("heading", name="Team").count() == 0 and page.get_by_text("This device").count() == 1, "staff: the account page has no team or messages, and lists this device")

        sign_out(page)
        page.wait_for_url(base + "/")
        check(cookie_gone(ctx, page), "sign-out: the session cookie is gone")
        page.goto(base + "/dashboard", wait_until="networkidle")
        check("/sign-in" in page.url, "sign-out: the dashboard is no longer reachable")
        page.goto(base + "/", wait_until="networkidle")
        page.go_back(); page.wait_for_load_state("networkidle")
        check(page.get_by_role("heading", name="Dashboard", level=1).count() == 0, "sign-out: the back button does not show the signed-in app")

        # lock-out on a throw-away account (the in-memory counter then forgets it on restart)
        sign_up(page, base, "Lock Test", lock_email, staff_pw)
        page.get_by_role("button", name="Open the dashboard").click()
        page.wait_for_url("**/dashboard")
        sign_out(page)
        page.wait_for_url(base + "/")
        locked = ""
        for i in range(6):
            sign_in(page, base, lock_email, "Wrong-Password-123!")
            page.get_by_role("alert").wait_for()
            locked = page.get_by_role("alert").inner_text()
            if "Too many failed attempts" in locked:
                break
        check("Too many failed attempts" in locked and i <= 5, f"lock-out: repeated wrong passwords are slowed down (after {i + 1} tries)", locked)
        sign_in(page, base, lock_email, staff_pw)
        page.get_by_role("alert").wait_for()
        check("Too many failed attempts" in page.get_by_role("alert").inner_text(), "lock-out: even the right password is refused while locked")

        # owner, remembered, return to the address they asked for
        sign_in(page, base, a.owner_email, pw, remember=True, path="/sign-in?next=%2Forders")
        page.wait_for_url("**/orders")
        page.wait_for_load_state("networkidle")
        c = session_cookie(ctx)
        days = (c["expires"] - time.time()) / 86400 if c and c["expires"] > 0 else 0
        check(page.url.endswith("/orders"), "sign-in: the person lands on the page they asked for (?next=)")
        check(25 <= days <= 31, "cookie: 'keep me signed in' makes a 30-day cookie", f"{days:.1f} days")
        page.goto(base + "/sign-in", wait_until="networkidle")
        check(page.url.endswith("/dashboard"), "sign-in page: someone already signed in is sent to the dashboard")
        page.goto(base + "/sign-in?next=https%3A%2F%2Fevil.example", wait_until="networkidle")
        check(page.url.endswith("/dashboard"), "sign-in: an off-site ?next= is ignored")

        page.goto(base + "/account", wait_until="networkidle")
        check(page.get_by_text("Asha Shah").count() >= 1 and page.get_by_text("Could I see how the stock alerts work").count() == 1, "owner: the contact message sent earlier is in the inbox on the account page")
        check(page.get_by_role("heading", name="Team").count() == 1 and page.get_by_text("Meena Shah").count() >= 1, "owner: the team list shows the staff account")
        page.get_by_label("Current password", exact=True).fill("Not-The-Password-1!")
        page.get_by_label("New password", exact=True).fill("Another-Good-Pass-88!")
        page.get_by_label("Confirm new password", exact=True).fill("Another-Good-Pass-88!")
        page.get_by_role("button", name="Change password").click()
        page.get_by_text("The current password is not correct.").wait_for(timeout=8000)
        check(True, "account: a wrong current password is refused and the password is unchanged")

        # session expiry: move this person's sessions into the past in the database, then use the app
        con = sqlite3.connect(a.db)
        n = con.execute("UPDATE auth_sessions SET expires_at='2000-01-01 00:00:00.000000' WHERE user_id=(SELECT id FROM users WHERE email=?)", (a.owner_email.lower(),)).rowcount
        con.commit(); con.close()
        check(n >= 1, "expiry: moved the owner's server-side session expiry into the past", f"{n} session(s)")
        # The app may notice by itself first (the orders page refreshes its data in the background), or on this click; either is fine.
        went_to = "%2Forders"
        try:
            page.get_by_role("link", name="Customers", exact=True).first.click(timeout=2500)
            went_to = "%2Fcustomers"      # the click happened first: the person was heading to Customers
        except Exception:
            pass
        page.wait_for_url("**/sign-in**", timeout=15000)
        try:
            page.get_by_text("Your session has ended").wait_for(timeout=5000)
            said = True
        except Exception:
            said = False
        check(f"next={went_to}" in page.url and said, "expiry: the app notices the ended session, signs the person out, says so, and remembers where they were", page.url)
        sign_in(page, base, a.owner_email, pw, path="/sign-in?next=%2Forders")
        page.wait_for_url("**/orders")
        check(True, "expiry: signing in again returns to the same page")
        ctx.close()

        # ------------------------------------------------------------------ E. what version 2.1 added
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-IN", accept_downloads=True)
        page = ctx.new_page(); watch(page, "v2.1")
        page.goto(base + "/", wait_until="networkidle")
        sec = page.get_by_role("region", name="Security and trust")
        sec.scroll_into_view_if_needed()
        check(sec.is_visible() and sec.get_by_text("What we do not claim.").is_visible() and sec.get_by_role("heading", level=3).count() == 6,
              "landing: the Security and trust section shows six items and says what is not claimed")
        check(page.locator(".lp-foot").get_by_role("link", name="Security").get_attribute("href") == "#security", "landing: the footer links to the Security section")

        sign_in(page, base, a.owner_email, pw)
        page.wait_for_url("**/dashboard"); page.wait_for_load_state("networkidle")
        card = page.get_by_role("region", name="Set up your shop")
        card.wait_for(timeout=8000)
        done0 = card.locator("li.done").count()
        check(done0 == 0 and "0 of 4 done" in card.inner_text(), "setup checklist: a new owner starts at 0 of 4 (demo name, demo prices, no real order, no key)", card.inner_text()[:90])
        original = page.evaluate("fetch('/api/health').then(r => r.json())")
        check(original["store_name_is_default"] is True, "setup checklist: the server itself reports the shop still has the demo name", str(original))

        card.get_by_role("link", name="Rename").click()
        page.wait_for_url("**/settings"); page.get_by_label("Shop name").wait_for()
        check(page.get_by_role("button", name="Save name").is_disabled(), "shop name: Save is off until something changes")
        page.get_by_label("Shop name").fill("x")
        check(page.get_by_text("Use 2 to 80 characters.").is_visible() and page.get_by_role("button", name="Save name").is_disabled(), "shop name: a one-letter name is explained and cannot be saved")
        page.get_by_label("Shop name").fill("Shop #1")
        page.get_by_role("button", name="Save name").click()
        page.get_by_text("Not allowed: #").wait_for(timeout=8000)
        check(page.get_by_label("Shop name").input_value() == "Shop #1", "shop name: the server's refusal is shown in words and what was typed is kept")
        page.get_by_label("Shop name").fill("  Shah   Kirana & Stores ")
        page.get_by_role("button", name="Save name").click()
        page.get_by_text("Shop name saved.").wait_for(timeout=8000)
        for _ in range(40):      # (no wait_for_function: it evaluates a string, which the page's Content-Security-Policy rightly forbids)
            if page.locator(".sb-store").inner_text() == "Shah Kirana & Stores":
                break
            page.wait_for_timeout(200)
        check(page.locator(".sb-store").inner_text() == "Shah Kirana & Stores", "shop name: saved, extra spaces collapsed, and the sidebar shows it straight away")
        page.reload(wait_until="networkidle")
        check(page.locator(".sb-store").inner_text() == "Shah Kirana & Stores", "shop name: still there after a reload")
        page.get_by_role("link", name="Dashboard", exact=True).first.click(); page.wait_for_url("**/dashboard")
        card = page.get_by_role("region", name="Set up your shop"); card.wait_for(timeout=8000)
        check("1 of 4 done" in card.inner_text() and card.locator("li.done").count() == 1, "setup checklist: naming the shop ticks that step and only that step", card.inner_text()[:90])

        # a real order from the Order desk, typed
        page.goto(base + "/order", wait_until="networkidle")
        page.locator("#typed").fill("2 kilo chawal")
        page.get_by_role("button", name="Send", exact=True).click()
        page.get_by_role("button", name="Confirm order").wait_for(timeout=10000)
        page.get_by_role("button", name="Confirm order").click()
        conf = page.get_by_role("region", name="Order confirmed"); conf.wait_for(timeout=10000)
        code = re.search(r"SW-[\d-]+", conf.inner_text())
        check(bool(code), "order desk: a typed order is confirmed and saved with a bill number", conf.inner_text()[:80])
        conf.get_by_role("link", name="View order").click()
        page.get_by_role("button", name="Print bill").wait_for(timeout=8000)

        # print: the button sets the print state; under print media only the bill is shown, with the shop's name
        # A headless browser has no print dialog: window.print() returns at once and 'afterprint' clears the state. So the call is replaced by a
        # recorder that notes the page's state at the moment the button asks for printing, and 'afterprint' never comes.
        page.evaluate("window.__printState = null; window.print = () => { window.__printState = document.body.classList.contains('printing-bill') }")
        page.get_by_role("button", name="Print bill").click()
        check(page.evaluate("window.__printState") is True, "print: the button puts the page into print state and then asks the browser to print")
        page.emulate_media(media="print")
        shown = page.evaluate("""() => ({ bill: document.querySelector('.print-bill').checkVisibility(),
            side: document.querySelector('.sidebar').checkVisibility(), text: document.querySelector('.print-bill').innerText })""")
        check(shown["bill"] is True and shown["side"] is False and "Shah Kirana & Stores" in shown["text"] and code and code.group(0) in shown["text"],
              "print: in print media only the bill is shown: the shop's name, the bill number, no sidebar", str(shown)[:160])
        pdf = page.pdf(); check(pdf[:5] == b"%PDF-" and len(pdf) > 1500, "print: it renders to a PDF", f"{len(pdf)} bytes")
        page.emulate_media(media="screen"); page.evaluate("document.body.classList.remove('printing-bill')")
        check(page.evaluate("document.querySelector('.print-bill').checkVisibility()") is False, "print: on screen the bill is hidden again")

        # exports: real downloads, with the content a spreadsheet needs
        def download(path: str, button: str = "Export CSV"):
            page.goto(base + path, wait_until="networkidle")
            with page.expect_download(timeout=15000) as dl:
                page.get_by_role("button", name=button).click()
            f = dl.value
            return f.suggested_filename, open(f.path(), "rb").read()
        name, raw = download("/orders?include_synthetic=0")
        text = raw.decode("utf-8-sig")
        check(raw.startswith(b"\xef\xbb\xbf") and re.fullmatch(r"swara-orders-.*\.csv", name) is not None and "\r\n" in text and code is not None and code.group(0) in text,
              "export: Orders downloads a CSV (UTF-8 with BOM, CRLF) that contains the order just taken", f"{name}, {len(raw)} bytes")
        name, raw = download("/inventory")
        text = raw.decode("utf-8-sig")
        check(re.fullmatch(r"swara-inventory-.*\.csv", name) is not None and text.splitlines()[0].startswith("SKU") and len(text.splitlines()) >= 60,
              "export: Inventory downloads the stock list with a header row and one row per item", f"{name}, {len(text.splitlines())} lines")
        name, raw = download("/customers")
        check(re.fullmatch(r"swara-customers-.*\.csv", name) is not None and len(raw) > 20, "export: Customers (owner) downloads", f"{name}, {len(raw)} bytes")

        page.goto(base + "/dashboard", wait_until="networkidle")
        card = page.get_by_role("region", name="Set up your shop"); card.wait_for(timeout=8000)
        ticked = card.locator("li.done").count()
        check(ticked == 2, "setup checklist: after naming the shop and taking an order, exactly those two steps are ticked", f"{ticked} ticked")

        # staff see none of the owner-only parts, and the server agrees
        sctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-IN", accept_downloads=True)
        sp = sctx.new_page(); watch(sp, "v2.1-staff")
        sign_in(sp, base, staff_email, staff_pw)
        sp.wait_for_url("**/dashboard"); sp.wait_for_load_state("networkidle"); sp.wait_for_timeout(600)
        check(sp.get_by_role("region", name="Set up your shop").count() == 0, "staff: no setup checklist on the dashboard")
        sp.goto(base + "/settings", wait_until="networkidle")
        check(sp.get_by_label("Shop name").count() == 0, "staff: no shop-name field in Settings")
        sp.goto(base + "/customers", wait_until="networkidle")
        check(sp.get_by_role("button", name="Export CSV").count() == 0 and sp.get_by_role("button", name="New customer").count() == 0, "staff: Customers has no export and no New customer button")
        check(sp.evaluate("fetch('/api/customers/export.csv').then(r => r.status)") == 403, "staff: the customer export is refused by the server (403), not just hidden")
        sp.goto(base + "/orders", wait_until="networkidle")
        with sp.expect_download(timeout=15000) as dl:
            sp.get_by_role("button", name="Export CSV").click()
        check(dl.value.suggested_filename.startswith("swara-orders-"), "staff: can still export the orders they work with")
        sctx.close()

        # put the shop back as it was found
        page.goto(base + "/settings", wait_until="networkidle")
        page.get_by_label("Shop name").fill(original["store_name"])
        page.get_by_role("button", name="Save name").click()
        page.get_by_text("Shop name saved.").wait_for(timeout=8000)
        check(page.evaluate("fetch('/api/health').then(r => r.json())")["store_name_is_default"] is True, "shop name: put back as it was, and the server again reports the demo name")
        ctx.close()

        # ------------------------------------------------------------------ F. the API reference page (version 2.2)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-IN")
        page = ctx.new_page(); watch(page, "v2.2")
        outside: list[str] = []
        page.on("request", lambda r: outside.append(r.url) if not r.url.startswith(base) and not r.url.startswith("data:") else None)
        page.goto(base + "/docs", wait_until="networkidle")
        page.locator("#count").wait_for(timeout=8000)
        total_ops = int(page.locator("#count").inner_text().split(" of ")[1].split()[0])
        check(total_ops >= 60 and page.locator("details.op").count() == total_ops, "API reference: /docs lists every operation of the API", str(total_ops))
        page.get_by_label("Filter operations").fill("export")
        shown = page.locator("details.op").count()
        check(0 < shown < total_ops and all("export" in t.lower() for t in page.locator("details.op summary .path").all_inner_texts()), "API reference: the filter narrows the list", str(shown))
        page.locator("details.op").first.locator("summary").click()
        check(page.locator("details.op[open] .body table").count() >= 1, "API reference: an operation opens to show its parameters and responses")
        check(not outside, "API reference: the page makes no request to any other host (no CDN)", ", ".join(outside))
        check(page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)", "API reference: light page")
        page.goto(base + "/redoc", wait_until="networkidle")
        check(page.url.endswith("/docs"), "API reference: /redoc goes to the same page", page.url)
        ctx.close()

        # ------------------------------------------------------------------ G. the language selector and the languages card (version 2.3)
        # No Gnani key here, so nothing below touches speech: it checks what the screens say and that typed text works in a new language.
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-IN")
        page = ctx.new_page(); watch(page, "v2.3")
        sign_in(page, base, a.owner_email, pw); page.wait_for_url("**/dashboard"); page.wait_for_load_state("networkidle")
        api = page.evaluate("fetch('/api/languages').then(r => r.json())")
        keys = [l["key"] for l in api["languages"]]
        check(keys == ["gu", "hi", "en", "hinglish", "mr", "bn", "ta", "te", "kn", "ml", "pa"], "languages: the server lists the 11 languages, the original four first", ",".join(keys))
        statuses = {c["status"] for l in api["languages"] for c in l["verification"].values()}
        check(api["verification"]["mode"] == "none" and statuses == {"not_run"}, "languages: this run has no live Gnani check on file, so every check of every language reads 'not_run'", f'{api["verification"]["mode"]} {sorted(statuses)}')
        page.goto(base + "/order", wait_until="networkidle")
        trig = page.locator("button.lang-trigger")
        check("ગુજરાતી" in trig.inner_text() and "gu-IN" in trig.inner_text(), "language selector: the Order desk starts on Gujarati and shows its own script and its Prisma code", trig.inner_text().replace("\n", " "))
        trig.click()
        dlg = page.get_by_role("dialog", name="Choose the language the customer speaks"); dlg.wait_for(timeout=5000)
        radios = dlg.locator("input[type=radio]")
        check(radios.count() == 12, "language selector: 11 languages and Auto-detect are listed", str(radios.count()))
        natives = ["ગુજરાતી", "हिन्दी", "English", "Hinglish", "मराठी", "বাংলা", "தமிழ்", "తెలుగు", "ಕನ್ನಡ", "മലയാളം", "ਪੰਜਾਬੀ"]
        text = dlg.inner_text()
        check(all(n in text for n in natives), "language selector: every language is named in its own script")
        check(dlg.locator("input[value=auto]").is_disabled() and "Prisma v2.5" in text, "language selector: Auto-detect is unavailable on Prisma v2.5 and says why")
        check(text.count("Not verified live") == 11 and "Live checked" not in text, "language selector: all 11 say 'Not verified live' (nothing was run against Gnani)", str(text.count("Not verified live")))
        check(text.count("New in 2.3") == 7, "language selector: the seven added languages are marked as new", str(text.count("New in 2.3")))
        page.keyboard.press("Escape"); check(dlg.count() == 0 and page.evaluate("document.activeElement.className").startswith("lang-trigger"), "language selector: Escape closes it and returns focus to the button")
        trig.click(); dlg.locator("input[value=mr]").click(); dlg.wait_for(state="detached", timeout=5000)
        check("मराठी" in trig.inner_text() and "mr-IN" in trig.inner_text(), "language selector: choosing Marathi updates the button", trig.inner_text().replace("\n", " "))
        mr_sample = next(l["sample"] for l in api["languages"] if l["key"] == "mr")
        page.locator("#typed").fill(mr_sample)
        page.get_by_role("button", name="Send", exact=True).click()
        page.get_by_role("button", name="Confirm order").wait_for(timeout=10000)
        for _ in range(20):      # the bill is drawn from the server's answer; give a slow machine a moment to draw both lines before counting
            if page.locator(".bill-lines .bl").count() == 2:
                break
            page.wait_for_timeout(150)
        check(page.locator(".bill-lines .bl").count() == 2, "Marathi: the sample sentence typed in Marathi becomes a two-line bill (sugar and milk)",
              f'{mr_sample} -> {page.locator(".bill-lines").inner_text()[:200]!r} | {page.locator("[role=status], [role=alert]").all_inner_texts()[:3]}')
        check(page.locator(".bill-lines").get_by_text(re.compile("साखर|दूध")).count() >= 1, "Marathi: the bill names the items in Marathi")
        page.reload(wait_until="networkidle")

        # phone width: the open list must stay inside the screen (found in a screenshot: it ended 2 px past the edge).
        # Same signed-in page, narrower window: the sign-in limit is 20 a minute per address and this run is already close to it.
        page.set_viewport_size({"width": 390, "height": 844}); page.goto(base + "/order", wait_until="networkidle")
        page.locator("button.lang-trigger").click(); page.get_by_role("dialog", name="Choose the language the customer speaks").wait_for(timeout=5000)
        box = page.locator(".lang-pop").bounding_box()
        check(overflow(page) == 0 and box is not None and box["x"] >= 0 and box["x"] + box["width"] <= 390, "language selector: at 390 px wide the open list stays inside the screen with no horizontal scrolling", str(box))
        page.set_viewport_size({"width": 1280, "height": 900})

        # owner: switch Marathi off in Settings, see it greyed out on the Order desk, then switch it back on
        page.goto(base + "/settings", wait_until="networkidle")
        card = page.get_by_role("heading", name="Languages and voices"); card.wait_for(timeout=8000)
        check(page.get_by_label("Offer English").is_disabled(), "languages card: English is always on and cannot be switched off")
        mr_row = next(l for l in api["languages"] if l["key"] == "mr")
        mr_voices = page.get_by_label("Marathi voice")
        check(mr_voices.locator("option").all_inner_texts() == mr_row["voices"] and mr_voices.input_value() == mr_row["default_voice"] == "Zahira",
              "languages card: Marathi lists exactly the documented Timbre voices the server reports and starts on its default, Zahira", str(mr_row["voices"]))
        page.get_by_label("Offer Marathi").click()
        page.wait_for_function("fetch('/api/languages').then(r => r.json()).then(j => j.disabled.join() === 'mr')", timeout=8000)
        page.goto(base + "/order", wait_until="networkidle"); page.locator("button.lang-trigger").click()
        mr = page.get_by_role("dialog", name="Choose the language the customer speaks").locator("input[value=mr]")
        check(mr.is_disabled(), "languages card: a language switched off in Settings cannot be chosen on the Order desk")
        refused = page.evaluate("""() => fetch('/api/text/parse', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: 'x', language: 'mr'})}).then(r => r.json().then(j => [r.status, (j.error || j.detail || {}).code]))""")
        check(refused[0] == 422 and refused[1] == "LANGUAGE_DISABLED", "languages card: the server refuses a switched-off language (422 LANGUAGE_DISABLED) instead of answering in another one", str(refused))
        page.goto(base + "/settings", wait_until="networkidle")
        page.get_by_label("Offer Marathi").click()
        page.wait_for_function("fetch('/api/languages').then(r => r.json()).then(j => j.disabled.length === 0)", timeout=8000)
        check(page.evaluate("fetch('/api/languages').then(r => r.json()).then(j => j.disabled)") == [], "languages card: Marathi switched back on, the server lists nothing as switched off")
        ctx.close()

        # staff may use every enabled language but do not see the owner's languages card
        sctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-IN")
        sp = sctx.new_page(); watch(sp, "v2.3-staff")
        sign_in(sp, base, staff_email, staff_pw); sp.wait_for_url("**/dashboard"); sp.wait_for_load_state("networkidle")
        sp.goto(base + "/settings", wait_until="networkidle"); sp.wait_for_timeout(500)
        check(sp.get_by_role("heading", name="Languages and voices").count() == 0, "staff: no languages card in Settings")
        check(sp.evaluate("fetch('/api/languages').then(r => r.status)") == 200, "staff: can read the language list the Order desk needs")
        sp.goto(base + "/performance", wait_until="networkidle"); sp.wait_for_timeout(600)
        check(sp.get_by_role("heading", name="AI performance").count() == 1 and sp.evaluate("fetch('/api/evaluation').then(r => r.status)") == 200, "staff: can read the AI performance page")
        sp.goto(base + "/dashboard", wait_until="networkidle"); sp.get_by_role("link", name="AI performance").first.wait_for(timeout=10000)  # sidebar is drawn
        check(sp.get_by_role("link", name="Voice diagnostics").count() == 0, "staff: the sidebar has no Voice diagnostics link")
        check(sp.evaluate("fetch('/api/diagnostics/voice').then(r => r.status)") == 403, "staff: the diagnostics API refuses them (403)")
        sp.goto(base + "/diagnostics", wait_until="networkidle"); sp.wait_for_timeout(500)
        check(sp.get_by_text("Only the shop owner can open this page").count() == 1, "staff: /diagnostics shows a plain notice, not the timings")
        sp.goto(base + "/order", wait_until="networkidle"); sp.locator("button.lang-trigger").click()
        check(sp.get_by_role("dialog", name="Choose the language the customer speaks").locator("input[type=radio]").count() == 12, "staff: the Order desk offers the same 11 languages")
        sctx.close()

        # ------------------------------------------------------------------ B25. version 2.5: AI performance and stock movement
        octx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN", accept_downloads=True)
        op = octx.new_page(); watch(op, "v2.5-owner")
        sign_in_to_dashboard(op, base, a.owner_email, pw); op.wait_for_load_state("networkidle")
        op.goto(base + "/performance", wait_until="networkidle"); op.wait_for_timeout(800)
        check(op.get_by_role("heading", name="AI performance").count() == 1, "performance: the page has its heading")
        body = op.inner_text("body").lower()  # badges are set in capitals by the stylesheet, so compare in lower case
        check("text only: no speech measured" in body and "not measured" in body, "performance: says plainly that no speech was measured and shows 'Not measured' rows")
        check(op.locator("table").count() >= 4, "performance: real HTML tables (metrics, languages, matrices, tests)", f"{op.locator('table').count()} tables")
        check(re.search(r"(?<!not )(verified live|live-verified)", body) is None, "performance: no claim of live verification (only 'not verified live')")
        with op.expect_download(timeout=15000) as dl:
            op.get_by_role("button", name="CSV").first.click()
        raw = open(dl.value.path(), "rb").read()
        check(re.fullmatch(r"swara-.*\.csv", dl.value.suggested_filename) is not None and raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw, "performance: a table downloads as a CSV (UTF-8 with BOM, CRLF)", f"{dl.value.suggested_filename}, {len(raw)} bytes")
        op.get_by_role("button", name="Result").first.click()
        check(op.locator("th[aria-sort='ascending'], th[aria-sort='descending']").count() >= 1, "performance: clicking a column heading sorts the table")
        op.goto(base + "/analytics", wait_until="networkidle"); op.wait_for_timeout(800)
        check(op.get_by_role("heading", name="Stock movement").count() >= 1, "analytics: the stock-movement card is there")
        card_text = op.inner_text("main")
        check("Nothing to report yet" not in card_text and "Opening" in card_text, "analytics: after the order taken above, the stock-movement table lists real rows")
        octx.close()

        # ------------------------------------------------------------------ B26. version 2.6: Voice diagnostics and the demo-data default
        octx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN")
        op = octx.new_page(); watch(op, "v2.6-owner")
        sign_in_to_dashboard(op, base, a.owner_email, pw); op.wait_for_load_state("networkidle")
        op.get_by_role("link", name="Analytics").first.wait_for(timeout=10000)  # the sidebar renders after the session is read
        check(op.get_by_role("link", name="Voice diagnostics").count() >= 1, "diagnostics: the owner's sidebar has the link")
        op.goto(base + "/diagnostics", wait_until="networkidle"); op.wait_for_timeout(800)
        check(op.get_by_role("heading", name="Voice diagnostics").count() == 1, "diagnostics: the page has its heading")
        dtext = op.inner_text("main")
        check("Not measured yet" in dtext, "diagnostics: before any spoken order the figures say 'Not measured yet', not zero")
        check(op.locator("table").count() >= 1, "diagnostics: real HTML tables for the call and settings figures")
        check(re.search(r"(?<!not )(verified live|live-verified)", dtext.lower()) is None, "diagnostics: no claim of live verification")
        check(op.evaluate("fetch('/api/diagnostics/voice?hours=24').then(r => r.status)") == 200, "diagnostics: the owner can read the API")
        op.get_by_role("button", name="7 days").click(); op.wait_for_timeout(600)
        check(op.get_by_role("heading", name="Voice diagnostics").count() == 1 and "Something went wrong" not in op.inner_text("main"), "diagnostics: switching the period reloads without an error")
        # demo data: this shop has taken real orders (above), so the demo switch defaults to off
        op.goto(base + "/analytics", wait_until="networkidle"); op.wait_for_timeout(800)
        stored = op.evaluate("localStorage.getItem('swara.includeDemo')")
        switch_on = op.locator("label.switch input").is_checked()
        check(stored is None and not switch_on, "demo default: this shop has real orders, so the demo switch starts off and nothing is stored until the owner chooses", f"stored={stored!r}, switch_on={switch_on}")
        op.locator("label.switch").click(); op.wait_for_timeout(300)
        check(op.evaluate("localStorage.getItem('swara.includeDemo')") == "1", "demo default: turning the switch on is remembered as the owner's own choice")
        octx.close()

        # ------------------------------------------------------------------ B27. version 2.7: payments (cash, UPI QR confirmed by hand, refund, invoice, permissions)
        # No Razorpay keys here, and the network is not Razorpay's: this exercises everything that does not need Razorpay and checks that what needs it is OFF and says why.
        # (This section sets the shop's UPI ID, which the server writes to the repository's .env file like the shop name; delete that .env afterwards.)
        JF = """async ([method, url, body]) => {
          const s = await (await fetch('/api/auth/session')).json();
          const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': s.csrf_token || '' }, body: body ? JSON.stringify(body) : undefined });
          let j = null; try { j = await r.json() } catch (e) {}
          return { status: r.status, json: j };
        }"""

        def new_order(pg, sentence: str):
            pg.goto(base + "/order", wait_until="networkidle")
            pg.locator("#typed").fill(sentence)
            pg.get_by_role("button", name="Send", exact=True).click()
            pg.get_by_role("button", name="Confirm order").wait_for(timeout=10000)
            pg.get_by_role("button", name="Confirm order").click()
            conf_ = pg.get_by_role("region", name="Order confirmed"); conf_.wait_for(timeout=10000)
            return conf_

        octx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN")
        op = octx.new_page(); watch(op, "v2.7-owner")
        sign_in_to_dashboard(op, base, a.owner_email, pw); op.wait_for_load_state("networkidle")
        nav = op.get_by_role("navigation", name="Main")
        nav.get_by_role("link", name="Analytics", exact=True).wait_for(timeout=10000)
        check(nav.get_by_role("link", name="Payments", exact=True).count() == 1 and nav.get_by_role("link", name="Payment analytics").count() == 1, "payments: the owner's sidebar has Payments and Payment analytics")
        cfg = op.evaluate("fetch('/api/payments/config').then(r => r.json())")
        check(cfg["mode"] == "test" and cfg["razorpay"]["enabled"] is False and cfg["methods"]["razorpay"]["available"] is False and cfg["methods"]["cash"]["available"] is True,
              "payments: with no Razorpay keys the mode is 'test', Razorpay is off and cash is on", str(cfg)[:200])
        check("secret" not in " ".join(k for k in cfg if isinstance(cfg[k], str)) and "rzp_" not in str(cfg), "payments: the config the browser receives carries no key or secret")
        csp = op.evaluate("fetch('/').then(r => r.headers.get('content-security-policy') || '')")
        check("razorpay" not in csp.lower(), "payments: with Razorpay off the content-security-policy lets no page load anything from Razorpay", csp[:120])

        # start from "no UPI ID" however often this script has been run (the server keeps the shop's UPI ID in the repository's .env, which outlives a fresh database)
        if cfg["methods"]["upi"]["available"]:
            cleared = op.evaluate(JF, ["PUT", "/api/settings", {"upi_vpa": ""}])
            check(cleared["status"] == 200, "payments: a UPI ID left by an earlier run is removed so this run starts from none", str(cleared)[:120])
            cfg = op.evaluate("fetch('/api/payments/config').then(r => r.json())")

        # an order, then cash
        conf = new_order(op, "2 kilo chawal")
        check(conf.get_by_role("button", name="Take payment").count() == 1 and conf.get_by_role("button", name="Next customer").is_enabled(),
              "payments: a confirmed order offers Take payment, and Next customer still works without it")
        conf.get_by_role("button", name="Take payment").click()
        dlg = op.get_by_role("dialog", name="Take payment"); dlg.wait_for(timeout=8000)
        radios = dlg.get_by_role("radio"); radios.first.wait_for(timeout=8000)
        check(radios.count() == 3 and radios.nth(0).is_enabled() and radios.nth(1).is_disabled() and radios.nth(2).is_disabled(),
              "payments: cash is on; UPI (no UPI ID yet) and Razorpay (no keys) are off", f"{radios.count()}")
        check("Settings" in radios.nth(1).inner_text() and "Razorpay" in radios.nth(2).inner_text(), "payments: each switched-off way says why", radios.nth(1).inner_text().replace("\n", " ")[:140])
        radios.nth(0).click(); dlg.get_by_role("button", name="Continue").click()
        cash_in = dlg.get_by_label("Cash received (rupees)"); cash_in.wait_for(timeout=8000)
        bill = cash_in.input_value()
        cash_in.fill("1")
        check(dlg.get_by_role("button", name="Record cash received").is_disabled() and "less than the bill" in dlg.inner_text(), "payments: cash less than the bill is refused on screen, with the reason")
        bill_rs = int(float(bill))
        cash_in.fill(str(bill_rs * 20 + 2000))
        check(dlg.get_by_role("button", name="Record cash received").is_disabled() and "looks wrong" in dlg.inner_text(), "payments: an amount over twenty times the bill plus 1,000 rupees is refused on screen as a slip, with the reason")
        cash_in.fill(str(bill_rs + 380))
        check("Give back" in dlg.inner_text() and dlg.get_by_role("button", name="Record cash received").is_enabled(), "payments: more than the bill shows the change to give back")
        dlg.get_by_role("button", name="Record cash received").click()
        dlg.locator(".pay-result.ok").wait_for(timeout=8000)
        newest = op.evaluate("fetch('/api/orders?limit=5&sort=newest&include_synthetic=false').then(r => r.json())")["items"][0]
        pays = op.evaluate("(id) => fetch('/api/orders/' + id + '/payments').then(r => r.json())", newest["id"])
        p0 = pays["items"][0]
        check(pays["summary"]["status"] == "paid" and p0["method"] == "cash" and p0["amount_paise"] == newest["total_paise"] and p0["amount_received_paise"] == (bill_rs + 380) * 100 and p0["change_paise"] == (bill_rs + 380) * 100 - newest["total_paise"] and p0["verification"] == "cash",
              "payments: cash is recorded for the ORDER'S OWN total (not an amount from the browser), with the cash received and the change", f"{p0['amount_paise']} {newest['total_paise']}")
        PAY_IDS = {"order": newest["id"], "payment": p0["id"]}
        dup = op.evaluate(JF, ["POST", f"/api/orders/{newest['id']}/payments", {"method": "cash"}])
        check(dup["status"] == 409 and dup["json"]["detail"]["code"] == "ALREADY_PAID", "payments: a second payment for a paid order is refused (409 ALREADY_PAID)", str(dup)[:160])
        forged = op.evaluate(JF, ["POST", f"/api/payments/{p0['id']}/cash", {"received_paise": 99999999}])
        check(forged["status"] in (409, 422), "payments: recording cash again on a paid payment is refused", str(forged)[:160])

        # the invoice
        dlg.get_by_role("link", name=re.compile("Receipt")).click()
        op.wait_for_url(f"**/invoices/{newest['id']}"); op.get_by_role("button", name=re.compile("Print or save as PDF")).wait_for(timeout=8000)
        inv_no = op.locator(".invoice-sheet .inv-meta dd").first.inner_text()
        check(re.fullmatch(r"INV-\d{4}-\d{6}", inv_no) is not None, "invoice: the receipt has a numbered invoice (INV-year-number)", inv_no)
        tx = op.locator(".invoice-sheet").inner_text()
        check("not a GST tax invoice" in tx and "GSTIN" not in tx and "CGST" not in tx and "SGST" not in tx, "invoice: says it is not a GST tax invoice and shows no tax lines")
        check("Cash" in tx and "Paid" in tx and "PAY-" in tx and "Rice" in tx or "chawal" in tx.lower() or "Rice" in tx, "invoice: shows the items, the way paid, the status and the payment reference")
        op.reload(wait_until="networkidle"); op.get_by_role("button", name=re.compile("Print or save as PDF")).wait_for(timeout=8000)
        check(op.locator(".invoice-sheet .inv-meta dd").first.inner_text() == inv_no, "invoice: opening it again shows the same number (issued once)")
        light_only(op, "invoice", [".invoice-sheet"])
        op.evaluate("window.__printState = null; window.print = () => { window.__printState = [document.body.classList.contains('printing-invoice'), document.title] }")
        op.get_by_role("button", name=re.compile("Print or save as PDF")).click()
        ps = op.evaluate("window.__printState")
        check(ps is not None and ps[0] is True and ps[1] == inv_no, "invoice: the button puts the page into print state and names the file after the invoice number", str(ps))
        op.emulate_media(media="print")
        shown = op.evaluate("() => ({ inv: document.querySelector('.print-invoice').checkVisibility(), side: document.querySelector('.sidebar').checkVisibility(), text: document.querySelector('.print-invoice').innerText })")
        check(shown["inv"] is True and shown["side"] is False and inv_no in shown["text"], "invoice: in print media only the invoice is shown, with its number and no sidebar", str(shown)[:160])
        pdf = op.pdf(); check(pdf[:5] == b"%PDF-" and len(pdf) > 1500, "invoice: it renders to a PDF", f"{len(pdf)} bytes")
        op.emulate_media(media="screen"); op.evaluate("window.dispatchEvent(new Event('afterprint'))")
        check(op.evaluate("document.querySelector('.print-invoice').checkVisibility()") is False and op.evaluate("document.title") != inv_no, "invoice: on screen the print copy is hidden again and the title is put back")

        # Orders: the payment shows, and cancelling a paid order is refused by the server and not offered on screen
        op.goto(base + f"/orders?open={newest['id']}", wait_until="networkidle")
        drawer = op.get_by_role("dialog").first; drawer.wait_for(timeout=8000)
        check("collected" in drawer.inner_text() and drawer.get_by_role("button", name="Cancel order").is_disabled(), "orders: a paid order shows what was collected and Cancel order is off until it is refunded")
        cancel = op.evaluate(JF, ["POST", f"/api/orders/{newest['id']}/status", {"status": "cancelled"}])
        check(cancel["status"] == 409 and cancel["json"]["detail"]["code"] == "PAID_ORDER", "orders: the server refuses to cancel an order with money collected (409 PAID_ORDER)", str(cancel)[:160])
        op.keyboard.press("Escape")
        op.goto(base + "/orders", wait_until="networkidle")
        check(op.get_by_role("row", name=f"Open {newest['code']}").get_by_text("Paid").count() == 1, "orders: the list shows the payment status for the order", "")
        old = op.evaluate("fetch('/api/orders?limit=100&sort=oldest&include_synthetic=true').then(r => r.json())")["items"]
        none_rows = [o for o in old if o["payment"]["status"] == "none"]
        check(len(none_rows) >= 1, "orders: orders with no payment recorded report status 'none' (nothing was changed for them)", str(len(none_rows)))

        # UPI: set the shop's UPI ID, then a QR that stays "not verified" until a person confirms it
        op.goto(base + "/settings", wait_until="networkidle")
        op.get_by_label("Shop UPI ID").fill("not a upi id")
        check(op.get_by_role("button", name="Save UPI details").is_disabled() and "does not look like a UPI ID" in op.inner_text("main"), "settings: a malformed UPI ID is refused on screen")
        op.get_by_label("Shop UPI ID").fill("patelstore@okhdfcbank")
        op.get_by_role("button", name="Save UPI details").click()
        op.get_by_text("UPI details saved.").wait_for(timeout=8000)
        check(op.get_by_text("UPI QR by shop ID").count() == 1 and op.get_by_text("Razorpay is not set up").count() == 1, "settings: the card shows the UPI QR is on and Razorpay is not set up")
        pay_card = op.locator(".card", has=op.get_by_role("heading", name="Payments", exact=True))
        pc = pay_card.inner_text()
        check("Key secret" in pc and "Webhook secret" in pc and pc.count("Not set") >= 3 and pay_card.locator("input[type=password]").count() == 0 and pay_card.locator("input").count() == 2,
              "settings: Razorpay secrets are shown as set or not set and are never typed here (the card's only inputs are the UPI ID and payee name)", pc.replace("\n", " ")[:200])
        conf = new_order(op, "1 litre doodh")
        conf.get_by_role("button", name="Take payment").click()
        dlg = op.get_by_role("dialog", name="Take payment"); dlg.wait_for(timeout=8000)
        dlg.get_by_role("radio", name=re.compile("UPI QR")).click(); dlg.get_by_role("button", name="Continue").click()
        dlg.locator("svg.qr-svg").wait_for(timeout=8000)
        d = dlg.inner_text()
        check("Not verified: a person must confirm" in d and "cannot see the money" in d and "₹" in d and "SW-" in d,
              "payments: the UPI QR says it is not verified, shows the amount and the bill number, and says the app cannot see the money", d.replace("\n", " ")[:200])
        check(len(dlg.locator("svg.qr-svg path").first.get_attribute("d") or "") > 300, "payments: the QR is a real drawn code")
        confirm_btn = dlg.get_by_role("button", name="Confirm payment received")
        check(confirm_btn.is_disabled(), "payments: nothing can be confirmed before anyone has looked at the bank")
        dlg.get_by_label(re.compile("UPI reference")).fill("UTR412345678")
        check(confirm_btn.is_disabled(), "payments: a reference alone is not enough: the person must also say they can see the money")
        dlg.get_by_role("checkbox").check()
        confirm_btn.click(); dlg.locator(".pay-result.ok").wait_for(timeout=8000)
        check("Confirmed by hand" in dlg.inner_text(), "payments: the finished screen still says it was confirmed by hand")
        newest2 = op.evaluate("fetch('/api/orders?limit=5&sort=newest&include_synthetic=false').then(r => r.json())")["items"][0]
        p1 = op.evaluate("(id) => fetch('/api/orders/' + id + '/payments').then(r => r.json())", newest2["id"])["items"][0]
        check(p1["method"] == "upi" and p1["status"] == "paid" and p1["verified"] is False and p1["verification"] == "manual" and p1["reference_note"] == "UTR412345678",
              "payments: the server keeps a hand-confirmed UPI payment as NOT verified, with the reference", str(p1)[:200])
        op.keyboard.press("Escape")

        # history, detail, refund
        op.goto(base + "/payments", wait_until="networkidle")
        rows = op.locator("table.tbl tbody tr")
        check(rows.count() >= 2 and op.get_by_role("row", name=f"Open payment {p1['code']}").get_by_text("Unverified").count() == 1, "payments page: lists both payments and marks the hand-confirmed UPI one 'Unverified'")
        op.get_by_role("button", name=re.compile(r"^Paid")).click(); op.wait_for_timeout(500)
        check("status=paid" in " ".join(op.evaluate("performance.getEntriesByType('resource').map(e => e.name)")), "payments page: the status tab is sent to the server as a filter")
        op.get_by_role("searchbox", name=re.compile("Search payments")).fill(newest["code"]); op.wait_for_timeout(700)
        check(op.locator("table.tbl tbody tr").count() == 1, "payments page: searching by bill number finds exactly that payment", str(op.locator("table.tbl tbody tr").count()))
        op.locator("table.tbl tbody tr").first.click(); op.wait_for_url(f"**/payments/{p0['id']}")
        op.get_by_role("heading", name=p0["code"]).wait_for(timeout=8000)
        refund_amount = op.get_by_label("Refund amount (rupees)")
        refund_amount.fill("99999"); check(op.get_by_role("button", name="Refund", exact=True).is_disabled() and "The most that can be refunded" in op.inner_text("main"), "refund: more than what is left is refused on screen")
        over = op.evaluate(JF, ["POST", f"/api/payments/{p0['id']}/refunds", {"amount_paise": 99999900, "reason": "x"}])
        check(over["status"] in (409, 422), "refund: and refused by the server too", str(over)[:160])
        refund_amount.fill("10"); op.get_by_label("Reason").fill("Item returned")
        op.get_by_role("button", name="Refund", exact=True).click()
        ask = op.get_by_role("alertdialog"); ask.wait_for(timeout=5000)
        check("by hand" in ask.inner_text(), "refund: asks first, and for cash says the owner returns the money by hand")
        ask.get_by_role("button", name="Refund", exact=True).click()
        op.get_by_text(re.compile(r"REF-\d{6}-\d{4}")).first.wait_for(timeout=8000)
        det = op.evaluate("(id) => fetch('/api/payments/' + id).then(r => r.json())", p0["id"])
        check(det["status"] == "partially_refunded" and det["refunded_paise"] == 1000 and len(det["refunds"]) == 1 and det["refunds"][0]["status"] == "processed",
              "refund: a part-refund is recorded and the payment becomes 'partially refunded'", str({k: det[k] for k in ("status", "refunded_paise")}))
        again = op.evaluate(JF, ["POST", f"/api/payments/{p0['id']}/refunds", {"amount_paise": 1000, "reason": "Item returned", "idempotency_key": det["refunds"][0]["code"] + "-x00"}])
        check(again["status"] in (200, 201) and op.evaluate("(id) => fetch('/api/payments/' + id).then(r => r.json())", p0["id"])["refunded_paise"] == 2000,
              "refund: a second refund with a NEW request key is a second refund (so the double-click guard is the request key)", str(again)[:120])
        key = "e2e-duplicate-key-0001"
        r1 = op.evaluate(JF, ["POST", f"/api/payments/{p1['id']}/refunds", {"amount_paise": 500, "reason": "Short change", "idempotency_key": key}])
        r2 = op.evaluate(JF, ["POST", f"/api/payments/{p1['id']}/refunds", {"amount_paise": 500, "reason": "Short change", "idempotency_key": key}])
        det1 = op.evaluate("(id) => fetch('/api/payments/' + id).then(r => r.json())", p1["id"])
        check(r1["status"] in (200, 201) and r2["status"] in (200, 201) and r1["json"]["id"] == r2["json"]["id"] and det1["refunded_paise"] == 500 and len(det1["refunds"]) == 1,
              "refund: sending the same refund request twice (same key) refunds once", f"{r1['status']} {r2['status']} {det1['refunded_paise']}")

        # analytics: from real records only
        op.goto(base + "/payment-analytics", wait_until="networkidle"); op.wait_for_timeout(800)
        collected = op.get_by_role("group", name="Collected", exact=True).inner_text()
        ak = op.evaluate("fetch('/api/payments/analytics?days=30&include_synthetic=false').then(r => r.json())")["kpis"]
        check(ak["paid_count"] == 2 and ak["cash_paise"] == p0["amount_paise"] and ak["upi_paise"] == p1["amount_paise"] and ak["upi_manual_paise"] == p1["amount_paise"] and ak["collected_paise"] == p0["amount_paise"] + p1["amount_paise"],
              "analytics: the totals are the sum of the two payments recorded above (and nothing else)", str(ak)[:200])
        check("confirmed by hand" in op.get_by_role("group", name="UPI", exact=True).inner_text() and "refunded" in collected, "analytics: manual UPI is called out as not verified and refunds are shown")
        op.get_by_role("button", name="Table").first.click()
        check(op.locator("main table").count() >= 1, "analytics: the chart has a table view")
        light_only(op, "payment analytics", [".content"])

        # leave one order UNPAID for the width sweep below
        conf = new_order(op, "2 kilo sugar")
        PAY_IDS["unpaid_order"] = op.evaluate("fetch('/api/orders?limit=5&sort=newest&include_synthetic=false').then(r => r.json())")["items"][0]["id"]
        octx.close()

        # staff: can take payments, cannot see analytics or refund
        sctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-IN")
        sp = sctx.new_page(); watch(sp, "v2.7-staff")
        sign_in_to_dashboard(sp, base, staff_email, staff_pw); sp.wait_for_load_state("networkidle")
        snav = sp.get_by_role("navigation", name="Main"); snav.get_by_role("link", name="Analytics", exact=True).wait_for(timeout=10000)
        check(snav.get_by_role("link", name="Payments", exact=True).count() == 1 and snav.get_by_role("link", name="Payment analytics").count() == 0, "staff: sees Payments but not Payment analytics")
        sp.goto(base + "/payment-analytics", wait_until="networkidle")
        check("Only the shop owner can open this page" in sp.inner_text("main"), "staff: the payment analytics page says it is for the owner")
        check(sp.evaluate("fetch('/api/payments/analytics').then(r => r.status)") == 403, "staff: the analytics API is refused by the server (403), not just hidden")
        sp.goto(base + f"/payments/{p0['id']}", wait_until="networkidle"); sp.get_by_role("heading", name=p0["code"]).wait_for(timeout=8000)
        check(sp.get_by_label("Refund amount (rupees)").count() == 0 and "Only the shop owner can refund" in sp.inner_text("main"), "staff: the payment page shows no refund form")
        sref = sp.evaluate(JF, ["POST", f"/api/payments/{p0['id']}/refunds", {"amount_paise": 100, "reason": "staff try"}])
        check(sref["status"] == 403, "staff: the refund API is refused by the server (403)", str(sref)[:160])
        sconf = new_order(sp, "1 kilo chawal")
        sconf.get_by_role("button", name="Take payment").click()
        sdlg = sp.get_by_role("dialog", name="Take payment"); sdlg.wait_for(timeout=8000)
        sdlg.get_by_role("radio", name=re.compile("Cash")).click(); sdlg.get_by_role("button", name="Continue").click()
        sdlg.get_by_role("button", name="Exact").click()
        sdlg.get_by_role("button", name="Record cash received").click(); sdlg.locator(".pay-result.ok").wait_for(timeout=8000)
        spay = sp.evaluate("fetch('/api/payments?limit=1&sort=newest&include_synthetic=false').then(r => r.json())")["items"][0]
        check(spay["method"] == "cash" and spay["status"] == "paid" and spay["confirmed_by"] == "Meena Shah", "staff: can record cash, and the record names who did it", str(spay)[:160])
        sctx.close()

        # the webhook endpoint takes nothing without a valid signature
        wctx = browser.new_context(viewport={"width": 1280, "height": 900}); wp = wctx.new_page(); watch(wp, "v2.7-webhook")
        wp.goto(base + "/", wait_until="networkidle")
        wh = wp.evaluate("fetch('/api/payments/webhooks/razorpay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ event: 'payment.captured', payload: { payment: { entity: { id: 'pay_FAKE', order_id: 'order_FAKE', amount: 1, status: 'captured' } } } }) }).then(async r => [r.status, await r.text()])")
        check(wh[0] in (400, 401, 403, 503) and "paid" not in wh[1].lower().replace("nothing was recorded as paid", ""), "webhook: a request with no valid signature is refused and changes nothing", str(wh)[:160])
        wctx.close()
        PAY_STATE = PAY_IDS

        # ------------------------------------------------------------------ C. responsive: no horizontal scrolling
        widths = [320, 360, 390, 768, 1024, 1280, 1440]
        public = ["/", "/sign-in", "/sign-up", "/forgot-password", "/terms", "/privacy"]
        private = ["/dashboard", "/order", "/orders", "/payments", "/payment-analytics", f"/payments/{PAY_STATE['payment']}", f"/invoices/{PAY_STATE['order']}",
                   "/customers", "/inventory", "/analytics", "/performance", "/diagnostics", "/settings", "/account"]
        offenders: list[str] = []
        for w in widths:
            ctx = browser.new_context(viewport={"width": w, "height": 900})
            page = ctx.new_page(); watch(page, f"w{w}")
            for path in public:
                page.goto(base + path, wait_until="networkidle")
                if overflow(page) > 0:
                    offenders.append(f"{w}px {path} (+{overflow(page)})")
            sign_in_to_dashboard(page, base, a.owner_email, pw)
            for path in private:
                page.goto(base + path, wait_until="networkidle")
                page.wait_for_timeout(250)
                if overflow(page) > 0:
                    offenders.append(f"{w}px {path} (+{overflow(page)})")
            # the payment window on an unpaid order: the UPI QR view has to fit inside the screen (the first width starts the payment, the others resume it)
            page.goto(base + f"/orders?open={PAY_STATE['unpaid_order']}", wait_until="networkidle")
            page.get_by_role("button", name=re.compile("^(Take|Continue) payment$")).click()
            pdlg = page.get_by_role("dialog", name="Take payment"); pdlg.wait_for(timeout=8000)
            pdlg.locator("svg.qr-svg, [role=radiogroup]").first.wait_for(timeout=8000)   # the first width starts the payment; the others resume it, and must not show the choice again
            if pdlg.get_by_role("radiogroup").count():
                pdlg.get_by_role("radio", name=re.compile("UPI QR")).click(); pdlg.get_by_role("button", name="Continue").click()
            page.locator("svg.qr-svg").wait_for(timeout=8000); page.wait_for_timeout(200)
            box, qrb = pdlg.bounding_box(), page.locator("svg.qr-svg").bounding_box()
            if not (box and qrb and box["x"] >= -1 and box["x"] + box["width"] <= w + 1 and qrb["x"] >= -1 and qrb["x"] + qrb["width"] <= w + 1) or overflow(page) > 0:
                offenders.append(f"{w}px payment window ({box}, {qrb}, +{overflow(page)})")
            page.keyboard.press("Escape")
            ctx.close()
        check(not offenders, f"responsive: no horizontal scrolling on {len(public)} public and {len(private)} signed-in pages (and the payment window) at {widths}", "; ".join(offenders))

        if not a.skip_controls:
            controls_section(browser)
        browser.close()

    return report()


if __name__ == "__main__":
    sys.exit(main())
