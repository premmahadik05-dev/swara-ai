"""Text normalisation and script detection for the ten Indian languages SWARA AI supports (plus Hinglish / English).

Everything downstream (number parsing, unit parsing, product matching) works on the
output of :func:`normalize_text`, so this module is the single place that decides how
raw ASR text is cleaned.
"""
from __future__ import annotations

import re
import unicodedata

# Unicode blocks of the Indic scripts the app reads. The key is the *script* key used across the NLU:
# "hi" is Devanagari (Hindi and Marathi share it); the others are one script per language.
SCRIPT_RANGES: dict[str, tuple[int, int]] = {
    "hi": (0x0900, 0x097F),  # Devanagari (Hindi, Marathi)
    "bn": (0x0980, 0x09FF),  # Bengali
    "pa": (0x0A00, 0x0A7F),  # Gurmukhi (Punjabi)
    "gu": (0x0A80, 0x0AFF),  # Gujarati
    "ta": (0x0B80, 0x0BFF),  # Tamil
    "te": (0x0C00, 0x0C7F),  # Telugu
    "kn": (0x0C80, 0x0CFF),  # Kannada
    "ml": (0x0D00, 0x0D7F),  # Malayalam
}
SCRIPT_KEY_BY_NAME = {
    "latin": "latin", "devanagari": "hi", "bengali": "bn", "gurmukhi": "pa", "gujarati": "gu",
    "tamil": "ta", "telugu": "te", "kannada": "kn", "malayalam": "ml",
}
INDIC_SCRIPTS = tuple(SCRIPT_RANGES)
GUJARATI_RANGE = SCRIPT_RANGES["gu"]
DEVANAGARI_RANGE = SCRIPT_RANGES["hi"]

# Native digits: every Indic script has its own ten digits at a fixed offset from the block start
_DIGIT_STARTS = (0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0BE6, 0x0C66, 0x0CE6, 0x0D66)  # hi bn pa gu ta te kn ml
_GU_DIGITS = "૦૧૨૩૪૫૬૭૮૯"
_DEV_DIGITS = "०१२३४५६७८९"
_DIGIT_MAP = {start + i: str(i) for start in _DIGIT_STARTS for i in range(10)}

# zero-width characters that ASR / keyboards sprinkle into Indic text
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)

# chandrabindu -> anusvara (ASR engines use them interchangeably); nukta and Gurmukhi addak removed
_CHAR_FIXES = {
    0x0901: "\u0902",  # Devanagari chandrabindu -> anusvara
    0x0A81: "\u0A82",  # Gujarati
    0x0981: "\u0982",  # Bengali
    0x0A01: "\u0A02",  # Gurmukhi
    0x0A70: "\u0A02",  # Gurmukhi tippi -> bindi (both are the nasal sign)
    0x0C01: "\u0C02",  # Telugu
    0x0C81: "\u0C82",  # Kannada
    0x093C: None,  # Devanagari nukta
    0x0ABC: None,  # Gujarati nukta
    0x09BC: None,  # Bengali nukta
    0x0A3C: None,  # Gurmukhi nukta
    0x0CBC: None,  # Kannada nukta
    0x0A71: None,  # Gurmukhi addak (doubles the next consonant; the skeleton ignores doubling anyway)
}


def script_of(ch: str) -> str:
    """Script key of one character: an Indic key (hi, bn, pa, gu, ta, te, kn, ml), ``latin`` or ``""``."""
    o = ord(ch)
    if o < 0x0900:
        return "latin" if (ch.isascii() and ch.isalpha()) else ""
    if o > 0x0D7F:
        return ""
    for key, (lo, hi) in SCRIPT_RANGES.items():
        if lo <= o <= hi:
            return key if ch.isalpha() or unicodedata.category(ch)[0] == "M" else ""
    return ""


def _is_gu(ch: str) -> bool:
    return GUJARATI_RANGE[0] <= ord(ch) <= GUJARATI_RANGE[1]


def _is_dev(ch: str) -> bool:
    return DEVANAGARI_RANGE[0] <= ord(ch) <= DEVANAGARI_RANGE[1]


def script_letter_counts(text: str) -> dict[str, int]:
    """Letters per script key (Indic keys + ``latin``); scripts with no letters are left out."""
    counts: dict[str, int] = {}
    for c in text:
        if not c.isalpha():
            continue
        k = script_of(c)
        if k:
            counts[k] = counts.get(k, 0) + 1
    return counts


def detect_script(text: str) -> str:
    """Return a script key (``gu``, ``hi`` = Devanagari, ``bn`` ...), ``latin``, ``mixed`` or ``none``."""
    present = [k for k, n in script_letter_counts(text).items() if n]
    if not present:
        return "none"
    return present[0] if len(present) == 1 else "mixed"


def dominant_script(text: str) -> str:
    counts = script_letter_counts(text)
    if not counts:
        return "none"
    # on a tie keep the pre-2.3 order: Gujarati, then Devanagari, then Latin
    order = {"gu": 0, "hi": 1, "latin": 2}
    return max(counts, key=lambda k: (counts[k], -order.get(k, 3)))


def _strip_latin_diacritics(text: str) -> str:
    """"dūdh" -> "dudh", "ṭamāṭar" -> "tamatar". Only touches Latin letters, never Indic matras."""
    if text.isascii():
        return text
    out = []
    for ch in text:
        if ord(ch) < 0x250 and not ch.isascii():
            out.append("".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)))
        else:
            out.append(ch)
    return "".join(out)


def script_token_counts(words: list[str]) -> tuple[int, int, int]:
    """(gujarati, devanagari, latin) word counts - used for code-mixed sentences."""
    c = script_word_counts(words)
    return c.get("gu", 0), c.get("hi", 0), c.get("latin", 0)


def script_word_counts(words: list[str]) -> dict[str, int]:
    """Words per script key. A word counts for every Indic script it contains a letter of, and for ``latin`` when it is ASCII."""
    out: dict[str, int] = {}
    for w in words:
        keys = {script_of(c) for c in w}
        keys.discard("")
        if w.isascii() and any(c.isalpha() for c in w):
            keys = {"latin"}
        for k in keys:
            out[k] = out.get(k, 0) + 1
    return out


def normalize_text(text: str, keep_separators: bool = False) -> str:
    """Lower-case, strip punctuation, unify digits and Indic variants.

    With ``keep_separators`` list/sentence punctuation becomes a literal "," token so the
    parser can split "2 kilo chawal, 1 litre doodh" into items.

    Keeps decimal points between digits ("1.5") and letter/digit boundaries are split
    so that "2kg" becomes "2 kg".
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = _strip_latin_diacritics(text)
    text = text.translate(_ZERO_WIDTH).translate(_DIGIT_MAP).translate(_CHAR_FIXES)
    text = text.casefold()
    out: list[str] = []
    n = len(text)
    for i, ch in enumerate(text):
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "M", "N"):
            out.append(ch)
        elif ch in ".,/" and 0 < i < n - 1 and text[i - 1].isdigit() and text[i + 1].isdigit():
            # keep "1.5" and "1/2"; treat "1,5" as decimal comma too
            out.append("." if ch == "," else ch)
        elif ch == "₹":
            out.append(" rs ")
        elif keep_separators and ch in ",;।॥\n|.!?":
            out.append(" , ")
        else:
            out.append(" ")
    s = "".join(out)
    # split digit<->letter boundaries: "2kg" -> "2 kg", "kg2" -> "kg 2"
    s = re.sub(r"(?<=\d)(?=[^\W\d_]|[ऀ-෿])", " ", s)
    s = re.sub(r"(?<=[^\W\d_])(?=\d)", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokenize(text: str) -> list[str]:
    n = normalize_text(text, keep_separators=True)
    toks = n.split(" ") if n else []
    # collapse runs of separators and drop leading/trailing ones
    out: list[str] = []
    for t in toks:
        if t == "," and (not out or out[-1] == ","):
            continue
        out.append(t)
    while out and out[-1] == ",":
        out.pop()
    return out
