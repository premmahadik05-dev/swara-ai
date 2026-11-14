"""Central language registry - the one place that says which languages SWARA AI offers and how each maps to Gnani.

Add a language: add one :class:`Language` entry below (plus its NLU pack in ``nlu/langpacks``).
Disable a language without touching code: set ``DISABLED_LANGUAGES=mr,bn`` in ``.env``.

Every code and voice name here comes from Gnani's published documentation (checked 2026-11-10):

* Speech-to-text language codes (Prisma v2.5 and v3.0): https://docs.gnani.ai/api/STT/prisma-v2.5.md
  ``bn-IN en-IN gu-IN hi-IN kn-IN ml-IN mr-IN pa-IN ta-IN te-IN``. One code per request; v2.5 has no
  auto-detect. English-Hindi mixed speech is handled through ``en-IN`` (Latin-script output).
* Text-to-speech ``language`` values and the Timbre v2.5 voice catalogue:
  https://docs.gnani.ai/api/TTS/available-voices.md - ``hi-en`` (voice Poorvi) is the documented Hinglish value.

Nothing here claims a language *works*. Whether Gnani accepted a code or voice with a real key is recorded by
``scripts/verify_gnani.py`` in ``eval/results/live_verification.json`` and surfaced by ``GET /api/languages``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    from .config import Settings

DOC_STT = "https://docs.gnani.ai/api/STT/prisma-v2.5.md"
DOC_TTS_VOICES = "https://docs.gnani.ai/api/TTS/available-voices.md"
DOC_TTS_NORMALIZATION = "https://docs.gnani.ai/api/TTS/text-normalization.md"
DOCS_CHECKED_ON = "2026-11-10"

# Timbre v2.5 catalogue (each voice has one preferred language; another language "may reduce quality").
# Voices from the v3.0 catalogue are different names and are rejected with HTTP 400 on timbre-v2.5.
TIMBRE_V25_VOICES: dict[str, tuple[str, ...]] = {
    "hi-IN": ("Ambuja", "Bhavna", "Chitra", "Deepak", "Hemraj", "Jalaj", "Jwala", "Nalini", "Omkar", "Roopesh", "Urmila", "Vikrant", "Yashvi"),
    "en-IN": ("Devika", "Girish", "Kaveri", "Pranav", "Shlok", "Trupti"),
    "ta-IN": ("Asmita", "Brinda", "Noopur", "Trisha", "Vedika"),
    "te-IN": ("Lavanya", "Lehara", "Suhana", "Varuni", "Yukti"),
    "kn-IN": ("Kavin", "Saanvi"),
    "ml-IN": ("Reshma", "Riyaan"),
    "mr-IN": ("Ishaan", "Zahira"),
    "bn-IN": ("Dhruva", "Kirra"),
    "gu-IN": ("Falak", "Veera"),
    "pa-IN": ("Mehuli", "Zayan"),
    "hi-en": ("Poorvi",),
}

# Gnani's text-normalization guide: deepest TTS text handling for Hindi, Marathi, Tamil, English; the other six are
# "fully supported" with word choices still being refined.
_TTS_DEEP = {"hi-IN", "mr-IN", "ta-IN", "en-IN"}


@dataclass(frozen=True)
class Language:
    key: str  # what the app, the database and the UI use: gu | hi | en | hinglish | mr | bn | ta | te | kn | ml | pa
    name: str
    native: str
    script: str  # latin | devanagari | gujarati | bengali | gurmukhi | tamil | telugu | kannada | malayalam
    stt_code: str  # Gnani `language_code` for Prisma
    tts_code: str  # Gnani `language` for Timbre
    default_voice: str
    origin: str  # "original" = shipped before the multilingual release; "expansion" = added in 2.3.0
    sample: str  # a short kirana order used by the tests and by scripts/verify_gnani.py (authored here, see nlu_status)
    sample_expect: tuple[tuple[str, str, str], ...] = (("SUGAR", "2", "kg"), ("MILK", "1", "l"))
    stt_note: str = ""

    @property
    def voices(self) -> tuple[str, ...]:
        return TIMBRE_V25_VOICES[self.tts_code]

    @property
    def sample_expect_pairs(self) -> list[tuple[str, float]]:
        """``sample_expect`` as (SKU, quantity) pairs, the shape the live scripts compare against."""
        return [(sku, float(qty)) for sku, qty, _unit in self.sample_expect]

    @property
    def nlu_status(self) -> str:
        """How far the NLU/reply text for this language can be trusted. Honest, not promotional."""
        if self.origin == "original":
            return "tested"
        return "authored"  # written for this release; unit-tested here; not reviewed by a native speaker; not validated on real Prisma output

    @property
    def tts_depth(self) -> str:
        return "deep" if self.tts_code in _TTS_DEEP else "supported"


_SAMPLE = {
    "gu": "મને બે કિલો ખાંડ અને એક લીટર દૂધ જોઈએ છે",
    "hi": "मुझे दो किलो चीनी और एक लीटर दूध चाहिए",
    "en": "I need two kilos of sugar and one litre of milk",
    "hinglish": "mujhe do kilo chini aur ek litre doodh chahiye",
    "mr": "मला दोन किलो साखर आणि एक लिटर दूध पाहिजे",
    "bn": "আমার দুই কেজি চিনি আর এক লিটার দুধ লাগবে",
    "ta": "எனக்கு இரண்டு கிலோ சர்க்கரை மற்றும் ஒரு லிட்டர் பால் வேண்டும்",
    "te": "నాకు రెండు కిలోల చక్కెర మరియు ఒక లీటర్ పాలు కావాలి",
    "kn": "ನನಗೆ ಎರಡು ಕಿಲೋ ಸಕ್ಕರೆ ಮತ್ತು ಒಂದು ಲೀಟರ್ ಹಾಲು ಬೇಕು",
    "ml": "എനിക്ക് രണ്ട് കിലോ പഞ്ചസാരയും ഒരു ലിറ്റർ പാലും വേണം",
    "pa": "ਮੈਨੂੰ ਦੋ ਕਿਲੋ ਖੰਡ ਅਤੇ ਇੱਕ ਲੀਟਰ ਦੁੱਧ ਚਾਹੀਦਾ ਹੈ",
}

_EN_NOTE = "Prisma v2.5 handles English-Hindi mixed speech through en-IN; the transcript comes back in Latin script."

# The order here is the order of the language selector.
LANGUAGE_LIST: tuple[Language, ...] = (
    Language("gu", "Gujarati", "ગુજરાતી", "gujarati", "gu-IN", "gu-IN", "Falak", "original", _SAMPLE["gu"]),
    Language("hi", "Hindi", "हिन्दी", "devanagari", "hi-IN", "hi-IN", "Nalini", "original", _SAMPLE["hi"]),
    Language("en", "English (India)", "English", "latin", "en-IN", "en-IN", "Devika", "original", _SAMPLE["en"]),
    Language("hinglish", "Hinglish", "Hinglish", "latin", "en-IN", "hi-en", "Poorvi", "original", _SAMPLE["hinglish"], stt_note=_EN_NOTE),
    Language("mr", "Marathi", "मराठी", "devanagari", "mr-IN", "mr-IN", "Zahira", "expansion", _SAMPLE["mr"]),
    Language("bn", "Bengali", "বাংলা", "bengali", "bn-IN", "bn-IN", "Kirra", "expansion", _SAMPLE["bn"]),
    Language("ta", "Tamil", "தமிழ்", "tamil", "ta-IN", "ta-IN", "Asmita", "expansion", _SAMPLE["ta"]),
    Language("te", "Telugu", "తెలుగు", "telugu", "te-IN", "te-IN", "Lavanya", "expansion", _SAMPLE["te"]),
    Language("kn", "Kannada", "ಕನ್ನಡ", "kannada", "kn-IN", "kn-IN", "Saanvi", "expansion", _SAMPLE["kn"]),
    Language("ml", "Malayalam", "മലയാളം", "malayalam", "ml-IN", "ml-IN", "Reshma", "expansion", _SAMPLE["ml"]),
    Language("pa", "Punjabi", "ਪੰਜਾਬੀ", "gurmukhi", "pa-IN", "pa-IN", "Mehuli", "expansion", _SAMPLE["pa"]),
)
LANGUAGES: dict[str, Language] = {lang.key: lang for lang in LANGUAGE_LIST}
ORDER: tuple[str, ...] = tuple(LANGUAGES)

# Everything the voice endpoints accept besides a language key.
STT_MODES = ("auto", "mixed")  # Prisma v3.0 only (v2.5: "one code per request", no auto-detect)

# Derived maps (kept under the old names so existing imports keep working)
LANG_TO_STT: dict[str, str] = {k: v.stt_code for k, v in LANGUAGES.items()}
LANG_TO_TTS: dict[str, str] = {k: v.tts_code for k, v in LANGUAGES.items()}
STT_CODES: tuple[str, ...] = tuple(sorted({v.stt_code for v in LANGUAGES.values()}))
TTS_CODES: tuple[str, ...] = tuple(sorted({v.tts_code for v in LANGUAGES.values()}))

# The ten languages Gnani documents for Prisma v2.5 / Timbre v2.5 (hi-en is a Timbre value, not an extra STT language)
DOCUMENTED_STT_CODES = ("bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN")


class LanguageError(Exception):
    """A language choice the server will not act on. ``code`` is machine-readable; ``message`` is for people."""

    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def get(key: str) -> Optional[Language]:
    return LANGUAGES.get(key)


def disabled_keys(settings: "Settings") -> set[str]:
    """Keys listed in DISABLED_LANGUAGES. Unknown names are ignored; English can never be disabled
    (it is the language of the browser fallback messages)."""
    raw = getattr(settings, "disabled_languages", "") or ""
    keys = {p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()}
    return {k for k in keys if k in LANGUAGES and k != "en"}


def enabled_keys(settings: "Settings") -> list[str]:
    off = disabled_keys(settings)
    return [k for k in ORDER if k not in off]


def is_enabled(settings: "Settings", key: str) -> bool:
    return key in LANGUAGES and key not in disabled_keys(settings)


def configured_voice(settings: "Settings", key: str) -> str:
    """The voice chosen in .env / Settings for this language, or the registry default when the saved name is not in
    the documented Timbre v2.5 catalogue for the language (so a stale name can never reach Gnani and fail with a 400)."""
    lang = LANGUAGES[key]
    chosen = getattr(settings, f"tts_voice_{key}", "") or ""
    return chosen if chosen in lang.voices else lang.default_voice


def choose(settings: "Settings", value: str) -> str:
    """Validate a language choice from a request (a language key, or ``auto``/``mixed``).

    Raises :class:`LanguageError` with a precise reason instead of silently substituting another language:
    unknown value, language switched off, or an auto/mixed mode the configured model cannot do."""
    v = value or ""  # exact keys only: "GU" or " gu" is a typo to report, not something to guess at
    if v in STT_MODES:
        if settings.gnani_stt_model != "prisma-v3.0":
            raise LanguageError(
                "AUTO_DETECT_NEEDS_V3",
                "Automatic language detection is not available on Prisma v2.5 (one language per request). "
                "Pick the language being spoken, or set GNANI_STT_MODEL=prisma-v3.0.",
            )
        return v
    if v not in LANGUAGES:
        raise LanguageError("BAD_LANGUAGE", f"language must be one of {sorted([*LANGUAGES, *STT_MODES])}")
    if v in disabled_keys(settings):
        raise LanguageError("LANGUAGE_DISABLED", f"{LANGUAGES[v].name} is switched off on this server (DISABLED_LANGUAGES).")
    return v


def hint(settings: "Settings", value: Optional[str]) -> Optional[str]:
    """The language the user *selected*, as a hint for text understanding (``None`` = detect from the text itself).

    Empty, ``auto`` and ``mixed`` mean "no single language was picked", so there is no hint (and, unlike :func:`choose`, they
    are fine on Prisma v2.5 because nothing is sent to Gnani for a typed sentence). Anything else must be an enabled language."""
    v = value or ""  # exact keys only: "GU" or " gu" is a typo to report, not something to guess at
    if not v or v in STT_MODES:
        return None
    return choose(settings, v)

