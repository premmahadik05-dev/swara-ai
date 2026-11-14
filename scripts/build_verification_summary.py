"""Turn the saved test logs into eval/results/verification_summary.json, the file behind the "Test and verification" table.

   python scripts/build_verification_summary.py

It READS logs that a test run already wrote to docs/test-results/ and counts what they say; it never runs a test and never types a
number in by hand. A log that is missing gives a "Not run" row, so a stale or absent run cannot look like a pass.

Logs it uses (written by the commands in docs/TESTING.md):
  backend_pytest.xml     pytest --junitxml            -> one row per group of test files, counted from every test case
  frontend_vitest.txt    npm test                      -> "Tests  N passed (N)" line
  frontend_build.txt     npm run build                 -> type-check and bundle
  e2e_browser_main.txt   scripts/e2e_browser.py        -> "N of M checks passed"
  e2e_browser_controls.txt   the same script, owner and visitor control sweep
  dependency_audits.txt  npm audit and pip-audit
and the NLU regression check eval/results/nlu_eval_vNNN_check.json (+ nlu_failures_vNNN_check.json) and the stock-guard counts in
eval/results/evaluation_summary.json. Live Gnani checks are "Not run" unless eval/results/live_verification.json exists. The Razorpay check against the real service is always "Not run" here:
no log of one exists, and the payment tests use a stand-in.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "docs" / "test-results"
RES = ROOT / "eval" / "results"
OUT = RES / "verification_summary.json"

# Test files -> the group they are reported under. Anything not listed lands in "Other backend tests" so the rows always add up.
GROUPS: list[tuple[str, str, list[str]]] = [
    ("Accounts, sessions and security", "Sign-up, sign-in, CSRF, route guard, rate limits, injection strings, uploads, order integrity",
     ["test_auth", "test_security", "test_order_integrity", "test_exports_and_shop"]),
    ("Order parser and dialogue", "Quantities, units, products, branded packs, confirmation flow, noise, 11 languages",
     ["test_nlu_parser", "test_units", "test_branded_nlu", "test_dialogue_api", "test_cart_edit", "test_noise", "test_languages_nlu", "test_languages_registry", "test_languages_api"]),
    ("Gnani client (mocked HTTP, not live)", "Request shapes, headers, error handling and key secrecy against a mock server",
     ["test_gnani_contract", "test_ws_proxy"]),
    ("Shop API, data and evaluation files", "Products, inventory, orders, analytics, seed data, stock movement, evaluation summary",
     ["test_api_admin", "test_api_reference", "test_api_voice", "test_saas_api", "test_seed", "test_data_pipeline", "test_performance_api", "test_evaluation_summary"]),
    ("Voice path, diagnostics and update safety (2.6)", "Pooled Gnani connection, time limits and retries, reply first and voice after, stage timing, owner-only diagnostics, the .env and database kept on update (mocked Gnani, not live)",
     ["test_release_260"]),
    ("Payments, refunds, invoices and migration (2.7, Razorpay simulated)", "Cash, hand-confirmed UPI, Razorpay against a stand-in, signatures and webhooks, duplicates, refunds, permissions, the additive migration, secrets (no real Razorpay call)",
     ["test_payments_cash_upi", "test_payments_razorpay", "test_payments_refunds", "test_payments_history_invoice_analytics", "test_payments_migration", "test_payments_security"]),
    ("Branding, wording and Windows scripts", "Product name, light theme only, landing-page claims, script structure (cmd.exe itself was not run)",
     ["test_branding", "test_landing_claims", "test_landing_design", "test_light_only", "test_independent_product", "test_scripts"]),
]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _row(category: str, total, passed, failed, skipped, how: str, ran: str, status: str | None = None) -> dict:
    if status is None:
        status = "Failed" if failed else "Passed"
    return {"category": category, "total": total, "passed": passed, "failed": failed, "skipped": skipped, "status": status, "how": how, "ran": ran}


def _not_run(category: str, how: str, why: str) -> dict:
    return _row(category, None, None, None, None, how, why, status="Not run")


def _ran(p: Path) -> str:
    return f"Executed in this environment (Linux), log saved {_iso(p.stat().st_mtime)[:16].replace('T', ' ')} UTC"


def backend_rows() -> list[dict]:
    p = LOGS / "backend_pytest.xml"
    if not p.exists():
        return [_not_run(g[0], g[1], "No backend_pytest.xml found. Run: pytest --junitxml=docs/test-results/backend_pytest.xml") for g in GROUPS]
    root = ET.parse(p).getroot()
    modules: dict[str, dict[str, int]] = {}
    for case in root.iter("testcase"):
        parts = (case.get("classname") or "").split(".")
        # Tests written as classes report "<module>.<Class>"; the group is keyed by the module.
        mod = next((x for x in reversed(parts) if x.startswith("test_")), parts[-1]) or "unknown"
        m = modules.setdefault(mod, {"total": 0, "failed": 0, "skipped": 0})
        m["total"] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            m["failed"] += 1
        elif case.find("skipped") is not None:
            m["skipped"] += 1
    listed = {mod for g in GROUPS for mod in g[2]}
    groups = list(GROUPS)
    other = sorted(set(modules) - listed)
    if other:
        groups.append(("Other backend tests", ", ".join(other), other))
    rows = []
    for name, what, mods in groups:
        t = sum(modules.get(m, {}).get("total", 0) for m in mods)
        f = sum(modules.get(m, {}).get("failed", 0) for m in mods)
        s = sum(modules.get(m, {}).get("skipped", 0) for m in mods)
        rows.append(_row(name, t, t - f - s, f, s, what, _ran(p)))
    grand = sum(r["total"] for r in rows)
    assert grand == sum(m["total"] for m in modules.values()), "backend rows do not add up to the log"
    return rows


def vitest_row() -> dict:
    p = LOGS / "frontend_vitest.txt"
    text = _read(p)
    how = "Components, pages, tables, charts and helpers in jsdom (Vitest); includes the shipped evaluation file contract"
    if text is None:
        return _not_run("Front-end tests", how, "No frontend_vitest.txt found. Run: cd frontend && npm test")
    line = next((l for l in text.splitlines() if re.match(r"\s*Tests\s", l)), "")
    nums = {k: int(v) for v, k in re.findall(r"(\d+) (failed|passed|skipped|todo)", line)}
    total = int(m.group(1)) if (m := re.search(r"\((\d+)\)", line)) else None
    if total is None:
        return _not_run("Front-end tests", how, "frontend_vitest.txt has no summary line")
    return _row("Front-end tests", total, nums.get("passed", 0), nums.get("failed", 0), nums.get("skipped", 0) + nums.get("todo", 0), how, _ran(p))


def build_row() -> dict:
    p = LOGS / "frontend_build.txt"
    text = _read(p)
    how = "tsc --noEmit (type-check) then vite build (npm run build)"
    if text is None:
        return _not_run("Front-end build", how, "No frontend_build.txt found. Run: cd frontend && npm run build")
    ok = "built in" in text and "error TS" not in text and "error during build" not in text
    return _row("Front-end build", 1, 1 if ok else 0, 0 if ok else 1, 0, how, _ran(p))


def e2e_rows() -> list[dict]:
    rows = []
    for fname, cat, how in (("e2e_browser_main.txt", "Real-browser end-to-end checks", "Chromium on a fresh database: sign-up, order desk, payments and invoices, every page, 20 pages and the payment window at 7 widths, console errors"),
                            ("e2e_browser_controls.txt", "Real-browser control sweep", "Every enabled button and link on the visitor and owner pages")):
        p = LOGS / fname
        text = _read(p)
        if text is None:
            rows.append(_not_run(cat, how, f"No {fname} found. Run: python scripts/e2e_browser.py"))
            continue
        m = re.search(r"(\d+) of (\d+) checks passed", text)
        if not m:
            rows.append(_not_run(cat, how, f"{fname} has no result line"))
            continue
        passed, total = int(m.group(1)), int(m.group(2))
        rows.append(_row(cat, total, passed, total - passed, 0, how, _ran(p)))
    return rows


def audit_row() -> dict:
    p = LOGS / "dependency_audits.txt"
    text = _read(p)
    how = "npm audit (front end) and pip-audit (back end); advisory databases change daily"
    if text is None:
        return _not_run("Dependency audits", how, "No dependency_audits.txt found")
    npm = "found 0 vulnerabilities" in text
    pip = "No known vulnerabilities found" in text
    return _row("Dependency audits", 2, int(npm) + int(pip), 2 - int(npm) - int(pip), 0, how, _ran(p))


def nlu_row() -> dict:
    tag = "v" + re.sub(r"\D", "", _version())
    ev, fl = RES / f"nlu_eval_{tag}_check.json", RES / f"nlu_failures_{tag}_check.json"
    how = "288 held-out sentences in 4 languages parsed and compared with their gold lines (scripts/evaluate_nlu.py)"
    if not ev.exists() or not fl.exists():
        return _not_run("Parser regression check", how, f"No nlu_eval_{tag}_check.json yet. Run: python scripts/evaluate_nlu.py --tag {tag}_check")
    n = json.loads(ev.read_text(encoding="utf-8"))["n_total"]
    failures = json.loads(fl.read_text(encoding="utf-8"))
    nfail = len(failures) if isinstance(failures, list) else sum(len(v) for v in failures.values())
    return _row("Parser regression check", n, n - nfail, nfail, 0, how, _ran(ev))


def stock_guard_row() -> dict:
    how = "Every order sentence replayed against an empty shelf and a half-stocked shelf; no stock may go negative"
    p = RES / "evaluation_summary.json"
    if not p.exists():
        return _not_run("Stock guard", how, "No evaluation_summary.json")
    g = json.loads(p.read_text(encoding="utf-8"))["end_to_end"]["stock_guard"]
    total = g["empty_checked"] + g["half_checked"]
    bad = (g["empty_checked"] - g["empty_refused"]) + g["empty_negative_stock"] + g["half_negative_stock"] + (g["half_checked"] - g["half_asked_or_offered"] - g["half_refused"])
    return _row("Stock guard", total, total - bad, bad, 0, how, _ran(p))


def live_row() -> dict:
    how = "Real Gnani calls: speech synthesis, language code and speech recognition per language (python scripts/verify_gnani.py, about 33 calls)"
    if (RES / "live_verification.json").exists():
        return _row("Live Gnani verification", None, None, None, None, how, "See eval/results/live_verification.json", status="Recorded")
    return _not_run("Live Gnani verification", how, "Needs a Gnani API key and network access, which this environment does not have")


def razorpay_row() -> dict:
    return _not_run("Razorpay against the real service (test mode)", "Create an order, open Checkout, receive a signed webhook and make a refund with your own Razorpay TEST keys (docs/RAZORPAY_SETUP.md)",
                    "This environment has no Razorpay account and no route to Razorpay; every Razorpay test uses a stand-in written from Razorpay's public documentation as remembered while building, not checked against a live account")


def windows_row() -> dict:
    return _not_run("Windows scripts run on Windows", "setup.bat, start.bat, dev.bat, test.bat, verify_gnani.bat run by cmd.exe",
                    "cmd.exe is not available here; the scripts were read and their structure is tested (see Branding, wording and Windows scripts)")


def _version() -> str:
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8"))
    return m.group(1) if m else "unknown"


def main() -> int:
    rows = backend_rows() + [vitest_row(), build_row(), *e2e_rows(), audit_row(), nlu_row(), stock_guard_row(), live_row(), razorpay_row(), windows_row()]
    out = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": _version(),
        "rows": rows,
        "note": "Counted from saved logs; nothing here is typed in. 'Not run' means no log exists, not that it passed.",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    failed = [r["category"] for r in rows if r["status"] == "Failed"]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} rows, {sum(1 for r in rows if r['status'] == 'Not run')} not run, failed: {failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
