"""Per-language NLU packs for the languages added in 2.3.0 (Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam, Punjabi).

A pack is plain data: number words, fractions, units, intent cue phrases, reply templates and the product names for the
65 staple SKUs. ``nlu/vocab.py`` merges the vocabulary into the shared tables (every list is written in natural spelling
and normalised there), ``nlu/nlg.py`` merges the reply templates, and ``services/catalog.py`` attaches the product names.

HONEST STATUS: these packs were authored for this release. They are unit-tested (``tests/test_languages_nlu.py``) but have
**not** been reviewed by native speakers and have **not** been validated against real Prisma v2.5 output. Treat them as a
careful first draft; fix a word by editing the one pack file - nothing else needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LangPack:
    key: str
    numbers: dict[str, int]  # "word|word|word": value   (pipe = alternative spellings)
    hundred: str
    thousand: str
    fractions: dict[str, str]  # "words": "0.5"
    units: dict[str, str]  # "words": kg | g | l | ml | pack | pc | dozen | bottle | box | bag
    conj: str  # words that join two items ("and", "then")
    and_words: str  # the subset of `conj` that means plain "and" (used in "one and a half")
    fillers: str  # words that carry no product meaning (pronouns, "want", "give", honorifics, case particles)
    need_verbs: str  # "want / give" verbs: their presence means a price question is really an order
    cues: dict[str, list[str]]  # intent -> phrases (confirm, deny, cancel, done, remove, set, query, greeting)
    unit_labels: dict[str, tuple[str, str]]  # canonical unit -> (singular, plural) as spoken in replies
    and_join: str  # " word " used between the last two items of a read-back
    templates: dict[str, str]  # reply templates keyed like nlg.T (all keys required)
    names: dict[str, str]  # SKU -> "primary name|alias|alias" (primary is what the reply shows)
    prefix_add: str = ""  # "saade" = + 0.5 on the next number
    prefix_add_quarter: str = ""  # "sava" = + 0.25 (also a bare 1.25)
    prefix_sub_quarter: str = ""  # "paune" = - 0.25
    ambiguous: str = ""  # "a little / some / a lot": we must ask how much
    markers: str = ""  # native-script words that tell this language from a script-mate (Marathi vs Hindi)
    roman_markers: str = ""  # Latin-script words that identify this language in typed text
    suffixes: str = ""  # case endings / clitics tried when a word is not found as typed
    extra: dict[str, str] = field(default_factory=dict)


# Words that are Hindi and not Marathi (Devanagari). Used with the Marathi markers to tell the two apart.
HINDI_DEVANAGARI_MARKERS = (
    "मुझे|मुझको|मेरे|मेरा|मेरी|और|है|हैं|चाहिए|चाहिये|दीजिए|दीजिये|कृपया|आपको|चीनी|चावल|आटा|नमक|प्याज|आलू|लहसुन|अदरक|"
    "दो|पाँच|पांच|छह|नौ|दस|ग्यारह|बारह|डेढ़|डेढ|आधा|पौना|ढाई|साढ़े|साढे|कितना|कितने|नहीं|हाँ|हां|क्या|थोड़ा|थोड़ी|बस|कर दो"
)


def load_all() -> dict[str, LangPack]:
    from . import bn, kn, ml, mr, pa, ta, te

    packs = {m.PACK.key: m.PACK for m in (mr, bn, ta, te, kn, ml, pa)}
    for key, pack in packs.items():
        missing = _missing_templates(pack)
        if missing:  # a pack with a hole would fall back to English mid-conversation: fail loudly at import instead
            raise ValueError(f"language pack {key!r} is missing reply templates: {sorted(missing)}")
    return packs


# the reply keys every pack must supply (kept here so a new pack cannot forget one)
REQUIRED_TEMPLATES = (
    "greeting", "added", "added_only", "updated", "assumed", "confirm_summary", "confirmed", "cancelled", "need_qty",
    "need_unit", "confirm_unit", "unit_wrong", "need_pack_count", "need_whole", "choose_product", "out_of_stock",
    "no_more_stock", "confirm_partial", "unknown", "confirm_suggestion", "removed", "not_in_cart", "cart_empty",
    "what_else", "no_problem_change", "price_one", "price_qty", "price_oos", "didnt_understand", "no_speech", "skipped",
    "stock_changed",
)


def _missing_templates(pack: LangPack) -> set[str]:
    return set(REQUIRED_TEMPLATES) - set(pack.templates)
