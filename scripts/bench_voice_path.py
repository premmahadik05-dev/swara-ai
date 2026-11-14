"""Benchmark of the voice request path against a LOCAL STAND-IN for Gnani with fixed delays.

What this is: a way to see what OUR code does with a slow upstream (how many connections it opens, how long the screen waits for the
spoken reply, how long a hung call blocks). The stand-in's delays are inputs you choose (--stt-ms, --tts-ms, --handshake-ms); they are NOT
Gnani's real speed, and nothing here talks to Gnani or needs a key. Real latency is recorded by the app itself for every call it makes:
see Settings -> Voice diagnostics (owner) after you take voice orders with your own key.

    backend/.venv/bin/python scripts/bench_voice_path.py                       # this tree
    backend/.venv/bin/python scripts/bench_voice_path.py --backend-dir /path/to/older/backend --label 2.5.0

It runs on any version of the backend (it feature-detects the pieces added later), so the same script gives the "before" and "after" numbers.
Output: one JSON object on stdout (and --out FILE).
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import statistics
import sys
import tempfile
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PW = "Quartz-Velvet-42!"   # throw-away account on a throw-away database


def wav_bytes(seconds: float = 1.0, rate: int = 16000, tone: bool = True) -> bytes:
    n = int(seconds * rate)
    frames = b"".join(int(6000 * math.sin(2 * math.pi * 220 * i / rate)).to_bytes(2, "little", signed=True) if tone else b"\x00\x00" for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(frames)
    return buf.getvalue()


class Stub(ThreadingHTTPServer):
    """Local fake of the two Gnani endpoints. Counts connections; can delay each new connection (a stand-in for TCP+TLS setup)."""
    daemon_threads = True

    def __init__(self, stt_ms: int, tts_ms: int, handshake_ms: int, hang: bool = False):
        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"   # keep-alive, so a client that reuses its connection can

            def log_message(self, *a):  # quiet
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                if hang:
                    time.sleep(30)
                if self.path.startswith("/stt/"):
                    time.sleep(stt_ms / 1000)
                    body = json.dumps({"success": True, "transcript": "2 kilo rice", "model": "prisma-v2.5", "request_id": "bench", "processing_time": 0.0}).encode()
                    ctype = "application/json"
                else:
                    time.sleep(tts_ms / 1000)
                    body, ctype = wav_bytes(0.5, 24000, tone=False), "audio/wav"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        super().__init__(("127.0.0.1", 0), H)
        self.connections = 0
        self.handshake_s = handshake_ms / 1000
        self.port = self.server_address[1]

    def get_request(self):
        sock, addr = super().get_request()
        self.connections += 1
        if self.handshake_s:
            time.sleep(self.handshake_s)   # every NEW connection pays this; a reused one does not
        return sock, addr

    def start(self) -> "Stub":
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self.shutdown(); self.server_close()


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return round(s[min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))], 1)


def settings_cls(**kw):
    from app.config import Settings
    fields = set(Settings.model_fields)
    return Settings(_env_file=None, **{k: v for k, v in kw.items() if k in fields})


# ---------------------------------------------------------------------------------------------------- M1: connections
def m1_connection_reuse(calls: int, stt_ms: int, handshake_ms: int) -> dict:
    from app.gnani.client import GnaniClient
    srv = Stub(stt_ms, 0, handshake_ms).start()
    try:
        cfg = settings_cls(gnani_api_key="stub-key-not-real", gnani_base_url=f"http://127.0.0.1:{srv.port}", gnani_max_calls_per_hour=100000)
        data = wav_bytes(0.5)

        async def go() -> list[float]:
            c = GnaniClient(cfg)
            per = []
            for _ in range(calls):
                t = time.perf_counter()
                await c.transcribe(data, language_code="en-IN")
                per.append((time.perf_counter() - t) * 1000)
            if hasattr(c, "aclose"):
                await c.aclose()
            return per

        t0 = time.perf_counter()
        per = asyncio.run(go())
        return {"calls": calls, "tcp_connections_opened": srv.connections, "total_ms": round((time.perf_counter() - t0) * 1000), "per_call_p50_ms": pct(per, 50),
                "first_call_ms": round(per[0], 1), "later_calls_p50_ms": pct(per[1:], 50) if calls > 1 else None}
    finally:
        srv.stop()


# ---------------------------------------------------------------------------------------------------- M2: reply visible
def m2_reply_visible(runs: int, stt_ms: int, tts_ms: int, handshake_ms: int) -> dict:
    from fastapi.testclient import TestClient
    from app.main import create_app
    srv = Stub(stt_ms, tts_ms, handshake_ms).start()
    tmp = Path(tempfile.mkdtemp(prefix="swara-bench-"))
    try:
        cfg = settings_cls(database_url=f"sqlite:///{tmp / 'b.db'}", data_dir=tmp, seed_on_startup=True, demo_history_days=7, scrypt_log2_n=10, scrypt_p=1,
                           gnani_api_key="stub-key-not-real", gnani_base_url=f"http://127.0.0.1:{srv.port}", gnani_max_calls_per_hour=100000,
                           rate_limit_per_minute=100000, auth_rate_per_minute=100000, cookie_secure=False)
        with TestClient(create_app(cfg), base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as c:
            r = c.post("/api/auth/signup", json={"full_name": "Bench Owner", "email": "bench@example.com", "password": PW, "accept_terms": True}); r.raise_for_status()
            H = {"X-CSRF-Token": r.json()["csrf_token"]}
            audio = wav_bytes(1.0)

            def fresh() -> None:
                for f in (tmp / "tts_cache").glob("*.wav"):
                    f.unlink()   # every run pays the (stand-in) TTS call: no cache hits

            def turn(speak: bool) -> tuple[float, dict]:
                t = time.perf_counter()
                r = c.post("/api/voice/turn", files={"audio": ("o.wav", audio, "audio/wav")}, data={"language": "en", "speak_reply": "true" if speak else "false"}, headers=H)
                r.raise_for_status()
                return (time.perf_counter() - t) * 1000, r.json()

            turn(True)   # warm-up (imports, first connection)
            serial, visible, ready, server_total = [], [], [], []
            has_speak_route = True
            for _ in range(runs):
                fresh()
                ms, _ = turn(True)
                serial.append(ms)
                fresh()
                ms, out = turn(False)
                visible.append(ms)
                if has_speak_route:
                    t = time.perf_counter()
                    r = c.post(f"/api/turns/{out['assistant_turn_id']}/speak", headers=H)
                    if r.status_code in (404, 405):
                        has_speak_route = False
                    else:
                        r.raise_for_status()
                        ready.append(ms + (time.perf_counter() - t) * 1000)
                if (out.get("timings") or {}).get("server_ms") is not None:
                    server_total.append(out["timings"]["server_ms"])
            res = {"runs": runs, "stub_stt_ms": stt_ms, "stub_tts_ms": tts_ms, "stub_new_connection_ms": handshake_ms,
                   "reply_with_voice_in_one_call_ms": {"p50": pct(serial, 50), "p95": pct(serial, 95)}}
            if has_speak_route:
                res["reply_on_screen_when_voice_is_deferred_ms"] = {"p50": pct(visible, 50), "p95": pct(visible, 95)}
                res["voice_ready_when_deferred_ms"] = {"p50": pct(ready, 50), "p95": pct(ready, 95)}
            if server_total:
                res["server_reported_total_ms_p50"] = pct(server_total, 50)
            return res
    finally:
        srv.stop()


# ---------------------------------------------------------------------------------------------------- M3: hung upstream
def m3_hang(timeout_s: float) -> dict:
    from app.gnani.client import GnaniClient, GnaniError
    srv = Stub(0, 0, 0, hang=True).start()
    try:
        cfg = settings_cls(gnani_api_key="stub-key-not-real", gnani_base_url=f"http://127.0.0.1:{srv.port}", gnani_timeout_s=timeout_s,
                           gnani_stt_timeout_s=timeout_s, gnani_tts_timeout_s=timeout_s, gnani_max_calls_per_hour=100000)

        async def go() -> dict:
            c = GnaniClient(cfg)
            t = time.perf_counter()
            try:
                await c.transcribe(wav_bytes(0.5), language_code="en-IN")
                err, attempts = None, None
            except GnaniError as exc:
                err, attempts = exc.error_type, getattr(exc.meta, "attempts", None)
            ms = round((time.perf_counter() - t) * 1000)
            if hasattr(c, "aclose"):
                await c.aclose()
            return {"timeout_s": timeout_s, "blocked_for_ms": ms, "error": err, "attempts": attempts}

        return asyncio.run(go())
    finally:
        srv.stop()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backend-dir", default=str(REPO / "backend"))
    ap.add_argument("--label", default="this tree")
    ap.add_argument("--stt-ms", type=int, default=600, help="stand-in speech-to-text time per call")
    ap.add_argument("--tts-ms", type=int, default=500, help="stand-in text-to-speech time per call")
    ap.add_argument("--handshake-ms", type=int, default=100, help="stand-in cost of opening a NEW connection")
    ap.add_argument("--calls", type=int, default=20)
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--hang-timeout-s", type=float, default=1.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.backend_dir).resolve()))
    from app.main import VERSION
    out = {
        "label": a.label, "version": VERSION, "stand_in": "local fake of the Gnani endpoints with the delays below; not Gnani's real speed",
        "m1_connections": m1_connection_reuse(a.calls, a.stt_ms, a.handshake_ms),
        "m2_reply_visible": m2_reply_visible(a.runs, a.stt_ms, a.tts_ms, a.handshake_ms),
        "m3_hung_upstream": m3_hang(a.hang_timeout_s),
    }
    text = json.dumps(out, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
