"""Voice + text ordering endpoints."""
from __future__ import annotations

import time
from datetime import timedelta
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import cookie_name, resolve_session
from ..deps import get_catalog, get_db
from ..gnani.client import GnaniError
from ..gnani.voices import bias_script, bias_words, stt_params
from ..languages import LanguageError, hint as language_hint
from ..nlu import nlg
from ..models import Turn, utcnow
from ..security import AUDIO_ID_RE, rate_limit
from ..services import audio as audio_svc
from ..services import pipeline
from ..services.apilog import log_call
from ..services.catalog import CatalogCache, load_views
from ..services.speech import speak

router = APIRouter(prefix="/api", tags=["ordering"])
public = APIRouter(prefix="/api", tags=["landing-demo"])  # no sign-in needed: the landing page parses a sentence without storing anything



def language_http_error(exc: LanguageError) -> HTTPException:
    """A language the server cannot honour is a clear 4xx with its reason, never a silent switch to another language."""
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


def gnani_http_error(exc: GnaniError) -> HTTPException:
    t, st = exc.error_type, exc.status
    if t == "NOT_CONFIGURED":
        code = 503
    elif t in ("MISSING_API_KEY", "INVALID_API_KEY", "SCOPE_NOT_ALLOWED") or st in (401, 403):
        code = 502
    elif st == 402:
        code = 402
    elif st == 429 or t in ("RATE_LIMITED", "LOCAL_BUDGET_EXCEEDED"):
        code = 429
    elif t in ("NETWORK", "TIMEOUT"):
        code = 504
    elif st and 400 <= st < 500:
        code = 422
    else:
        code = 502
    return HTTPException(status_code=code, detail={"code": t, "message": exc.user_message})


class TextTurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    session_id: Optional[str] = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9_-]*$")
    speak: bool = False
    customer_id: Optional[int] = Field(default=None, ge=1)
    language: Optional[str] = Field(default=None, max_length=12, pattern=r"^[A-Za-z]*$")  # the language chosen in the selector (a hint, not a limit)


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    language: Optional[str] = Field(default=None, max_length=12, pattern=r"^[A-Za-z]*$")


@router.post("/text/turn")
async def text_turn(body: TextTurnIn, request: Request, db: Session = Depends(get_db), catalog: CatalogCache = Depends(get_catalog), _=Depends(rate_limit)):
    try:
        hint = language_hint(request.app.state.settings, body.language)
    except LanguageError as exc:
        raise language_http_error(exc) from exc
    out = pipeline.process_turn(db, catalog, body.text, session_id=body.session_id, input_mode="text", customer_id=body.customer_id, language_hint=hint)
    out["audio"] = None
    if body.speak:
        out["audio"] = await speak(request.app, db, out["reply_text"], out["reply_lang"])
        if out["audio"].get("audio_id"):
            tm = pipeline.attach_audio(db, out["assistant_turn_id"], out["audio"]["audio_id"], out["audio"]["tts_ms"] or 0, bool(out["audio"].get("cached")))
            out["timings"]["tts_ms"] = out["audio"]["tts_ms"]
            if tm:
                out["timings"]["server_ms"] = tm.get("server_ms")
    return out


@public.post("/text/parse")
def text_parse(body: ParseIn, request: Request, db: Session = Depends(get_db), catalog: CatalogCache = Depends(get_catalog), _=Depends(rate_limit)):
    """Stateless parse used by the landing-page demo. Nothing is stored and no stock is reserved.
    The answer names real items with their prices and stock, so a shop that does not want strangers to see those sets PUBLIC_DEMO=false;
    the endpoint then needs a signed-in person like everything else."""
    s = request.app.state.settings
    if not s.public_demo and resolve_session(db, s, request.cookies.get(cookie_name(s)))[0] is None:
        raise HTTPException(403, detail={"code": "DEMO_OFF", "message": "The live demo is switched off on this server. Sign in to use the order desk."})
    try:
        hint = language_hint(s, body.language)
    except LanguageError as exc:
        raise language_http_error(exc) from exc
    return pipeline.parse_only(db, catalog, body.text, language_hint=hint)


@router.post("/voice/turn")
async def voice_turn(
    request: Request,
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(default=None),
    language: str = Form(default="gu"),
    speak_reply: bool = Form(default=True),
    customer_id: Optional[int] = Form(default=None, ge=1),
    db: Session = Depends(get_db),
    catalog: CatalogCache = Depends(get_catalog),
    _=Depends(rate_limit),
):
    t_start = time.perf_counter()
    s = request.app.state.settings
    try:
        lang_code, fmt = stt_params(s, language)  # validates the choice: unknown, switched off, or auto/mixed on a model that cannot do it
    except LanguageError as exc:
        raise language_http_error(exc) from exc
    hint = language_hint(s, language)
    if session_id and not all(c.isalnum() or c in "_-" for c in session_id) or (session_id and len(session_id) > 40):
        raise HTTPException(422, detail={"code": "BAD_SESSION", "message": "Invalid session id."})
    data = await audio.read(s.max_upload_bytes + 1)
    if len(data) > s.max_upload_bytes:
        raise HTTPException(413, detail={"code": "TOO_LARGE", "message": f"Audio larger than {s.max_upload_bytes // (1024 * 1024)} MB."})
    kind = audio_svc.sniff_audio(data)
    if kind is None or kind == "webm":
        raise HTTPException(415, detail={"code": "UNSUPPORTED_AUDIO", "message": "Unsupported audio. Send WAV, MP3, OGG, FLAC, AAC or M4A (the in-app recorder sends WAV)."})
    if kind == "wav":
        try:
            info = audio_svc.inspect_wav(data)
        except Exception:  # noqa: BLE001
            raise HTTPException(415, detail={"code": "BAD_WAV", "message": "Could not read this WAV file."})
        if info.duration > s.max_audio_seconds + 0.5:
            raise HTTPException(422, detail={"code": "MAX_AUDIO_DURATION_EXCEEDED", "message": f"Audio is {info.duration:.0f}s; Gnani REST accepts up to {s.max_audio_seconds:.0f}s."})
        if info.duration < 0.15:
            raise HTTPException(422, detail={"code": "EMPTY_AUDIO", "message": "Recording is too short."})

    bias = None
    if s.gnani_stt_bias and s.gnani_stt_model == "prisma-v2.5" and hint:
        # Product words in the script of the chosen language (Latin for English and Hinglish). Only when a single language was picked:
        # a bias list is one script's words, and v2.5 has no other mode anyway.
        bias = bias_words([p.all_names() for p in load_views(db).values()], bias_script(hint))
    validate_ms = round((time.perf_counter() - t_start) * 1000, 2)
    try:
        stt = await request.app.state.gnani.transcribe(
            data, language_code=lang_code, fmt=fmt, filename=f"order.{kind}", content_type=audio_svc.CONTENT_TYPES[kind],
            bias_list=bias or None,
        )
    except GnaniError as exc:
        log_call(db, exc.meta)
        raise gnani_http_error(exc) from exc
    log_call(db, stt.meta)

    if not stt.transcript:
        sess = pipeline.get_or_create_session(db, session_id)
        db.commit()
        reply_lang = hint or (sess.language if sess.language in nlg.LANGS else "en")
        reply = nlg.render("no_speech", reply_lang)
        out = pipeline.no_speech_turn(db, sess.id, reply, reply_lang, stt_ms=stt.meta.latency_ms,
                                      timing_in={"validate_ms": validate_ms, "stt_ms": stt.meta.latency_ms, "stt_attempts": stt.meta.attempts})
        out["stt"] = {"model": stt.model, "request_id": stt.request_id, "latency_ms": stt.meta.latency_ms, "language_code": lang_code, "attempts": stt.meta.attempts}
        if speak_reply:
            out["audio"] = await speak(request.app, db, reply, reply_lang)
            if out["audio"].get("audio_id"):
                pipeline.attach_audio(db, out["assistant_turn_id"], out["audio"]["audio_id"], out["audio"]["tts_ms"] or 0, bool(out["audio"].get("cached")))
        return out

    out = pipeline.process_turn(db, catalog, stt.transcript, session_id=session_id, input_mode="voice", stt_ms=stt.meta.latency_ms, customer_id=customer_id,
                                language_hint=hint, timing_in={"validate_ms": validate_ms, "stt_ms": stt.meta.latency_ms, "stt_attempts": stt.meta.attempts})
    out["stt"] = {
        "model": stt.model, "request_id": stt.request_id, "latency_ms": stt.meta.latency_ms, "language_code": lang_code,
        "server_processing_s": stt.processing_time, "end_to_end_s": stt.end_to_end_latency,
        "detected_language_code": stt.detected_language_code, "bias_words": len(bias or []), "attempts": stt.meta.attempts,
    }
    out["audio"] = None
    if speak_reply:
        # speak_reply=false is the fast path the app uses: the reply and the bill come back at once and the voice is fetched next
        # (POST /api/turns/{id}/speak), so the screen never waits for speech synthesis.
        out["audio"] = await speak(request.app, db, out["reply_text"], out["reply_lang"])
        if out["audio"].get("audio_id"):
            tm = pipeline.attach_audio(db, out["assistant_turn_id"], out["audio"]["audio_id"], out["audio"]["tts_ms"] or 0, bool(out["audio"].get("cached")))
            out["timings"]["tts_ms"] = out["audio"]["tts_ms"]
            if tm:
                out["timings"]["server_ms"] = tm.get("server_ms")
    return out


SPEAK_MAX_AGE = timedelta(hours=1)


@router.post("/turns/{turn_id}/speak")
async def speak_turn(turn_id: int, request: Request, db: Session = Depends(get_db), _=Depends(rate_limit)):
    """Spoken version of an assistant reply that is already stored.

    The text is the one the server saved for that turn; nothing the caller sends is spoken, so this cannot be used to have arbitrary text read out
    on the shop's Gnani credits. Repeating the call is free (same reply, same voice: served from the audio cache)."""
    t = db.get(Turn, turn_id)
    if t is None or t.role != "assistant":
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "No such reply."})
    if utcnow() - t.created_at > SPEAK_MAX_AGE:
        raise HTTPException(410, detail={"code": "TOO_OLD", "message": "This reply is too old to be spoken now."})
    audio = await speak(request.app, db, t.text, t.language or "en")
    timings: dict = {"tts_ms": audio.get("tts_ms")}
    if audio.get("audio_id"):
        tm = pipeline.attach_audio(db, t.id, audio["audio_id"], audio["tts_ms"] or 0, bool(audio.get("cached")))
        if tm:
            timings["server_ms"] = tm.get("server_ms")
    return {"turn_id": t.id, "audio": audio, "timings": timings}


class ClientTimingIn(BaseModel):
    model_config = {"extra": "forbid"}
    capture_ms: Optional[int] = Field(default=None, ge=0, le=120_000)         # how long the person spoke / the recording ran
    end_to_reply_ms: Optional[int] = Field(default=None, ge=0, le=300_000)    # end of speech -> the reply is on screen (measured in the browser)
    end_to_audio_ms: Optional[int] = Field(default=None, ge=0, le=300_000)    # end of speech -> the spoken reply starts
    upload_bytes: Optional[int] = Field(default=None, ge=0, le=64 * 1024 * 1024)
    endpoint: Optional[Literal["manual", "auto", "live"]] = None              # how the end of speech was decided


@router.post("/turns/{turn_id}/client-timing")
def client_timing(turn_id: int, body: ClientTimingIn, db: Session = Depends(get_db), _=Depends(rate_limit)):
    """The browser reports how long the person waited. Shown in the owner's diagnostics next to the server's own stage times, and labelled as
    browser-reported there."""
    values = body.model_dump(exclude_none=True)
    if not values or not pipeline.record_client_timing(db, turn_id, values):
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "No such reply."})
    return {"ok": True}


@router.get("/audio/{audio_id}")
def get_audio(audio_id: str, request: Request):
    if not AUDIO_ID_RE.match(audio_id):  # also blocks path traversal
        raise HTTPException(404, "Not found")
    path = request.app.state.settings.tts_dir / f"{audio_id}.wav"
    if not path.is_file():
        raise HTTPException(404, "Audio expired")
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/sessions")
def new_session(db: Session = Depends(get_db)):
    s = pipeline.get_or_create_session(db, None)
    db.commit()
    return {"session_id": s.id}


@router.get("/sessions")
def sessions(limit: int = 20, db: Session = Depends(get_db)):
    return pipeline.list_sessions(db, min(max(limit, 1), 100))


@router.get("/sessions/{session_id}")
def session_detail(session_id: str, db: Session = Depends(get_db)):
    snap = pipeline.session_snapshot(db, session_id)
    if snap is None:
        raise HTTPException(404, "Session not found")
    return snap


class ConfirmIn(BaseModel):
    customer_id: Optional[int] = Field(default=None, ge=1)


@router.post("/sessions/{session_id}/confirm")
async def confirm_session(
    session_id: str, request: Request, body: Optional[ConfirmIn] = None, db: Session = Depends(get_db),
    catalog: CatalogCache = Depends(get_catalog), _=Depends(rate_limit),
):
    """Button fallback for 'confirm': goes through the same dialogue path as speech, and means "that's all, confirm".

    A bare "confirm" typed while the assistant is asking "Anything else?" would be read as a yes to that question, so the
    bill would not be saved and the shopkeeper would have to press the button twice. When that question is open, the button
    first answers it ("that's all") to reach the read-back, then confirms. The button says nothing about the customer's
    language, so it never changes the conversation language or the language stored on the order."""
    snap = pipeline.session_snapshot(db, session_id)
    if snap is None:
        raise HTTPException(404, "Session not found")
    cid = body.customer_id if body else None

    def say(text: str) -> dict:
        return pipeline.process_turn(db, catalog, text, session_id=session_id, input_mode="text", customer_id=cid, keep_language=True)

    if snap["phase"] == "collecting" and snap["awaiting"] == "more_items" and not snap["pending"] and snap["cart"]["lines"]:
        say("that's all")
    out = say("confirm")
    if out["phase"] == "confirming" and not out["order"]:
        out = say("confirm")
    out["audio"] = None
    return out


class CartEditIn(BaseModel):
    product_id: int = Field(ge=1)
    qty: Decimal = Field(ge=0, le=Decimal(10000))
    mode: Literal["set", "add"] = "set"


@router.post("/sessions/{session_id}/cart")
def edit_session_cart(session_id: str, body: CartEditIn, db: Session = Depends(get_db), _=Depends(rate_limit)):
    """Set or add a quantity on the open bill without going through speech (same stock rules as a spoken order)."""
    try:
        return pipeline.edit_cart(db, session_id, body.product_id, body.qty, body.mode)
    except pipeline.CartError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)})
