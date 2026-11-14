"""Voice selection and STT language mapping (codes and voices come from the central registry, app/languages.py)."""
from __future__ import annotations

import unicodedata

from ..config import Settings
from ..languages import (  # noqa: F401  (TIMBRE_V25_VOICES, LANG_TO_* are re-exported for older imports)
    LANG_TO_STT, LANG_TO_TTS, LANGUAGES, TIMBRE_V25_VOICES, LanguageError, configured_voice, choose,
)


def tts_params(settings: Settings, reply_lang: str) -> tuple[str, str]:
    """Return (voice, Timbre ``language``) for a reply language key.

    A key that is not in the registry (older rows) is spoken as English, which is also what the reply text is."""
    key = reply_lang if reply_lang in LANGUAGES else "en"
    return configured_voice(settings, key), LANG_TO_TTS[key]


def stt_params(settings: Settings, language_pref: str) -> tuple[str, str | None]:
    """Map the language choice to (language_code, format).

    A language key -> its single Prisma code (v2.5 takes exactly one language per request; English-Hindi mixed speech
    goes through ``en-IN``). ``auto`` / ``mixed`` exist only on Prisma v3.0 (``indic-auto`` / a comma list with
    ``format=codemix``). On v2.5 they raise :class:`LanguageError` - there is no silent substitute language.
    A language that is switched off raises too.
    """
    pref = choose(settings, language_pref)
    if pref == "auto":
        return "indic-auto", None
    if pref == "mixed":
        return "gu-IN,en-IN", "codemix"
    return LANG_TO_STT[pref], None


def _is_bias_word(w: str) -> bool:
    # Gnani: one word, letters only (Latin or Indian scripts); no spaces/digits/punctuation
    return bool(w) and all(unicodedata.category(c)[0] in ("L", "M") for c in w)


def bias_words(alias_lists: list[list[str]], script: str, limit: int = 100) -> list[str]:
    """Pick single-word, letters-only vocabulary in the right script for ``bias_list`` (Prisma v2.5).

    ``script`` is a key from ``nlu.normalize.SCRIPT_RANGES`` (hi, gu, bn, ...) or ``latin``."""
    from ..nlu.normalize import dominant_script

    seen: dict[str, None] = {}
    for aliases in alias_lists:
        for a in aliases:
            for w in a.split():
                if _is_bias_word(w) and dominant_script(w) == script and len(w) >= 3:
                    seen.setdefault(w.lower(), None)
                if len(seen) >= limit:
                    return list(seen)
    return list(seen)


def bias_script(language: str) -> str:
    """Which script's vocabulary to send as bias words for a language key (Latin for English / Hinglish)."""
    from ..nlu.normalize import SCRIPT_KEY_BY_NAME

    lang = LANGUAGES.get(language)
    return SCRIPT_KEY_BY_NAME.get(lang.script, "latin") if lang else "latin"
