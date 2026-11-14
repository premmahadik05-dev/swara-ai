"""Measure the NLU (text -> structured order lines) on eval/utterances.jsonl.  Fully offline, deterministic.

What this does and does NOT measure
-----------------------------------
* Input is TEXT. It measures the parser/lexicon, not speech recognition.
* The gold labels were written by the same author as the parser. Treat numbers as optimistic.
* "Simulated transcript noise" corrupts characters in the text to mimic spelling errors. It is NOT acoustic
  noise and does not reproduce Gnani's real error distribution - see scripts/evaluate_noise.py for audio.

Usage:  python scripts/evaluate_nlu.py [--tag first_run] [--failures]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.db import Base, make_engine, make_session_factory  # noqa: E402
from app.nlu.lexicon import Lexicon  # noqa: E402
from app.nlu.parser import parse_utterance  # noqa: E402
from app.seed import seed_products  # noqa: E402
from app.services.catalog import load_views  # noqa: E402

UNIT_ALIAS = {"bottle": "bottle"}


def build_lexicon():
    d = Path(tempfile.mkdtemp())
    eng = make_engine(f"sqlite:///{d / 'e.db'}")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as db:
        seed_products(db)
        db.commit()
        views = load_views(db)
    return Lexicon(list(views.values())), {pid: v.sku for pid, v in views.items()}


def corrupt(text: str, rate: float, rng: random.Random) -> str:
    """Character-level corruption of letters only (digits untouched): delete / substitute / duplicate."""
    out = []
    for ch in text:
        if ch.isalpha() and rng.random() < rate:
            op = rng.choice("dsu")
            if op == "d":
                continue
            if op == "s":
                same_script = [c for c in text if c.isalpha() and (ord(c) >> 7) == (ord(ch) >> 7) and c != ch]
                out.append(rng.choice(same_script) if same_script else ch)
                continue
            out.append(ch + ch)
        else:
            out.append(ch)
    return "".join(out)


def predict(text, lex, sku_of):
    r = parse_utterance(text, lex)
    lines = []
    for ln in r.lines:
        sku = sku_of[ln.product_ids[0]] if ln.resolved else None
        lines.append({"sku": sku, "qty": str(ln.qty) if ln.qty is not None else None, "unit": ln.unit,
                      "n_cand": len(ln.product_ids), "unknown": ln.unknown_term})
    return r, lines


def norm_qty(q):
    return None if q is None else str(Decimal(str(q)).normalize())


def score(rows, lex, sku_of, text_fn=lambda t: t):
    tp = fp = fn = 0
    tp_p = fp_p = fn_p = 0
    exact = n_norm = 0
    amb_ok = amb_n = 0
    noitem_ok = noitem_n = 0
    lang_ok = lang_n = lang_conf_ok = lang_conf_n = 0
    fails = []
    for row in rows:
        r, pred = predict(text_fn(row["text"]), lex, sku_of)
        lang_n += 1
        lang_ok += r.language == row["lang"]
        if r.lang_confident:
            lang_conf_n += 1
            lang_conf_ok += r.language == row["lang"]
        resolved = [p for p in pred if p["sku"]]
        if row["kind"] == "no_item":
            noitem_n += 1
            ok = not resolved
            noitem_ok += ok
            if not ok:
                fails.append((row, pred))
            continue
        if row["kind"] == "ambiguous":
            amb_n += 1
            g = row["gold"][0]
            ok = bool(pred) and pred[0]["sku"] is None and pred[0]["n_cand"] >= 2 and norm_qty(pred[0]["qty"]) == norm_qty(g[1])
            amb_ok += ok
            if not ok:
                fails.append((row, pred))
            continue
        n_norm += 1
        gold = Counter((g[0], norm_qty(g[1]), g[2]) for g in row["gold"])
        got = Counter((p["sku"], norm_qty(p["qty"]), p["unit"]) for p in resolved)
        inter = sum((gold & got).values())
        tp += inter
        fp += sum(got.values()) - inter
        fn += sum(gold.values()) - inter
        gold_p, got_p = Counter(g[0] for g in row["gold"]), Counter(p["sku"] for p in resolved)
        ip = sum((gold_p & got_p).values())
        tp_p += ip
        fp_p += sum(got_p.values()) - ip
        fn_p += sum(gold_p.values()) - ip
        if gold == got and len(resolved) == len(pred):
            exact += 1
        else:
            fails.append((row, pred))

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}

    return {
        "utterances": len(rows), "order_utterances": n_norm,
        "line_exact (sku+qty+unit)": prf(tp, fp, fn), "product_only": prf(tp_p, fp_p, fn_p),
        "utterance_exact": round(exact / n_norm, 4) if n_norm else None,
        "ambiguous_not_guessed": f"{amb_ok}/{amb_n}", "no_item_no_false_add": f"{noitem_ok}/{noitem_n}",
        "language_acc_all": round(lang_ok / lang_n, 4), "language_acc_when_confident": round(lang_conf_ok / lang_conf_n, 4) if lang_conf_n else None,
        "language_confident_share": round(lang_conf_n / lang_n, 4),
    }, fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="latest")
    ap.add_argument("--failures", action="store_true")
    a = ap.parse_args()
    rows = [json.loads(l) for l in (ROOT / "eval" / "utterances.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    lex, sku_of = build_lexicon()
    result = {"tag": a.tag, "n_total": len(rows), "sets": {}, "by_language": {}, "noise": {}}
    all_fails = {}
    for s in ("handwritten", "templated"):
        sub = [r for r in rows if r["set"] == s]
        result["sets"][s], f = score(sub, lex, sku_of)
        all_fails[s] = f
        for lang in ("gu", "hi", "hinglish", "en"):
            ss = [r for r in sub if r["lang"] == lang]
            result["by_language"][f"{s}/{lang}"], _ = score(ss, lex, sku_of)
    # simulated transcript noise (handwritten only), 5 seeds each
    hw = [r for r in rows if r["set"] == "handwritten" and r["kind"] == "normal"]
    for rate in (0.0, 0.03, 0.06, 0.10, 0.15):
        accs, f1s = [], []
        for seed in range(5):
            rng = random.Random(1000 + seed)
            m, _ = score(hw, lex, sku_of, text_fn=lambda t, rate=rate, rng=rng: corrupt(t, rate, rng))
            accs.append(m["utterance_exact"])
            f1s.append(m["line_exact (sku+qty+unit)"]["f1"])
        result["noise"][f"char_error_rate_{rate:.2f}"] = {"utterance_exact_mean": round(statistics.mean(accs), 4),
                                                           "line_f1_mean": round(statistics.mean(f1s), 4),
                                                           "utterance_exact_min": min(accs), "utterance_exact_max": max(accs)}
    # latency of the parser alone (single thread, warm)
    times = []
    for _ in range(5):
        for r in rows:
            t0 = time.perf_counter()
            parse_utterance(r["text"], lex)
            times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    result["parser_latency_ms"] = {"n": len(times), "p50": round(times[len(times) // 2], 3), "p95": round(times[int(len(times) * .95)], 3),
                                   "max": round(times[-1], 3)}
    out = ROOT / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"nlu_eval_{a.tag}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    fails_out = [{"id": r["id"], "text": r["text"], "gold": r["gold"], "kind": r["kind"], "pred": p} for s in all_fails for r, p in all_fails[s]]
    (out / f"nlu_failures_{a.tag}.json").write_text(json.dumps(fails_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["sets"], ensure_ascii=False, indent=1))
    print("noise:", json.dumps(result["noise"]))
    print("latency:", result["parser_latency_ms"])
    print(f"failures: {len(fails_out)}")
    if a.failures:
        for f in fails_out:
            print(f["id"], f["text"], "| gold", f["gold"], "| pred", [(p["sku"], p["qty"], p["unit"], p["n_cand"]) for p in f["pred"]])


if __name__ == "__main__":
    main()
