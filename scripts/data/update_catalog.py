"""One command to rebuild and re-check the catalogue, with a diff against the previous build.

    python scripts/data/update_catalog.py             # verify raw -> build -> validate -> print what changed
    python scripts/data/update_catalog.py --no-fetch  # skip the hash verification step

To move to a newer snapshot first run `fetch_sources.py --update ...` (see its --help), then this script.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import CATALOG_CSV  # noqa: E402


def eans() -> dict[str, str]:
    if not CATALOG_CSV.exists():
        return {}
    with open(CATALOG_CSV, newline="", encoding="utf-8") as fh:
        return {r["ean"]: r["name"] for r in csv.DictReader(fh)}


def run(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(HERE / script), *args], check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()
    before = eans()
    if not args.no_fetch:
        run("fetch_sources.py")
    run("build_catalog.py")
    run("validate_catalog.py")
    after = eans()
    added, removed = set(after) - set(before), set(before) - set(after)
    print(f"\nchange vs previous build: {len(added)} added, {len(removed)} removed, {len(after)} total")
    for e in sorted(added)[:10]:
        print("  +", e, after[e])
    for e in sorted(removed)[:10]:
        print("  -", e, before[e])
    print("next: re-seed the app database (scripts/seed_db.py --reset) to load the new catalogue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
