"""Cross-script phonetic skeletons.

The Indic scripts are parallel Brahmic scripts: Unicode lays each one out in its own 128-code-point block with the
same internal order (Gujarati sits 0x180 above Devanagari, Bengali 0x80, Gurmukhi 0x100, Tamil 0x280, Telugu 0x300,
Kannada 0x380, Malayalam 0x400), so a token in any of them is shifted onto Devanagari and transliterated with one
table. Latin (Hinglish / romanised) tokens go through the same final *skeleton* reduction.  The result: ``દૂધ``,
``दूध``, ``doodh``, ``দুধ`` and ``dudh`` all collapse to the same string, which makes product matching robust to
script choice and to the spelling variation ASR engines produce for code-mixed speech.

The skeleton is *lossy by design* - it is only used for matching, never displayed.
"""
from __future__ import annotations

import re
from functools import lru_cache

_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}
_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}
_SIGNS = {"ं": "n", "ः": "h"}
# letters that exist only in some scripts (Tamil/Malayalam zha, rra, nnn; Tamil/Telugu/Kannada/Malayalam short e and o)
_CONS.update({"ऴ": "l", "ऱ": "r", "ऩ": "n"})
_VOWELS.update({"ऎ": "e", "ऒ": "o"})
_MATRAS.update({"ॆ": "e", "ॊ": "o"})
_VIRAMA = "्"
_INHERENT = "ɐ"  # marker for the inherent 'a' so we can apply schwa deletion


# script block start -> offset from Devanagari (0x0900)
_OFFSETS = ((0x0980, 0x0A00, 0x080), (0x0A00, 0x0A80, 0x100), (0x0A80, 0x0B00, 0x180), (0x0B80, 0x0C00, 0x280),
            (0x0C00, 0x0C80, 0x300), (0x0C80, 0x0D00, 0x380), (0x0D00, 0x0D80, 0x400))
_DRAVIDIAN = ((0x0B80, 0x0C00), (0x0C00, 0x0C80), (0x0C80, 0x0D00), (0x0D00, 0x0D80))  # anusvara is /m/ there
# characters whose block position does not land on the matching Devanagari letter
_SPECIAL = {
    0x09CE: "त",  # Bengali khanda ta
    0x0A72: "इ", 0x0A73: "उ",  # Gurmukhi iri / ura (vowel carriers)
    0x0D7A: "ण", 0x0D7B: "न", 0x0D7C: "र", 0x0D7D: "ल", 0x0D7E: "ळ", 0x0D7F: "क",  # Malayalam chillu letters
}


def _to_devanagari(token: str) -> str:
    out = []
    for ch in token:
        o = ord(ch)
        if o in _SPECIAL:
            out.append(_SPECIAL[o])
            continue
        if o < 0x0980 or o > 0x0D7F:
            out.append(ch)
            continue
        for lo, hi, off in _OFFSETS:
            if lo <= o < hi:
                if o in (0x0B82, 0x0C02, 0x0C82, 0x0D02) and any(a <= o < b for a, b in _DRAVIDIAN):
                    out.append("म्")  # Dravidian anusvara = a final "m"
                else:
                    out.append(chr(o - off))
                break
        else:
            out.append(ch)
    return "".join(out)


def _translit_dev(token: str) -> str:
    out: list[str] = []
    i, n = 0, len(token)
    while i < n:
        ch = token[i]
        if ch in _CONS:
            out.append(_CONS[ch])
            nxt = token[i + 1] if i + 1 < n else ""
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 2
                continue
            if nxt == _VIRAMA:
                i += 2
                continue
            out.append(_INHERENT)
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _SIGNS:
            out.append(_SIGNS[ch])
        elif ch in _MATRAS:  # stray matra
            out.append(_MATRAS[ch])
        elif ch == _VIRAMA:
            pass
        elif ch.isascii() and ch.isalpha():
            out.append(ch)
        i += 1
    # schwa deletion: the final inherent vowel is silent in Hindi/Gujarati/Marathi
    while out and out[-1] == _INHERENT:
        out.pop()
    return "".join(out).replace(_INHERENT, "a")


def _roman_skeleton(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z]", "", s)
    if not s:
        return ""
    s = s.replace("chh", "C").replace("ch", "C")
    s = s.replace("sh", "s")
    s = s.replace("ph", "f")
    s = re.sub(r"([kgtdbjp])h", r"\1", s)  # drop aspiration
    s = re.sub(r"c(?=[eiy])", "s", s).replace("c", "k")
    s = s.replace("zh", "l").replace("w", "v").replace("z", "j").replace("q", "k").replace("x", "ks").replace("y", "i")
    s = re.sub(r"(.)\1+", r"\1", s)  # collapse doubles (aa, ee, oo, kk ...)
    s = s.replace("ai", "i").replace("au", "u").replace("ri", "ri")
    s = s.replace("o", "u").replace("e", "i")
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


@lru_cache(maxsize=20000)
def skeleton(token: str) -> str:
    """Phonetic skeleton of a single (already normalised) token."""
    has_indic = any(0x0900 <= ord(c) <= 0x0D7F for c in token)
    if has_indic:
        roman = _translit_dev(_to_devanagari(token))
    else:
        roman = token
    return _roman_skeleton(roman)


def skeleton_phrase(tokens: list[str] | str) -> str:
    if isinstance(tokens, str):
        tokens = tokens.split()
    return " ".join(s for s in (skeleton(t) for t in tokens) if s)
