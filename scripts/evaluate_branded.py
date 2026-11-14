"""Can a customer order an imported branded product by its spoken name?  (held-out `test` split of the catalogue)

    python scripts/evaluate_branded.py

Setup: a fresh in-memory shop with the 65 curated staples plus ONLY the held-out test products imported (price is a dummy
value; it is irrelevant to recognition). Each templated sentence is parsed and the result is compared with the expected EAN.
This measures TEXT recognition of product names. It says nothing about speech recognition and nothing about prices.
Writes data/test/branded_results.json.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db import Base, make_engine, make_session_factory  # noqa: E402
from app.models import CatalogItem  # noqa: E402
from app.nlu.lexicon import Lexicon  # noqa: E402
from app.nlu.parser import parse_utterance  # noqa: E402
from app.seed import seed_catalog, seed_products  # noqa: E402
from app.services.catalog import load_views  # noqa: E402
from app.services.catalog_items import import_to_shop  # noqa: E402


def run() -> dict:
    cases = [json.loads(l) for l in open(ROOT / "data" / "test" / "branded_utterances.jsonl", encoding="utf-8")]
    d = Path(tempfile.mkdtemp())
    eng = make_engine(f"sqlite:///{d / 'b.db'}")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as db:
        seed_products(db)
        seed_catalog(db)
        for it in db.scalars(select(CatalogItem).where(CatalogItem.split == "test")).all():
            import_to_shop(db, it.id, 1000, Decimal(5), Decimal(1), None)
        views = load_views(db)
    lex = Lexicon(list(views.values()))
    ean_of = {pid: v.sku.removeprefix("EAN-") for pid, v in views.items() if v.sku.startswith("EAN-")}
    pid_of = {e: pid for pid, e in ean_of.items()}
    detail = []
    by_lang: dict[str, Counter] = {}
    total = Counter()
    misses = []
    for c in cases:
        r = parse_utterance(c["text"], lex)
        ids = [i for ln in r.lines for i in ln.product_ids]
        eans = [ean_of.get(i) for i in ids]
        if r.lines and r.lines[0].resolved and eans and eans[0] == c["expect_ean"]:
            verdict = "exact"
        elif c["expect_ean"] in eans:
            verdict = "ambiguous_contains_expected"  # e.g. several pack sizes of the same product: the app asks which one
        elif not ids:
            verdict = "not_recognised"
        else:
            verdict = "wrong_product"
        total[verdict] += 1
        detail.append({"id": c["id"], "lang": c["lang"], "verdict": verdict, "expected": c["expect_name"],
                       "expected_category": views[pid_of[c["expect_ean"]]].category if c["expect_ean"] in pid_of else "",
                       "got": [views[i].name_en for i in ids][:3], "got_categories": [views[i].category for i in ids][:3]})
        by_lang.setdefault(c["lang"], Counter())[verdict] += 1
        if verdict in ("wrong_product", "not_recognised") and len(misses) < 15:
            misses.append({"text": c["text"], "expected": c["expect_name"], "verdict": verdict,
                           "got": [views[i].name_en for i in ids][:3]})
    n = len(cases)
    handled = total["exact"] + total["ambiguous_contains_expected"]
    res = {
        "cases": n, "held_out_products_imported": len(ean_of), "verdicts": dict(total),
        "recognised_or_asked_to_choose_pct": round(100 * handled / n, 1), "exact_pct": round(100 * total["exact"] / n, 1),
        "wrong_product_pct": round(100 * total["wrong_product"] / n, 1),
        "by_language": {k: dict(v) for k, v in sorted(by_lang.items())}, "sample_misses": misses, "case_details": detail,
        "caveats": [
            "Sentences are templated from the product's own name, so this is an optimistic ceiling for name recognition.",
            "Text only: no speech recognition is involved. Gnani Prisma may mis-hear brand names; run the Noise lab for that.",
            "Only the held-out 10% of catalogue products are imported, so there are fewer look-alike competitors than in a full shop.",
        ],
    }
    (ROOT / "data" / "test" / "branded_results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return res


if __name__ == "__main__":
    res = run()
    print(json.dumps({k: res[k] for k in ("verdicts", "recognised_or_asked_to_choose_pct", "exact_pct", "wrong_product_pct", "by_language")} | {"case_details": len(res["case_details"])}, indent=2))
    for m in res["sample_misses"][:8]:
        print(" ", m)
