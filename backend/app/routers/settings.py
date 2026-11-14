"""Settings & API configuration. The Gnani key can be written but is never returned."""
from __future__ import annotations

import re
import unicodedata
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy.orm import Session

from ..config import ENV_FILE
from ..deps import get_db
from ..gnani.client import GnaniError
from ..gnani.voices import TIMBRE_V25_VOICES
from .. import languages as reg
from ..auth import Principal, require_owner, require_user
from ..security import mask_key
from ..services.apilog import log_call
from ..services import payments as pay_svc
from .voice import gnani_http_error, language_http_error

router = APIRouter(prefix="/api/settings", tags=["settings"])
KEY_RE = re.compile(r"^[A-Za-z0-9_\-\.=:+/]{8,200}$")  # blocks newlines / spaces -> no .env injection


class KeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=200)


STORE_NAME_PUNCT = set(" &'.,-()/+@")   # no # " \\ $ or line breaks: the name is written to .env, where those characters mean something


def clean_store_name(value: str) -> str:
    """The shop name as it will be stored: Unicode letters, marks and digits (Gujarati and Hindi names are fine) plus a few
    punctuation marks, one space between words, 2 to 80 characters. Raises ValueError with a message the owner can act on."""
    name = " ".join(unicodedata.normalize("NFC", value).split())
    if not 2 <= len(name) <= 80:
        raise ValueError("The shop name needs 2 to 80 characters.")
    if not any(unicodedata.category(c)[0] in "LN" for c in name):
        raise ValueError("The shop name needs at least one letter or number.")
    bad = sorted({c for c in name if unicodedata.category(c)[0] not in "LMN" and c not in STORE_NAME_PUNCT})
    if bad:
        raise ValueError("Use letters, numbers, spaces and & ' . , - ( ) / + @ in the shop name. Not allowed: " + " ".join(bad[:6]))
    return name


def clean_upi_vpa(value: str) -> str:
    """The shop's UPI ID (for example shopname@bank), or an empty string to remove it. It is not a secret: it is printed in the QR code customers scan."""
    v = (value or "").strip()
    if v and not pay_svc.valid_vpa(v):
        raise ValueError("That does not look like a UPI ID. It should look like name@bank, for example patelstore@okhdfcbank.")
    return v


def clean_payee_name(value: str) -> str:
    """The name a customer sees in their UPI app next to the amount (empty means the shop name is used)."""
    v = " ".join((value or "").split())
    if not v:
        return ""
    if not 2 <= len(v) <= 40:
        raise ValueError("The name shown in the customer's UPI app needs 2 to 40 characters.")
    clean_store_name(v)  # same character rules as the shop name
    return v


class SettingsPatch(BaseModel):
    store_name: Optional[str] = None
    upi_vpa: Optional[str] = Field(default=None, max_length=100)  # "" removes it
    upi_payee_name: Optional[str] = Field(default=None, max_length=100)
    gnani_stt_model: Optional[Literal["prisma-v2.5", "prisma-v3.0"]] = None
    gnani_stt_format: Optional[Literal["verbatim", "transcribe", "codemix", "transliterate"]] = None
    gnani_stt_bias: Optional[bool] = None
    # One Timbre voice per language; each is checked against that language's catalogue in update_settings.
    tts_voice_gu: Optional[str] = Field(default=None, max_length=40)
    tts_voice_hi: Optional[str] = Field(default=None, max_length=40)
    tts_voice_en: Optional[str] = Field(default=None, max_length=40)
    tts_voice_hinglish: Optional[str] = Field(default=None, max_length=40)
    tts_voice_mr: Optional[str] = Field(default=None, max_length=40)
    tts_voice_bn: Optional[str] = Field(default=None, max_length=40)
    tts_voice_ta: Optional[str] = Field(default=None, max_length=40)
    tts_voice_te: Optional[str] = Field(default=None, max_length=40)
    tts_voice_kn: Optional[str] = Field(default=None, max_length=40)
    tts_voice_ml: Optional[str] = Field(default=None, max_length=40)
    tts_voice_pa: Optional[str] = Field(default=None, max_length=40)
    tts_speed: Optional[float] = Field(default=None, ge=0.85, le=1.15)
    disabled_languages: Optional[list[str]] = Field(default=None, max_length=len(reg.ORDER))  # keys switched off; [] switches all back on

    @field_validator("store_name")
    @classmethod
    def _store_name(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else clean_store_name(v)

    @field_validator("upi_vpa")
    @classmethod
    def _upi_vpa(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else clean_upi_vpa(v)

    @field_validator("upi_payee_name")
    @classmethod
    def _upi_payee(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else clean_payee_name(v)


def _env_value(value: str) -> str:
    """Plain values are written as they are; anything with spaces or punctuation is double-quoted so .env reads it back unchanged."""
    return value if re.fullmatch(r"[A-Za-z0-9_.:/+\-]*", value) else '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write_env(updates: dict[str, str]) -> None:
    """Upsert KEY=VALUE lines in the repo-root .env (created if missing). Only the keys in ``updates`` are touched: every other line, comment
    and blank line is kept as it was. The file is replaced in one step (write a temporary file next to it, then rename it over), so a crash or a
    full disk part-way through cannot leave a half-written .env and lose the Gnani key. A UTF-8 byte-order mark (Windows Notepad adds one) is read
    correctly instead of hiding the first key."""
    import os
    import tempfile

    lines = ENV_FILE.read_text(encoding="utf-8-sig").splitlines() if ENV_FILE.exists() else []
    seen = set()
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=", ln)
        if m and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={_env_value(updates[m.group(1)])}"
            seen.add(m.group(1))
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={_env_value(v)}")
    text = "\n".join(lines) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=str(ENV_FILE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, ENV_FILE.stat().st_mode & 0o777 if ENV_FILE.exists() else 0o600)
        except OSError:  # pragma: no cover - permissions are best effort (Windows)
            pass
        os.replace(tmp, ENV_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _public(request: Request, owner: bool = True) -> dict:
    s = request.app.state.settings
    g = request.app.state.gnani
    return {
        "store_name": s.store_name,
        "gnani": {
            "configured": s.gnani_configured, "key_hint": mask_key(s.gnani_key) if (owner and s.gnani_configured) else None,
            "base_url": s.gnani_base_url if owner else None, "stt_model": s.gnani_stt_model, "stt_format": s.gnani_stt_format,
            "stt_bias": s.gnani_stt_bias, "tts_model": s.gnani_tts_model,
            "calls_last_hour": g.budget.used, "max_calls_per_hour": s.gnani_max_calls_per_hour,
        },
        "voices": {
            **{k: reg.configured_voice(s, k) for k in reg.ORDER},
            "speed": s.tts_speed, "catalogue": TIMBRE_V25_VOICES,
        },
        "languages": {"disabled": sorted(reg.disabled_keys(s)), "env": "DISABLED_LANGUAGES"},
        "evon": {
            "available_on_gnani_api": False,
            "configured": bool(s.evon_base_url),
            "note": "Evon v3.3 is not exposed on Gnani's API platform (weights are open on request). Reasoning here is a deterministic engine; an optional self-hosted adapter is described in docs/EVON.md.",
        },
        "payments": pay_svc.public_config(s, owner=owner),
        "limits": {"max_upload_mb": s.max_upload_bytes / (1024 * 1024), "max_audio_seconds": s.max_audio_seconds, "rate_limit_per_minute": s.rate_limit_per_minute},
    }


@router.get("")
def get_settings(request: Request, p: Principal = Depends(require_user)):
    return _public(request, owner=p.user.role == "owner")


@router.put("", dependencies=[Depends(require_owner)])
def update_settings(body: SettingsPatch, request: Request):
    s = request.app.state.settings
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    for key in reg.ORDER:
        voice = data.get(f"tts_voice_{key}")
        if voice is not None and voice not in reg.LANGUAGES[key].voices:
            raise HTTPException(422, detail={"code": "BAD_VOICE", "message": f"Unknown {reg.LANGUAGES[key].name} voice for Timbre v2.5: {voice!r}. Choose one of {', '.join(reg.LANGUAGES[key].voices)}."})
    if "disabled_languages" in data:
        off = list(dict.fromkeys(data["disabled_languages"]))
        bad = [k for k in off if k not in reg.LANGUAGES]
        if bad:
            raise HTTPException(422, detail={"code": "BAD_LANGUAGE", "message": f"Unknown language key(s): {', '.join(bad)}. Valid keys: {', '.join(reg.ORDER)}."})
        if "en" in off:
            raise HTTPException(422, detail={"code": "LANGUAGE_REQUIRED", "message": "English cannot be switched off: the assistant falls back to English wording for unknown text."})
        data["disabled_languages"] = ",".join(off)
    env = {}
    for k, v in data.items():
        setattr(s, k, v)
        env[k.upper()] = str(v).lower() if isinstance(v, bool) else str(v)
    if env:
        _write_env(env)
    return _public(request)


@router.put("/gnani-key", dependencies=[Depends(require_owner)])
def set_key(body: KeyIn, request: Request):
    key = body.api_key.strip()
    if not KEY_RE.match(key):
        raise HTTPException(422, "That does not look like an API key (unexpected characters).")
    s = request.app.state.settings
    s.gnani_api_key = SecretStr(key)
    _write_env({"GNANI_API_KEY": key})
    return _public(request)


@router.post("/test-gnani", dependencies=[Depends(require_owner)])
async def test_gnani(request: Request, db: Session = Depends(get_db), language: str = "en"):
    """Real round trip: Timbre speaks a short phrase, Prisma transcribes that audio. Costs 2 calls.

    ``language`` picks which language to check (default English). It is a *loopback*: Prisma hears Timbre's synthetic voice, so a pass
    shows that both services accept the language and the voice, not how well Prisma recognises a person speaking it."""
    s = request.app.state.settings
    g = request.app.state.gnani
    try:
        key = reg.choose(s, language)
    except reg.LanguageError as exc:
        raise language_http_error(exc) from exc
    if key in reg.STT_MODES:
        raise language_http_error(reg.LanguageError("BAD_LANGUAGE", "Pick one language to test, not an automatic mode."))
    lang = reg.LANGUAGES[key]
    voice = reg.configured_voice(s, key)
    phrase = "two kilo rice and one litre milk" if key == "en" else lang.sample
    report: dict = {
        "language": key, "phrase": phrase, "loopback": True, "tts_language": lang.tts_code, "stt_language_code": lang.stt_code,
        "tts": {"ok": False}, "stt": {"ok": False},
    }
    try:
        tts = await g.synthesize(phrase, language=lang.tts_code, voice=voice, speed=1.0, sample_rate=16000)
        log_call(db, tts.meta)
        report["tts"] = {"ok": True, "latency_ms": tts.meta.latency_ms, "bytes": len(tts.audio), "model": s.gnani_tts_model, "voice": voice}
    except GnaniError as exc:
        log_call(db, exc.meta)
        report["tts"] = {"ok": False, "error": exc.user_message, "code": exc.error_type}
        if exc.error_type == "NOT_CONFIGURED":
            raise gnani_http_error(exc) from exc
        return report
    try:
        stt = await g.transcribe(tts.audio, language_code=lang.stt_code, filename="check.wav")
        log_call(db, stt.meta)
        report["stt"] = {"ok": True, "latency_ms": stt.meta.latency_ms, "model": stt.model, "transcript": stt.transcript, "request_id": stt.request_id}
    except GnaniError as exc:
        log_call(db, exc.meta)
        report["stt"] = {"ok": False, "error": exc.user_message, "code": exc.error_type}
    return report
