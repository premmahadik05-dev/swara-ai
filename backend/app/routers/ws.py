"""Realtime speech: browser <-> this backend <-> Gnani Prisma streaming WebSocket.

Browsers cannot set the ``x-api-key-id`` header on a WebSocket upgrade (Gnani docs say to proxy through
your backend), so this endpoint holds the key, relays raw PCM frames and turns every final
``transcript`` message into a full ordering turn (parse -> dialogue -> optional Timbre reply).

Browser -> backend: binary PCM16 mono 16 kHz frames (any size; re-chunked to Gnani's exact 1024 bytes),
                    text frames ``{"type": "commit"}`` and ``{"type": "end"}``.
Backend -> browser: ``ready | speech_start | processing | turn | audio | error | closed`` JSON messages.
With ``defer_audio=true`` (what the app uses) the ``turn`` message, with the reply text and the bill, is sent as soon as the order logic has run, and
the spoken reply follows in a separate ``audio`` message for that turn, so the screen never waits for speech synthesis and the next utterance is not
held up behind it. Without it (the default, kept for older clients) the voice is attached to the ``turn`` message as before.

Note: per the Gnani docs each streamed ``transcript`` is a completed speech segment (no interim/partial
transcripts), so "realtime" here means low-latency per-utterance results, not word-by-word captions.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from ..auth import cookie_name, resolve_session
from ..gnani.voices import stt_params
from ..languages import LanguageError, hint as language_hint
from ..services import pipeline
from ..services.speech import speak

log = logging.getLogger("swara.ws")
router = APIRouter()
FRAME = 1024  # bytes per binary frame required by Gnani (512 samples of PCM16)


def _ws_url(base: str) -> str:
    return base.rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + "/stt/v3/stream"


def _origin_ok(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if not origin:
        return True  # non-browser client
    allowed = set(ws.app.state.settings.cors_list)
    host = ws.headers.get("host", "")
    return origin in allowed or origin.endswith("//" + host)


@router.websocket("/ws/voice")
async def ws_voice(ws: WebSocket, language: str = "gu", session_id: str | None = None, speak_reply: bool = True, customer_id: int | None = None,
                   defer_audio: bool = False):
    app = ws.app
    s = app.state.settings
    if not _origin_ok(ws):
        await ws.close(code=1008)
        return
    # Same cookie as the REST API. A browser sends it on the handshake; no cookie, no voice proxy (and no Gnani spend).
    with app.state.session_factory() as db:
        who, _ = resolve_session(db, s, ws.cookies.get(cookie_name(s)))
    if who is None:
        await ws.close(code=4401)
        return
    await ws.accept()
    if not s.gnani_configured:
        await ws.send_json({"type": "error", "code": "NOT_CONFIGURED", "message": "Gnani API key is not configured."})
        await ws.close(code=1011)
        return
    try:
        lang_code, fmt = stt_params(s, language)  # unknown / switched-off language, or auto/mixed on a model that cannot do it
    except LanguageError as exc:
        await ws.send_json({"type": "error", "code": exc.code, "message": exc.message})
        await ws.close(code=1003)
        return
    hint = language_hint(s, language)
    if session_id and not all(c.isalnum() or c in "_-" for c in session_id):
        session_id = None
    # Gnani's streaming docs name the language header two ways (``lang_code`` on the endpoint page, ``language_code`` in the examples), so both are sent;
    # the service reads whichever it knows. Which one it needs has not been confirmed against the live service (docs/LIMITATIONS.md).
    headers = {"x-api-key-id": s.gnani_key or "", "lang_code": lang_code, "language_code": lang_code, "x-sample-rate": "16000", "x-idle-timeout-sec": "120"}
    if s.gnani_stt_model == "prisma-v3.0":
        headers["model"] = "prisma-v3.0"
    if fmt:
        headers["format"] = fmt

    state: dict[str, Any] = {"session_id": session_id}
    voice_tasks: set[asyncio.Task] = set()

    async def send_audio(turn_id: int, text: str, lang: str) -> None:
        """Fetch the spoken reply for one turn and send it when ready. Runs beside the main loop, so a slow synthesis delays only its own audio."""
        db2 = app.state.session_factory()
        try:
            audio = await speak(app, db2, text, lang)
            tm = None
            if audio.get("audio_id"):
                tm = pipeline.attach_audio(db2, turn_id, audio["audio_id"], audio["tts_ms"] or 0, bool(audio.get("cached")))
        except Exception:  # noqa: BLE001 - a failed voice must never take the live connection down; the reply text is already on screen
            log.exception("deferred voice failed")
            audio, tm = {"audio_id": None, "audio_url": None, "tts_ms": None, "cached": False, "error": "The spoken reply could not be made."}, None
        finally:
            db2.close()
        await _safe_send(ws, jsonable_encoder({"type": "audio", "assistant_turn_id": turn_id, "audio": audio, "timings": {"tts_ms": audio.get("tts_ms"), "server_ms": (tm or {}).get("server_ms")}}))

    try:
        async with ws_connect(_ws_url(s.gnani_base_url), additional_headers=headers, max_size=2**20, open_timeout=15) as up:

            async def client_to_gnani() -> None:
                buf = bytearray()
                while True:
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        return
                    if msg.get("bytes"):
                        buf.extend(msg["bytes"])
                        while len(buf) >= FRAME:
                            await up.send(bytes(buf[:FRAME]))
                            del buf[:FRAME]
                    elif msg.get("text"):
                        try:
                            data = json.loads(msg["text"])
                        except ValueError:
                            continue
                        if data.get("type") == "commit":
                            await up.send(json.dumps({"type": "commit"}))
                        elif data.get("type") == "end":
                            if buf:  # pad the last partial frame with silence
                                buf.extend(b"\x00" * (FRAME - len(buf)))
                                await up.send(bytes(buf))
                                buf.clear()
                            await up.send(json.dumps({"type": "commit"}))
                            await asyncio.sleep(1.2)  # docs: keep ~1 s of silence so the last sentence finalises
                            return

            async def gnani_to_client() -> None:
                async for raw in up:
                    if isinstance(raw, bytes):
                        continue
                    try:
                        m = json.loads(raw)
                    except ValueError:
                        continue
                    t = m.get("type")
                    if t == "transcript":
                        text = (m.get("text") or "").strip()
                        if not text:
                            continue
                        db = app.state.session_factory()
                        try:
                            stt_ms = int(float(m["latency"]) * 1000) if m.get("latency") else None
                            out = pipeline.process_turn(db, app.state.catalog, text, session_id=state["session_id"], input_mode="stream", stt_ms=stt_ms,
                                                        customer_id=customer_id if customer_id and customer_id > 0 else None, language_hint=hint,
                                                        timing_in={"stt_ms": stt_ms} if stt_ms is not None else None)
                            state["session_id"] = out["session_id"]
                            out["audio"] = None
                            if speak_reply and not defer_audio:
                                out["audio"] = await speak(app, db, out["reply_text"], out["reply_lang"])
                                if out["audio"].get("audio_id"):
                                    pipeline.attach_audio(db, out["assistant_turn_id"], out["audio"]["audio_id"], out["audio"]["tts_ms"] or 0, bool(out["audio"].get("cached")))
                        finally:
                            db.close()
                        await ws.send_json(jsonable_encoder({"type": "turn", **out, "segment": {"id": m.get("segment_id"), "audio_ms": m.get("audio_duration_ms")}}))
                        if speak_reply and defer_audio:
                            task = asyncio.create_task(send_audio(out["assistant_turn_id"], out["reply_text"], out["reply_lang"]))
                            voice_tasks.add(task)
                            task.add_done_callback(voice_tasks.discard)
                    elif t == "connected":
                        await ws.send_json({"type": "ready", "config": m.get("config"), "language_code": lang_code, "model": s.gnani_stt_model})
                    elif t in ("speech_start", "processing"):
                        await ws.send_json({"type": t})
                    elif t == "error":
                        await ws.send_json({"type": "error", "code": "GNANI_STREAM", "message": str(m.get("message", "stream error"))[:200]})

            tasks = [asyncio.create_task(client_to_gnani()), asyncio.create_task(gnani_to_client())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            for d in done:
                exc = d.exception()
                if exc and not isinstance(exc, (WebSocketDisconnect, ConnectionClosed)):
                    raise exc
    except InvalidStatus as exc:
        code = getattr(exc.response, "status_code", 0)
        msg = "Gnani rejected the API key." if code == 401 else f"Gnani refused the connection (HTTP {code})."
        await _safe_send(ws, {"type": "error", "code": "HANDSHAKE", "message": msg})
    except (OSError, asyncio.TimeoutError) as exc:
        await _safe_send(ws, {"type": "error", "code": "NETWORK", "message": f"Could not reach Gnani realtime service ({type(exc).__name__})."})
    except (WebSocketDisconnect, ConnectionClosed):
        pass
    except Exception:  # noqa: BLE001
        log.exception("ws_voice failed")
        await _safe_send(ws, {"type": "error", "code": "INTERNAL", "message": "Streaming failed unexpectedly."})
    finally:
        for t in list(voice_tasks):
            t.cancel()
        await _safe_send(ws, {"type": "closed", "session_id": state.get("session_id")})
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


async def _safe_send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_json(payload)
    except Exception:  # noqa: BLE001
        pass
