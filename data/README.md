# data/

Everything in here is documented in [docs/DATA.md](../docs/DATA.md). In short:

| Folder | Class | Contents |
|---|---|---|
| `raw/` | **sourced** | `off_india_2026-07-05.csv`: the Open Food Facts India snapshot exactly as retrieved (sha256 in `sources/MANIFEST.json`). Never edited |
| `sources/` | provenance | `MANIFEST.json` (source, URL, licence, retrieval date, fields, limitations, pinned commit, hash) and the licence text of the repository it came through |
| `processed/` | **transformed** | `catalog_off_india.csv` (5,325 products; cleaned columns beside the `*_raw` originals, plus the rules applied to each row) and `build_report.json` (rows kept and rejected, with reasons) |
| `test/` | **synthetic** sentences about **sourced** products | Held-out evaluation set, see `test/README.md` |

Licence of the data: Open Food Facts, ODbL 1.0 (database) and DbCL 1.0 (contents). Attribution: Open Food Facts contributors, https://world.openfoodfacts.org/. There are **no prices** in any file here; the source has none.

Rebuild or verify: `python scripts/data/update_catalog.py` (verify hash, rebuild, validate, show what changed).
