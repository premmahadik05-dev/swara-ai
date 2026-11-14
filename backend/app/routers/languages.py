"""The language registry as an API: what the selector shows, and what has (and has not) been verified."""
from __future__ import annotations

from fastapi import APIRouter, Request

from .. import languages as reg
from ..services import verification

router = APIRouter(prefix="/api", tags=["languages"])


def _modes(settings) -> list[dict]:
    v3 = settings.gnani_stt_model == "prisma-v3.0"
    return [
        {"key": "auto", "name": "Auto-detect", "available": v3,
         "reason": None if v3 else "Needs Prisma v3.0. Prisma v2.5 takes exactly one language per request."},
        {"key": "mixed", "name": "Gujarati + English mix", "available": v3,
         "reason": None if v3 else "Needs Prisma v3.0 (code-mixed transcription). On v2.5, pick English (en-IN): it handles English-Hindi mixed speech."},
    ]


@router.get("/languages")
def list_languages(request: Request):
    s = request.app.state.settings
    ver = verification.load(s)
    off = reg.disabled_keys(s)
    rows = []
    for key in reg.ORDER:
        lang = reg.LANGUAGES[key]
        rows.append({
            "key": key, "name": lang.name, "native": lang.native, "script": lang.script,
            "stt_code": lang.stt_code, "tts_code": lang.tts_code,
            "voice": reg.configured_voice(s, key), "default_voice": lang.default_voice, "voices": list(lang.voices),
            "enabled": key not in off, "origin": lang.origin,
            "nlu_status": lang.nlu_status,        # "tested" (the original four, with real-world checks) or "authored" (unit-tested only)
            "tts_depth": lang.tts_depth,           # how deeply Gnani documents its text handling for this language
            "stt_note": lang.stt_note, "sample": lang.sample,
            "verification": ver["languages"][key],
        })
    return {
        "default": "gu",
        "stt_model": s.gnani_stt_model, "tts_model": s.gnani_tts_model,
        "modes": _modes(s),
        "disabled": sorted(off),
        "docs": {"stt": reg.DOC_STT, "tts_voices": reg.DOC_TTS_VOICES, "tts_text": reg.DOC_TTS_NORMALIZATION, "checked_on": reg.DOCS_CHECKED_ON},
        "verification": {"mode": ver["mode"], "generated_at": ver["generated_at"], "stt_model": ver["stt_model"], "tts_model": ver["tts_model"]},
        "languages": rows,
    }
