"""Clean the raw Open Food Facts India snapshot into a kirana reference catalogue.

    python scripts/data/build_catalog.py

Input : data/raw/off_india_2026-07-05.csv         (sourced, never edited)
Output: data/processed/catalog_off_india.csv      (transformed: one row per product, with raw values kept beside cleaned ones)
        data/processed/build_report.json          (counts after every stage and every rejection reason)

Rules are deterministic and listed in `transforms` on each row. Nothing is invented: a missing brand stays blank,
no Gujarati/Hindi names are generated, and there is no price column because the source has no prices.
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import hashlib
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CATALOG_CSV, RAW_FILE, REPORT_JSON, SOURCE_ID, ean13_valid, fold, pack_label, parse_name_cell, parse_quantity,
    pick_name, tidy_name, write_json,
)

csv.field_size_limit(10**9)

TAXONOMY = [
    "Grains & Flour", "Pulses", "Oil & Ghee", "Sugar, Salt & Tea", "Dairy & Bakery", "Spices", "Snacks",
    "Beverages", "Dry Fruits", "Biscuits & Sweets", "Breakfast & Noodles", "Sauces & Spreads",
]

# Words that mark a product as outside a kirana's food range. Checked first.
EXCLUDE = re.compile(
    r"\b(supplement|protein powder|protein bar|whey|capsule|tablet|vitamin|probiotic|pet food|dog food|cat food|"
    r"baby formula|infant formula|lactogen|pediasure|ensure|nan pro|similac|enfamil|cosmetic|shampoo|detergent|non food|open products facts|open beauty facts)\b"
)

# (category, strong regex, weak regex). Strong words are specific enough to trust on a product NAME;
# weak words are only used on OFF's own category text. First matching category wins, so order matters.
_R = lambda s: re.compile(s)  # noqa: E731
RULES: list[tuple[str, re.Pattern, re.Pattern | None]] = [
    ("Biscuits & Sweets", _R(r"\b(biscuits?|cookies?|rusks?|chocolates?|candy|candies|toffee|toffees|gummies|laddoo|ladoo|mithai|halwa|"
                              r"barfi|burfi|rasgulla|gulab jamun|jalebi|wafer bars?|cakes?)\b"), _R(r"\b(sweets?|confectioner\w*|cocoa|desserts?)\b")),
    ("Breakfast & Noodles", _R(r"\b(noodles?|pasta|macaroni|vermicelli|corn ?flakes|cornflax|chocos|muesli|oats|breakfast cereals?|instant (?:mix|soup))\b"), _R(r"\b(breakfast|instant)\b")),
    ("Oil & Ghee", _R(r"\b(ghee|(?:cooking|edible|sunflower|mustard|groundnut|coconut|olive|sesame|soybean|soya|palm|rice bran|vegetable|refined) oil)\b"), _R(r"\b(vegetable fats?|fats and oils|oils?)\b")),
    ("Sauces & Spreads", _R(r"\b(ketchup|sauces?|mayonnaise|jam|jams|pickles?|chutney|vinegar|honey|peanut butters?|spread|soups?)\b"), _R(r"\b(condiments?|spreads?|oilseed purees|legume butters)\b")),
    ("Beverages", _R(r"\b(coffee|juice|juices|soft drinks?|cola|soda|energy drinks?|squash|sharbat|packaged (?:drinking )?water|drinking water|lassi|buttermilk|milkshake|horlicks|bournvita|complan|health drink)\b"), _R(r"\b(beverages?|drinks?|sodas?|carbonated)\b")),
    ("Sugar, Salt & Tea", _R(r"\b(tea|chai|sugar|jaggery|gur|salt|rock salt)\b"), _R(r"\b(teas|sweeteners?|hot beverages)\b")),
    ("Snacks", _R(r"\b(chips|crisps|namkeen|bhujia|mixture|popcorn|wafers?|puffs|nachos|papad|papadum|snacks?|makhana|murukku|chakli|chiwda|chivda|sev|ganthia|gathiya|farsan|khakhra|thepla|fafda)\b"), _R(r"\b(salty snacks|appetizers|chips and fries)\b")),
    ("Dairy & Bakery", _R(r"\b(milk|curd|dahi|yogh?urt|paneer|butter|cheese|cream|ice creams?|khoa|bread|buns?|pav)\b"), _R(r"\b(dairies|dairy|milks|fermented milk products|breads|bakery|frozen desserts)\b")),
    ("Spices", _R(r"\b(masala|spices?|turmeric|haldi|cumin|jeera|coriander|chilli powder|chili powder|pepper|cardamom|cloves?|cinnamon|hing|asafoetida|ajwain|fenugreek|saffron|kasuri methi|javitri|rai|sarso|mustard seeds?|saunf|fennel|methi|kalonji|dalchini|elaichi|laung|mirch|dhania|amchur|hing powder)\b"), _R(r"\b(herbs and spices|herbs|condiments)\b")),
    ("Pulses", _R(r"\b(dal|daal|lentils?|chickpeas?|chana|rajma|moong|mung|toor|tur|urad|masoor|soya chunks?|pulses)\b"), _R(r"\b(legumes?|legumes and their products)\b")),
    ("Dry Fruits", _R(r"\b(almonds?|cashews?|raisins?|walnuts?|pistachios?|dates|dried fruits?|chia|flax|peanuts?|makhana|dry fruits?)\b"), _R(r"\b(nuts|seeds|nuts and their products|dried products)\b")),
    ("Grains & Flour", _R(r"\b(atta|flour|maida|besan|rice|wheat|semolina|suji|sooji|rava|poha|millets?|ragi|jowar|bajra|quinoa|basmati)\b"), _R(r"\b(cereals and potatoes|cereals and their products|cereal grains|flours)\b")),
]


def classify(categories: str, name: str) -> tuple[str, str] | None:
    """Return (kirana category, rule) or None.

    Three passes, so that a specific word beats a generic OFF tag like 'Breakfasts' or 'Desserts':
      1. strong words in OFF's category text   2. strong words in the product name   3. weak words in the category text
    """
    cat_text = fold(categories)
    name_text = fold(name)
    if EXCLUDE.search(cat_text) or EXCLUDE.search(name_text):
        return None
    for label, strong, _weak in RULES:
        if cat_text and strong.search(cat_text):
            return label, "cat:categories"
    for label, strong, _weak in RULES:
        if strong.search(name_text):
            return label, "cat:name"
    for label, _strong, weak in RULES:
        if cat_text and weak and weak.search(cat_text):
            return label, "cat:categories-generic"
    return None


def split_of(ean: str) -> str:
    """Deterministic 10% hold-out. Heuristics are tuned on `train` only; `test` is reported once."""
    return "test" if int(hashlib.sha256(ean.encode()).hexdigest(), 16) % 10 == 0 else "train"


def build() -> dict:
    rejects: collections.Counter = collections.Counter()
    stages: dict[str, int] = {}
    with open(RAW_FILE, newline="", encoding="utf-8") as fh:
        raw_rows = list(csv.DictReader(fh))
    stages["raw_rows"] = len(raw_rows)

    # brand display casing: most common raw variant per accent-folded key
    variants: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in raw_rows:
        first = (r.get("brands") or "").split(",")[0].strip()
        if first:
            variants[fold(first)][first] += 1

    def brand_display(raw: str) -> str:
        key = fold(raw)
        if not key:
            return ""
        best = max(variants[key].items(), key=lambda kv: (kv[0] != kv[0].lower(), kv[1]))[0]
        return best if best != best.lower() else best.title()

    kept: list[dict] = []
    for r in raw_rows:
        ean = (r.get("code") or "").strip()
        if not ean13_valid(ean):
            rejects["invalid_or_non_ean13_barcode"] += 1
            continue
        parts = parse_name_cell(r.get("product_name", ""))
        name_raw, name_rule = pick_name(parts)
        unescaped = html.unescape(name_raw)
        name, changed = tidy_name(unescaped)
        changed = changed or unescaped != name_raw
        if not name:
            rejects["blank_name"] += 1
            continue
        pq = parse_quantity(r.get("quantity", ""))
        if pq is None:
            rejects["quantity_blank_or_unparseable"] += 1
            continue
        value, unit, q_rule = pq
        cls = classify(r.get("categories", ""), name)
        if cls is None:
            rejects["no_kirana_category_or_excluded_type"] += 1
            continue
        category, c_rule = cls
        brand_raw = (r.get("brands") or "").split(",")[0].strip()
        transforms = [name_rule, q_rule, c_rule] + (["name:cleaned"] if changed else []) + ([] if brand_raw else ["brand:missing"])
        try:
            lm = dt.datetime.fromtimestamp(int(r.get("last_modified_t") or 0), dt.timezone.utc).date().isoformat()
        except (ValueError, OSError):
            lm = ""
        kept.append({
            "ean": ean, "name": name, "name_raw": name_raw, "brand": brand_display(brand_raw), "brand_raw": brand_raw,
            "category": category, "pack_size": f"{value:f}", "pack_unit": unit, "pack_label": pack_label(value, unit),
            "quantity_raw": (r.get("quantity") or "").strip(), "off_categories_raw": (r.get("categories") or "").strip(),
            "nova_group": (r.get("nova_group") or "").strip(), "nutriscore_grade": (r.get("nutriscore_grade") or "").strip(),
            "last_modified": lm, "source_id": SOURCE_ID, "provenance": "transformed", "transforms": "|".join(transforms),
            "split": split_of(ean),
        })
    stages["after_filters"] = len(kept)

    # near-duplicates: same brand + same cleaned name + same pack. Keep the most recently edited record.
    best: dict[tuple, dict] = {}
    for row in kept:
        key = (fold(row["brand"]), fold(row["name"]), row["pack_size"], row["pack_unit"])
        if key not in best or row["last_modified"] > best[key]["last_modified"]:
            best[key] = row
    rejects["near_duplicate_of_a_newer_record"] += len(kept) - len(best)
    final = sorted(best.values(), key=lambda x: (x["category"], fold(x["brand"]), fold(x["name"]), x["ean"]))
    stages["catalog_rows"] = len(final)

    CATALOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_CSV, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=list(final[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(final)

    by_cat = collections.Counter(r["category"] for r in final)
    by_rule = collections.Counter(r["transforms"].split("|")[2] for r in final)
    report = {
        "source_id": SOURCE_ID, "built_by": "scripts/data/build_catalog.py",
        "stages": stages, "rejections": dict(rejects.most_common()),
        "catalog": {
            "rows": len(final), "with_brand": sum(1 for r in final if r["brand"]), "brands": len({fold(r["brand"]) for r in final if r["brand"]}),
            "by_category": dict(by_cat.most_common()), "category_rule_used": dict(by_rule),
            "split": dict(collections.Counter(r["split"] for r in final)),
            "pack_units": dict(collections.Counter(r["pack_unit"] for r in final)),
        },
    }
    write_json(REPORT_JSON, report)
    return report


if __name__ == "__main__":
    rep = build()
    print(f"raw rows {rep['stages']['raw_rows']} -> catalog rows {rep['stages']['catalog_rows']}")
    for k, v in rep["rejections"].items():
        print(f"  rejected {v:6d}  {k}")
    for k, v in rep["catalog"]["by_category"].items():
        print(f"  {v:6d}  {k}")
