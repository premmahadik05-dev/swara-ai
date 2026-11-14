"""Multilingual utterance parser: text -> structured order lines + intent cues.

Pipeline (all deterministic, no network):
  1. normalise + tokenise (Gujarati / Devanagari / Latin, digits unified)
  2. tag tokens: NUM, HUND, FRAC, UNIT, CONJ, FILL, AMBQ, CUE, WORD
  3. split into segments on conjunctions / commas
  4. inside each segment find product spans (exact -> phonetic skeleton -> fuzzy)
  5. extract quantity groups ("2 kilo", "dedh kilo", "બે કિલો", "one and a half kg")
  6. bind quantities to products (qty-first or product-first word order)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .lexicon import Lexicon, Match
from .normalize import dominant_script, normalize_text, script_word_counts, tokenize
from .translit import skeleton
from .units import WEIGHT, VOLUME
from . import vocab

SEP = ","
_DIGITS = re.compile(r"^\d+(\.\d+)?$")
_FRACTION = re.compile(r"^(\d+)/(\d+)$")
VERB_BEFORE_DO = {"de", "dena", "kar", "karo", "dedo", "dijiye", "dijie", "kijiye", "दे", "देना", "कर", "करो", "दीजिए"}
AND_WORDS = {normalize_text(w) for w in ["and", "aur", "और", "ane", "અને"]} | vocab.AND_WORDS_EXTRA
QUESTION_WORDS = vocab._norm_set(
    "kya|kaise|kab|kaha|kahan|kyun|kyu|what|how|why|when|where|which|who|shu|su|kem|"
    "क्या|कैसे|कब|कहाँ|कहां|क्यों|શું|ક્યાં|કેમ|કેવી|કેવું|तो|toh|to|bhi|hi|jee"
)
# tokens occurring in any intent-cue phrase are never mistaken for unknown product names
CUE_TOKENS: set[str] = set()
for _phrases in vocab.INTENT_CUES.values():
    for _p in _phrases:
        CUE_TOKENS.update(normalize_text(_p).split())
CUE_PHRASES: dict[str, list[str]] = {
    k: sorted({normalize_text(p) for p in v}, key=len, reverse=True) for k, v in vocab.INTENT_CUES.items()
}
NEED_VERBS = vocab._norm_set(
    "chahiye|chahie|chaiye|dedo|dijiye|dena|add|give|need|want|get|aapjo|apjo|aapo|apo|joie|joiye|joshe|"
    "चाहिए|चाहिये|दीजिए|दे|જોઈએ|જોઈશે|આપજો|આપો|આપ"
) | vocab.NEED_VERBS_EXTRA


@dataclass
class Tok:
    text: str
    tag: str
    value: Optional[Decimal] = None
    unit: Optional[str] = None


@dataclass
class QtyGroup:
    start: int
    end: int
    qty: Optional[Decimal]
    unit: Optional[str]
    ambiguous: bool = False
    implicit: bool = False


@dataclass
class ParsedLine:
    product_ids: list[int] = field(default_factory=list)
    match_kind: Optional[str] = None
    match_score: float = 0.0
    assumed_default: bool = False
    alternatives: list[int] = field(default_factory=list)
    qty: Optional[Decimal] = None
    unit: Optional[str] = None
    qty_ambiguous: bool = False
    qty_implicit: bool = False
    unknown_term: Optional[str] = None
    bare_unknown: bool = False  # unknown words with no quantity attached
    spoken: str = ""

    @property
    def resolved(self) -> bool:
        return len(self.product_ids) == 1


@dataclass
class ParseResult:
    text: str
    normalized: str
    tokens: list[str]
    script: str
    language: str  # gu | hi | hinglish | en | mr | bn | ta | te | kn | ml | pa
    lang_confident: bool
    lines: list[ParsedLine]
    cues: dict[str, list[str]]
    intent: str


# --------------------------------------------------------------------------- tagging
def _numeric_value(t: str) -> Optional[Decimal]:
    if _DIGITS.match(t):
        return Decimal(t)
    m = _FRACTION.match(t)
    if m and int(m.group(2)) != 0:
        return Decimal(int(m.group(1))) / Decimal(int(m.group(2)))
    return None


def tag_tokens(tokens: list[str]) -> list[Tok]:
    tags: list[Tok] = []
    n = len(tokens)
    for i, t in enumerate(tokens):
        if t == SEP:
            tags.append(Tok(t, "SEP"))
            continue
        v = _numeric_value(t)
        if v is not None:
            tags.append(Tok(t, "NUM", v))
        elif t == "do":
            tags.append(Tok(t, "NUM", Decimal(2)))  # refined below
        elif t in vocab.NUMBER_WORDS:
            tags.append(Tok(t, "NUM", Decimal(vocab.NUMBER_WORDS[t])))
        elif t in vocab.HUNDRED:
            tags.append(Tok(t, "HUND"))
        elif t in vocab.THOUSAND:
            tags.append(Tok(t, "THOU"))
        elif t in vocab.PREFIX_ADD:
            tags.append(Tok(t, "PADD", vocab.PREFIX_ADD[t]))
        elif t in vocab.PREFIX_SUB_QUARTER:
            tags.append(Tok(t, "PSUB", Decimal("-0.25")))
        elif t in vocab.FRACTION_WORDS:
            tags.append(Tok(t, "FRAC", vocab.FRACTION_WORDS[t]))
        elif t in vocab.UNIT_WORDS:
            tags.append(Tok(t, "UNIT", unit=vocab.UNIT_WORDS[t]))
        elif t in vocab.ARTICLE_ONE:
            tags.append(Tok(t, "ART", Decimal(1)))
        elif t in vocab.AMBIGUOUS_QTY:
            tags.append(Tok(t, "AMBQ"))
        elif t in vocab.CONJUNCTIONS:
            tags.append(Tok(t, "CONJ"))
        elif t in vocab.FILLERS:
            tags.append(Tok(t, "FILL"))
        elif t in CUE_TOKENS or t in QUESTION_WORDS:
            tags.append(Tok(t, "CUE"))
        else:
            tags.append(Tok(t, "WORD"))
    # refine "do": the Hindi verb "do" (give) vs the number two
    for i, tk in enumerate(tags):
        if tk.text != "do" or tk.tag != "NUM":
            continue
        prev_t = tags[i - 1].text if i > 0 else ""
        nxt = tags[i + 1] if i + 1 < n else None
        if prev_t in VERB_BEFORE_DO or nxt is None or nxt.tag in ("SEP", "CONJ", "CUE"):
            tags[i] = Tok("do", "FILL")
    # "a"/"an" is only a quantity before a unit ("a kilo of sugar")
    for i, tk in enumerate(tags):
        if tk.tag == "ART" and not (i + 1 < n and tags[i + 1].tag == "UNIT"):
            tags[i] = Tok(tk.text, "FILL")
    return tags


# --------------------------------------------------------------------------- number grammar
def _parse_number(tags: list[Tok], i: int, e: int) -> tuple[Optional[Decimal], int, bool]:
    """Parse a number expression at ``i``.  Returns (value, next_index, range_ambiguous)."""
    j = i
    prefix = Decimal(0)
    tg = tags[j].tag
    if tg == "ART":
        return Decimal(1), j + 1, False
    if tg == "PADD" and j + 1 < e and tags[j + 1].tag in ("NUM",):
        prefix = tags[j].value or Decimal(0)
        j += 1
    elif tg == "PSUB" and j + 1 < e and tags[j + 1].tag == "NUM":
        prefix = tags[j].value or Decimal(0)
        j += 1
    elif tg == "FRAC" and tags[j].text in vocab.PREFIX_ADD_QUARTER and j + 1 < e and tags[j + 1].tag == "NUM":
        prefix = Decimal("0.25")
        j += 1
    elif tg == "FRAC":
        v = tags[j].value or Decimal(0)
        j += 1
        if j < e and tags[j].tag == "HUND":  # "dhai sau" = 250
            return v * 100, j + 1, False
        if j < e and tags[j].tag == "THOU":
            return v * 1000, j + 1, False
        return v, j, False

    total = Decimal(0)
    cur = Decimal(0)
    last_kind = None
    last_val = Decimal(0)
    from_digits = False
    ambiguous = False
    started = False
    while j < e:
        tk = tags[j]
        if tk.tag == "NUM":
            v = tk.value or Decimal(0)
            is_digit = bool(_DIGITS.match(tk.text) or _FRACTION.match(tk.text))
            if last_kind == "NUM":
                tens_plus_unit = last_val >= 20 and last_val % 10 == 0 and v < 10 and not from_digits and not is_digit
                if tens_plus_unit:
                    cur += v
                    last_val = v
                    from_digits = False
                    j += 1
                    continue
                if is_digit or from_digits:
                    break  # two separate numbers
                ambiguous = True  # "do teen kilo": a range, not a quantity
                j += 1
                continue
            cur += v
            last_kind, last_val, from_digits, started = "NUM", v, is_digit, True
        elif tk.tag == "HUND" and (started or j == i):  # bare "sau" / "सौ" / "સો" = 100
            cur = (cur if cur else Decimal(1)) * 100
            last_kind, started = "HUND", True
        elif tk.tag == "THOU" and (started or j == i):  # bare "hazaar" = 1000
            total += (cur if cur else Decimal(1)) * 1000
            cur = Decimal(0)
            last_kind, started = "THOU", True
        else:
            break
        j += 1
    if not started:
        return None, i, False
    value = total + cur + prefix
    # "one and a half" / "ek aur aadha"
    if j + 1 < e and tags[j].tag == "CONJ" and tags[j].text in AND_WORDS:
        k = j + 1
        if tags[k].tag in ("ART", "FILL") and k + 1 < e:
            k += 1
        if k < e and tags[k].tag == "FRAC" and tags[k].text not in vocab.PREFIX_ADD_QUARTER:
            value += tags[k].value or Decimal(0)
            j = k + 1
    return value, j, ambiguous


def _protected_conj(tags: list[Tok]) -> set[int]:
    """CONJ tokens that belong to a quantity ("one *and* a half") and must not split segments."""
    prot: set[int] = set()
    n = len(tags)
    for i, tk in enumerate(tags):
        if tk.tag == "CONJ" and tk.text in AND_WORDS and 0 < i < n - 1 and tags[i - 1].tag == "NUM":
            k = i + 1
            if tags[k].tag in ("ART", "FILL") and k + 1 < n:
                k += 1
            if tags[k].tag == "FRAC" and tags[k].text not in vocab.PREFIX_ADD_QUARTER:
                prot.add(i)
    return prot


def _extract_groups(tags: list[Tok], s: int, e: int, covered: list[bool]) -> list[QtyGroup]:
    groups: list[QtyGroup] = []
    i = s
    while i < e:
        if covered[i]:
            i += 1
            continue
        tk = tags[i]
        if tk.tag == "AMBQ":
            groups.append(QtyGroup(i, i + 1, None, None, ambiguous=True))
            i += 1
            continue
        if tk.tag in ("NUM", "HUND", "THOU", "FRAC", "PADD", "PSUB", "ART"):
            qty, j, amb = _parse_number(tags, i, e)
            if qty is None:
                i += 1
                continue
            unit = None
            if qty < 1:  # "half a kilo" / "quarter of a kilo": skip the article between fraction and unit
                k = j
                while k < e and k - j < 2 and tags[k].tag in ("ART", "FILL"):
                    k += 1
                if k > j and k < e and tags[k].tag == "UNIT" and not covered[k]:
                    j = k
            if j < e and tags[j].tag == "UNIT" and not covered[j]:
                unit = tags[j].unit
                j += 1
            groups.append(QtyGroup(i, j, None if amb else qty, unit, ambiguous=amb))
            i = j
            continue
        if tk.tag == "UNIT":
            groups.append(QtyGroup(i, i + 1, Decimal(1), tk.unit, implicit=True))
            i += 1
            continue
        i += 1
    return groups


def _combine(groups: list[QtyGroup]) -> tuple[Optional[Decimal], Optional[str], bool, bool]:
    """Merge groups bound to one product: "1 kilo 500 gram" -> 1.5 kg."""
    if not groups:
        return None, None, False, False
    if any(g.ambiguous for g in groups):
        return None, groups[0].unit, True, False
    if len(groups) == 1:
        g = groups[0]
        return g.qty, g.unit, False, g.implicit
    units = [g.unit for g in groups]
    if all(u in WEIGHT for u in units):
        return sum((g.qty * WEIGHT[g.unit] for g in groups), Decimal(0)), "kg", False, False  # type: ignore[operator]
    if all(u in VOLUME for u in units):
        return sum((g.qty * VOLUME[g.unit] for g in groups), Decimal(0)), "l", False, False  # type: ignore[operator]
    g = groups[0]
    return g.qty, g.unit, False, g.implicit


# --------------------------------------------------------------------------- matching
def _find_matches(tags: list[Tok], s: int, e: int, lex: Lexicon) -> list[Match]:
    toks = [t.text for t in tags]
    matches: list[Match] = []
    i = s
    while i < e:
        if tags[i].tag != "WORD":
            i += 1
            continue
        found: Optional[Match] = None
        max_len = min(4, e - i)
        # pass 1: exact / skeleton, longest window first. A product name that contains a unit word ("water bottle",
        # "पानी की बोतल") can only be matched as an exact alias; the unit words inside it then belong to the name.
        for L in range(max_len, 0, -1):
            blockers = {tags[k].tag for k in range(i, i + L)}
            if blockers & {"SEP", "CONJ", "NUM"}:
                continue
            has_unit = "UNIT" in blockers
            if has_unit and L < 2:
                continue
            if not has_unit and tags[i + L - 1].tag != "WORD":
                continue
            m = lex.match_phrase(toks, i, i + L, allow_fuzzy=False, exact_only=has_unit)
            if m:
                found = m
                break
        # pass 2: fuzzy (ASR spelling noise)
        if not found:
            for L in range(min(3, max_len), 0, -1):
                if tags[i + L - 1].tag != "WORD":
                    continue
                if any(tags[k].tag in ("SEP", "CONJ", "NUM", "UNIT") for k in range(i, i + L)):
                    continue
                m = lex.match_phrase(toks, i, i + L, allow_fuzzy=True)
                if m:
                    found = m
                    break
        if found:
            matches.append(found)
            i = found.end
        else:
            i += 1
    return matches


def _split_segments(tags: list[Tok]) -> list[tuple[int, int]]:
    prot = _protected_conj(tags)
    segs: list[tuple[int, int]] = []
    start = 0
    for i, tk in enumerate(tags):
        if tk.tag in ("SEP", "CONJ") and i not in prot:
            if i > start:
                segs.append((start, i))
            start = i + 1
    if start < len(tags):
        segs.append((start, len(tags)))
    return segs


def _bind(
    seg: tuple[int, int], tags: list[Tok], matches: list[Match], groups: list[QtyGroup]
) -> list[ParsedLine]:
    s, e = seg
    toks = [t.text for t in tags]
    lines: list[ParsedLine] = []
    covered = [False] * len(tags)
    for m in matches:
        for k in range(m.start, m.end):
            covered[k] = True

    def mk(m: Match) -> ParsedLine:
        return ParsedLine(
            product_ids=list(m.product_ids),
            match_kind=m.kind,
            match_score=m.score,
            assumed_default=m.assumed_default,
            alternatives=list(m.alternatives),
            spoken=" ".join(toks[m.start : m.end]),
        )

    events: list[tuple[int, str, object]] = [(m.start, "P", m) for m in matches] + [(g.start, "Q", g) for g in groups]
    events.sort(key=lambda x: x[0])

    if matches:
        qty_first = bool(events) and events[0][1] == "Q"
        bound: list[tuple[ParsedLine, list[QtyGroup]]] = []
        if qty_first:
            pending: list[QtyGroup] = []
            for _pos, kind, obj in events:
                if kind == "Q":
                    pending.append(obj)  # type: ignore[arg-type]
                else:
                    ln = mk(obj)  # type: ignore[arg-type]
                    bound.append((ln, pending))
                    pending = []
            if pending and bound:  # trailing quantity after the last product: "2 kilo chawal 1 litre"
                last_ln, last_q = bound[-1]
                if not last_q:
                    bound[-1] = (last_ln, pending)
        else:
            cur: Optional[tuple[ParsedLine, list[QtyGroup]]] = None
            for _pos, kind, obj in events:
                if kind == "P":
                    cur = (mk(obj), [])  # type: ignore[arg-type]
                    bound.append(cur)
                elif cur is not None:
                    cur[1].append(obj)  # type: ignore[arg-type]
        for ln, qgs in bound:
            qty, unit, amb, implicit = _combine(qgs)
            ln.qty, ln.unit, ln.qty_ambiguous, ln.qty_implicit = qty, unit, amb, implicit
            lines.append(ln)
        return lines

    # no product matched in this segment
    words = [tags[k].text for k in range(s, e) if tags[k].tag == "WORD"]
    if groups:
        qty, unit, amb, implicit = _combine(groups[:1] if len(groups) > 1 and not groups[0].unit else groups)
        lines.append(
            ParsedLine(
                qty=qty, unit=unit, qty_ambiguous=amb, qty_implicit=implicit,
                unknown_term=" ".join(words) or None, spoken=" ".join(words),
            )
        )
    elif words:
        lines.append(ParsedLine(unknown_term=" ".join(words), bare_unknown=True, spoken=" ".join(words)))
    return lines


# --------------------------------------------------------------------------- intents & language
def _cue_hits(norm: str) -> dict[str, list[str]]:
    padded = f" {norm} "
    hits: dict[str, list[str]] = {}
    for intent, phrases in CUE_PHRASES.items():
        for p in phrases:
            if p and f" {p} " in padded:
                hits.setdefault(intent, []).append(p)
    # a leading "hi" is a greeting; "itna hi" (Hindi emphasis) is not
    if norm.split()[:1] == ["hi"]:
        hits.setdefault("greeting", []).append("hi")
    return hits


# Indic script -> language key. Devanagari is shared by Hindi and Marathi and is settled by _devanagari_language().
SCRIPT_LANG = {"gu": "gu", "bn": "bn", "pa": "pa", "ta": "ta", "te": "te", "kn": "kn", "ml": "ml"}
_SCRIPT_PRIORITY = ("gu", "hi", "bn", "pa", "ta", "te", "kn", "ml")  # on a tie the older languages win


def _devanagari_language(words: list[str], hint: Optional[str]) -> str:
    """Hindi or Marathi? Marker words decide; the language the person picked (``hint``) breaks ties and is only
    overruled when the sentence has two or more words of the other language and none of the chosen one."""
    mr = sum(1 for w in words if w in vocab.MARATHI_MARKERS)
    hi = sum(1 for w in words if w in vocab.HINDI_DEV_MARKERS)
    if hint == "mr":
        return "hi" if (hi >= 2 and mr == 0) else "mr"
    if hint == "hi":
        return "mr" if (mr >= 2 and hi == 0) else "hi"
    return "mr" if mr > hi else "hi"


def _script_language(script: str, words: list[str], hint: Optional[str]) -> str:
    return _devanagari_language(words, hint) if script == "hi" else SCRIPT_LANG[script]


def detect_language(text: str, tokens: list[str], hint: Optional[str] = None) -> tuple[str, bool]:
    """Language of an utterance.  Indic scripts identify their language (Devanagari: Hindi or Marathi via
    :func:`_devanagari_language`); Latin text is Gujarati-roman / Hinglish / English by marker words, or one of the
    newer languages typed in Latin when it carries that language's marker words.  ``hint`` is the language picked in
    the selector; it only resolves ambiguity, it never turns Latin English into another language."""
    words = [t for t in tokens if t != SEP and not _DIGITS.match(t)]
    counts = script_word_counts(words)
    lat_t = counts.get("latin", 0)
    indic = {k: n for k, n in counts.items() if k != "latin"}
    # Indic-script words win even inside a code-mixed sentence ("મને 2 kg sugar અને 1 litre milk જોઈએ")
    if indic:
        best = max(indic, key=lambda k: (indic[k], -_SCRIPT_PRIORITY.index(k)))
        if indic[best] >= 2 or lat_t <= 2:
            return _script_language(best, words, hint), True
    script = dominant_script(text)
    if script in _SCRIPT_PRIORITY:
        return _script_language(script, words, hint), True
    # typed in Latin script: a newer language's own marker words
    roman = {k: sum(1 for w in words if w in ms) for k, ms in vocab.ROMAN_MARKERS.items()}
    if hint in roman and roman[hint]:
        return hint, True
    best_roman = max(roman, key=roman.get) if roman else None  # type: ignore[arg-type]
    if best_roman and roman[best_roman] >= 2:
        return best_roman, True
    gu_hits = sum(1 for w in words if w in vocab.GUJARATI_ROMAN)
    hi_hits = sum(1 for w in words if w in vocab.HINGLISH_STRONG and w not in vocab.GUJARATI_ROMAN)
    if gu_hits and gu_hits >= hi_hits:
        return "gu", True
    en_hits = sum(1 for w in words if w in vocab.ENGLISH_MARKERS)
    # one stray Hindi word inside an otherwise English sentence ("bhai give me two kg rice please") stays English
    weak = sum(1 for w in words if w in vocab.HINGLISH_WEAK)
    if (hi_hits and not (hi_hits == 1 and en_hits >= 3)) or (weak and not en_hits):
        return "hinglish", True
    return "en", en_hits >= 1


def primary_intent(cues: dict[str, list[str]], lines: list[ParsedLine], tokens: list[str], cart_skus_present: bool = False) -> str:
    has_product = any(ln.product_ids for ln in lines)
    has_qty_or_unknown = any((ln.qty is not None or ln.qty_ambiguous or (ln.unknown_term and not ln.bare_unknown)) for ln in lines)
    need_verb = any(t in NEED_VERBS for t in tokens)
    if has_product or has_qty_or_unknown:
        if "remove" in cues and has_product:
            return "remove"
        if "query" in cues and not need_verb:
            return "query"
        if "set" in cues and cart_skus_present:
            return "set"
        return "add"
    for name in ("cancel", "done", "confirm", "deny", "greeting"):
        if name in cues:
            return name
    if "query" in cues and ("done" in cues or "total" in tokens):
        return "done"
    if any(ln.unknown_term for ln in lines):
        return "add"
    return "unknown"


GENITIVE = frozenset({"ki", "ka", "ke", "की", "का", "के", "ની", "નો", "નું"})


def _drop_genitives(tokens: list[str]) -> list[str]:
    """"moong ki dal" / "मूंग की दाल" -> "moong dal": a particle between two plain words is not part of the phrase."""
    if not any(t in GENITIVE for t in tokens):
        return tokens
    tags = tag_tokens(tokens)
    return [t for i, t in enumerate(tokens)
            if not (t in GENITIVE and 0 < i < len(tokens) - 1 and tags[i - 1].tag == "WORD" and tags[i + 1].tag == "WORD")]


def parse_utterance(text: str, lex: Lexicon, cart_has_items: bool = False, language_hint: Optional[str] = None) -> ParseResult:
    raw_tokens = tokenize(text)
    language, confident = detect_language(text, raw_tokens, language_hint)  # particles like "ki/ka" are language evidence
    tokens = _drop_genitives(raw_tokens)
    norm_plain = normalize_text(text)
    tags = tag_tokens(tokens)

    lines: list[ParsedLine] = []
    for seg in _split_segments(tags):
        s, e = seg
        matches = _find_matches(tags, s, e, lex)
        covered = [False] * len(tags)
        for m in matches:
            for k in range(m.start, m.end):
                covered[k] = True
        groups = _extract_groups(tags, s, e, covered)
        lines.extend(_bind(seg, tags, matches, groups))

    cues = _cue_hits(norm_plain)
    intent = primary_intent(cues, lines, tokens, cart_has_items)
    # bare unknown words are only meaningful for add/query intents
    if intent not in ("add", "query"):
        lines = [ln for ln in lines if not ln.bare_unknown]
    return ParseResult(
        text=text,
        normalized=norm_plain,
        tokens=tokens,
        script=dominant_script(text),
        language=language,
        lang_confident=confident,
        lines=lines,
        cues=cues,
        intent=intent,
    )
