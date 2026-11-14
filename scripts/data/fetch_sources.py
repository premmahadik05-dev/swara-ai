"""Fetch (or verify) the raw source snapshot and write data/sources/MANIFEST.json.

    python scripts/data/fetch_sources.py              # verify the committed copy; download only if it is missing
    python scripts/data/fetch_sources.py --refresh    # re-download from the pinned commit and compare the hash
    python scripts/data/fetch_sources.py --update --ref <commit> --file data/all_2026-09-01.csv --id off_india_2026-09-01

The only network host used is raw.githubusercontent.com. Nothing here calls Open Food Facts directly.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MANIFEST, RAW, RAW_FILE, SOURCE_ID, SOURCES, sha256_file, write_json  # noqa: E402

REPO = "mvark/indiafoodstats"
PINNED_COMMIT = "d3624c4e5b00d2e5aa6d9d3c4b0b24f82a7bbb5a"
PINNED_PATH = "data/all_2026-07-05.csv"
PINNED_SHA256 = "dd54bd7908e6111b1fb9243529e67230d78f24071d95fabc7164a418370fe639"
RETRIEVED_ON = "2026-11-10"


def raw_url(commit: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{REPO}/{commit}/{path}"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "SWARA-AI-data-pipeline/1.0 (+student project)"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        out.write(resp.read())


def count_rows(path: Path) -> tuple[int, list[str]]:
    csv.field_size_limit(10**9)
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        return sum(1 for _ in reader), header


def build_manifest(source_id: str, raw_path: Path, commit: str, repo_path: str, retrieved_on: str) -> dict:
    rows, header = count_rows(raw_path)
    return {
        "schema": 1,
        "sources": [
            {
                "id": source_id,
                "title": "Open Food Facts: products sold in India (cleaned CSV snapshot)",
                "origin": {
                    "name": "Open Food Facts (India database)",
                    "url": "https://in.openfoodfacts.org/",
                    "licence_database": "Open Database License (ODbL) 1.0",
                    "licence_contents": "Database Contents License (DbCL) 1.0",
                    "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
                    "attribution": "Open Food Facts contributors, https://world.openfoodfacts.org/",
                },
                "retrieved_via": {
                    "name": f"GitHub repository {REPO} (a volunteer's cleaned export of the OFF India database)",
                    "repo_url": f"https://github.com/{REPO}",
                    "file_url_pinned": raw_url(commit, repo_path),
                    "commit": commit,
                    "repo_licence": "GNU AGPL-3.0 (see data/sources/indiafoodstats.LICENSE.txt)",
                    "why_this_route": (
                        "The build sandbox's network policy blocks openfoodfacts.org, data.gov.in and Kaggle. "
                        "GitHub raw is reachable, so this republished export was used. Run scripts/data/fetch_sources.py "
                        "on a machine with open internet to pin a newer snapshot."
                    ),
                },
                "retrieved_on": retrieved_on,
                "snapshot_date_from_filename": "2026-07-05",
                "local_file": str(raw_path.relative_to(raw_path.parents[2])).replace("\\", "/"),
                "sha256": sha256_file(raw_path),
                "bytes": raw_path.stat().st_size,
                "rows": rows,
                "fields": header,
                "field_notes": {
                    "code": "Barcode (EAN/UPC) as typed by OFF contributors. Not all are valid.",
                    "product_name": "Serialised list of {lang, text}; many rows are blank.",
                    "brands": "Comma-separated, contributor-typed; casing and accents vary.",
                    "categories": "Free text, partly English tags; blank for more than half of the rows.",
                    "quantity": "Contributor-typed pack size ('250g', '1 l', '6 x 50 g'); blank for most rows.",
                    "nova_group / nutriscore_grade": "OFF-computed where inputs exist; kept for reference only.",
                    "creator / last_modified_t": "OFF contributor id and Unix time of last edit.",
                },
                "limitations": [
                    "Crowdsourced: names, brands and pack sizes can be wrong or out of date.",
                    "Contains NO prices, stock, sales or shop-level data of any kind.",
                    "Over-represents packaged and branded food; loose staples (dal, rice, vegetables) are largely absent.",
                    "More than half of the rows lack a category or a usable pack size and are dropped by build_catalog.py.",
                    "No Gujarati or Hindi product names; those are never invented by this pipeline.",
                    "Popular products are not identifiable: the file has no scan counts, so selection is by completeness, not popularity.",
                ],
            }
        ],
        "not_available_here": [
            {
                "source": "Open Prices (prices.openfoodfacts.org)",
                "reason": "Host blocked by the build sandbox policy. One attempt to reach it through a browser was also blocked, and no further route was tried.",
                "how_to_add": "Run a price-ingest on a machine with internet and put the CSV in data/raw/, then extend build_catalog.py.",
            },
            {
                "source": "Department of Consumer Affairs retail prices (data.gov.in)",
                "reason": "Host blocked by the build sandbox policy; the portal also requires an API key for bulk access.",
                "how_to_add": "Same as above. Commodity-level prices would feed `reference_price`, never a specific branded SKU.",
            },
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-download the pinned file and compare hashes")
    ap.add_argument("--update", action="store_true", help="fetch a different snapshot (needs --ref, --file, --id)")
    ap.add_argument("--ref", default=PINNED_COMMIT)
    ap.add_argument("--file", dest="repo_file", default=PINNED_PATH)
    ap.add_argument("--id", dest="source_id", default=SOURCE_ID)
    args = ap.parse_args()

    if args.update:
        dest = RAW / f"{args.source_id}.csv"
        print(f"downloading {raw_url(args.ref, args.repo_file)}")
        download(raw_url(args.ref, args.repo_file), dest)
        write_json(MANIFEST, build_manifest(args.source_id, dest, args.ref, args.repo_file, dt.date.today().isoformat()))
        print(f"wrote {dest.name} ({sha256_file(dest)[:12]}...) and MANIFEST.json. Update SOURCE_ID/RAW_FILE in common.py, then run build_catalog.py")
        return 0

    if args.refresh or not RAW_FILE.exists():
        print(f"downloading {raw_url(PINNED_COMMIT, PINNED_PATH)}")
        tmp = RAW_FILE.with_suffix(".download")
        download(raw_url(PINNED_COMMIT, PINNED_PATH), tmp)
        if sha256_file(tmp) != PINNED_SHA256:
            tmp.unlink(missing_ok=True)
            print("ERROR: downloaded file does not match the pinned SHA-256; refusing to use it", file=sys.stderr)
            return 2
        tmp.replace(RAW_FILE)

    actual = sha256_file(RAW_FILE)
    if actual != PINNED_SHA256:
        print(f"ERROR: {RAW_FILE.name} sha256 {actual} != pinned {PINNED_SHA256}", file=sys.stderr)
        return 2
    SOURCES.mkdir(parents=True, exist_ok=True)
    write_json(MANIFEST, build_manifest(SOURCE_ID, RAW_FILE, PINNED_COMMIT, PINNED_PATH, RETRIEVED_ON))
    print(f"ok: {RAW_FILE.name} verified ({actual[:12]}...); manifest written to {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
