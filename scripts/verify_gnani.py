"""LIVE check of your Gnani key, one language at a time: Timbre (TTS) and Prisma (STT) are checked independently.

Run this yourself (needs internet + GNANI_API_KEY in .env). It is the only way to see real Gnani behaviour: nothing in the automated
test-suite talks to Gnani, and the sandbox this project was built in had no key and no route to Gnani. Until you run it, the app reports every
language's live status as "not run".

    python scripts/verify_gnani.py                  # all 11 languages, 3 calls each (about 33 calls)
    python scripts/verify_gnani.py --langs ta mr    # a subset
    python scripts/verify_gnani.py --stream         # also the realtime WebSocket (+1 call per language)

Four checks per language, each recorded on its own (a failure of one never hides or fakes another):

  tts           Timbre speaks the language's sample sentence with the configured voice.            (1 call)
  stt_code      Prisma accepts the language code for an audio request. The audio is a generated
                non-speech tone, so this proves the CODE is accepted, not that speech is recognised. (1 call)
  stt_loopback  Prisma transcribes the Timbre audio from ``tts``; the parser must find the expected order.
                A loopback (synthetic voice, same vendor): a weak signal, and skipped if ``tts`` failed. (1 call)
  stt_human     Prisma transcribes a recording of a PERSON, if you put one at eval/samples/<lang>.wav
                (say the sample sentence the app shows for that language; optional eval/samples/<lang>.txt holds
                the exact words if you said something else). The only evidence about real recognition.   (1 call)

Output: a table on screen, eval/results/gnani_live_<timestamp>.{md,json}, and eval/results/live_verification.json, which GET /api/languages
reads so the app can show what has been verified. Only measured values are written; a language you did not run keeps its earlier result
(if it came from the same Gnani models and host) or stays "not run".
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import struct
import sys
import time
import wave
import io
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from _live import PHRASES, ROOT, Env, Row, make_env, parsed_lines, pct, save_report, synth, transcribe_row

from app import languages as reg  # noqa: E402
from app.gnani.client import GnaniError  # noqa: E402
from app.gnani.voices import stt_params  # noqa: E402
from app.services import noise as nz  # noqa: E402

CHECKS = ("tts", "stt_code", "stt_loopback", "stt_human")
SAMPLES_DIR = ROOT / "eval" / "samples"
LIVE_FILE = ROOT / "eval" / "results" / "live_verification.json"
STOP_ON = ("NOT_CONFIGURED", "INVALID_API_KEY", "MISSING_API_KEY", "SCOPE_NOT_ALLOWED", "LOCAL_BUDGET_EXCEEDED", "RATE_LIMITED")


def probe_tone(seconds: float = 1.5, sr: int = 16000) -> bytes:
    """A short generated test clip that is NOT speech (an amplitude-modulated tone). Used only to see whether a language code is accepted."""
    n = int(seconds * sr)
    frames = b"".join(struct.pack("<h", int(0.3 * 32767 * math.sin(2 * math.pi * 220 * i / sr) * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / sr)))) for i in range(n))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(frames)
    return buf.getvalue()


def _fail(exc: GnaniError) -> dict:
    return {"status": "failed", "error_code": exc.error_type, "detail": exc.user_message[:240]}


async def check_language(env: Env, key: str, samples_dir: Path, *, stream: bool = False) -> tuple[dict, Row, Optional[dict], bool]:
    """Run the four independent checks for one language. Returns (checks, loopback row, stream result, stop) - ``stop`` means the key itself is the problem."""
    lang = reg.LANGUAGES[key]
    code, _fmt = stt_params(env.settings, key)
    checks: dict[str, dict] = {c: {"status": "skipped", "detail": "not run"} for c in CHECKS}
    row = Row(lang=key, phrase=lang.sample, condition="loopback")
    streamed: Optional[dict] = None
    stop = False
    wav: Optional[bytes] = None

    # 1. TTS on its own
    try:
        res, voice = await synth(env, key, lang.sample)
        wav = res.audio
        ok = wav[:4] == b"RIFF" and len(wav) > 1000
        checks["tts"] = {"status": "passed" if ok else "failed", "latency_ms": res.meta.latency_ms, "audio_bytes": len(wav), "voice": voice,
                         "detail": f"Timbre returned {len(wav)} bytes for voice {voice}, language {lang.tts_code}." if ok else "Timbre returned something that is not a WAV file."}
        row.tts_ms, row.voice = res.meta.latency_ms, voice
        if not ok:
            wav = None
    except GnaniError as exc:
        checks["tts"] = _fail(exc)
        row.error = f"TTS {exc.error_type}: {exc.user_message}"
        stop = exc.error_type in STOP_ON

    # 2. STT accepts the code (independent of TTS: a generated tone, not Timbre audio)
    if not stop:
        try:
            r = await env.client.transcribe(probe_tone(), language_code=code, filename="probe.wav")
            checks["stt_code"] = {"status": "passed", "latency_ms": r.meta.latency_ms, "transcript": r.transcript or "",
                                  "detail": f"Prisma accepted language_code={code} for a generated non-speech tone (this does not show speech is recognised)."}
        except GnaniError as exc:
            checks["stt_code"] = _fail(exc)
            stop = exc.error_type in STOP_ON

    # 3. Loopback: Timbre's audio through Prisma (needs the TTS audio)
    if not stop:
        if wav is None:
            checks["stt_loopback"] = {"status": "skipped", "detail": "No Timbre audio to send (the tts check did not pass)."}
        else:
            await transcribe_row(env, row, wav, lang.sample_expect_pairs, lang.sample)
            if row.error:
                err = row.error.split(":", 1)
                checks["stt_loopback"] = {"status": "failed", "error_code": err[0][:60], "detail": row.error[:240]}
            else:
                checks["stt_loopback"] = {
                    "status": "passed" if row.chain_ok else "failed", "latency_ms": row.stt_ms, "transcript": row.transcript or "", "expected": lang.sample,
                    "matched": bool(row.chain_ok),
                    "detail": ("Timbre audio -> Prisma -> parser gave the expected order (loopback: synthetic voice from the same vendor)."
                               if row.chain_ok else f"Prisma answered, but the parser found {row.parsed or 'no order'} instead of the expected order."),
                }

    # 4. A person's recording, if the owner supplied one
    human = samples_dir / f"{key}.wav"
    if stop:
        pass
    elif not human.is_file():
        checks["stt_human"] = {"status": "skipped", "detail": f"No recording at eval/samples/{key}.wav."}
    else:
        ref_file = samples_dir / f"{key}.txt"
        reference = ref_file.read_text(encoding="utf-8").strip() if ref_file.is_file() else lang.sample
        expected = lang.sample_expect_pairs if not ref_file.is_file() else parsed_lines(env, reference, key)
        hrow = Row(lang=key, phrase=reference, condition="human")
        try:
            data = human.read_bytes()
            if len(data) > env.settings.max_upload_bytes:
                raise ValueError("file is larger than the upload limit")
            nz.read_wav(data)  # must be a readable PCM WAV
        except Exception as exc:  # noqa: BLE001
            checks["stt_human"] = {"status": "skipped", "detail": f"eval/samples/{key}.wav was not used: {str(exc)[:120]}"}
        else:
            await transcribe_row(env, hrow, data, expected, reference)
            if hrow.error:
                checks["stt_human"] = {"status": "failed", "error_code": hrow.error.split(':', 1)[0][:60], "detail": hrow.error[:240]}
            else:
                checks["stt_human"] = {"status": "passed" if hrow.chain_ok else "failed", "latency_ms": hrow.stt_ms, "transcript": hrow.transcript or "",
                                       "expected": reference, "matched": bool(hrow.chain_ok),
                                       "detail": f"A person's recording, word error rate {hrow.wer}." if hrow.chain_ok else f"The parser found {hrow.parsed or 'no order'} (word error rate {hrow.wer})."}

    if stream and not stop and wav is not None:
        streamed = await stream_once(env, key, wav)
        streamed["lang"] = key
    return checks, row, streamed, stop


async def stream_once(env: Env, lang: str, wav24_or16: bytes, timeout: float = 25.0) -> dict:
    """Send audio to the realtime endpoint exactly as the backend proxy does (1024-byte PCM16 frames, language sent in both documented header names)."""
    from websockets.asyncio.client import connect
    s = env.settings
    code, fmt = stt_params(s, lang)
    url = s.gnani_base_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + "/stt/v3/stream"
    headers = {"x-api-key-id": s.gnani_key or "", "lang_code": code, "language_code": code, "x-sample-rate": "16000"}
    if s.gnani_stt_model == "prisma-v3.0":
        headers["model"] = "prisma-v3.0"
    if fmt:
        headers["format"] = fmt
    x, sr = nz.read_wav(wav24_or16)
    x = nz.resample(x, sr, 16000) if sr != 16000 else x
    pcm = (x.clip(-1, 1) * 32767).astype("<i2").tobytes() + b"\x00" * 32000  # 1 s of trailing silence finalises the last sentence
    out = {"ok": False, "transcript": None, "first_transcript_ms": None, "error": None}
    t0 = time.perf_counter()
    try:
        async with connect(url, additional_headers=headers, open_timeout=15) as ws:
            async def sender():
                for i in range(0, len(pcm), 1024):
                    chunk = pcm[i:i + 1024].ljust(1024, b"\x00")
                    await ws.send(chunk)
                    await asyncio.sleep(0.032)  # real-time pace: 512 samples @16 kHz = 32 ms
                await ws.send(json.dumps({"type": "commit"}))
            task = asyncio.create_task(sender())
            try:
                while time.perf_counter() - t0 < timeout:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    if isinstance(msg, bytes):
                        continue
                    m = json.loads(msg)
                    if m.get("type") == "transcript" and m.get("text"):
                        out.update(ok=True, transcript=m["text"], first_transcript_ms=int((time.perf_counter() - t0) * 1000))
                        break
                    if m.get("type") == "error":
                        out["error"] = str(m)[:200]
                        break
            finally:
                task.cancel()
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return out


async def verify(env: Env, langs: list[str], stream: bool = False, samples_dir: Optional[Path] = None) -> dict:
    """All checks for ``langs``. Returns {"checks": {lang: {...}}, "rows": [...], "streams": [...]}; stops early if the key itself is rejected."""
    samples_dir = samples_dir or SAMPLES_DIR
    out: dict = {"checks": {}, "rows": [], "streams": []}
    for key in langs:
        checks, row, streamed, stop = await check_language(env, key, samples_dir, stream=stream)
        out["checks"][key] = checks
        out["rows"].append(row)
        if streamed:
            out["streams"].append(streamed)
        if stop:
            break
    return out


async def run(env: Env, langs: list[str], stream: bool = False) -> tuple[list[Row], list[dict]]:
    """Older entry point (kept for the tests and anyone importing it): the loopback rows and the stream results."""
    res = await verify(env, langs, stream)
    return res["rows"], res["streams"]


def build_result(env: Env, checks: dict, mode: str) -> dict:
    """The document written to eval/results/live_verification.json (schema 1; read by app/services/verification.py)."""
    s = env.settings
    return {
        "schema": 1, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "mode": mode,
        "stt_model": s.gnani_stt_model, "tts_model": s.gnani_tts_model, "gnani_host": urlparse(s.gnani_base_url).netloc,
        "note": "Written by scripts/verify_gnani.py. mode=live means the checks reached the real Gnani service with a real key.",
        "checks": checks,
    }


def merge_with_previous(result: dict, path: Path) -> dict:
    """Keep the earlier live results of languages that were not run this time, if they came from the same host and models."""
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    if not isinstance(old, dict) or old.get("mode") != "live" or any(old.get(k) != result[k] for k in ("stt_model", "tts_model", "gnani_host")):
        return result
    kept = {k: v for k, v in (old.get("checks") or {}).items() if k in reg.LANGUAGES and k not in result["checks"] and isinstance(v, dict)}
    result["checks"] = {**kept, **result["checks"]}
    return result


def write_live_file(result: dict, path: Path = LIVE_FILE) -> Path:
    """Write the live results, keeping earlier live results of languages that were not run this time (same host and models only)."""
    result = merge_with_previous(result, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def render(rows, streams, env: Env, note: str, checks: Optional[dict] = None) -> str:
    s = env.settings
    L = [f"# Gnani live verification ({note})", "",
         f"* Date: {time.strftime('%Y-%m-%d %H:%M:%S')} | Python {platform.python_version()} | {platform.system()}",
         f"* Base URL: `{s.gnani_base_url}` | STT model: `{s.gnani_stt_model}` | TTS model: `{s.gnani_tts_model}`",
         "* The loopback audio is Timbre TTS output (a clean synthetic voice), NOT a human recording. Only the `stt_human` check uses a person's recording.", ""]
    if checks:
        L += ["## Independent checks", "", "| Language | TTS (Timbre) | STT language code | STT loopback | STT human recording |", "|---|---|---|---|---|"]
        for key, c in checks.items():
            cell = lambda n: c[n]["status"] + (f" ({c[n]['latency_ms']:.0f} ms)" if c[n].get("latency_ms") and c[n]["status"] == "passed" else "")  # noqa: E731
            L.append(f"| {reg.LANGUAGES[key].name} ({key}) | {cell('tts')} | {cell('stt_code')} | {cell('stt_loopback')} | {cell('stt_human')} |")
        L.append("")
    L += ["## Loopback detail (Timbre audio -> Prisma -> parser)", "",
          "| Lang | Voice | TTS ms | STT ms | WER | Transcript | Parsed order | Chain OK |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r.lang} | {r.voice or '-'} | {r.tts_ms or '-'} | {r.stt_ms or '-'} | {r.wer if r.wer is not None else '-'} | "
                 f"{(r.transcript or r.error or '-').replace('|', '/')} | {r.parsed or '-'} | {r.chain_ok if r.chain_ok is not None else '-'} |")
    ok = [r for r in rows if r.chain_ok]
    L += ["", f"Chain OK (TTS -> STT -> parser gives the expected order): **{len(ok)}/{len(rows)}**"]
    stt = [r.stt_ms for r in rows if r.stt_ms]
    if stt:
        L.append(f"STT latency over {len(stt)} calls: p50 {pct(stt, 50)} ms, max {max(stt)} ms (includes your network round trip).")
    if streams:
        L += ["", "## Realtime WebSocket", "", "| Lang | OK | Time to transcript ms | Transcript / error |", "|---|---|---|---|"]
        for r in streams:
            L.append(f"| {r['lang']} | {r['ok']} | {r['first_transcript_ms'] or '-'} | {(r['transcript'] or r['error'] or '-')} |")
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--langs", nargs="*", default=list(reg.ORDER), choices=list(reg.ORDER), help="default: every language in the registry")
    ap.add_argument("--stream", action="store_true", help="also test wss://.../stt/v3/stream")
    ap.add_argument("--samples", type=Path, default=SAMPLES_DIR, help="folder with optional <lang>.wav recordings of a person")
    a = ap.parse_args(argv)
    env = make_env()
    if not env.settings.gnani_configured:
        print("GNANI_API_KEY is not set. Copy .env.example to .env, paste your key, run again.", file=sys.stderr)
        return 2
    off = reg.disabled_keys(env.settings) & set(a.langs)
    langs = [k for k in a.langs if k not in off]
    if off:
        print(f"Skipping languages switched off in DISABLED_LANGUAGES: {', '.join(sorted(off))}", file=sys.stderr)
    need = len(langs) * (4 if a.stream else 3) + sum(1 for k in langs if (a.samples / f"{k}.wav").is_file())
    print(f"Checking {len(langs)} language(s): about {need} Gnani calls (local limit {env.settings.gnani_max_calls_per_hour}/hour).", file=sys.stderr)
    res = asyncio.run(verify(env, langs, a.stream, a.samples))
    live = env.client._transport is None  # a client with a fake transport (tests) never produces a "live" file
    md = render(res["rows"], res["streams"], env, "LIVE" if live else "SIMULATED", res["checks"])
    print(md)
    if res["checks"] and live:
        print("saved:", write_live_file(build_result(env, res["checks"], "live"), LIVE_FILE))
    p = save_report("gnani_live", {"rows": [asdict(r) for r in res["rows"]], "streams": res["streams"], "checks": res["checks"], "base_url": env.settings.gnani_base_url,
                                   "stt_model": env.settings.gnani_stt_model, "tts_model": env.settings.gnani_tts_model}, md)
    print("saved:", p)
    failed = any(c["status"] == "failed" for v in res["checks"].values() for c in v.values())
    return 0 if res["checks"] and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
