"""Timbre TTS with an on-disk cache so identical replies never spend credits twice."""
from __future__ import annotations

import hashlib
from typing import Any

from fastapi import FastAPI

from ..gnani.client import GnaniError
from ..gnani.voices import tts_params
from ..languages import LANGUAGES, is_enabled
from .apilog import log_call

MAX_CACHE_FILES = 300


def _prune(tts_dir) -> None:
    files = sorted(tts_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
    for p in files[: max(0, len(files) - MAX_CACHE_FILES)]:
        try:
            p.unlink()
        except OSError:  # pragma: no cover
            pass


async def speak(app: FastAPI, db, text: str, reply_lang: str) -> dict[str, Any]:
    s = app.state.settings
    if not s.gnani_configured:
        return {"audio_id": None, "audio_url": None, "tts_ms": None, "cached": False, "error": "Gnani key not configured - voice reply skipped."}
    lang_key = reply_lang if reply_lang in LANGUAGES else "en"
    if not is_enabled(s, lang_key):
        return {"audio_id": None, "audio_url": None, "tts_ms": None, "cached": False,
                "error": f"{LANGUAGES[lang_key].name} is switched off on this server (DISABLED_LANGUAGES) - voice reply skipped."}
    voice, language = tts_params(s, reply_lang)
    key = hashlib.sha256(f"{s.gnani_tts_model}|{voice}|{language}|{s.tts_speed}|{s.tts_sample_rate}|{text}".encode()).hexdigest()[:32]
    path = s.tts_dir / f"{key}.wav"
    if path.exists():
        return {"audio_id": key, "audio_url": f"/api/audio/{key}", "tts_ms": 0, "cached": True, "error": None, "voice": voice}
    try:
        res = await app.state.gnani.synthesize(text, language=language, voice=voice, speed=s.tts_speed, sample_rate=s.tts_sample_rate)
    except GnaniError as exc:
        log_call(db, exc.meta)
        return {"audio_id": None, "audio_url": None, "tts_ms": None, "cached": False, "error": exc.user_message}
    s.tts_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(res.audio)
    _prune(s.tts_dir)
    log_call(db, res.meta)
    return {"audio_id": key, "audio_url": f"/api/audio/{key}", "tts_ms": res.meta.latency_ms, "cached": False, "error": None, "voice": voice}
