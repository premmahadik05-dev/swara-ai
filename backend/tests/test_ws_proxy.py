"""Realtime proxy conformance test against a LOCAL fake Gnani streaming server.

The fake server implements the protocol as documented (headers for auth/config, 1024-byte binary PCM16 frames,
JSON ``commit``, ``transcript`` messages). It proves our proxy follows that protocol; it does not prove
that Gnani's live server accepts it - see scripts/verify_gnani.py for the live check.
"""
from __future__ import annotations

import asyncio
import json
import threading

import httpx
import pytest
from websockets.asyncio.server import serve

from .helpers import AuthedClient, KEY, make_wav


class FakeStreamServer:
    def __init__(self, transcripts, reject_status=None):
        self.transcripts, self.reject_status = list(transcripts), reject_status
        self.frames: list[int] = []
        self.texts: list[str] = []
        self.headers: dict[str, str] = {}
        self.port = None
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    async def _handler(self, ws):
        self.headers = {k.lower(): v for k, v in ws.request.headers.items()}
        await ws.send(json.dumps({"type": "connected", "config": {"language_code": self.headers.get("language_code")}}))
        pending = 0
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    self.frames.append(len(msg))
                    pending += 1
                    if pending == 1:
                        await ws.send(json.dumps({"type": "speech_start"}))
                else:
                    self.texts.append(msg)
                    if json.loads(msg).get("type") == "commit" and self.transcripts:
                        await ws.send(json.dumps({"type": "processing"}))
                        await ws.send(json.dumps({"type": "transcript", "text": self.transcripts.pop(0), "segment_id": 1,
                                                  "audio_duration_ms": 1200, "latency": 0.42}))
        except Exception:  # noqa: BLE001
            pass

    async def _process_request(self, connection, request):
        if self.reject_status:
            return connection.respond(self.reject_status, "nope")
        return None

    def _run(self):
        asyncio.set_event_loop(self._loop)

        async def main():
            async with serve(self._handler, "127.0.0.1", 0, process_request=self._process_request) as s:
                self.port = s.sockets[0].getsockname()[1]
                self._stop = asyncio.Event()
                self._ready.set()
                await self._stop.wait()

        try:
            self._loop.run_until_complete(main())
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._loop.close()

    def __enter__(self):
        self._thread.start()
        assert self._ready.wait(5)
        return self

    def __exit__(self, *a):
        # shut the server down cleanly: no "event loop is closed" noise at interpreter exit
        if getattr(self, "_stop", None) is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout=5)


def pcm_of(seconds=1.0):
    return make_wav(seconds, 16000)[44:]


def collect(ws, until=("turn", "error", "closed"), limit=12):
    out = []
    for _ in range(limit):
        m = ws.receive_json()
        out.append(m)
        if m["type"] in until:
            break
    return out


def test_proxy_follows_documented_protocol_and_turns_transcripts_into_orders(make_app):
    with FakeStreamServer(["do kilo chini aur ek litre doodh"]) as fake:
        app = make_app(gnani_api_key=KEY, gnani_base_url=f"http://127.0.0.1:{fake.port}")
        with AuthedClient(app) as c, c.websocket_connect("/ws/voice?language=hi&speak_reply=false") as ws:
            assert ws.receive_json()["type"] == "ready"
            pcm = pcm_of(1.0)
            ws.send_bytes(pcm[:700])           # odd-sized chunks must be re-framed
            ws.send_bytes(pcm[700:2500])
            ws.send_bytes(pcm[2500:])
            ws.send_text(json.dumps({"type": "commit"}))
            msgs = collect(ws)
            turn = next(m for m in msgs if m["type"] == "turn")
            assert turn["transcript"] == "do kilo chini aur ek litre doodh"
            assert turn["cart"]["total_paise"] == 2 * 4600 + 5600
            assert turn["segment"]["audio_ms"] == 1200 and turn["timings"]["stt_ms"] == 420
            ws.send_text(json.dumps({"type": "end"}))
    assert fake.frames and set(fake.frames) == {1024}, "every binary frame must be exactly 1024 bytes"
    assert fake.headers["x-api-key-id"] == KEY and fake.headers["language_code"] == "hi-IN"
    assert any(json.loads(t)["type"] == "commit" for t in fake.texts)


def test_partial_last_frame_is_padded_not_dropped(make_app):
    with FakeStreamServer([]) as fake:
        app = make_app(gnani_api_key=KEY, gnani_base_url=f"http://127.0.0.1:{fake.port}")
        with AuthedClient(app) as c, c.websocket_connect("/ws/voice?language=gu&speak_reply=false") as ws:
            assert ws.receive_json()["type"] == "ready"
            ws.send_bytes(b"\x01\x00" * 700)  # 1400 bytes -> one full frame + 376 bytes tail
            ws.send_text(json.dumps({"type": "end"}))
            collect(ws, until=("closed",))
    assert fake.frames == [1024, 1024]


def test_ws_without_key_returns_clear_error(client):
    with client.websocket_connect("/ws/voice?language=gu") as ws:
        m = ws.receive_json()
        assert m["type"] == "error" and m["code"] == "NOT_CONFIGURED"


def test_ws_bad_language_is_rejected(make_app):
    with AuthedClient(make_app(gnani_api_key=KEY)) as c, c.websocket_connect("/ws/voice?language=klingon") as ws:
        assert ws.receive_json()["code"] == "BAD_LANGUAGE"


def test_ws_surfaces_handshake_rejection_without_leaking_key(make_app):
    with FakeStreamServer([], reject_status=401) as fake:
        app = make_app(gnani_api_key=KEY, gnani_base_url=f"http://127.0.0.1:{fake.port}")
        with AuthedClient(app) as c, c.websocket_connect("/ws/voice?language=gu") as ws:
            msgs = collect(ws, until=("closed",))
    err = next(m for m in msgs if m["type"] == "error")
    assert err["code"] == "HANDSHAKE" and "API key" in err["message"] and KEY not in json.dumps(msgs)


def test_ws_unreachable_upstream_reports_network_error(make_app):
    app = make_app(gnani_api_key=KEY, gnani_base_url="http://127.0.0.1:9")
    with AuthedClient(app) as c, c.websocket_connect("/ws/voice?language=gu") as ws:
        msgs = collect(ws, until=("closed",))
    assert any(m["type"] == "error" and m["code"] == "NETWORK" for m in msgs)


# ---------------------------------------------------------------- 2.6.0: reply first, voice after, on the live connection
def _tts_transport(status=200, calls=None):
    def handler(req: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(json.loads(req.content)["text"])
        if status != 200:
            return httpx.Response(status, json={"success": False, "message": "simulated"})
        return httpx.Response(200, content=make_wav(0.3, 24000), headers={"content-type": "audio/wav"})
    return httpx.MockTransport(handler)


def _speak_one_sentence(ws):
    assert ws.receive_json()["type"] == "ready"
    ws.send_bytes(pcm_of(1.0))
    ws.send_text(json.dumps({"type": "commit"}))


def test_deferred_audio_sends_the_turn_first_and_the_voice_after(make_app):
    spoken: list[str] = []
    with FakeStreamServer(["do kilo chini aur ek litre doodh"]) as fake:
        app = make_app(gnani_api_key=KEY, gnani_base_url=f"http://127.0.0.1:{fake.port}", gnani_max_calls_per_hour=1000)
        app.state.gnani._transport = _tts_transport(calls=spoken)
        with AuthedClient(app) as c, c.websocket_connect("/ws/voice?language=hi&speak_reply=true&defer_audio=true") as ws:
            _speak_one_sentence(ws)
            msgs = collect(ws, until=("audio", "error", "closed"), limit=20)
            ws.send_text(json.dumps({"type": "end"}))
    kinds = [m["type"] for m in msgs]
    assert "turn" in kinds and "audio" in kinds and kinds.index("turn") < kinds.index("audio")
    turn, audio = next(m for m in msgs if m["type"] == "turn"), next(m for m in msgs if m["type"] == "audio")
    assert turn["audio"] is None and turn["reply_text"] and turn["cart"]["total_paise"] == 2 * 4600 + 5600   # the reply and the bill do not wait for the voice
    assert audio["assistant_turn_id"] == turn["assistant_turn_id"] and audio["audio"]["audio_url"] and audio["audio"]["error"] is None
    assert spoken == [turn["reply_text"]]                                                                       # the voice says exactly the stored reply


def test_deferred_audio_that_fails_still_follows_the_turn_and_keeps_the_connection(make_app):
    with FakeStreamServer(["do kilo chini aur ek litre doodh", "ek kilo dal"]) as fake:
        app = make_app(gnani_api_key=KEY, gnani_base_url=f"http://127.0.0.1:{fake.port}", gnani_max_calls_per_hour=1000)
        app.state.gnani._transport = _tts_transport(status=400)
        with AuthedClient(app) as c, c.websocket_connect("/ws/voice?language=hi&speak_reply=true&defer_audio=true") as ws:
            _speak_one_sentence(ws)
            first = collect(ws, until=("audio", "closed"), limit=20)
            ws.send_bytes(pcm_of(1.0))                       # the connection is still usable: a second sentence is understood
            ws.send_text(json.dumps({"type": "commit"}))
            second = collect(ws, until=("turn", "closed"), limit=20)
            ws.send_text(json.dumps({"type": "end"}))
    audio = next(m for m in first if m["type"] == "audio")
    assert audio["audio"]["audio_url"] is None and audio["audio"]["error"]
    assert any(m["type"] == "turn" for m in second)


def test_without_deferred_audio_the_voice_comes_inside_the_turn(make_app):
    with FakeStreamServer(["do kilo chini aur ek litre doodh"]) as fake:
        app = make_app(gnani_api_key=KEY, gnani_base_url=f"http://127.0.0.1:{fake.port}", gnani_max_calls_per_hour=1000)
        app.state.gnani._transport = _tts_transport()
        with AuthedClient(app) as c, c.websocket_connect("/ws/voice?language=hi&speak_reply=true") as ws:
            _speak_one_sentence(ws)
            msgs = collect(ws, until=("turn", "error", "closed"), limit=20)
            ws.send_text(json.dumps({"type": "end"}))
    turn = next(m for m in msgs if m["type"] == "turn")
    assert turn["audio"]["audio_url"] and not any(m["type"] == "audio" for m in msgs)
