"""Validate the processed catalogue and its provenance. Exit code 0 = valid.

    python scripts/data/validate_catalog.py
"""
from __future__ import annotations

import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_catalog import TAXONOMY  # noqa: E402
from common import CATALOG_CSV, MANIFEST, PROVENANCE, RAW_FILE, REPORT_JSON, SOURCE_ID, ean13_valid, sha256_file  # noqa: E402

REQUIRED = [
    "ean", "name", "name_raw", "brand", "brand_raw", "category", "pack_size", "pack_unit", "pack_label", "quantity_raw",
    "off_categories_raw", "nova_group", "nutriscore_grade", "last_modified", "source_id", "provenance", "transforms", "split",
]
FORBIDDEN_COLUMNS = {"price", "price_paise", "mrp", "stock", "sales", "revenue"}  # the source has none; none may appear


def validate() -> list[str]:
    errors: list[str] = []
    if not CATALOG_CSV.exists():
        return [f"{CATALOG_CSV} is missing; run build_catalog.py"]
    with open(CATALOG_CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        rows = list(reader)
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        errors.append(f"missing columns: {missing}")
    bad_cols = FORBIDDEN_COLUMNS.intersection(header)
    if bad_cols:
        errors.append(f"forbidden (price/sales-like) columns present: {sorted(bad_cols)}")
    if len(rows) < 1000:
        errors.append(f"only {len(rows)} rows; expected thousands")

    seen: set[str] = set()
    for i, r in enumerate(rows, start=2):
        where = f"row {i} (ean {r.get('ean')})"
        if not ean13_valid(r["ean"]):
            errors.append(f"{where}: bad EAN-13 check digit")
        if r["ean"] in seen:
            errors.append(f"{where}: duplicate ean")
        seen.add(r["ean"])
        if not r["name"].strip():
            errors.append(f"{where}: blank name")
        if r["category"] not in TAXONOMY:
            errors.append(f"{where}: category {r['category']!r} not in taxonomy")
        if r["provenance"] not in PROVENANCE:
            errors.append(f"{where}: provenance {r['provenance']!r} not allowed")
        if r["provenance"] != "transformed":
            errors.append(f"{where}: OFF-derived rows must be 'transformed'")
        if r["source_id"] != SOURCE_ID:
            errors.append(f"{where}: unexpected source_id {r['source_id']!r}")
        if r["pack_unit"] not in ("kg", "l", "pc"):
            errors.append(f"{where}: bad pack_unit {r['pack_unit']!r}")
        try:
            size = Decimal(r["pack_size"])
            if size <= 0:
                errors.append(f"{where}: non-positive pack_size")
        except Exception:
            errors.append(f"{where}: pack_size not numeric")
        if r["split"] not in ("train", "test"):
            errors.append(f"{where}: bad split")
        if "&quot;" in r["name"] or "&amp;" in r["name"]:
            errors.append(f"{where}: unescaped HTML entity in name")
        if not r["transforms"].startswith("name:"):
            errors.append(f"{where}: transforms not recorded")
        if len(errors) > 50:
            errors.append("... stopping after 50 errors")
            break

    # provenance chain: manifest -> raw file hash -> report
    if not MANIFEST.exists():
        errors.append("data/sources/MANIFEST.json missing; run fetch_sources.py")
    else:
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        src = next((s for s in m["sources"] if s["id"] == SOURCE_ID), None)
        if src is None:
            errors.append("manifest has no entry for the current source id")
        elif not RAW_FILE.exists() or sha256_file(RAW_FILE) != src["sha256"]:
            errors.append("raw file hash does not match the manifest")
    if REPORT_JSON.exists():
        rep = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
        if rep["catalog"]["rows"] != len(rows):
            errors.append("build_report.json row count differs from the CSV")
    else:
        errors.append("build_report.json missing")
    return errors


if __name__ == "__main__":
    errs = validate()
    if errs:
        print(f"INVALID ({len(errs)} problems)")
        for e in errs:
            print("  -", e)
        raise SystemExit(1)
    print("catalogue valid")
