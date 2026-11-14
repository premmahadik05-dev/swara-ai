"""Noisy Audio Testing Mode: degrade a clip (noise at a chosen SNR, telephony band-limit), send each
variant to Gnani STT and report transcripts, WER/CER against a reference, and the parsed order."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..deps import get_catalog, get_db
from ..gnani.client import GnaniError
from ..gnani.voices import stt_params
from ..languages import LanguageError, hint as language_hint
from ..security import rate_limit
from ..services import audio as audio_svc
from ..services import noise as noise_svc
from ..services import pipeline
from ..services.apilog import log_call
from ..services.catalog import CatalogCache
from .voice import gnani_http_error, language_http_error

router = APIRouter(prefix="/api/noise", tags=["noise-lab"])
MAX_CONDITIONS = 8


async def _read_wav(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, detail={"code": "TOO_LARGE", "message": "Audio too large."})
    if audio_svc.sniff_audio(data) != "wav":
        raise HTTPException(415, detail={"code": "WAV_ONLY", "message": "Noise Lab needs a PCM WAV file (the in-app recorder produces one)."})
    return data


def _conditions(raw: str) -> list[dict]:
    try:
        conds = json.loads(raw)
        assert isinstance(conds, list) and 0 < len(conds) <= MAX_CONDITIONS
        for c in conds:
            assert isinstance(c, dict)
            kind = c.get("kind")
            assert kind is None or kind in noise_svc.NOISE_KINDS
            if kind:
                assert -10 <= float(c["snr_db"]) <= 40
    except Exception:  # noqa: BLE001
        raise HTTPException(422, detail={"code": "BAD_CONDITIONS", "message": f"conditions must be a JSON list (max {MAX_CONDITIONS}) of {{kind, snr_db, telephony}}"})
    return conds


@router.post("/preview")
async def preview(
    request: Request, audio: UploadFile = File(...), kind: Optional[str] = Form(default=None),
    snr_db: Optional[float] = Form(default=None), telephony: bool = Form(default=False), _=Depends(rate_limit),
):
    data = await _read_wav(audio, request.app.state.settings.max_upload_bytes)
    try:
        d = noise_svc.degrade(data, kind=kind or None, snr_db=snr_db, use_telephony=telephony)
    except (noise_svc.AudioFormatError, ValueError) as exc:
        raise HTTPException(422, detail={"code": "BAD_AUDIO", "message": str(exc)})
    hdr = {"X-Condition": d.label}
    if d.measured_snr_db is not None:
        hdr["X-Measured-SNR-dB"] = f"{d.measured_snr_db:.1f}"
    return Response(d.wav, media_type="audio/wav", headers=hdr)


@router.post("/run")
async def run(
    request: Request, audio: UploadFile = File(...), conditions: str = Form(...), language: str = Form(default="gu"),
    reference_text: str = Form(default=""), db: Session = Depends(get_db), catalog: CatalogCache = Depends(get_catalog),
    _=Depends(rate_limit),
):
    s = request.app.state.settings
    if not s.gnani_configured:
        raise HTTPException(503, detail={"code": "NOT_CONFIGURED", "message": "Gnani API key is not configured - the Noise Lab needs real STT calls."})
    data = await _read_wav(audio, s.max_upload_bytes)
    conds = [{"kind": None, "snr_db": None, "telephony": False}] + [c for c in _conditions(conditions) if c.get("kind") or c.get("telephony")]
    conds = conds[: MAX_CONDITIONS + 1]
    try:
        lang_code, fmt = stt_params(s, language)
    except LanguageError as exc:
        raise language_http_error(exc) from exc
    hint = language_hint(s, language)
    ref = reference_text.strip()[:400]
    results = []
    for c in conds:
        try:
            d = noise_svc.degrade(data, kind=c.get("kind"), snr_db=c.get("snr_db"), use_telephony=bool(c.get("telephony")))
        except (noise_svc.AudioFormatError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "BAD_AUDIO", "message": str(exc)})
        row = {"label": d.label, "kind": c.get("kind"), "snr_db": c.get("snr_db"), "telephony": bool(c.get("telephony")),
               "measured_snr_db": None if d.measured_snr_db is None else round(d.measured_snr_db, 1)}
        try:
            stt = await request.app.state.gnani.transcribe(d.wav, language_code=lang_code, fmt=fmt, filename="noise.wav")
        except GnaniError as exc:
            log_call(db, exc.meta)
            if exc.error_type in ("NOT_CONFIGURED", "INVALID_API_KEY", "MISSING_API_KEY", "LOCAL_BUDGET_EXCEEDED", "RATE_LIMITED") or exc.status in (401, 402, 403, 429):
                raise gnani_http_error(exc) from exc
            row.update({"error": exc.user_message, "transcript": None})
            results.append(row)
            continue
        log_call(db, stt.meta)
        parsed = pipeline.parse_only(db, catalog, stt.transcript, language_hint=hint) if stt.transcript else None
        row.update({
            "transcript": stt.transcript, "latency_ms": stt.meta.latency_ms,
            "wer": round(noise_svc.wer(ref, stt.transcript), 4) if ref else None,
            "cer": round(noise_svc.cer(ref, stt.transcript), 4) if ref else None,
            "parsed_lines": [
                {"spoken": ln["spoken"], "product": ln["candidates"][0]["name"] if ln["resolved"] else None, "qty": ln["qty"], "unit": ln["unit"]}
                for ln in (parsed["parse"]["lines"] if parsed else [])
            ],
        })
        results.append(row)
    return {
        "language": language, "language_code": lang_code, "stt_model": s.gnani_stt_model, "reference_text": ref or None,
        "noise_note": "Noise is synthetic and speech-shaped babble is not a real crowd recording.",
        "results": results,
    }
