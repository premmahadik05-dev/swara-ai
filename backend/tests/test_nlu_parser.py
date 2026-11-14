"""Multilingual parsing: Gujarati, Hindi, English, Hinglish and mixed utterances (typed transcripts)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.nlu.normalize import dominant_script, normalize_text
from app.nlu.parser import parse_utterance
from app.nlu.translit import skeleton

CASES = [
    # --- the three kinds of sentence the brief asks for
    ("Bhai mujhe 2 kilo chawal aur 1 litre doodh chahiye", "hinglish", [("RICE-REGULAR", "2", "kg"), ("MILK", "1", "l")]),
    ("મને બે કિલો ખાંડ અને એક લિટર દૂધ જોઈએ છે", "gu", [("SUGAR", "2", "kg"), ("MILK", "1", "l")]),
    ("भैया ढाई किलो चीनी और आधा किलो चायपत्ती दे दो", "hi", [("SUGAR", "2.5", "kg"), ("TEA", "0.5", "kg")]),
    # --- English
    ("2 kilo sugar and 1 liter milk please", "en", [("SUGAR", "2", "kg"), ("MILK", "1", "l")]),
    ("I want two kg rice and one litre oil", "en", [("RICE-REGULAR", "2", "kg"), ("OIL-GROUNDNUT", "1", "l")]),
    ("one and a half kilo onion", "en", [("ONION", "1.5", "kg")]),
    # --- Hinglish number grammar
    ("dedh kilo atta", "hinglish", [("ATTA", "1.5", "kg")]),
    ("dhai kilo chini", "hinglish", [("SUGAR", "2.5", "kg")]),
    ("sava kilo namak", "hinglish", [("SALT", "1.25", "kg")]),
    ("saade teen kilo aloo", "hinglish", [("POTATO", "3.5", "kg")]),
    ("paune do kilo pyaz", "hinglish", [("ONION", "1.75", "kg")]),
    ("aadha kilo tamatar", "hinglish", [("TOMATO", "0.5", "kg")]),
    ("pachas gram jeera", None, [("CUMIN", "50", "g")]),
    ("do dozen eggs", None, [("EGGS", "2", "dozen")]),
    ("ek packet maggi", "hinglish", [("NOODLES", "1", "pack")]),
    ("500 gram paneer", None, [("PANEER", "500", "g")]),
    ("250 gm sugar", None, [("SUGAR", "250", "g")]),
    # --- Gujarati
    ("અડધો કિલો બટાકા", "gu", [("POTATO", "0.5", "kg")]),
    ("દોઢ કિલો ડુંગળી", "gu", [("ONION", "1.5", "kg")]),
    ("અઢી કિલો લોટ આપો", "gu", [("ATTA", "2.5", "kg")]),
    ("ત્રણ કિલો ટામેટા અને બે કિલો બટાકા", "gu", [("TOMATO", "3", "kg"), ("POTATO", "2", "kg")]),
    # --- Gujarati in Latin script (typed)
    ("mane 2 kilo batata ane 1 kilo dungri aapo", "gu", [("POTATO", "2", "kg"), ("ONION", "1", "kg")]),
    # --- Gujarati-English code mix
    ("મને 2 kg sugar અને 1 litre milk જોઈએ", "gu", [("SUGAR", "2", "kg"), ("MILK", "1", "l")]),
    # --- Devanagari / Gujarati digits
    ("२ किलो चावल", "hi", [("RICE-REGULAR", "2", "kg")]),
    ("૩ કિલો ખાંડ", "gu", [("SUGAR", "3", "kg")]),
    # --- separators and no conjunction
    ("2 kilo sugar, 1 kilo salt, 1 litre milk", "en", [("SUGAR", "2", "kg"), ("SALT", "1", "kg"), ("MILK", "1", "l")]),
    ("do kilo chini do kilo namak", "hinglish", [("SUGAR", "2", "kg"), ("SALT", "2", "kg")]),
    # --- product-first ordering
    ("chawal 3 kilo aur doodh 2 litre", "hinglish", [("RICE-REGULAR", "3", "kg"), ("MILK", "2", "l")]),
]


@pytest.mark.parametrize("text,language,expected", CASES, ids=[c[0][:40] for c in CASES])
def test_parse_cases(text, language, expected, lexicon, sku_by_id):
    r = parse_utterance(text, lexicon)
    if language is not None:  # None = no language-specific word, only the product parse is asserted
        assert r.language == language
    got = [(sku_by_id[ln.product_ids[0]], ln.qty, ln.unit) for ln in r.lines if ln.resolved]
    want = [(sku, Decimal(q), u) for sku, q, u in expected]
    assert got == want


def test_unknown_product_is_reported_not_guessed(lexicon):
    r = parse_utterance("2 kilo dragonfruit", lexicon)
    assert not any(ln.resolved for ln in r.lines)
    assert any(ln.unknown_term for ln in r.lines)


def test_generic_word_with_one_shop_default_is_assumed(lexicon, sku_by_id):
    r = parse_utterance("ek litre tel", lexicon)
    assert [sku_by_id[ln.product_ids[0]] for ln in r.lines] == ["OIL-GROUNDNUT"]
    assert r.lines[0].assumed_default is True and r.lines[0].resolved


def test_generic_word_with_several_owners_is_not_guessed(lexicon, sku_by_id):
    r = parse_utterance("ek kilo dal", lexicon)
    ln = r.lines[0]
    assert not ln.resolved
    assert {sku_by_id[i] for i in ln.product_ids} == {"DAL-TOOR", "DAL-MOONG", "DAL-CHANA", "DAL-URAD"}


def test_spelling_variants_resolve_to_same_product(lexicon, sku_by_id):
    seen = set()
    for w in ["doodh", "dudh", "dūdh", "milk", "દૂધ", "दूध", "dood", "DOODH"]:
        r = parse_utterance(f"1 litre {w}", lexicon)
        seen.add(tuple(sku_by_id[i] for ln in r.lines for i in ln.product_ids))
    assert seen == {("MILK",)}


def test_fuzzy_match_handles_asr_style_misspelling(lexicon, sku_by_id):
    r = parse_utterance("do kilo shakkar", lexicon)
    assert [sku_by_id[ln.product_ids[0]] for ln in r.lines if ln.resolved] == ["SUGAR"]


@pytest.mark.parametrize("text,intent", [
    ("hello", "greeting"), ("haan", "confirm"), ("nahi", "deny"), ("bas itna hi", "done"), ("cancel kar do", "cancel"),
    ("નમસ્તે", "greeting"), ("બસ", "done"), ("હા", "confirm"),
])
def test_intents(text, intent, lexicon):
    assert parse_utterance(text, lexicon, cart_has_items=True).intent == intent


def test_itna_hi_is_not_a_greeting(lexicon):
    assert parse_utterance("itna hi", lexicon, cart_has_items=True).intent != "greeting"


def test_script_detection():
    assert dominant_script("મને દૂધ જોઈએ") == "gu"
    assert dominant_script("मुझे दूध चाहिए") == "hi"
    assert dominant_script("I need milk") == "latin"


def test_normalisation_digits_and_zero_width():
    assert normalize_text("૨ કિલો") == "2 કિલો"
    assert normalize_text("२​ किलो") == "2 किलो"


def test_cross_script_skeleton_equivalence():
    assert skeleton("દૂધ") == skeleton("दूध") == skeleton("doodh") == skeleton("dudh")
    assert skeleton("ખાંડ") == skeleton("खांड")


def test_no_crash_on_hostile_input(lexicon):
    for t in ["", "   ", "💥💥", "a" * 600, "૧૨૩૪૫૬૭૮૯૦" * 20, "'; DROP TABLE products;--", "\x00\x01 2 kilo", "kilo kilo kilo kilo"]:
        r = parse_utterance(t, lexicon)
        assert r.intent in {"add", "unknown", "greeting", "confirm", "deny", "done", "cancel", "remove", "set", "query"}
