"""Non-regression: importing real branded products must not change how the existing orders are understood."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import Base, make_engine, make_session_factory
from app.models import CatalogItem
from app.nlu.lexicon import Lexicon
from app.nlu.parser import parse_utterance
from app.seed import seed_catalog, seed_products
from app.services.catalog import load_views
from app.services.catalog_items import import_to_shop, make_aliases

GOLD = Path(__file__).resolve().parents[2] / "eval" / "utterances.jsonl"


@pytest.fixture(scope="module")
def both(tmp_path_factory):
    d = tmp_path_factory.mktemp("branded")
    eng = make_engine(f"sqlite:///{d / 'b.db'}")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as db:
        seed_products(db)
        base = load_views(db)
        seed_catalog(db)
        for it in db.scalars(select(CatalogItem)).all():  # worst case: the shop sells the ENTIRE catalogue
            import_to_shop(db, it.id, 5000, Decimal(10), Decimal(2), None)
        aug = load_views(db)
    eng.dispose()
    return base, aug


def _pred(text, views):
    lex = Lexicon(list(views.values()))
    r = parse_utterance(text, lex)
    return [(views[ln.product_ids[0]].sku if ln.resolved else None, str(ln.qty) if ln.qty is not None else None, ln.unit, len(ln.product_ids))
            for ln in r.lines]


def test_importing_the_whole_catalogue_changes_no_gold_utterance(both):
    base, aug = both
    assert len(aug) > 5000 and len(base) == 65
    lex_b, lex_a = Lexicon(list(base.values())), Lexicon(list(aug.values()))

    def pred(text, lex, views):
        r = parse_utterance(text, lex)
        return [(views[ln.product_ids[0]].sku if ln.resolved else None, str(ln.qty) if ln.qty is not None else None, ln.unit, len(ln.product_ids))
                for ln in r.lines]

    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 288
    changed = [r["text"] for r in rows if pred(r["text"], lex_b, base) != pred(r["text"], lex_a, aug)]
    assert changed == []


def test_chitchat_never_matches_a_product(both):
    _, aug = both
    lex = Lexicon(list(aug.values()))
    for t in ["hello how are you", "thank you very much", "yes please", "ok bhai", "bas itna hi", "cancel the order"]:
        assert all(not ln.resolved for ln in parse_utterance(t, lex).lines), t


def test_branded_phrases_resolve_to_the_branded_item(both):
    """Whatever comes back must be the named brand's own product. When the brand sells several packs the customer did not name,
    several of its packs come back (the dialogue then asks which one); none of another brand's products may."""
    _, aug = both
    lex = Lexicon(list(aug.values()))
    for text, brand in [("ek amul butter", "Amul Butter"), ("do tata salt", "Tata Salt"), ("મને એક Amul butter જોઈએ", "Amul Butter")]:
        r = parse_utterance(text, lex)
        assert r.lines and r.lines[0].product_ids, text
        assert all(aug[i].name_en.startswith(brand) for i in r.lines[0].product_ids), (text, [aug[i].name_en for i in r.lines[0].product_ids])


def test_a_brand_sold_in_several_packs_asks_which_pack_instead_of_picking_the_first_imported(both):
    """Regression (2.5.0): a pack-less alias used to belong only to the pack imported first, so "amul butter" quietly became that pack
    whatever the shop also stocked. Same-brand packs now share the alias, the parse is ambiguous and the dialogue asks."""
    _, aug = both
    lex = Lexicon(list(aug.values()))
    r = parse_utterance("ek amul butter", lex)
    ids = r.lines[0].product_ids
    assert len(ids) >= 2 and not r.lines[0].resolved
    assert all(aug[i].name_en.startswith("Amul Butter") for i in ids)


@pytest.mark.parametrize("brand,name,expected_has,expected_not", [
    ("Amul", "Amul Butter", "amul butter", {"butter", "amul"}),
    ("Yu", "Yu 100% coconut water", "yu coconut water", {"yu"}),
    ("Parle", "Parle-G Original Gluco Biscuits", "parle g", {"biscuits", "gluco"}),
    ("", "Paneer", None, {"paneer"}),
])
def test_alias_generation_rules(brand, name, expected_has, expected_not):
    a = make_aliases(brand, name)
    if expected_has:
        assert expected_has in a
    assert not expected_not & set(a)  # never a bare generic word or a too-short brand


def test_aliases_skip_ones_already_taken():
    assert "amul butter" not in make_aliases("Amul", "Amul Butter", taken={"amul butter"})
