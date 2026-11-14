"""The language registry (app/languages.py): the one place that says which languages, codes and voices exist.

OFFLINE tests. They read the registry and the settings object; no network, no Gnani. They check that what we send to Gnani is a code
or voice that Gnani's documentation lists (the lists below were copied from docs.gnani.ai on 2026-11-10), and that disabling a language
is refused clearly instead of being swapped for another language. They cannot show that the live service accepts a code today - only
``scripts/verify_gnani.py`` with a real key can.
"""
from __future__ import annotations

import pytest

from app import languages as reg
from app.config import Settings
from app.gnani.client import effective_stt_format
from app.gnani.voices import stt_params, tts_params

# Prisma v2.5 language codes, as documented (docs.gnani.ai/api/STT/prisma-v2.5.md).
DOC_STT_CODES = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}
# The ten languages the product supports, each with the key used inside the app.
TEN = {"hi": "hi-IN", "en": "en-IN", "gu": "gu-IN", "mr": "mr-IN", "bn": "bn-IN", "ta": "ta-IN", "te": "te-IN", "kn": "kn-IN", "ml": "ml-IN", "pa": "pa-IN"}
# Timbre v2.5 voices per Timbre ``language`` value, as documented:
DOC_VOICES = {
    "en-IN": {"Kaveri", "Trupti", "Devika", "Pranav", "Shlok", "Girish"},
    "hi-IN": {"Nalini", "Bhavna", "Yashvi", "Urmila", "Jwala", "Chitra", "Ambuja", "Deepak", "Roopesh", "Vikrant", "Hemraj", "Jalaj", "Omkar"},
    "hi-en": {"Poorvi"},
    "ta-IN": {"Asmita", "Trisha", "Brinda", "Vedika", "Noopur"},
    "te-IN": {"Suhana", "Lehara", "Lavanya", "Yukti", "Varuni"},
    "kn-IN": {"Saanvi", "Kavin"},
    "ml-IN": {"Reshma", "Riyaan"},
    "mr-IN": {"Zahira", "Ishaan"},
    "bn-IN": {"Kirra", "Dhruva"},
    "gu-IN": {"Falak", "Veera"},
    "pa-IN": {"Mehuli", "Zayan"},
}  # 42 voices; copied from the Timbre v2.5 section of docs.gnani.ai/api/TTS/available-voices.md on 2026-11-10 (v3.0 voices are a different list)


def cfg(**kw) -> Settings:
    return Settings(_env_file=None, gnani_api_key=None, **kw)


def test_registry_has_the_ten_documented_languages_plus_hinglish():
    assert set(reg.ORDER) == set(TEN) | {"hinglish"}
    assert {reg.LANGUAGES[k].stt_code for k in TEN} == DOC_STT_CODES
    for key, code in TEN.items():
        assert reg.LANGUAGES[key].stt_code == code == reg.LANGUAGES[key].tts_code


def test_every_stt_code_is_a_documented_prisma_code():
    assert set(reg.STT_CODES) <= DOC_STT_CODES
    assert set(reg.DOCUMENTED_STT_CODES) == DOC_STT_CODES


def test_hinglish_is_spoken_through_en_in_and_answered_with_the_documented_hinglish_voice():
    h = reg.LANGUAGES["hinglish"]
    assert h.stt_code == "en-IN"  # Prisma v2.5 has no Hinglish code; en-IN handles English-Hindi mix
    assert h.tts_code == "hi-en" and h.default_voice == "Poorvi"


def test_voice_catalogue_matches_the_documented_timbre_v25_voices():
    assert {k: set(v) for k, v in reg.TIMBRE_V25_VOICES.items()} == DOC_VOICES
    assert sum(len(v) for v in reg.TIMBRE_V25_VOICES.values()) == 42
    for lang in reg.LANGUAGE_LIST:
        assert lang.default_voice in DOC_VOICES[lang.tts_code], lang.key
        assert set(lang.voices) == DOC_VOICES[lang.tts_code], lang.key


def test_settings_defaults_agree_with_the_registry():
    s = cfg()
    for lang in reg.LANGUAGE_LIST:
        assert getattr(s, f"tts_voice_{lang.key}") == lang.default_voice
        assert reg.configured_voice(s, lang.key) == lang.default_voice


def test_a_saved_voice_that_is_not_in_the_catalogue_falls_back_to_the_default():
    s = cfg(tts_voice_ta="NoSuchVoice")
    assert reg.configured_voice(s, "ta") == "Asmita"


@pytest.mark.parametrize("key", reg.ORDER)
def test_stt_and_tts_parameters_per_language(key):
    s = cfg()
    lang = reg.LANGUAGES[key]
    assert stt_params(s, key) == (lang.stt_code, None)
    assert tts_params(s, key) == (lang.default_voice, lang.tts_code)


def test_unknown_reply_language_is_spoken_as_english_never_as_another_indian_language():
    assert tts_params(cfg(), "klingon") == ("Devika", "en-IN")


@pytest.mark.parametrize("bad", ["", "xx", "GU", " gu", "gu-IN", "'; drop"])
def test_bad_language_values_are_reported_not_guessed(bad):
    with pytest.raises(reg.LanguageError) as e:
        reg.choose(cfg(), bad)
    assert e.value.code == "BAD_LANGUAGE" and e.value.status == 422


def test_auto_and_mixed_need_prisma_v3_and_say_so_on_v25():
    for mode in ("auto", "mixed"):
        with pytest.raises(reg.LanguageError) as e:
            stt_params(cfg(gnani_stt_model="prisma-v2.5"), mode)
        assert e.value.code == "AUTO_DETECT_NEEDS_V3"
    v3 = cfg(gnani_stt_model="prisma-v3.0")
    assert stt_params(v3, "auto") == ("indic-auto", None)
    assert stt_params(v3, "mixed") == ("gu-IN,en-IN", "codemix")


def test_hint_treats_auto_and_blank_as_no_hint_on_any_model():
    s = cfg(gnani_stt_model="prisma-v2.5")
    assert reg.hint(s, None) is None and reg.hint(s, "") is None and reg.hint(s, "auto") is None and reg.hint(s, "mixed") is None
    assert reg.hint(s, "ta") == "ta"


def test_disabling_a_language_removes_it_and_refuses_it():
    s = cfg(disabled_languages="mr, bn ,xx")
    assert reg.disabled_keys(s) == {"mr", "bn"}  # blanks trimmed, unknown keys ignored
    assert "mr" not in reg.enabled_keys(s) and "ta" in reg.enabled_keys(s)
    with pytest.raises(reg.LanguageError) as e:
        stt_params(s, "mr")
    assert e.value.code == "LANGUAGE_DISABLED"
    with pytest.raises(reg.LanguageError):
        reg.hint(s, "bn")


def test_english_cannot_be_switched_off():
    s = cfg(disabled_languages="en,hi")
    assert reg.is_enabled(s, "en") and not reg.is_enabled(s, "hi")


def test_itn_formatting_only_where_prisma_v25_supports_it():
    assert effective_stt_format("prisma-v2.5", "hi-IN", "transcribe") == "transcribe"
    assert effective_stt_format("prisma-v2.5", "en-IN", "transcribe") == "transcribe"
    for code in ("gu-IN", "mr-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "pa-IN"):
        assert effective_stt_format("prisma-v2.5", code, "transcribe") is None, code


def test_each_language_has_a_sample_with_the_expected_order_and_an_honest_status():
    for lang in reg.LANGUAGE_LIST:
        assert lang.sample and lang.sample_expect
        assert lang.nlu_status == ("tested" if lang.origin == "original" else "authored")
