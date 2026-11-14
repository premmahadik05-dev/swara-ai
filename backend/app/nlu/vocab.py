"""Static vocabulary: number words, fractions, units, fillers and intent cue words.

Every entry is passed through :func:`normalize_text` at import time so that the tables
can be written in natural spelling (e.g. ``पाँच``) and still match normalised input.
"""
from __future__ import annotations

from decimal import Decimal

from .normalize import normalize_text


def _norm_keys(d: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        for part in k.split("|"):
            out[normalize_text(part)] = v
    return out


def _norm_set(words: str) -> set[str]:
    return {normalize_text(w) for w in words.split("|") if w.strip()}


# --------------------------------------------------------------------------- numbers
_NUMBER_SRC: dict[str, int] = {
    # 0-10
    "zero|shunya|शून्य|શૂન્ય": 0,
    "one|ek|एक|એક": 1,
    "two|do|दो|be|બે|bey": 2,
    "three|teen|तीन|tran|ત્રણ|trann": 3,
    "four|char|chaar|चार|ચાર": 4,
    "five|panch|paanch|paach|पांच|पाँच|પાંચ|pach": 5,
    "six|chhe|chhah|chheh|cheh|chha|छह|छः|छे|छ|છ": 6,
    "seven|saat|sat|सात|સાત": 7,
    "eight|aath|ath|आठ|આઠ": 8,
    "nine|nau|nav|नौ|નવ": 9,
    "ten|das|dus|दस|દસ": 10,
    # 11-20
    "eleven|gyarah|gyaraah|agiyar|ग्यारह|અગિયાર": 11,
    "twelve|barah|baarah|बारह|બાર": 12,
    "thirteen|terah|ter|तेरह|તેર": 13,
    "fourteen|chaudah|chaud|चौदह|ચૌદ": 14,
    "fifteen|pandrah|pandar|पंद्रह|पन्द्रह|પંદર": 15,
    "sixteen|solah|sol|सोलह|સોળ": 16,
    "seventeen|satrah|सत्रह|સત્તર": 17,
    "eighteen|atharah|अठारह|અઢાર": 18,
    "nineteen|unnis|oganis|उन्नीस|ઓગણીસ": 19,
    "twenty|bees|vees|vis|बीस|વીસ": 20,
    # tens / common kirana quantities
    "twenty five|pachchis|pachis|pachees|पच्चीस|પચીસ|પચ્ચીસ": 25,
    "thirty|tees|tis|तीस|ત્રીસ": 30,
    "forty|chalis|चालीस|ચાલીસ": 40,
    "fifty|pachas|pachaas|पचास|પચાસ": 50,
    "sixty|साठ|સાઠ": 60,
    "seventy|sattar|सत्तर|સિત્તેર": 70,
    "eighty|assi|अस्सी|એંસી": 80,
    "ninety|nabbe|नब्बे|નેવું": 90,
}
NUMBER_WORDS: dict[str, int] = _norm_keys(_NUMBER_SRC)  # type: ignore[assignment]

HUNDRED = _norm_set("hundred|sau|सौ|સો")
THOUSAND = _norm_set("thousand|hazaar|hazar|hajar|हज़ार|हजार|હજાર")

# Fractions that stand alone as a quantity (value in whole units)
_FRACTION_SRC: dict[str, str] = {
    "half|aadha|adha|aadhaa|aadhi|adhi|aadhe|adhe|आधा|आधी|आधे|અડધો|અડધું|અડધી|adhdo|adhu": "0.5",
    "quarter|paav|pav|पाव|પા|pa": "0.25",
    "pauna|pona|पौना|पौन|પોણો|પોણા": "0.75",
    "sava|sawa|सवा|સવા": "1.25",
    "dedh|derh|deadh|डेढ|ડેઢ|દોઢ|doadh|dodh": "1.5",
    "dhai|dhaai|adhai|ढाई|અઢી": "2.5",
}
FRACTION_WORDS: dict[str, Decimal] = {k: Decimal(v) for k, v in _norm_keys(_FRACTION_SRC).items()}  # type: ignore[arg-type]

# Words that add to the *following* number: "saade teen" = 3.5, "sava do" = 2.25
PREFIX_ADD: dict[str, Decimal] = {
    **{k: Decimal("0.5") for k in _norm_set("saade|sade|saadhe|साढ़े|साढे|સાડા")},
}
PREFIX_ADD_QUARTER = _norm_set("sava|sawa|सवा|સવા")  # also a bare 1.25
PREFIX_SUB_QUARTER = _norm_set("paune|paun|पौने|पौन|પોણા")

# Vague quantity words -> we must ask how much
AMBIGUOUS_QTY = _norm_set(
    "thoda|thodi|thode|thoda sa|kuch|kuchh|zyada|jyada|bahut|bohot|some|few|little|bit|couple|several|"
    "थोड़ा|थोड़ी|थोड़े|थोडा|कुछ|ज़्यादा|ज्यादा|बहुत|થોડું|થોડા|થોડી|થોડુક|કંઈક|ઘણું|ઘણા"
)

ARTICLE_ONE = {"a", "an"}  # "a kilo of sugar"

# --------------------------------------------------------------------------- units
# canonical: kg, g, l, ml, pack, pc, dozen, bottle, box, bag
_UNIT_SRC: dict[str, str] = {
    "kg|kgs|kilo|kilos|kilogram|kilograms|kilogramme|kelo|kilu|किलो|किलोग्राम|केजी|કિલો|કિલોગ્રામ|કેજી": "kg",
    "g|gm|gms|gram|grams|gramme|ग्राम|ગ્રામ|ગ્રા": "g",
    "l|lt|ltr|ltrs|lit|litre|litres|liter|liters|लीटर|लिटर|લીટર|લિટર": "l",
    "ml|mls|millilitre|milliliter|मिली|मिलीलीटर|એમએલ|મિલી": "ml",
    "pack|packs|packet|packets|pkt|pkts|pouch|पैकेट|पैक|पाउच|પેકેટ|પેક|પાઉચ": "pack",
    "pc|pcs|piece|pieces|nang|nag|number|numbers|नग|नंग|पीस|નંગ|પીસ": "pc",
    "dozen|dzn|darjan|दर्जन|ડઝન": "dozen",
    "bottle|bottles|botal|बोतल|बॉटल|બોટલ": "bottle",
    "box|boxes|dabba|dabbe|dibba|डिब्बा|डिब्बे|डब्बा|ડબ્બો|ડબ્બા|ડિબ્બા": "box",
    "bag|bags|thaili|thaila|थैली|थैला|થેલી|થેલો": "bag",
}
UNIT_WORDS: dict[str, str] = _norm_keys(_UNIT_SRC)  # type: ignore[assignment]

# --------------------------------------------------------------------------- fillers
CONJUNCTIONS = _norm_set(
    "aur|और|ane|અને|tatha|तथा|તથા|and|plus|also|then|phir|fir|फिर|pachi|પછી|temaj|તેમજ|"
    "saath|साथ|sathe|સાથે|ke saath|valli|વળી"
)

# words that carry no product meaning; stripped before looking for unknown terms
FILLERS = _norm_set(
    # Hindi / Hinglish
    "bhai|bhaiya|bhaiyya|bhaisaab|bhai saab|sir|madam|uncle|uncleji|kaka|kaki|dada|dadaji|"
    "mujhe|mujhko|mere|meri|mera|humko|hume|hamein|ko|ka|ki|ke|se|me|mein|main|hai|hain|hoga|hogi|"
    "chahiye|chahie|chaiye|chahiyen|chahta|chahti|chahunga|chahungi|"
    "de|dena|dedo|dijiye|dijiyega|deejiye|dijie|dijiyo|denaa|denge|do|karo|kar|kijiye|kijiyega|"
    "लेना|लूंगा|लूँगा|लूंगी|"
    "bhaiyaa|please|plz|pls|kripya|jara|zara|ek baar|yaar|yar|dost|"
    "भाई|भैया|भइया|सर|मुझे|मुझको|मेरे|मेरा|मेरी|हमको|हमें|को|का|की|के|से|में|है|हैं|होगा|होगी|"
    "चाहिए|चाहिये|चाहता|चाहती|चाहूंगा|दे|देना|दीजिए|दीजिये|दीजियेगा|दो|कीजिए|कर|करो|ज़रा|ज़रा|जरा|कृपया|यार|"
    # Gujarati
    "mane|mara|mari|maru|maare|mare|joie|joiye|joshe|joia|aapjo|apjo|aapo|apo|aapsho|aapi|api|aapine|"
    "aapi do|api do|karo ne|ne|ni|no|nu|na|nā|chhe|che|"
    "મને|મારે|મારા|મારી|મારું|જોઈએ|જોઈશે|જોઈયે|આપજો|આપો|આપશો|આપી|આપ|આપીને|ને|ની|નો|નું|ના|છે|છો|"
    "ભાઈ|ભાઈજી|કાકા|કાકી|સાહેબ|દાદા|મહેરબાની|કૃપા|જરા|થોડું ધ્યાન|"
    # English
    "i|me|my|we|us|our|want|need|would|like|will|shall|can|could|give|get|take|put|add|include|buy|order|"
    "to|of|for|the|in|into|is|are|it|that|this|these|those|some more|more|extra|another|too|"
    "cart|basket|bill|list|item|items|thing|things|stuff|"
    "hello|hi|hey|namaste|namaskar|नमस्ते|નમસ્તે|હેલો"
)

# --------------------------------------------------------------------------- intents
INTENT_CUES: dict[str, list[str]] = {
    "greeting": [
        "namaste", "namaskar", "hello", "hey", "good morning", "good evening", "good afternoon",
        "kem cho", "kemcho", "kem chho", "jai shree krishna", "jsk", "ram ram", "radhe radhe",
        "નમસ્તે", "નમસ્કાર", "કેમ છો", "જય શ્રી કૃષ્ણ", "રામ રામ", "હેલો", "नमस्ते", "नमस्कार", "राम राम", "हेलो",
    ],
    "confirm": [
        "haan", "han", "haa", "ha", "ji", "jee", "ji haan", "ji ha", "theek hai", "thik hai", "theek", "sahi hai",
        "bilkul", "pakka", "confirm", "confirmed", "yes", "yeah", "yep", "yup", "ok", "okay", "sure", "correct",
        "right", "go ahead", "place order", "place the order", "order karo", "order kar do", "kar do",
        "chalega", "chalo", "done", "proceed", "that is correct", "that's correct", "sounds good",
        "હા", "હા જી", "જી", "ભલે", "બરાબર", "ઠીક છે", "સાચું", "ચાલશે", "ચાલે", "કરો", "કન્ફર્મ", "કન્ફર્મ કરો",
        "પાક્કું", "હા ભાઈ", "ઓકે",
        "हाँ", "हां", "जी", "जी हाँ", "जी हां", "ठीक है", "सही है", "बिल्कुल", "पक्का", "कन्फर्म", "हा", "चलेगा", "ओके", "कर दो",
    ],
    "deny": [
        "nahi", "nahin", "nai", "na", "no", "nope", "nah", "mat",
        "नहीं", "नही", "ना", "मत", "ના", "નહિ", "નહીં", "નથી",
    ],
    "cancel": [
        "cancel", "cancel karo", "cancel order", "order cancel", "rehne do", "rahne do", "chhodo", "chodo",
        "leave it", "forget it", "never mind", "nevermind", "start over", "start again",
        "रहने दो", "रद्द", "कैंसल", "छोड़ो", "छोड़ दो", "कैंसल कर दो",
        "કેન્સલ", "રદ", "રહેવા દો", "રહેવા દે", "છોડો", "કેન્સલ કરો",
    ],
    "done": [
        "bas", "bas itna", "bas itna hi", "itna hi", "that's all", "thats all", "that is all", "nothing else",
        "no more", "that's it", "thats it", "total", "bill", "summary", "kitna hua", "kitna hoga", "total kitna",
        "hisab", "hisaab", "order summary", "checkout", "finish", "bill banao", "bill bana do",
        "बस", "बस इतना", "बस इतना ही", "इतना ही", "कितना हुआ", "कितना होगा", "कुल कितना", "हिसाब", "बिल बनाओ", "बिल",
        "બસ", "બસ આટલું", "બસ આટલું જ", "આટલું જ", "આટલું", "બિલ", "કેટલા થયા", "કુલ કેટલા", "કેટલું થયું",
        "કેટલા થશે", "હિસાબ", "બિલ બનાવો", "બિલ બનાવી દો",
    ],
    "remove": [
        "hata do", "hatao", "hata dijiye", "hataiye", "nikal do", "nikaal do", "nikalo", "remove", "delete",
        "drop", "skip", "mat do", "nahi chahiye", "nahin chahiye", "not needed", "don't want", "dont want",
        "do not want", "no need", "take out", "cancel", "hata de", "hata",
        "हटा दो", "हटाओ", "हटा दीजिए", "निकाल दो", "निकालो", "नहीं चाहिए", "मत दो", "हटा दे",
        "કાઢી નાખો", "કાઢો", "કાઢી દો", "હટાવો", "ન જોઈએ", "નથી જોઈતું", "નથી જોઈતા", "નથી જોઈતી",
        "નહીં જોઈએ", "નહિ જોઈએ", "નથી જોઈએ", "રહેવા દો", "બાદ કરો",
    ],
    "set": [
        "kar do", "kar dijiye", "kijiye", "make it", "make that", "change to", "change it to", "change",
        "set to", "set", "update", "instead", "badal do", "bana do", "sirf", "only", "just",
        "बना दो", "कर दो", "बदल दो", "सिर्फ", "केवल", "बदलो",
        "કરી દો", "બનાવો", "બનાવી દો", "બદલો", "બદલી નાખો", "ફક્ત", "માત્ર",
    ],
    "query": [
        "kitne ka", "kitne ki", "kitna ka", "kya rate", "kya bhav", "kya bhaav", "rate", "bhav", "bhaav", "price", "cost",
        "how much is", "how much are", "how much does", "what is the price", "hai kya", "available", "in stock", "stock",
        "milega", "milta hai", "kitne me", "kitne mein",
        "कितने का", "कितने की", "रेट", "भाव", "कीमत", "है क्या", "मिलेगा", "मिलता है",
        "કેટલાનું", "કેટલાની", "કેટલાના", "ભાવ", "રેટ", "કિંમત", "છે કે", "મળશે", "મળે છે", "શું ભાવ", "શું રેટ",
    ],
}

# Hindi/Gujarati *romanised* cue words that prove an English-looking sentence is Hinglish
HINGLISH_MARKERS = _norm_set(
    "bhai|bhaiya|mujhe|mujhko|chahiye|chahie|chaiye|aur|kitna|kitne|kilo|nahi|haan|dedo|dijiye|bas|thoda|thodi|"
    "aadha|adha|paav|sava|dedh|dhai|aap|tum|mere|meri|mane|joie|joiye|aapjo|apjo|ane|kem|cho|ek|teen|char|"
    "panch|paanch|saat|aath|doodh|dudh|chawal|chini|namak|atta|daal|tel|ghee|sabzi|aloo|pyaz|tamatar|haldi|mirch|chai|"
    "dukaan|rupaye|rupiya|sab|kuch|bhi|abhi|phir|lena|dena|wala|wali|hai|hain|kya|ka|ki|ke|ko|se|mein|bhav|bhaav|hoga|hogi|nahin|theek|thik|accha|achha"
)


# Words that mark a Latin-script sentence as Hinglish only if they are NOT also normal English usage.
HINGLISH_SHARED_WITH_ENGLISH = frozenset({"kilo", "chai", "ghee", "tel"})
HINGLISH_STRONG = frozenset((HINGLISH_MARKERS - HINGLISH_SHARED_WITH_ENGLISH) | _norm_set("sau|hazaar|hajar|pachas|bees|tees|chalis|saath|das|dus|nau"))

ENGLISH_MARKERS = _norm_set(
    # function words and English number words only. Units and product names (packet, gram, bread, milk ...) are
    # shared with Hinglish speech and are deliberately NOT evidence of English.
    "and|please|want|need|give|me|i|the|of|with|some|an|a|one|two|three|four|five|six|seven|eight|nine|ten|half|quarter|how|much|is|are|"
    "you|have|total|bill|thanks|thank|yes|no|okay|ok|confirm|cancel|add|remove|also|more|another|that|this|it|my|order|would|like|can|get|take|only|nothing|else|anything|hello"
)

# Hindi words that are also English words: evidence for Hinglish only when no English function word is present.
HINGLISH_WEAK = _norm_set("do")

# Romanised Gujarati (typed in Latin script). These also appear in HINGLISH_MARKERS for historical reasons;
# detect_language() counts them separately so "mane doodh joie" is Gujarati, not Hinglish.
GUJARATI_ROMAN = _norm_set(
    "mane|mare|mari|mara|tamne|aapjo|apjo|aapo|apo|joie|joiye|ane|chhe|chho|cho|shu|nathi|kem|haju|thodu|biju|bija|aapshu|kidhu"
)


# --------------------------------------------------------------------------- language packs (2.3.0)
# Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam and Punjabi are plain-data packs (nlu/langpacks). They are merged
# into the tables above in place, so every module that did ``from . import vocab`` sees one combined vocabulary.
from .langpacks import HINDI_DEVANAGARI_MARKERS, load_all as _load_packs  # noqa: E402

PACKS = _load_packs()
AND_WORDS_EXTRA: set[str] = set()
NEED_VERBS_EXTRA: set[str] = set()
MARATHI_MARKERS: set[str] = set()
HINDI_DEV_MARKERS: set[str] = _norm_set(HINDI_DEVANAGARI_MARKERS)
ROMAN_MARKERS: dict[str, set[str]] = {}
_suffixes: set[str] = set()


def _merge_checked(target: dict, add: dict, what: str, lang: str) -> None:
    """Merge a pack table; a word that already means something *different* is a bug in the pack, so fail at import."""
    for k, val in add.items():
        if k in target and target[k] != val:
            raise ValueError(f"language pack {lang!r}: {what} {k!r} already means {target[k]!r}, pack says {val!r}")
        target[k] = val


for _key, _pack in PACKS.items():
    _merge_checked(NUMBER_WORDS, _norm_keys(_pack.numbers), "number word", _key)  # type: ignore[arg-type]
    HUNDRED |= _norm_set(_pack.hundred)
    THOUSAND |= _norm_set(_pack.thousand)
    _merge_checked(FRACTION_WORDS, {k: Decimal(v) for k, v in _norm_keys(_pack.fractions).items()}, "fraction", _key)  # type: ignore[arg-type]
    for _w in _norm_set(_pack.prefix_add):
        PREFIX_ADD[_w] = Decimal("0.5")
    PREFIX_ADD_QUARTER |= _norm_set(_pack.prefix_add_quarter)
    PREFIX_SUB_QUARTER |= _norm_set(_pack.prefix_sub_quarter)
    AMBIGUOUS_QTY |= _norm_set(_pack.ambiguous)
    _merge_checked(UNIT_WORDS, _norm_keys(_pack.units), "unit word", _key)  # type: ignore[arg-type]
    CONJUNCTIONS |= _norm_set(_pack.conj)
    AND_WORDS_EXTRA |= _norm_set(_pack.and_words)
    FILLERS |= _norm_set(_pack.fillers)
    NEED_VERBS_EXTRA |= _norm_set(_pack.need_verbs)
    for _intent, _phrases in _pack.cues.items():
        _have = INTENT_CUES.setdefault(_intent, [])
        _have.extend(p for p in _phrases if p not in _have)
    ROMAN_MARKERS[_key] = _norm_set(_pack.roman_markers)
    _suffixes |= _norm_set(_pack.suffixes)
    if _key == "mr":
        MARATHI_MARKERS |= _norm_set(_pack.markers)

# longest first, so "ुक्कू" is tried before "ु"
CASE_SUFFIXES: tuple[str, ...] = tuple(sorted(_suffixes, key=lambda x: (-len(x), x)))
