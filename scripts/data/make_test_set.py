"""Build the held-out branded-ordering test set from the `test` split of the catalogue.

    python scripts/data/make_test_set.py

Output: data/test/branded_utterances.jsonl  (each line: id, text, lang, expect_ean, provenance="synthetic")

The product identities are REAL (sourced from Open Food Facts); the sentences are TEMPLATED and therefore SYNTHETIC.
Rows from the `train` split are never used here, so alias rules can be tuned on train and judged on this file.
"""
from __future__ import annotations

import csv
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CATALOG_CSV, TEST  # noqa: E402

TEMPLATES = [
    ("hinglish", "ek {n} dena"),
    ("hinglish", "bhaiya 2 {n} chahiye"),
    ("en", "I want one {n} please"),
    ("hi", "मुझे एक {n} दे दो"),
    ("gu", "મને એક {n} જોઈએ છે"),
]


def spoken_name(row: dict) -> str:
    """What a customer would say: brand + product, without the pack size."""
    name = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kg|kgs|g|gm|gms|gr|gram|grams|l|ltr|litre|liter|ml|pcs?)\b\.?", " ", row["name"], flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -,.")
    brand = row["brand"].strip()
    return name if (not brand or name.lower().startswith(brand.lower())) else f"{brand} {name}"


def main(limit: int = 300, seed: int = 2026) -> None:
    with open(CATALOG_CSV, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["split"] == "test" and r["brand"].strip()]
    rng = random.Random(seed)
    rng.shuffle(rows)
    out = []
    for i, r in enumerate(rows[:limit]):
        lang, tpl = TEMPLATES[i % len(TEMPLATES)]
        out.append({"id": f"b{i:04d}", "text": tpl.format(n=spoken_name(r)), "lang": lang, "expect_ean": r["ean"],
                    "expect_name": r["name"], "provenance": "synthetic", "product_provenance": "sourced"})
    TEST.mkdir(parents=True, exist_ok=True)
    path = TEST / "branded_utterances.jsonl"
    path.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} utterances to {path}")


if __name__ == "__main__":
    main()
