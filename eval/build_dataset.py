"""Builds eval/utterances.jsonl.

* ``handwritten``  - utterances written by the project author in a customer's voice. NOT independent of the
  parser's author (same person), so results are optimistic compared with a blind third-party test set.
* ``templated``    - generated from the catalogue with fixed templates (seed 11). By construction these use the
  catalogue's own names, so they are a *regression / sanity* check, not a generalisation measure.

Gold = list of (sku, qty, unit) as SPOKEN (unit None when the speaker gave none).
Kinds: normal | ambiguous (several products fit: must NOT be guessed) | no_item (no order item present).
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

H = []  # (lang, text, gold, kind)


def add(lang, text, *gold, kind="normal"):
    H.append((lang, text, [list(g) for g in gold], kind))


# ------------------------------------------------------------------ Gujarati
add("gu", "એક કિલો ખાંડ આપો", ("SUGAR", "1", "kg"))
add("gu", "બે લિટર દૂધ જોઈએ", ("MILK", "2", "l"))
add("gu", "અડધો કિલો ચા પત્તી", ("TEA", "0.5", "kg"))
add("gu", "પાંચ કિલો ચોખા અને બે કિલો લોટ", ("RICE-REGULAR", "5", "kg"), ("ATTA", "2", "kg"))
add("gu", "ત્રણ કિલો બટાકા, બે કિલો ડુંગળી, એક કિલો ટામેટા", ("POTATO", "3", "kg"), ("ONION", "2", "kg"), ("TOMATO", "1", "kg"))
add("gu", "એક પેકેટ મેગી આપો", ("NOODLES", "1", "pack"))
add("gu", "એક ડઝન ઈંડા", ("EGGS", "1", "dozen"))
add("gu", "૨૫૦ ગ્રામ હળદર", ("TURMERIC", "250", "g"))
add("gu", "દોઢ લિટર તેલ", ("OIL-GROUNDNUT", "1.5", "l"))
add("gu", "એક કિલો ઘી", ("GHEE", "1", "kg"))
add("gu", "બે પેકેટ બિસ્કિટ", ("BISC-GLUCOSE", "2", "pack"))  # relabelled after run 1: single shop default, not ambiguous
add("gu", "મરચું પાવડર અડધો કિલો", ("CHILLI-POWDER", "0.5", "kg"))
add("gu", "ચાર લીંબુ", ("LEMON", "4", None))
add("gu", "પનીર ૨૫૦ ગ્રામ", ("PANEER", "250", "g"))
add("gu", "મને એક કિલો મગની દાળ આપો", ("DAL-MOONG", "1", "kg"))
add("gu", "તુવેર દાળ બે કિલો", ("DAL-TOOR", "2", "kg"))
add("gu", "મીઠું એક કિલો", ("SALT", "1", "kg"))
add("gu", "આદુ સો ગ્રામ", ("GINGER", "100", "g"))
add("gu", "લસણ અડધો કિલો", ("GARLIC", "0.5", "kg"))
add("gu", "સવા કિલો ખાંડ", ("SUGAR", "1.25", "kg"))
add("gu", "સાડા ત્રણ કિલો ચોખા", ("RICE-REGULAR", "3.5", "kg"))
add("gu", "દહીં એક કિલો", ("CURD", "1", "kg"))
add("gu", "બ્રેડ બે પેકેટ", ("BREAD", "2", "pack"))
add("gu", "ચોખા બે કિલો અને દૂધ ત્રણ લિટર", ("RICE-REGULAR", "2", "kg"), ("MILK", "3", "l"))
add("gu", "ગાંઠિયા અડધો કિલો", ("GATHIYA", "0.5", "kg"))
add("gu", "ખાખરા ત્રણ પેકેટ", ("KHAKHRA", "3", "pack"))
add("gu", "સિંગદાણા એક કિલો", ("PEANUTS", "1", "kg"))
add("gu", "બદામ સો ગ્રામ", ("ALMOND", "100", "g"))
add("gu", "ભાઈ મને બે કિલો બટાકા અને એક કિલો રીંગણ આપજો", ("POTATO", "2", "kg"), ("BRINJAL", "1", "kg"))
add("gu", "કાકા એક લિટર સનફ્લાવર તેલ આપો", ("OIL-SUNFLOWER", "1", "l"))
# ------------------------------------------------------------------ Hindi (Devanagari)
add("hi", "एक किलो चीनी दे दो", ("SUGAR", "1", "kg"))
add("hi", "दो लीटर दूध चाहिए", ("MILK", "2", "l"))
add("hi", "आधा किलो चायपत्ती", ("TEA", "0.5", "kg"))
add("hi", "पाँच किलो चावल और दो किलो आटा", ("RICE-REGULAR", "5", "kg"), ("ATTA", "2", "kg"))
add("hi", "तीन किलो आलू, दो किलो प्याज़, एक किलो टमाटर", ("POTATO", "3", "kg"), ("ONION", "2", "kg"), ("TOMATO", "1", "kg"))
add("hi", "एक पैकेट मैगी", ("NOODLES", "1", "pack"))
add("hi", "एक दर्जन अंडे", ("EGGS", "1", "dozen"))
add("hi", "ढाई सौ ग्राम हल्दी", ("TURMERIC", "250", "g"))
add("hi", "डेढ़ लीटर तेल", ("OIL-GROUNDNUT", "1.5", "l"))
add("hi", "एक किलो घी", ("GHEE", "1", "kg"))
add("hi", "दो पैकेट बिस्किट", ("BISC-GLUCOSE", "2", "pack"))  # relabelled after run 1
add("hi", "लाल मिर्च पाउडर आधा किलो", ("CHILLI-POWDER", "0.5", "kg"))
add("hi", "चार नींबू", ("LEMON", "4", None))
add("hi", "पनीर दो सौ पचास ग्राम", ("PANEER", "250", "g"))
add("hi", "मूंग की दाल एक किलो", ("DAL-MOONG", "1", "kg"))
add("hi", "अरहर दाल दो किलो", ("DAL-TOOR", "2", "kg"))
add("hi", "नमक एक किलो", ("SALT", "1", "kg"))
add("hi", "अदरक सौ ग्राम", ("GINGER", "100", "g"))
add("hi", "लहसुन आधा किलो", ("GARLIC", "0.5", "kg"))
add("hi", "सवा किलो चीनी", ("SUGAR", "1.25", "kg"))
add("hi", "साढ़े तीन किलो चावल", ("RICE-REGULAR", "3.5", "kg"))
add("hi", "दही एक किलो", ("CURD", "1", "kg"))
add("hi", "ब्रेड दो पैकेट", ("BREAD", "2", "pack"))
add("hi", "मूंगफली एक किलो", ("PEANUTS", "1", "kg"))
add("hi", "बादाम सौ ग्राम", ("ALMOND", "100", "g"))
add("hi", "भैया दो किलो बैंगन और एक किलो भिंडी देना", ("BRINJAL", "2", "kg"), ("OKRA", "1", "kg"))
# ------------------------------------------------------------------ Hinglish (Latin)
add("hinglish", "bhaiya ek kilo cheeni dena", ("SUGAR", "1", "kg"))
add("hinglish", "do litre doodh chahiye", ("MILK", "2", "l"))
add("hinglish", "aadha kilo chai patti", ("TEA", "0.5", "kg"))
add("hinglish", "paanch kilo chawal aur do kilo atta", ("RICE-REGULAR", "5", "kg"), ("ATTA", "2", "kg"))
add("hinglish", "teen kilo aloo, do kilo pyaaz, ek kilo tamatar", ("POTATO", "3", "kg"), ("ONION", "2", "kg"), ("TOMATO", "1", "kg"))
add("hinglish", "ek packet maggi dena", ("NOODLES", "1", "pack"))
add("hinglish", "ek dozen ande", ("EGGS", "1", "dozen"))
add("hinglish", "dhai sau gram haldi", ("TURMERIC", "250", "g"))
add("hinglish", "dedh litre tel", ("OIL-GROUNDNUT", "1.5", "l"))
add("hinglish", "ek kilo ghee", ("GHEE", "1", "kg"))
add("hinglish", "do packet biscuit", ("BISC-GLUCOSE", "2", "pack"))  # relabelled after run 1
add("hinglish", "lal mirch powder aadha kilo", ("CHILLI-POWDER", "0.5", "kg"))
add("hinglish", "char nimbu", ("LEMON", "4", None))
add("hinglish", "paneer 250 gram", ("PANEER", "250", "g"))
add("hinglish", "moong dal ek kilo", ("DAL-MOONG", "1", "kg"))
add("hinglish", "toor dal do kilo", ("DAL-TOOR", "2", "kg"))
add("hinglish", "namak ek kilo", ("SALT", "1", "kg"))
add("hinglish", "adrak sau gram", ("GINGER", "100", "g"))
add("hinglish", "lehsun aadha kilo", ("GARLIC", "0.5", "kg"))
add("hinglish", "sava kilo cheeni", ("SUGAR", "1.25", "kg"))
add("hinglish", "saade teen kilo chawal", ("RICE-REGULAR", "3.5", "kg"))
add("hinglish", "dahi ek kilo", ("CURD", "1", "kg"))
add("hinglish", "bread do packet", ("BREAD", "2", "pack"))
add("hinglish", "moongfali ek kilo", ("PEANUTS", "1", "kg"))
add("hinglish", "badam sau gram", ("ALMOND", "100", "g"))
add("hinglish", "bhai 2 kilo basmati chawal", ("RICE-BASMATI", "2", "kg"))
add("hinglish", "5 kg atta aur 2 kg cheeni aur 1 litre doodh", ("ATTA", "5", "kg"), ("SUGAR", "2", "kg"), ("MILK", "1", "l"))
add("hinglish", "ek kilo besan", ("BESAN", "1", "kg"))
add("hinglish", "poha aadha kilo", ("POHA", "0.5", "kg"))
add("hinglish", "agarbatti do packet", ("AGARBATTI", "2", "pack"))
add("hinglish", "uncle mujhe teen kilo bhindi aur ek kilo baingan chahiye", ("OKRA", "3", "kg"), ("BRINJAL", "1", "kg"))
# ------------------------------------------------------------------ English
add("en", "one kilo sugar please", ("SUGAR", "1", "kg"))
add("en", "two litres of milk", ("MILK", "2", "l"))
add("en", "half a kilo tea", ("TEA", "0.5", "kg"))
add("en", "five kg rice and two kg flour", ("RICE-REGULAR", "5", "kg"), ("ATTA", "2", "kg"))
add("en", "three kilos potatoes, two kilos onions and one kilo tomatoes", ("POTATO", "3", "kg"), ("ONION", "2", "kg"), ("TOMATO", "1", "kg"))
add("en", "one packet of noodles", ("NOODLES", "1", "pack"))
add("en", "a dozen eggs", ("EGGS", "1", "dozen"))
add("en", "250 grams turmeric", ("TURMERIC", "250", "g"))
add("en", "one and a half litres of oil", ("OIL-GROUNDNUT", "1.5", "l"))
add("en", "1 kg ghee", ("GHEE", "1", "kg"))
add("en", "two packets of biscuits", ("BISC-GLUCOSE", "2", "pack"))  # relabelled after run 1
add("en", "red chilli powder half kg", ("CHILLI-POWDER", "0.5", "kg"))
add("en", "four lemons", ("LEMON", "4", None))
add("en", "paneer 250 grams", ("PANEER", "250", "g"))
add("en", "1 kg moong dal", ("DAL-MOONG", "1", "kg"))
add("en", "2 kg toor dal", ("DAL-TOOR", "2", "kg"))
add("en", "one kg salt", ("SALT", "1", "kg"))
add("en", "100 grams ginger", ("GINGER", "100", "g"))
add("en", "half kg garlic", ("GARLIC", "0.5", "kg"))
add("en", "a quarter kilo almonds", ("ALMOND", "0.25", "kg"))
add("en", "can I get 2 kg basmati rice and a bottle of cold drink", ("RICE-BASMATI", "2", "kg"), ("COLD-DRINK", "1", "bottle"))
# ------------------------------------------------------------------ code-mixed
add("gu", "મને 2 kg sugar અને 1 litre milk જોઈએ", ("SUGAR", "2", "kg"), ("MILK", "1", "l"))
add("gu", "ભાઈ 5 kg rice અને 2 kg atta આપજો", ("RICE-REGULAR", "5", "kg"), ("ATTA", "2", "kg"))
add("gu", "mane 2 kilo batata ane 1 kilo dungri aapo", ("POTATO", "2", "kg"), ("ONION", "1", "kg"))
add("gu", "mane ek kilo khand joie", ("SUGAR", "1", "kg"))
add("hi", "मुझे 2 kilo sugar और 1 litre milk चाहिए", ("SUGAR", "2", "kg"), ("MILK", "1", "l"))
add("hinglish", "bhai 1 kg sugar aur ek packet bread dena", ("SUGAR", "1", "kg"), ("BREAD", "1", "pack"))
# genuinely ambiguous: four dals, no shop default -> must be asked, never guessed (added after run 1 to replace the biscuit cases)
add("gu", "એક કિલો દાળ આપો", ("?", "1", "kg"), kind="ambiguous")
add("hi", "दो किलो दाल चाहिए", ("?", "2", "kg"), kind="ambiguous")
add("hinglish", "ek kilo daal dena", ("?", "1", "kg"), kind="ambiguous")
add("en", "one kg dal please", ("?", "1", "kg"), kind="ambiguous")
# ------------------------------------------------------------------ no order item present
for lang, t in [("en", "hello how are you"), ("en", "thank you very much"), ("hinglish", "kitna hua"), ("hinglish", "namaste bhaiya"),
                ("gu", "કેમ છો"), ("hi", "आप कैसे हैं"), ("en", "2 kilo dragonfruit"), ("hinglish", "ek packet xyzzy dena"),
                ("hi", "हवाई जहाज़ दे दो"), ("gu", "બે કિલો કીવી")]:
    add(lang, t, kind="no_item")

# ------------------------------------------------------------------ templated (regression)
def templated(rng: random.Random) -> list:
    from app.seed_data import CATALOG
    out = []
    qty_words = {
        "gu": [("એક", "1"), ("બે", "2"), ("ત્રણ", "3"), ("અડધો", "0.5"), ("દોઢ", "1.5"), ("અઢી", "2.5")],
        "hi": [("एक", "1"), ("दो", "2"), ("तीन", "3"), ("आधा", "0.5"), ("डेढ़", "1.5"), ("ढाई", "2.5")],
        "hinglish": [("ek", "1"), ("do", "2"), ("teen", "3"), ("aadha", "0.5"), ("dedh", "1.5"), ("dhai", "2.5")],
        "en": [("one", "1"), ("two", "2"), ("three", "3"), ("half", "0.5"), ("1.5", "1.5"), ("2.5", "2.5")],
    }
    unit_words = {"kg": {"gu": "કિલો", "hi": "किलो", "hinglish": "kilo", "en": "kilo"},
                  "l": {"gu": "લિટર", "hi": "लीटर", "hinglish": "litre", "en": "litre"}}
    tmpl = {"gu": "{q} {u} {n} આપો", "hi": "{q} {u} {n} दे दो", "hinglish": "{q} {u} {n} chahiye", "en": "{q} {u} {n} please"}
    loose = [c for c in CATALOG if c["unit"] in ("kg", "l")]
    for lang in ("gu", "hi", "hinglish", "en"):
        for c in rng.sample(loose, 40):
            qw, qv = rng.choice(qty_words[lang])
            name = {"gu": c["name_gu"], "hi": c["name_hi"], "hinglish": (c["aliases"][0] if c["aliases"] else c["name_en"]), "en": c["name_en"]}[lang]
            if "(" in name:
                name = name.split("(")[0].strip()
            if lang == "hinglish" and not name.isascii():
                name = c["name_en"].split("(")[0].strip()
            out.append((lang, tmpl[lang].format(q=qw, u=unit_words[c["unit"]][lang], n=name), [[c["sku"], qv, c["unit"]]], "normal"))
    return out


def main():
    rng = random.Random(11)
    rows = []
    for i, (lang, text, gold, kind) in enumerate(H):
        rows.append({"id": f"h{i:03d}", "set": "handwritten", "lang": lang, "kind": kind, "text": text, "gold": gold})
    for i, (lang, text, gold, kind) in enumerate(templated(rng)):
        rows.append({"id": f"t{i:03d}", "set": "templated", "lang": lang, "kind": kind, "text": text, "gold": gold})
    out = ROOT / "eval" / "utterances.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    from collections import Counter
    print(len(rows), "utterances;", dict(Counter((r["set"], r["lang"]) for r in rows)))


if __name__ == "__main__":
    main()
