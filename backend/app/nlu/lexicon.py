"""Product lexicon: exact -> phonetic-skeleton -> fuzzy matching of spoken product names."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from rapidfuzz import fuzz, process

from . import vocab
from .normalize import normalize_text
from .translit import skeleton_phrase

MIN_STEM = 2  # characters left after a case ending is taken off


@dataclass
class ProductView:
    """ORM-independent view of a product used by the NLU / dialogue layers."""

    id: int
    sku: str
    name_en: str
    name_gu: str
    name_hi: str
    unit: str  # kg | l | pack | pc
    price_paise: int
    stock: Decimal
    aliases: list[str] = field(default_factory=list)
    default_for: list[str] = field(default_factory=list)
    pack_size: Optional[Decimal] = None
    pack_size_unit: Optional[str] = None
    category: str = ""
    reorder_level: Decimal = Decimal(0)
    is_active: bool = True
    # names in the languages added in 2.3.0: {"mr": ["display name", "alias", ...], ...}; only the 65 staples have them
    names: dict[str, list[str]] = field(default_factory=dict)

    def display_name(self, lang: str) -> str:
        if lang == "gu" and self.name_gu:
            return self.name_gu
        if lang == "hi" and self.name_hi:
            return self.name_hi
        local = self.names.get(lang)
        if local:
            return local[0]
        return self.name_en

    def all_names(self) -> list[str]:
        """Every name this product can be called, in every language (for matching and for ASR bias words)."""
        extra = [n for names in self.names.values() for n in names]
        return [n for n in (self.name_en, self.name_gu, self.name_hi, *self.aliases, *self.default_for, *extra) if n]


def _stems(token: str) -> list[str]:
    """Candidate stems of a word with a case ending / clitic taken off (Dravidian and Bengali/Marathi/Punjabi
    agglutination: "പാലും" = "പാൽ" + "ഉം"). Latin words are left alone."""
    if token.isascii():
        return []
    out = [token[: -len(s)] for s in vocab.CASE_SUFFIXES if token.endswith(s) and len(token) - len(s) >= MIN_STEM]
    return out[:4]


@dataclass
class Match:
    product_ids: list[int]  # more than one => ambiguous
    start: int
    end: int  # exclusive token index
    kind: str  # exact | skeleton | stem (a case ending taken off) | fuzzy
    score: float  # 0-100
    alias: str
    assumed_default: bool = False  # generic word resolved to the shop's default product
    alternatives: list[int] = field(default_factory=list)


class Lexicon:
    FUZZY_MIN_SKEL = 4
    FUZZY_CUTOFF_1 = 86.0
    FUZZY_CUTOFF_N = 90.0
    # A Latin-script word (a brand token such as "Nero", "Raw" or "Day") may reach a name written ONLY in a 2.3.0 language
    # pack's native script by sound alone when the two sound-alike skeletons are at least this long. Shorter skeletons
    # are too easy to hit by accident: "Nero" sounds like Telugu/Kannada "నీరు" (water), "Raw" like "రవ్వ" (semolina).
    PACK_SOUND_MIN_SKEL = 5

    def __init__(self, products: list[ProductView]):
        self.products = {p.id: p for p in products if p.is_active}
        self._exact: dict[str, set[int]] = {}
        self._skel: dict[str, set[int]] = {}
        self._default_exact: dict[str, int] = {}
        self._default_skel: dict[str, int] = {}
        self._fuzzy_keys: list[str] = []
        self._fuzzy_owner: list[set[int]] = []
        self._pack_only_skel: set[str] = set()  # skeletons that only a native-script 2.3.0 pack name produces
        self._build()

    # ---------------------------------------------------------------- build
    def _build(self) -> None:
        skel_to_owner: dict[str, set[int]] = {}
        pack_native: set[str] = set()  # skeletons produced by a native-script pack name
        other: set[str] = set()  # skeletons produced by any other name (Latin, Gujarati, Hindi, typed aliases ...)
        for p in self.products.values():
            pack_names = {n for names in p.names.values() for n in names}
            for raw in p.all_names():
                if not raw:
                    continue
                norm = normalize_text(raw)
                if not norm:
                    continue
                self._exact.setdefault(norm, set()).add(p.id)
                sk = skeleton_phrase(norm)
                if sk:
                    self._skel.setdefault(sk, set()).add(p.id)
                    skel_to_owner.setdefault(sk, set()).add(p.id)
                    (pack_native if raw in pack_names and not norm.isascii() else other).add(sk)
            for raw in p.default_for:
                norm = normalize_text(raw)
                if norm:
                    self._default_exact[norm] = p.id
                    sk = skeleton_phrase(norm)
                    if sk:
                        self._default_skel[sk] = p.id
        self._pack_only_skel = pack_native - other
        for sk, owners in skel_to_owner.items():
            if len(sk.replace(" ", "")) >= self.FUZZY_MIN_SKEL:
                self._fuzzy_keys.append(sk)
                self._fuzzy_owner.append(owners)

    def _too_weak(self, phrase: str, key: str) -> bool:
        """True when a Latin-script phrase would reach a native-script pack name by a short sound-alike skeleton only."""
        return phrase.isascii() and key in self._pack_only_skel and len(key.replace(" ", "")) < self.PACK_SOUND_MIN_SKEL

    # ---------------------------------------------------------------- resolve
    def _resolve(self, ids: set[int], default_map: dict[str, int], key: str) -> tuple[list[int], bool, list[int]]:
        ids_l = sorted(ids)
        d = default_map.get(key)
        if d is not None and d in ids:
            # a generic word ("biscuit", "oil") that the shop resolves to its default product
            return [d], True, [i for i in ids_l if i != d]
        return ids_l, False, []

    def match_phrase(self, tokens: list[str], start: int, end: int, allow_fuzzy: bool = True, exact_only: bool = False) -> Optional[Match]:
        phrase = " ".join(tokens[start:end])
        if phrase in self._exact:
            ids, assumed, alts = self._resolve(self._exact[phrase], self._default_exact, phrase)
            return Match(ids, start, end, "exact", 100.0, phrase, assumed, alts)
        if exact_only:
            return None
        sk = skeleton_phrase(phrase)
        if sk and sk in self._skel and not self._too_weak(phrase, sk):
            ids, assumed, alts = self._resolve(self._skel[sk], self._default_skel, sk)
            return Match(ids, start, end, "skeleton", 97.0, phrase, assumed, alts)
        for stem in _stems(tokens[end - 1]):
            head = " ".join([*tokens[start : end - 1], stem])
            if head in self._exact:
                ids, assumed, alts = self._resolve(self._exact[head], self._default_exact, head)
                return Match(ids, start, end, "stem", 96.0, phrase, assumed, alts)
            hsk = skeleton_phrase(head)
            if hsk and hsk in self._skel:
                ids, assumed, alts = self._resolve(self._skel[hsk], self._default_skel, hsk)
                return Match(ids, start, end, "stem", 94.0, phrase, assumed, alts)
        if allow_fuzzy and sk and len(sk.replace(" ", "")) >= self.FUZZY_MIN_SKEL and self._fuzzy_keys:
            cutoff = self.FUZZY_CUTOFF_1 if end - start == 1 else self.FUZZY_CUTOFF_N
            best = process.extractOne(sk, self._fuzzy_keys, scorer=fuzz.ratio, score_cutoff=cutoff)
            if best and not self._too_weak(phrase, best[0]):
                key, score, idx = best
                owners = self._fuzzy_owner[idx]
                ids, assumed, alts = self._resolve(owners, self._default_skel, key)
                return Match(ids, start, end, "fuzzy", float(score), phrase, assumed, alts)
        return None

    def suggest(self, phrase_tokens: list[str], limit: int = 3, cutoff: float = 62.0) -> list[tuple[int, float]]:
        """Loose nearest-product suggestions for an unknown term (used for 'did you mean')."""
        sk = skeleton_phrase(phrase_tokens)
        if not sk or not self._fuzzy_keys:
            return []
        results = process.extract(sk, self._fuzzy_keys, scorer=fuzz.ratio, score_cutoff=cutoff, limit=limit * 2)
        seen: dict[int, float] = {}
        for _key, score, idx in results:
            for pid in self._fuzzy_owner[idx]:
                if pid not in seen or score > seen[pid]:
                    seen[pid] = float(score)
        return sorted(seen.items(), key=lambda kv: -kv[1])[:limit]
