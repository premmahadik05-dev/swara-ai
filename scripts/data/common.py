"""Shared helpers for the data pipeline. Standard library only, so it runs without the app's virtualenv."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
TEST = DATA / "test"
SOURCES = DATA / "sources"

SOURCE_ID = "off_india_2026-07-05"
RAW_FILE = RAW / "off_india_2026-07-05.csv"
CATALOG_CSV = PROCESSED / "catalog_off_india.csv"
REPORT_JSON = PROCESSED / "build_report.json"
MANIFEST = SOURCES / "MANIFEST.json"

# The only values allowed in the `provenance` column of any record this project ships.
PROVENANCE = ("sourced", "transformed", "curated", "synthetic")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ean13_valid(code: str) -> bool:
    """GS1 check digit for a 13-digit EAN."""
    if not re.fullmatch(r"\d{13}", code):
        return False
    digits = [int(c) for c in code]
    total = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == digits[12]


def fold(text: str) -> str:
    """Accent-fold + lowercase + collapse non-alphanumerics, for grouping keys (not for display)."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


# ---- OFF product_name cell: "{'lang': 'main', 'text': 'X'}; {'lang': 'en', 'text': 'Y'}" ---------------------------
_NAME_PART = re.compile(r"\{\s*'lang':\s*'([^']*)',\s*'text':\s*(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")\s*\}")


def parse_name_cell(cell: str) -> dict[str, str]:
    """Return {lang: text}. A plain string cell is treated as the 'main' text."""
    cell = (cell or "").strip()
    if not cell:
        return {}
    found = _NAME_PART.findall(cell)
    if not found:
        return {"main": cell}
    out: dict[str, str] = {}
    for lang, a, b in found:
        text = (a or b).replace("\\'", "'").replace('\\"', '"').strip()
        if text and lang not in out:
            out[lang] = text
    return out


def pick_name(parts: dict[str, str]) -> tuple[str, str]:
    """Prefer the English text, else the 'main' text, else any. Returns (text, rule)."""
    for lang in ("en", "main"):
        if parts.get(lang):
            return parts[lang], f"name:{lang}"
    for lang, text in parts.items():
        return text, f"name:{lang}"
    return "", "name:none"


_SMALL = {"and", "of", "with", "in", "the", "for", "a", "an", "&", "n"}


def tidy_name(text: str) -> tuple[str, bool]:
    """Collapse whitespace; title-case only when the whole name is ALL CAPS or all lower case."""
    t = re.sub(r"\s+", " ", text).strip(" -,;:|")
    if not t:
        return "", False
    letters = [c for c in t if c.isalpha()]
    if letters and (all(c.isupper() for c in letters) or all(c.islower() for c in letters)):
        words = t.split(" ")
        t2 = " ".join(w if (i and w.lower() in _SMALL) else (w[:1].upper() + w[1:].lower()) for i, w in enumerate(words))
        return t2, t2 != t
    return t, False


# ---- pack size ------------------------------------------------------------------------------------------------------
_UNITS = {
    "g": ("kg", Decimal("0.001")), "gm": ("kg", Decimal("0.001")), "gms": ("kg", Decimal("0.001")),
    "gr": ("kg", Decimal("0.001")), "gram": ("kg", Decimal("0.001")), "grams": ("kg", Decimal("0.001")),
    "kg": ("kg", Decimal(1)), "kgs": ("kg", Decimal(1)),
    "ml": ("l", Decimal("0.001")), "l": ("l", Decimal(1)), "ltr": ("l", Decimal(1)), "litre": ("l", Decimal(1)),
    "liter": ("l", Decimal(1)), "litres": ("l", Decimal(1)), "liters": ("l", Decimal(1)),
    "pc": ("pc", Decimal(1)), "pcs": ("pc", Decimal(1)), "piece": ("pc", Decimal(1)), "pieces": ("pc", Decimal(1)),
}
_QTY = re.compile(r"^\s*(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)\s*$")


def parse_quantity(raw: str) -> tuple[Decimal, str, str] | None:
    """'250g' -> (0.250, 'kg', 'qty:g->kg').  Returns None when the text is not a clear weight/volume/count.

    A bare number ('500') is rejected on purpose: it could be grams, millilitres or a count.
    A multipack ('6 x 50 g') is multiplied out.
    """
    m = _QTY.match((raw or "").strip().lower())
    if not m:
        return None
    mult, num, unit = m.groups()
    if unit not in _UNITS:
        return None
    base_unit, factor = _UNITS[unit]
    try:
        value = Decimal(num.replace(",", ".")) * factor * (Decimal(mult) if mult else 1)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    if base_unit == "kg" and not (Decimal("0.005") <= value <= 50):
        return None
    if base_unit == "l" and not (Decimal("0.005") <= value <= 50):
        return None
    if base_unit == "pc" and not (1 <= value <= 500):
        return None
    rule = f"qty:{unit}->{base_unit}" + (":multipack" if mult else "")
    return value.normalize() if value != value.to_integral() else value.quantize(Decimal(1)), base_unit, rule


def pack_label(value: Decimal, unit: str) -> str:
    """Human label for a pack: 0.25 kg -> '250 g', 1 l -> '1 l', 6 pc -> '6 pcs'."""
    if unit == "kg":
        return f"{(value * 1000).normalize():f} g" if value < 1 else f"{value.normalize():f} kg"
    if unit == "l":
        return f"{(value * 1000).normalize():f} ml" if value < 1 else f"{value.normalize():f} l"
    n = int(value)
    return f"{n} pc" if n == 1 else f"{n} pcs"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
