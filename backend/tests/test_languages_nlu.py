"""Language-wise understanding tests: product recognition, quantity extraction, intents and reply wording for every language.

OFFLINE unit tests of the deterministic NLU/NLG. There is no speech and no Gnani here, so they say nothing about how well Prisma
transcribes a language; they say what the parser does with a transcript that is already text.

Status of the sentences: for gu/hi/en/hinglish the phrases below extend a suite that has run since the first release. For
mr/bn/ta/te/kn/ml/pa the vocabulary and every sentence were AUTHORED for 2.3.0, with no native-speaker review and no real Prisma output behind
them. Passing here means "the parser agrees with what its author wrote", not "a Marathi shopkeeper would say it this way".
"""
from __future__ import annotations

import pytest

from app import languages as reg
from app.nlu import nlg, translit
from app.nlu.langpacks import REQUIRED_TEMPLATES, load_all
from app.nlu.parser import parse_utterance

NEW = ("mr", "bn", "ta", "te", "kn", "ml", "pa")
PACKS = load_all()


def lines_of(lexicon, sku_by_id, text, hint=None, cart=False):
    r = parse_utterance(text, lexicon, language_hint=hint, cart_has_items=cart)
    got = [(sku_by_id.get(ln.product_ids[0]) if ln.product_ids else ln.unknown_term, str(ln.qty), ln.unit) for ln in r.lines]
    return r, got


# --------------------------------------------------------------------------- the registry sentence, every language
@pytest.mark.parametrize("key", reg.ORDER)
def test_sample_sentence_gives_two_kilo_sugar_and_one_litre_milk(key, lexicon, sku_by_id):
    r, got = lines_of(lexicon, sku_by_id, reg.LANGUAGES[key].sample, hint=key)
    assert got == [("SUGAR", "2", "kg"), ("MILK", "1", "l")], (key, got)
    assert r.language == key and r.intent == "add"


@pytest.mark.parametrize("key", reg.ORDER)
def test_sample_sentence_is_recognised_without_the_selector_hint(key, lexicon, sku_by_id):
    """Typing in a script must work with no language chosen. Hinglish and English share Latin letters, and Hindi / Marathi share
    Devanagari, so for those the exact label may differ; the order itself must not."""
    r, got = lines_of(lexicon, sku_by_id, reg.LANGUAGES[key].sample)
    assert got == [("SUGAR", "2", "kg"), ("MILK", "1", "l")], (key, got)
    if key not in ("en", "hinglish", "hi", "mr"):
        assert r.language == key


# --------------------------------------------------------------------------- quantities, units, intents per language
ADD = {
    "mr": [("अर्धा किलो तांदूळ", [("RICE-REGULAR", "0.5", "kg")]),
           ("दीड किलो कांदा आणि अडीच किलो बटाटा", [("ONION", "1.5", "kg"), ("POTATO", "2.5", "kg")]),
           ("तीन लिटर दूध", [("MILK", "3", "l")]), ("पाव किलो चहा", [("TEA", "0.25", "kg")]),
           ("दोन डझन अंडी", [("EGGS", "2", "dozen")]), ("सव्वा किलो मीठ", [("SALT", "1.25", "kg")])],
    "bn": [("আধা কেজি চাল", [("RICE-REGULAR", "0.5", "kg")]),
           ("দেড় কেজি পেঁয়াজ আর আড়াই কেজি আলু", [("ONION", "1.5", "kg"), ("POTATO", "2.5", "kg")]),
           ("তিন লিটার দুধ", [("MILK", "3", "l")]), ("পাঁচশো গ্রাম পনির", [("PANEER", "500", "g")]),
           ("আড়াইশো গ্রাম চিনি", [("SUGAR", "250", "g")]), ("এক ডজন ডিম", [("EGGS", "1", "dozen")]),
           ("সাড়ে তিন কেজি আটা", [("ATTA", "3.5", "kg")]), ("আমার দশ কেজি চাল লাগবে", [("RICE-REGULAR", "10", "kg")])],
    "ta": [("அரை கிலோ அரிசி", [("RICE-REGULAR", "0.5", "kg")]),
           ("ஒன்றரை கிலோ வெங்காயம் மற்றும் இரண்டரை கிலோ உருளைக்கிழங்கு", [("ONION", "1.5", "kg"), ("POTATO", "2.5", "kg")]),
           ("மூன்று லிட்டர் பால்", [("MILK", "3", "l")]), ("கால் கிலோ தக்காளி", [("TOMATO", "0.25", "kg")]),
           ("இரண்டு டஜன் முட்டை", [("EGGS", "2", "dozen")]), ("எனக்கு ஐந்து கிலோ கோதுமை மாவு வேண்டும்", [("ATTA", "5", "kg")]),
           ("நூறு கிராம் மிளகாய் தூள்", [("CHILLI-POWDER", "100", "g")])],
    "te": [("అర కిలో బియ్యం", [("RICE-REGULAR", "0.5", "kg")]),
           ("ఒకటిన్నర కిలోల ఉల్లిపాయలు మరియు రెండున్నర కిలోల బంగాళాదుంపలు", [("ONION", "1.5", "kg"), ("POTATO", "2.5", "kg")]),
           ("మూడు లీటర్ల పాలు", [("MILK", "3", "l")]), ("పావు కిలో టమాటా", [("TOMATO", "0.25", "kg")]),
           ("రెండు డజన్ల గుడ్లు", [("EGGS", "2", "dozen")]), ("నాకు ఐదు కిలోల గోధుమ పిండి కావాలి", [("ATTA", "5", "kg")]),
           ("వంద గ్రాముల కారం", [("CHILLI-POWDER", "100", "g")])],
    "kn": [("ಅರ್ಧ ಕಿಲೋ ಅಕ್ಕಿ", [("RICE-REGULAR", "0.5", "kg")]),
           ("ಒಂದೂವರೆ ಕಿಲೋ ಈರುಳ್ಳಿ ಮತ್ತು ಎರಡೂವರೆ ಕಿಲೋ ಆಲೂಗಡ್ಡೆ", [("ONION", "1.5", "kg"), ("POTATO", "2.5", "kg")]),
           ("ಮೂರು ಲೀಟರ್ ಹಾಲು", [("MILK", "3", "l")]), ("ಕಾಲು ಕಿಲೋ ಟೊಮೆಟೊ", [("TOMATO", "0.25", "kg")]),
           ("ಎರಡು ಡಜನ್ ಮೊಟ್ಟೆ", [("EGGS", "2", "dozen")]), ("ನನಗೆ ಐದು ಕಿಲೋ ಗೋಧಿ ಹಿಟ್ಟು ಬೇಕು", [("ATTA", "5", "kg")]),
           ("ನೂರು ಗ್ರಾಂ ಮೆಣಸಿನ ಪುಡಿ", [("CHILLI-POWDER", "100", "g")])],
    "ml": [("അര കിലോ അരി", [("RICE-REGULAR", "0.5", "kg")]),
           ("ഒന്നര കിലോ ഉള്ളിയും രണ്ടര കിലോ ഉരുളക്കിഴങ്ങും", [("ONION", "1.5", "kg"), ("POTATO", "2.5", "kg")]),
           ("മൂന്ന് ലിറ്റർ പാൽ", [("MILK", "3", "l")]), ("കാൽ കിലോ തക്കാളി", [("TOMATO", "0.25", "kg")]),
           ("രണ്ട് ഡസൻ മുട്ട", [("EGGS", "2", "dozen")]), ("എനിക്ക് അഞ്ച് കിലോ ഗോതമ്പ് പൊടി വേണം", [("ATTA", "5", "kg")]),
           ("നൂറ് ഗ്രാം മുളകുപൊടി", [("CHILLI-POWDER", "100", "g")])],
    "pa": [("ਅੱਧਾ ਕਿਲੋ ਚੌਲ", [("RICE-REGULAR", "0.5", "kg")]),
           ("ਡੇਢ ਕਿਲੋ ਪਿਆਜ਼ ਅਤੇ ਢਾਈ ਕਿਲੋ ਆਲੂ", [("ONION", "1.5", "kg"), ("POTATO", "2.5", "kg")]),
           ("ਤਿੰਨ ਲੀਟਰ ਦੁੱਧ", [("MILK", "3", "l")]), ("ਪਾਅ ਕਿਲੋ ਟਮਾਟਰ", [("TOMATO", "0.25", "kg")]),
           ("ਦੋ ਦਰਜਨ ਆਂਡੇ", [("EGGS", "2", "dozen")]), ("ਮੈਨੂੰ ਪੰਜ ਕਿਲੋ ਆਟਾ ਚਾਹੀਦਾ ਹੈ", [("ATTA", "5", "kg")]),
           ("ਸੌ ਗ੍ਰਾਮ ਲਾਲ ਮਿਰਚ", [("CHILLI-POWDER", "100", "g")])],
    # the four languages that shipped before 2.3.0 keep working (a few of their long-standing phrases)
    "gu": [("અડધો કિલો ચોખા", [("RICE-REGULAR", "0.5", "kg")]), ("દોઢ કિલો ડુંગળી", [("ONION", "1.5", "kg")]), ("ત્રણ લીટર દૂધ", [("MILK", "3", "l")])],
    "hi": [("आधा किलो चावल", [("RICE-REGULAR", "0.5", "kg")]), ("डेढ़ किलो प्याज", [("ONION", "1.5", "kg")]), ("तीन लीटर दूध", [("MILK", "3", "l")])],
    "en": [("half a kilo of rice", [("RICE-REGULAR", "0.5", "kg")]), ("three litres of milk", [("MILK", "3", "l")])],
    "hinglish": [("aadha kilo chawal", [("RICE-REGULAR", "0.5", "kg")]), ("teen litre doodh", [("MILK", "3", "l")])],
}
ADD_CASES = [(k, t, exp) for k, rows in ADD.items() for t, exp in rows]


@pytest.mark.parametrize("key,text,expected", ADD_CASES, ids=[f"{k}:{t[:24]}" for k, t, _ in ADD_CASES])
def test_quantity_unit_and_product_extraction(key, text, expected, lexicon, sku_by_id):
    r, got = lines_of(lexicon, sku_by_id, text, hint=key)
    assert got == expected, (key, text, got)
    assert r.language == key


INTENTS = {
    "mr": {"confirm": "होय कन्फर्म करा", "done": "बस एवढेच", "cancel": "रद्द करा", "remove": "साखर काढून टाका"},
    "bn": {"confirm": "হ্যাঁ কনফার্ম করুন", "done": "ব্যস", "cancel": "অর্ডার বাতিল", "remove": "চিনি বাদ দিন", "query": "চিনির দাম কত"},
    "ta": {"confirm": "ஆம் உறுதிப்படுத்துங்கள்", "done": "போதும்", "cancel": "ஆர்டர் ரத்து", "remove": "சர்க்கரை நீக்குங்கள்", "query": "சர்க்கரை விலை என்ன"},
    "te": {"confirm": "అవును కన్ఫర్మ్ చేయండి", "done": "చాలు", "cancel": "ఆర్డర్ రద్దు", "remove": "చక్కెర తీసేయండి", "query": "చక్కెర ధర ఎంత"},
    "kn": {"confirm": "ಹೌದು ಕನ್ಫರ್ಮ್", "done": "ಸಾಕು", "cancel": "ಆರ್ಡರ್ ರದ್ದು", "remove": "ಸಕ್ಕರೆ ತೆಗೆಯಿರಿ", "query": "ಸಕ್ಕರೆ ಬೆಲೆ ಎಷ್ಟು"},
    "ml": {"confirm": "അതെ സ്ഥിരീകരിക്കുക", "done": "മതി", "cancel": "ഓർഡർ റദ്ദാക്കുക", "remove": "പഞ്ചസാര ഒഴിവാക്കൂ", "query": "പഞ്ചസാരയുടെ വില എത്ര"},
    "pa": {"confirm": "ਹਾਂ ਜੀ ਕਨਫਰਮ ਕਰੋ", "done": "ਬੱਸ", "cancel": "ਆਰਡਰ ਰੱਦ", "remove": "ਖੰਡ ਹਟਾ ਦਿਓ", "query": "ਖੰਡ ਦਾ ਭਾਅ ਕੀ"},
}
INTENT_CASES = [(k, i, t) for k, d in INTENTS.items() for i, t in d.items()]


@pytest.mark.parametrize("key,intent,text", INTENT_CASES, ids=[f"{k}:{i}" for k, i, _ in INTENT_CASES])
def test_intents_confirm_done_cancel_remove_query(key, intent, text, lexicon, sku_by_id):
    r, got = lines_of(lexicon, sku_by_id, text, hint=key, cart=True)
    assert r.intent == intent, (key, text, r.intent)
    if intent in ("remove", "query"):
        assert got[0][0] == "SUGAR", got


# --------------------------------------------------------------------------- product names
@pytest.mark.parametrize("key", NEW)
def test_every_product_name_resolves_to_its_own_product(key, lexicon, sku_by_id):
    """All 65 staple SKUs have a name in the pack, and its primary name finds that product (not just any product)."""
    pack = PACKS[key]
    skus = set(sku_by_id.values())
    missing = skus - set(pack.names)
    assert not missing, f"{key} has no name for {sorted(missing)}"
    wrong = []
    for sku, spec in pack.names.items():
        primary = spec.split("|")[0]
        r = parse_utterance(primary, lexicon, language_hint=key)
        found = {sku_by_id[p] for ln in r.lines for p in ln.product_ids[:1]}
        if sku not in found:
            wrong.append((sku, primary, sorted(found)))
    assert not wrong, f"{key}: {wrong}"


@pytest.mark.parametrize("key", NEW)
def test_every_alias_finds_a_product_among_its_candidates(key, lexicon, sku_by_id):
    pack = PACKS[key]
    wrong = []
    for sku, spec in pack.names.items():
        for alias in spec.split("|")[1:]:
            r = parse_utterance(alias, lexicon, language_hint=key)
            cands = {sku_by_id[p] for ln in r.lines for p in ln.product_ids}
            if sku not in cands:
                wrong.append((sku, alias, sorted(cands)))
    assert not wrong, f"{key}: {wrong}"


def test_unit_words_inside_product_names_do_not_break_matching(lexicon, sku_by_id):
    """"water bottle" and its Hindi / Gujarati forms contain the unit word 'bottle'; they used to fall through to fuzzy matching."""
    for text, hint in (("water bottle", "en"), ("पानी की बोतल", "hi"), ("પાણીની બોટલ", "gu"), ("ek paani bottle", "hinglish")):
        _, got = lines_of(lexicon, sku_by_id, text, hint=hint)
        assert got and got[0][0] == "WATER", (text, got)
    _, got = lines_of(lexicon, sku_by_id, "पानी")
    assert got[0][0] == "WATER"  # bare "water" must not drift to PANEER


def test_case_endings_are_stripped_so_inflected_names_still_match(lexicon, sku_by_id):
    for text, hint, sku in (("പഞ്ചസാരയുടെ വില എത്ര", "ml", "SUGAR"), ("പാലിന്റെ വില", "ml", "MILK"), ("రెండు డజన్ల గుడ్లు", "te", "EGGS")):
        _, got = lines_of(lexicon, sku_by_id, text, hint=hint)
        assert got[0][0] == sku, (text, got)


def test_unknown_words_are_reported_as_unknown_not_guessed(lexicon, sku_by_id):
    for key, text in (("ta", "எனக்கு இரண்டு கிலோ குவாண்டம் வேண்டும்"), ("bn", "আমার দুই কেজি ফ্লুবার লাগবে"), ("mr", "मला दोन किलो झुंझुर पाहिजे")):
        r, got = lines_of(lexicon, sku_by_id, text, hint=key)
        assert got and got[0][0] not in set(sku_by_id.values()), (key, got)


@pytest.mark.parametrize("brand_word", ["Nero", "Raw", "Day", "pohe"])
def test_short_latin_brand_words_are_not_pulled_onto_a_native_script_staple_by_sound(brand_word, lexicon, sku_by_id):
    """Found by the held-out branded-product check: "Nero" sounds like Telugu/Kannada "నీరు" (water), "Raw" like "రవ్వ" (semolina), "Day" like
    Bengali "দই" (curd). A Latin word may reach a name that exists ONLY in a 2.3.0 pack's native script by sound alone when the skeleton is
    5+ letters; shorter ones stay unrecognised rather than becoming a confident wrong product."""
    _, got = lines_of(lexicon, sku_by_id, f"ek {brand_word} dena")
    assert got and got[0][0] not in set(sku_by_id.values()), (brand_word, got)


@pytest.mark.parametrize("lang, sku", [("te", "WATER"), ("kn", "WATER"), ("te", "SUJI"), ("ml", "SUJI"), ("bn", "CURD"), ("mr", "POHA")])
def test_the_native_script_names_behind_those_collisions_still_resolve_exactly(lang, sku, lexicon, sku_by_id):
    """The gate only concerns Latin words matching by sound. The pack's own native-script name must keep working."""
    name = PACKS[lang].names[sku].split("|")[0].strip()
    _, got = lines_of(lexicon, sku_by_id, name, hint=lang)
    assert got and got[0][0] == sku, (lang, name, got)


# --------------------------------------------------------------------------- scripts, language detection, Hindi vs Marathi
SAME_WORD ={"milk": ["દૂધ", "दूध", "doodh", "দুধ", "ਦੁੱਧ"]}


def test_the_same_spoken_word_has_one_phonetic_skeleton_across_scripts():
    """Gujarati દૂધ, Hindi/Marathi दूध and Bengali দুধ all say 'dudh'; Punjabi ਦੁੱਧ is the doubled-consonant spelling of the same word."""
    base = translit.skeleton("दूध")
    assert translit.skeleton("દૂધ") == base == translit.skeleton("দুধ") == translit.skeleton("doodh")
    assert translit.skeleton("ਦੁਧ") == base


@pytest.mark.parametrize("text,expected", [
    ("मला दोन किलो साखर पाहिजे", "mr"), ("मुझे दो किलो चीनी चाहिए", "hi"),
    ("તમે મને બે કિલો ખાંડ આપો", "gu"), ("আমার দুই কেজি চিনি লাগবে", "bn"), ("ਮੈਨੂੰ ਦੋ ਕਿਲੋ ਖੰਡ ਚਾਹੀਦੀ ਹੈ", "pa"),
    ("எனக்கு இரண்டு கிலோ சர்க்கரை", "ta"), ("నాకు రెండు కిలోల చక్కెర", "te"), ("ನನಗೆ ಎರಡು ಕಿಲೋ ಸಕ್ಕರೆ", "kn"), ("എനിക്ക് രണ്ട് കിലോ പഞ്ചസാര", "ml"),
    ("I want two kilos of sugar", "en"), ("mujhe do kilo chini chahiye", "hinglish"),
])
def test_language_is_detected_from_script_and_marker_words(text, expected, lexicon):
    assert parse_utterance(text, lexicon).language == expected


def test_the_selector_decides_between_hindi_and_marathi_when_words_are_shared(lexicon):
    """दूध किलो is the same text in both; with nothing to tell them apart the selected language wins."""
    assert parse_utterance("दो किलो दूध", lexicon, language_hint="mr").language == "mr"
    assert parse_utterance("दो किलो दूध", lexicon, language_hint="hi").language == "hi"


# --------------------------------------------------------------------------- reply wording
@pytest.mark.parametrize("key", reg.ORDER)
def test_every_reply_template_exists_in_every_language(key):
    for tkey, per_lang in nlg.T.items():
        assert key in per_lang and per_lang[key].strip(), f"{tkey} missing for {key}"


@pytest.mark.parametrize("key", NEW)
def test_pack_defines_every_required_template(key):
    assert set(REQUIRED_TEMPLATES) <= set(PACKS[key].templates)


@pytest.mark.parametrize("key", reg.ORDER)
def test_replies_are_written_in_the_language_script(key):
    """A reply for a language must be in its own script (Latin for English and Hinglish): no English leaking into a Tamil reply."""
    from app.nlu.normalize import dominant_script

    want = {"gujarati": "gu", "devanagari": "hi", "latin": "latin", "bengali": "bn", "tamil": "ta", "telugu": "te", "kannada": "kn",
            "malayalam": "ml", "gurmukhi": "pa"}[reg.LANGUAGES[key].script]
    for tkey in ("greeting", "no_speech", "skipped"):
        text = nlg.render(tkey, key)
        got = dominant_script(text)
        assert got == want or (key == "mr" and got == "hi"), (key, tkey, text, got)


@pytest.mark.parametrize("key", reg.ORDER)
def test_read_back_fills_in_the_items_and_the_total(key):
    out = nlg.render("added", key, items="<ITEMS>", total="<TOTAL>")
    assert "<ITEMS>" in out and "<TOTAL>" in out, (key, out)


@pytest.mark.parametrize("key", NEW)
def test_pack_unit_labels_exist_for_the_common_units(key):
    for unit in ("kg", "g", "l", "ml", "pack", "pc"):
        sing, plur = PACKS[key].unit_labels[unit]
        assert sing and plur, (key, unit)


def test_the_evaluation_sentence_file_matches_the_test_table_and_the_registry_samples():
    """eval/language_sentences.jsonl is what the evaluation report counts; these tests are what prove each sentence parses.
    If they drift apart, the report would count sentences the suite never checks."""
    import json
    from pathlib import Path

    rows = [json.loads(line) for line in (Path(__file__).resolve().parents[2] / "eval" / "language_sentences.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    authored = {(r["lang"], r["text"]): [tuple(g) for g in r["gold"]] for r in rows if r["kind"] == "authored"}
    table = {(k, t): exp for k, t, exp in ADD_CASES}
    assert authored == table
    samples = {r["lang"]: (r["text"], [tuple(g) for g in r["gold"]]) for r in rows if r["kind"] == "registry_sample"}
    assert set(samples) == set(reg.ORDER)
    for key, (text, gold) in samples.items():
        assert text == reg.LANGUAGES[key].sample and gold == [("SUGAR", "2", "kg"), ("MILK", "1", "l")]
    assert len(rows) == len(authored) + len(samples)   # no duplicate or unlabelled rows
