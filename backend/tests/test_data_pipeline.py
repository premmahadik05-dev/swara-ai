"""The data pipeline (scripts/data) and the shipped catalogue files."""
from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))

import build_catalog as bc  # noqa: E402
import common as cm  # noqa: E402
import validate_catalog as vc  # noqa: E402


def test_ean13_check_digit():
    assert cm.ean13_valid("8901030404603")
    assert not cm.ean13_valid("8901030404604")  # wrong check digit
    assert not cm.ean13_valid("51010814")  # EAN-8 is not accepted into the catalogue
    assert not cm.ean13_valid("89010304046O3")


def test_name_cell_prefers_english_and_handles_plain_text():
    cell = "{'lang': 'main', 'text': 'Javitri'}; {'lang': 'en', 'text': 'Mace (Javitri)'}"
    assert cm.pick_name(cm.parse_name_cell(cell)) == ("Mace (Javitri)", "name:en")
    assert cm.pick_name(cm.parse_name_cell("{'lang': 'main', 'text': 'Poha'}")) == ("Poha", "name:main")
    assert cm.pick_name(cm.parse_name_cell("Plain name")) == ("Plain name", "name:main")
    assert cm.parse_name_cell("") == {}


@pytest.mark.parametrize("raw,value,unit", [
    ("250g", "0.25", "kg"), ("1 kg", "1", "kg"), ("500 ml", "0.5", "l"), ("1 ltr", "1", "l"),
    ("200 GM", "0.2", "kg"), ("6 x 50 g", "0.3", "kg"), ("12 pcs", "12", "pc"), ("1,5 l", "1.5", "l"),
])
def test_quantity_parsing(raw, value, unit):
    v, u, _rule = cm.parse_quantity(raw)
    assert (v, u) == (Decimal(value), unit)


@pytest.mark.parametrize("raw", ["", "500", "abc", "0 g", "9999 kg", "2 oz", "12 tablets", "1 x"])
def test_quantity_rejects_ambiguous_or_implausible(raw):
    assert cm.parse_quantity(raw) is None  # a bare number could be g, ml or a count: never guessed


def test_pack_labels():
    assert cm.pack_label(Decimal("0.25"), "kg") == "250 g"
    assert cm.pack_label(Decimal("1"), "kg") == "1 kg"
    assert cm.pack_label(Decimal("0.5"), "l") == "500 ml"
    assert cm.pack_label(Decimal("6"), "pc") == "6 pcs"


@pytest.mark.parametrize("categories,name,expected", [
    ("Salts", "Tata Salt", "Sugar, Salt & Tea"),
    ("Dairies, Ghee", "Amul Cow Ghee", "Oil & Ghee"),
    ("Snacks, Biscuits", "Parle-G Gold Biscuits", "Biscuits & Sweets"),
    ("", "Maggi Masala Noodles", "Breakfast & Noodles"),
    ("Plant-based foods", "Chilli Powder", "Spices"),
    ("", "Peanut Butter Creamy", "Sauces & Spreads"),
    ("Peanut butters", "Saffola Creamy", "Sauces & Spreads"),
    ("Hot beverages", "Blue Tokai Coffee", "Beverages"),
])
def test_category_rules(categories, name, expected):
    assert bc.classify(categories, name)[0] == expected


def test_category_rules_exclude_non_kirana_items():
    assert bc.classify("Dietary supplements", "Whey Protein") is None
    assert bc.classify("Non food products", "Steel Bottle") is None
    assert bc.classify("", "Completely unknown thing") is None


def test_split_is_deterministic_and_about_ten_percent():
    assert bc.split_of("8901030404603") == bc.split_of("8901030404603")
    eans = [f"89010304{i:05d}" for i in range(2000)]
    test_share = sum(bc.split_of(e) == "test" for e in eans) / len(eans)
    assert 0.07 < test_share < 0.13


def test_shipped_catalogue_passes_validation():
    assert vc.validate() == []


def test_catalogue_has_no_prices_and_labels_provenance():
    with open(cm.CATALOG_CSV, newline="", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        header = rdr.fieldnames
        rows = list(rdr)
    assert not {"price", "price_paise", "mrp"} & set(header)
    assert {r["provenance"] for r in rows} == {"transformed"}
    assert len(rows) > 4000
    assert 0.07 < sum(r["split"] == "test" for r in rows) / len(rows) < 0.13
    assert all(r["name_raw"] for r in rows)  # the sourced value is kept beside the cleaned one


def test_validator_catches_a_corrupted_row(tmp_path, monkeypatch):
    bad = tmp_path / "c.csv"
    with open(cm.CATALOG_CSV, newline="", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        rows = list(rdr)
        header = rdr.fieldnames
    rows[0]["ean"] = "1234567890123"
    rows[1]["category"] = "Not a category"
    with open(bad, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    monkeypatch.setattr(vc, "CATALOG_CSV", bad)
    errs = vc.validate()
    assert any("EAN-13" in e for e in errs) and any("taxonomy" in e for e in errs)


def test_manifest_matches_raw_file():
    import json
    m = json.loads(cm.MANIFEST.read_text(encoding="utf-8"))["sources"][0]
    assert m["sha256"] == cm.sha256_file(cm.RAW_FILE)
    assert m["origin"]["licence_database"].startswith("Open Database License")
    assert "prices" in " ".join(m["limitations"]).lower()
