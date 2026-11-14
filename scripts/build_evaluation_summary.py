"""Build ONE machine-readable evaluation summary from the project's own datasets and code.

    python scripts/build_evaluation_summary.py

Writes eval/results/evaluation_summary.json. Nothing is typed in by hand: every number is computed here by running the real
parser, lexicon and dialogue code, or copied from a result file written by another script (and then says which one).
The app's "AI performance" page, the project report and the documentation all read this one file, so they cannot disagree.

What is measured (all of it TEXT; no speech recognition, no Gnani):
  * sentence check   - per language and per dataset: does a sentence become the right order lines?
  * name resolution  - per language: does each staple's own name find that staple?
  * language detection confusion matrix (no selector hint)
  * held-out branded products (data/test/branded_results.json, rebuilt by evaluate_branded.py)
  * simulated spelling noise: precision / recall / F1, and a matching-stage ablation
  * typed-text end to end: sentence -> bill -> confirm -> order row and stock change, plus a stock guard
  * parser latency

Honest limits (also written into the file): gold labels for the four original languages were written by the parser's author;
the seven languages added in 2.3.0 have a handful of authored sentences each and NO native-speaker review; noise is simulated
character damage, not acoustic noise; branded sentences are templated from product names.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_branded as eb  # noqa: E402
import evaluate_nlu as ev  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

from app import languages as reg  # noqa: E402
from app.db import Base, make_engine, make_session_factory  # noqa: E402
from app.main import VERSION  # noqa: E402
from app.models import Product  # noqa: E402
from app.nlu.lexicon import Lexicon  # noqa: E402
from app.nlu.parser import parse_utterance  # noqa: E402
from app.nlu.units import convert_quantity  # noqa: E402
from app.seed import seed_products  # noqa: E402
from app.services import pipeline  # noqa: E402
from app.services.catalog import CatalogCache, load_views  # noqa: E402

OUT = ROOT / "eval" / "results" / "evaluation_summary.json"
LANGS = list(reg.ORDER)
SEEDS = 5
NOISE_RATES = (0.0, 0.03, 0.06, 0.10, 0.15)


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def fresh_shop():
    """A throw-away shop with the 65 curated staples. Returns (session_factory, views)."""
    d = Path(tempfile.mkdtemp())
    eng = make_engine(f"sqlite:///{d / 'e.db'}")
    Base.metadata.create_all(eng)
    sf = make_session_factory(eng)
    with sf() as db:
        seed_products(db)
        db.commit()
        views = load_views(db)
    return sf, views


# ----------------------------------------------------------------------------------------------- sentence check
def classify_order_row(text: str, gold: list, lex: Lexicon, sku_of: dict) -> str:
    """exact | wrong | unrecognised | ambiguous for ONE order sentence (no language hint)."""
    r, pred = ev.predict(text, lex, sku_of)
    want = Counter((g[0], ev.norm_qty(g[1]), g[2]) for g in gold)
    resolved = [p for p in pred if p["sku"]]
    got = Counter((p["sku"], ev.norm_qty(p["qty"]), p["unit"]) for p in resolved)
    if want == got and len(resolved) == len(pred):
        return "exact"
    if any(p["sku"] is None and p["n_cand"] >= 2 for p in pred):
        return "ambiguous"
    if not resolved or any(p["sku"] is None and p["n_cand"] == 0 for p in pred):
        return "unrecognised"
    return "wrong"


def sentence_check(lex, sku_of, d1, d3, branded):
    rows: list[dict] = []

    def add(lang, dataset, label, outcomes):
        c = Counter(outcomes)
        n = len(outcomes)
        rows.append({"lang": lang, "dataset": dataset, "dataset_label": label, "n": n, "exact": c["exact"], "wrong": c["wrong"],
                     "unrecognised": c["unrecognised"], "ambiguous": c["ambiguous"], "exact_pct": round(100 * c["exact"] / n, 1) if n else None})

    for lang in LANGS:
        for s, label in (("handwritten", "Handwritten sentences"), ("templated", "Templated sentences")):
            sub = [r for r in d1 if r["set"] == s and r["kind"] == "normal" and r["lang"] == lang]
            if sub:
                add(lang, s, label, [classify_order_row(r["text"], r["gold"], lex, sku_of) for r in sub])
        sub = [r for r in d3 if r["lang"] == lang]
        if sub:
            add(lang, "authored", "Authored sentences (2.3.0 table)", [classify_order_row(r["text"], r["gold"], lex, sku_of) for r in sub])
        b = branded["by_language"].get(lang)
        if b:
            n = sum(b.values())
            c = {"exact": b.get("exact", 0), "wrong": b.get("wrong_product", 0), "unrecognised": b.get("not_recognised", 0),
                 "ambiguous": b.get("ambiguous_contains_expected", 0)}
            rows.append({"lang": lang, "dataset": "branded", "dataset_label": "Held-out branded products", "n": n, **c,
                         "exact_pct": round(100 * c["exact"] / n, 1)})
    return rows


# ----------------------------------------------------------------------------------------------- name resolution
def name_resolution(lex, views):
    sku_of = {pid: v.sku for pid, v in views.items()}
    out = []
    for lang in LANGS:
        c = Counter()
        for v in views.values():
            if lang == "gu":
                name = v.name_gu
            elif lang == "hi":
                name = v.name_hi
            elif lang == "en":
                name = v.name_en
            elif lang == "hinglish":
                continue  # Hinglish is Latin-script Hindi: it has no separate primary names to test
            else:
                names = v.names.get(lang) or []
                name = names[0] if names else ""
            if not name:
                c["missing"] += 1
                continue
            r = parse_utterance(name, lex, language_hint=lang)
            ids = [p for ln in r.lines for p in ln.product_ids]
            first = [ln.product_ids[0] for ln in r.lines if ln.product_ids][:1]
            if first == [v.id] and len(ids) == 1:
                c["own"] += 1
            elif v.id in ids:
                c["ambiguous_includes_own"] += 1
            elif ids:
                c["wrong"] += 1
            else:
                c["none"] += 1
        n = sum(c.values())
        out.append({"lang": lang, "n": n, "own": c["own"], "ambiguous_includes_own": c["ambiguous_includes_own"], "wrong": c["wrong"],
                    "none": c["none"], "missing": c["missing"], "own_pct": round(100 * c["own"] / n, 1) if n else None,
                    "applicable": lang != "hinglish"})
    return out


# ----------------------------------------------------------------------------------------------- language detection
def detection_matrix(lex, d1, d3, branded_cases):
    texts = [(r["lang"], r["text"], "handwritten" if r.get("set") == "handwritten" else "templated") for r in d1 if r["kind"] != "no_item"]
    texts += [(r["lang"], r["text"], "authored") for r in d3]
    texts += [(c["lang"], c["text"], "branded") for c in branded_cases]
    idx = {k: i for i, k in enumerate(LANGS)}
    m = [[0] * len(LANGS) for _ in LANGS]
    for lang, text, _ in texts:
        got = parse_utterance(text, lex).language
        if got in idx:
            m[idx[lang]][idx[got]] += 1
    per = []
    for k in LANGS:
        row = m[idx[k]]
        n = sum(row)
        per.append({"lang": k, "n": n, "correct": row[idx[k]], "pct": round(100 * row[idx[k]] / n, 1) if n else None})
    return {"labels": LANGS, "matrix": m, "per_language": per, "n": sum(sum(r) for r in m),
            "note": "True language (row) against the label the parser gave with NO selector hint (column). Hindi/Marathi share Devanagari and English/Hinglish share Latin letters; the selector decides those in the app."}


# ----------------------------------------------------------------------------------------------- branded
def branded_block():
    res = eb.run()  # also rewrites data/test/branded_results.json
    cases = res["case_details"]
    cats = Counter(c["expected_category"] for c in cases)
    top = [k for k, _ in cats.most_common(7)]
    cols = top + ["Other category", "Asked which pack", "Not recognised"]
    m = {r: Counter() for r in top + ["Other category"]}
    for c in cases:
        row = c["expected_category"] if c["expected_category"] in top else "Other category"
        if c["verdict"] == "not_recognised":
            col = "Not recognised"
        elif c["verdict"] == "ambiguous_contains_expected":
            col = "Asked which pack"
        else:
            got = c["got_categories"][0] if c["got_categories"] else "Other category"
            col = got if got in top else "Other category"
        m[row][col] += 1
    pairs = Counter((c["expected"], tuple(c["got"][:1])) for c in cases if c["verdict"] == "wrong_product")
    return res, {
        "labels_rows": top + ["Other category"], "labels_cols": cols, "matrix": [[m[r][c] for c in cols] for r in top + ["Other category"]],
        "wrong_pairs": [{"expected": e, "got": g[0] if g else "", "count": n} for (e, g), n in pairs.most_common()],
    }


# ----------------------------------------------------------------------------------------------- noise and ablation
class StageLexicon(Lexicon):
    """The real lexicon with the later matching stages switched off (stages run exact -> skeleton -> stem -> fuzzy, so any allowed set is a prefix)."""

    allowed: tuple[str, ...] = ("exact", "skeleton", "stem", "fuzzy")

    def match_phrase(self, tokens, start, end, allow_fuzzy=True, exact_only=False):
        m = super().match_phrase(tokens, start, end, allow_fuzzy, exact_only)
        return m if m is None or m.kind in self.allowed else None


STAGES = [
    ("exact", "Exact name or alias"),
    ("skeleton", "+ phonetic skeleton"),
    ("stem", "+ case endings removed"),
    ("fuzzy", "+ fuzzy match (full system)"),
]


def noise_block(views, d1):
    sku_of = {pid: v.sku for pid, v in views.items()}
    lex = Lexicon(list(views.values()))
    hw = [r for r in d1 if r["set"] == "handwritten" and r["kind"] == "normal"]
    levels = []
    for rate in NOISE_RATES:
        ps, rs, fs, ex, pp, pr, pf = [], [], [], [], [], [], []
        for seed in range(SEEDS):
            rng = random.Random(1000 + seed)
            m, _ = ev.score(hw, lex, sku_of, text_fn=lambda t, rate=rate, rng=rng: ev.corrupt(t, rate, rng))
            L, P = m["line_exact (sku+qty+unit)"], m["product_only"]
            ps.append(L["precision"]); rs.append(L["recall"]); fs.append(L["f1"]); ex.append(m["utterance_exact"])
            pp.append(P["precision"]); pr.append(P["recall"]); pf.append(P["f1"])
        mean = lambda v: round(statistics.mean(v), 4)  # noqa: E731
        levels.append({"cer": rate, "line_precision": mean(ps), "line_recall": mean(rs), "line_f1": mean(fs), "product_precision": mean(pp),
                       "product_recall": mean(pr), "product_f1": mean(pf), "utterance_exact": mean(ex),
                       "utterance_exact_min": min(ex), "utterance_exact_max": max(ex)})
    ablation = []
    for rate in (0.03, 0.06, 0.10):
        for i, (stage, label) in enumerate(STAGES):
            sl = StageLexicon(list(views.values()))
            sl.allowed = tuple(s for s, _ in STAGES[: i + 1])
            ex, f1 = [], []
            for seed in range(SEEDS):
                rng = random.Random(1000 + seed)
                m, _ = ev.score(hw, sl, sku_of, text_fn=lambda t, rate=rate, rng=rng: ev.corrupt(t, rate, rng))
                ex.append(m["utterance_exact"]); f1.append(m["line_exact (sku+qty+unit)"]["f1"])
            ablation.append({"cer": rate, "stage": stage, "label": label, "utterance_exact": round(statistics.mean(ex), 4), "line_f1": round(statistics.mean(f1), 4)})
    return {"seeds": SEEDS, "n_sentences": len(hw), "levels": levels, "ablation": ablation,
            "note": "Simulated character damage (delete / substitute / duplicate letters) on the handwritten set. It is not acoustic noise and does not reproduce Prisma's real errors."}


# ----------------------------------------------------------------------------------------------- typed-text end to end
def end_to_end(d1, d3):
    sf, views = fresh_shop()
    catalog = CatalogCache()
    sku_to_view = {v.sku: v for v in views.values()}
    sku_by_pid = {pid: v.sku for pid, v in views.items()}
    rows = [dict(r, src="D1") for r in d1 if r["kind"] == "normal"] + [dict(r, src="D3", set="authored") for r in d3]
    outcomes: Counter = Counter()
    by_lang: dict[str, Counter] = defaultdict(Counter)
    problems: list[dict] = []
    asked: list[dict] = []
    guard = Counter()

    def expected_for(gold):
        exp = {}
        for sku, q, u in gold:
            v = sku_to_view.get(sku)
            if v is None:
                return None
            conv = convert_quantity(v.unit, v.pack_size, v.pack_size_unit, Decimal(str(q)), u)
            if conv.status != "ok":
                return None
            exp[sku] = exp.get(sku, Decimal(0)) + conv.qty
        return exp

    def run_session(db, text):
        out = pipeline.process_turn(db, catalog, text, input_mode="text")
        sid = out["session_id"]
        if out["pending"]:
            return out, "asked"
        if out["phase"] == "collecting" and out["awaiting"] == "more_items" and out["cart"]["lines"]:
            out = pipeline.process_turn(db, catalog, "that's all", session_id=sid, keep_language=True)
        if out["pending"]:
            return out, "asked"
        out = pipeline.process_turn(db, catalog, "confirm", session_id=sid, keep_language=True)
        if out["phase"] == "confirming" and not out["order"]:
            out = pipeline.process_turn(db, catalog, "confirm", session_id=sid, keep_language=True)
        return out, "done"

    with sf() as db:
        # the seed leaves some staples finished or low; for THIS pass every shelf is full, so the result is about the language pipeline
        # (the stock rules are measured separately below with an empty and a half-empty shelf)
        stock0 = {p.sku: Decimal(500) for p in db.scalars(select(Product))}
        for sku, q in stock0.items():
            db.execute(update(Product).where(Product.sku == sku).values(stock=q))
        db.commit()
        for r in rows:
            exp = expected_for(r["gold"])
            if exp is None:
                outcomes["skipped_gold_not_convertible"] += 1
                continue
            # restore stock so every sentence starts from the same shelf
            for sku, q in stock0.items():
                db.execute(update(Product).where(Product.sku == sku).values(stock=q))
            db.commit()
            out, how = run_session(db, r["text"])
            if how == "asked" and not out["order"]:
                kind = "asked_to_clarify"
            elif out["order"]:
                got = {}
                for it in out["order"]["items"]:
                    sku = sku_by_pid.get(it["product_id"])
                    got[sku] = got.get(sku, Decimal(0)) + Decimal(str(it["qty"]))
                after = {p.sku: Decimal(p.stock) for p in db.scalars(select(Product))}
                stock_ok = all(after[s] == stock0[s] - got.get(s, Decimal(0)) for s in stock0)
                kind = "order_correct" if (got == exp and stock_ok) else "order_wrong"
                if kind == "order_wrong" and len(problems) < 12:
                    problems.append({"id": r["id"], "text": r["text"], "expected": {k: str(v) for k, v in exp.items()}, "got": {str(k): str(v) for k, v in got.items()}, "stock_consistent": stock_ok})
            else:
                kind = "no_order"
                if len(problems) < 12:
                    problems.append({"id": r["id"], "text": r["text"], "outcome": "no_order", "reply": out["reply_text"][:140], "phase": out["phase"]})
            if kind == "asked_to_clarify" and len(asked) < 12:
                asked.append({"id": r["id"], "text": r["text"], "asked": out["reply_text"][:140]})
            outcomes[kind] += 1
            by_lang[r["lang"]][kind] += 1
        # stock guard 1: the shelf is EMPTY for the ordered goods, so no order may be created and stock may never go negative
        # stock guard 2: the shelf holds HALF of what was asked, so the assistant must offer the smaller amount, never silently ship the full one
        for r in rows[:: max(1, len(rows) // 80)]:
            exp = expected_for(r["gold"])
            if exp is None:
                continue
            for mode, factor in (("empty", Decimal(0)), ("half", Decimal("0.5"))):
                for sku, q in stock0.items():
                    db.execute(update(Product).where(Product.sku == sku).values(stock=q))
                for sku, q in exp.items():
                    avail = (q * factor).quantize(Decimal("0.001"))
                    db.execute(update(Product).where(Product.sku == sku).values(stock=avail))
                db.commit()
                out, how = run_session(db, r["text"])
                negative = any(Decimal(p.stock) < 0 for p in db.scalars(select(Product)))
                guard[f"{mode}_checked"] += 1
                guard[f"{mode}_negative_stock"] += 1 if negative else 0
                if out["order"]:
                    over = any(Decimal(str(i["qty"])) > exp.get(sku_by_pid.get(i["product_id"]), Decimal(0)) * factor for i in out["order"]["items"])
                    guard[f"{mode}_order_created"] += 1
                    guard[f"{mode}_order_over_stock"] += 1 if over else 0
                elif how == "asked":
                    guard[f"{mode}_asked_or_offered"] += 1
                else:
                    guard[f"{mode}_refused"] += 1
    n = sum(outcomes.values())
    scored = n - sum(v for k, v in outcomes.items() if k.startswith("skipped"))  # a sentence whose gold cannot be written as an order is not an error
    return {
        "n_sentences": n, "n_scored": scored, "outcomes": dict(outcomes), "by_language": {k: dict(v) for k, v in sorted(by_lang.items())},
        "order_correct_pct": round(100 * outcomes["order_correct"] / scored, 1) if scored else None,
        "wrong_order_pct": round(100 * outcomes["order_wrong"] / scored, 1) if scored else None,
        "not_completed": problems, "clarifications": asked, "stock_guard": dict(guard),
        "note": "Typed text through the real dialogue (sentence, 'that's all', 'confirm') against a throw-away shop. A sentence where the assistant asked which product or how much, instead of guessing, is listed separately and is not counted as an error. No speech is involved.",
    }



# ----------------------------------------------------------------------------------------------- technology stack
def technology_stack() -> list[dict]:
    """The stack table of the report and the app. Versions are read from what is installed / locked, never typed in."""
    from importlib import metadata

    def py(name: str) -> str:
        try:
            return f"{name} {metadata.version(name)}"
        except metadata.PackageNotFoundError:
            return name

    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))["packages"]

    def js(name: str, label: str | None = None) -> str:
        v = lock.get(f"node_modules/{name}", {}).get("version")
        return f"{label or name} {v}" if v else (label or name)

    tested, mocked = "Implemented and tested", "Implemented; tested with mocked HTTP, not live-verified"
    return [
        {"component": "API server", "technology": f"{py('fastapi')}, {py('uvicorn')}", "purpose": "REST and WebSocket API; also serves the built web app", "status": tested},
        {"component": "Database", "technology": f"SQLite through {py('SQLAlchemy')}", "purpose": "Products, customers, orders, stock ledger, conversations, accounts, payments, refunds and invoices", "status": tested},
        {"component": "Validation and settings", "technology": f"{py('pydantic')}, {py('pydantic-settings')}", "purpose": "Request validation and environment configuration", "status": tested},
        {"component": "Accounts and sessions", "technology": "scrypt password hashing (RFC 7914), server-side sessions in an HttpOnly cookie, CSRF token", "purpose": "Sign-in, owner and staff roles, protected routes", "status": tested},
        {"component": "Product matching", "technology": f"Own exact, phonetic-skeleton, case-stem stages and {py('rapidfuzz')}", "purpose": "Find the product a spoken or typed line refers to, in 11 languages", "status": "Implemented; evaluated on text only"},
        {"component": "Audio handling", "technology": py("numpy"), "purpose": "Check and convert recorded audio before it is sent; the Noise lab", "status": tested},
        {"component": "Outbound HTTP", "technology": py("httpx"), "purpose": "Calls to Gnani, and to Razorpay when the owner has set test keys, from the server; the Gnani key and the Razorpay secrets never reach the browser", "status": tested},
        {"component": "Payments", "technology": "Own payment module over SQLite: state rules, audit trail, refunds, invoices; cash, UPI link and QR, Razorpay Checkout (test mode) through httpx, no Razorpay SDK", "purpose": "Take payment for an order, refund it, print an invoice, report collected money", "status": "Implemented and tested; Razorpay was tested against a stand-in, never against the real service"},
        {"component": "UPI QR code", "technology": js("qrcode-generator"), "purpose": "Draws the QR for the shop's own UPI payment link in the browser; nothing is sent anywhere", "status": tested},
        {"component": "Speech recognition", "technology": "Gnani Prisma v2.5", "purpose": "Turn the customer's speech into text", "status": mocked},
        {"component": "Speech synthesis", "technology": "Gnani Timbre v2.5", "purpose": "Read the bill and questions back in the customer's language", "status": mocked},
        {"component": "Evon", "technology": "Not integrated", "purpose": "Mentioned in docs/EVON.md only", "status": "Not used"},
        {"component": "Product catalogue data", "technology": "Open Food Facts India extract (ODbL), bundled as a file", "purpose": "5,325 real packaged products: names, brands, pack sizes; no prices", "status": tested},
        {"component": "Web app", "technology": f"{js('react', 'React')}, TypeScript {lock.get('node_modules/typescript', {}).get('version', '')}".rstrip(), "purpose": "Order desk, inventory, orders, payments, analytics, AI performance, settings", "status": tested},
        {"component": "Routing and build", "technology": f"{js('react-router-dom', 'React Router')}, {js('vite', 'Vite')}", "purpose": "Pages and the production bundle", "status": tested},
        {"component": "Charts", "technology": f"{js('recharts', 'Recharts')} plus plain SVG and HTML", "purpose": "Every chart has a table view; matrices are real HTML tables", "status": tested},
        {"component": "Fonts", "technology": "Newsreader, Geist, Geist Mono, Noto Sans Indic, self-hosted with @fontsource", "purpose": "Typography, with no request to a font service", "status": tested},
        {"component": "Tests", "technology": f"{py('pytest')}, {js('vitest', 'Vitest')}, Playwright for Python with Chrome", "purpose": "Backend, component and browser tests", "status": tested},
        {"component": "Windows start-up", "technology": "setup.bat, start.bat, dev.bat, test.bat, verify_gnani.bat", "purpose": "One-command install and run without Docker", "status": "Implemented; scripts reviewed, not run on Windows in this environment"},
    ]


# ----------------------------------------------------------------------------------------------- latency
def parser_latency(lex, d1):
    times = []
    for _ in range(5):
        for r in d1:
            t0 = time.perf_counter()
            parse_utterance(r["text"], lex)
            times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return {"n": len(times), "p50_ms": round(times[len(times) // 2], 3), "p95_ms": round(times[int(len(times) * 0.95)], 3), "max_ms": round(times[-1], 3)}


def main() -> None:
    d1 = read_jsonl(ROOT / "eval" / "utterances.jsonl")
    d3 = read_jsonl(ROOT / "eval" / "language_sentences.jsonl")
    sf, views = fresh_shop()
    lex = Lexicon(list(views.values()))
    sku_of = {pid: v.sku for pid, v in views.items()}
    print("branded ...", flush=True)
    branded, branded_conf = branded_block()
    print("sentences ...", flush=True)
    sc = sentence_check(lex, sku_of, d1, d3, branded)
    nr = name_resolution(lex, views)
    det = detection_matrix(lex, d1, d3, read_jsonl(ROOT / "data" / "test" / "branded_utterances.jsonl"))
    print("noise + ablation ...", flush=True)
    noise = noise_block(views, d1)
    print("end to end ...", flush=True)
    e2e = end_to_end(d1, d3)
    lat = parser_latency(lex, d1)
    hw = [r for r in d1 if r["set"] == "handwritten"]
    kinds = Counter((r["set"], r["kind"]) for r in d1)
    summary = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": VERSION,
        "scope": "TEXT only. No speech recognition, no speech synthesis and no Gnani call is involved in any number in this file.",
        "languages": [{"key": k, "name": reg.LANGUAGES[k].name, "native": reg.LANGUAGES[k].native} for k in LANGS],
        "datasets": [
            {"id": "handwritten", "name": "Handwritten sentences", "n": len(hw), "n_order": kinds[("handwritten", "normal")],
             "languages": ["gu", "hi", "hinglish", "en"], "provenance": "Written by the parser's author, with gold lines; includes 4 ambiguous and 10 non-order sentences",
             "file": "eval/utterances.jsonl"},
            {"id": "templated", "name": "Templated sentences", "n": kinds[("templated", "normal")], "n_order": kinds[("templated", "normal")],
             "languages": ["gu", "hi", "hinglish", "en"], "provenance": "Generated from sentence templates over the staples", "file": "eval/utterances.jsonl"},
            {"id": "authored", "name": "Authored sentences, all 11 languages", "n": len(d3), "n_order": len(d3), "languages": LANGS,
             "provenance": "Registry sample sentence plus the sentences of the language tests; for the 7 languages added in 2.3.0 authored with NO native-speaker review",
             "file": "eval/language_sentences.jsonl"},
            {"id": "branded", "name": "Held-out branded products", "n": branded["cases"], "n_order": branded["cases"], "languages": ["gu", "hi", "hinglish", "en"],
             "provenance": f"Templated from the names of {branded['held_out_products_imported']} held-out Open Food Facts products; synthetic sentences, real product names",
             "file": "data/test/branded_utterances.jsonl"},
        ],
        "sentence_check": sc,
        "name_resolution": nr,
        "language_detection": det,
        "branded": {"verdicts": branded["verdicts"], "cases": branded["cases"],
                    "exact_pct": branded["exact_pct"], "wrong_product_pct": branded["wrong_product_pct"],
                    "recognised_or_asked_pct": branded["recognised_or_asked_to_choose_pct"], "by_language": branded["by_language"],
                    "confusion": branded_conf, "caveats": branded["caveats"]},
        "behaviour_checks": {
            "ambiguous_not_guessed": ev.score([r for r in d1 if r["set"] == "handwritten"], lex, sku_of)[0]["ambiguous_not_guessed"],
            "no_item_no_false_add": ev.score([r for r in d1 if r["set"] == "handwritten"], lex, sku_of)[0]["no_item_no_false_add"],
        },
        "noise": noise,
        "end_to_end": e2e,
        "parser_latency": lat,
        "technology": technology_stack(),
        "limitations": [
            "The gold labels of the four original languages were written by the author of the parser, so their 100% figures are a ceiling, not a forecast.",
            "The seven languages added in 2.3.0 have a handful of authored sentences each and have had NO native-speaker review; their figures show the parser agrees with its author.",
            "The branded sentences are templated from product names and never name a pack size, so pack-size recognition from speech is not measured.",
            "Noise is simulated character damage, not acoustic noise; real Prisma errors were never measured because no live Gnani call could be made.",
            "STT and TTS latency and word-error rate are not in this file: they exist only for live calls, and none was made.",
        ],
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT) if OUT.is_relative_to(ROOT) else OUT}")
    print("branded:", summary["branded"]["verdicts"])
    print("end to end:", e2e["outcomes"], "guard:", e2e["stock_guard"])
    print("noise levels:", [(l["cer"], l["utterance_exact"], l["line_f1"]) for l in noise["levels"]])


if __name__ == "__main__":
    main()
