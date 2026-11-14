"""Gnani AI REST client (Prisma speech-to-text, Timbre text-to-speech).

Implemented against the public documentation (https://docs.gnani.ai):

* STT  ``POST {base}/stt/v3``  multipart/form-data  (audio_file, language_code, model?, format?, bias_*)
* TTS  ``POST {base}/api/v1/tts/inference``  JSON -> raw audio bytes
* Auth ``X-API-Key-ID`` header on every request
* Errors: STT ``{"success": false, "error": {"type", "message"}}``; auth/rate-limit
  ``{"detail": {"error_code", "message", "status_code"}}``; TTS ``{"success": false, "message"}``
* Retry (docs "Retry guidance"): connection errors and 429/500/502/503/504 with a short exponential
  back-off; no retry for other 4xx. A call that was SENT and then got no answer within its timeout is
  not retried: for a person waiting at a counter, a clear "that took too long, try again" after 20 s is
  better than a silent second wait of 20 s (and a second charge).
* One pooled HTTP connection is kept warm between calls (keep-alive), so only the first call after an idle
  minute pays for opening a connection; before 2.6.0 every call opened a new one.

The API key is read server-side only and is never logged or returned to the browser.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import httpx

from ..config import Settings

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BACKOFF_S = 0.25            # 0.25 s, then 0.5 s (was 0.5 s, then 1 s)
KEEPALIVE_S = 60.0          # how long an idle connection is kept for the next call
# Failures before the request was accepted: safe to try again on a fresh connection. (A stale pooled connection that the server closed shows up as
# RemoteProtocolError or ReadError on the next use.)
RETRY_ON = (httpx.ConnectError, httpx.ConnectTimeout, httpx.WriteError, httpx.RemoteProtocolError, httpx.ReadError)
# Sent, then no answer in time: reported as TIMEOUT, not retried.
TIMED_OUT = (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)

# Language -> Gnani code maps come from the central registry (app/languages.py): Timbre accepts hi-en for Hinglish
# (Poorvi); Prisma v2.5 handles English-Hindi mixed speech through en-IN; every other language maps 1:1.
from ..languages import LANG_TO_STT, LANG_TO_TTS  # noqa: E402,F401  (re-exported: older imports use these names)

# v2.5 documents `transcribe` (inverse text normalisation) for hi-IN and en-IN only; sending it for another language is a 400.
_ITN_V25 = {"hi-IN", "en-IN"}


def effective_stt_format(model: str, language_code: str, fmt: Optional[str]) -> Optional[str]:
    """The `format` form field to send, or None to leave it out (verbatim is the default).

    This only drops a format that the documentation says the model cannot do for that language; it never changes
    the language or the provider."""
    if not fmt or fmt == "verbatim":
        return None
    if model != "prisma-v3.0":
        return fmt if (fmt == "transcribe" and language_code in _ITN_V25) else None
    return fmt


@dataclass
class CallMeta:
    provider: str
    model: str
    ok: bool
    status_code: Optional[int]
    latency_ms: int
    error_type: Optional[str] = None
    units: int = 0
    attempts: int = 1


class GnaniError(Exception):
    def __init__(self, message: str, *, status: Optional[int] = None, error_type: str = "ERROR", meta: Optional[CallMeta] = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.error_type = error_type
        self.meta = meta

    @property
    def user_message(self) -> str:
        t = self.error_type
        if t == "NOT_CONFIGURED":
            return "Gnani API key is not configured. Add GNANI_API_KEY to .env (see README) and restart the backend."
        if t in ("MISSING_API_KEY", "INVALID_API_KEY"):
            return "Gnani rejected the API key. Check GNANI_API_KEY in .env."
        if self.status == 402:
            return "Gnani reports insufficient credit for this key."
        if t == "SCOPE_NOT_ALLOWED":
            return "This Gnani API key does not have the speech scope enabled."
        if t == "MAX_AUDIO_DURATION_EXCEEDED":
            return "Audio is longer than 30 seconds. Please speak a shorter order."
        if t == "EMPTY_AUDIO":
            return "No audio was received."
        if t in ("UNSUPPORTED_AUDIO_FORMAT", "AUDIO_CONVERSION_ERROR"):
            return "Gnani could not read this audio format. Use WAV, MP3, OGG, FLAC, AAC or M4A."
        if t == "TIMEOUT":
            return "The speech service took too long to answer. Your bill has not changed. Try again; if it keeps happening, check the internet connection."
        if t == "LOCAL_BUDGET_EXCEEDED":
            return self.message
        if self.status == 429 or t == "RATE_LIMITED":
            return "Gnani rate limit reached. Wait a moment and try again."
        return self.message or "Gnani request failed."


class GnaniNotConfigured(GnaniError):
    def __init__(self) -> None:
        super().__init__("Gnani API key not configured", error_type="NOT_CONFIGURED")


@dataclass
class STTResult:
    transcript: str
    model: str
    request_id: str
    processing_time: Optional[float]
    end_to_end_latency: Optional[float]
    detected_language_code: Optional[str]
    literal: Optional[str]
    meta: CallMeta
    raw: dict = field(default_factory=dict)


@dataclass
class TTSResult:
    audio: bytes
    content_type: str
    meta: CallMeta


class CallBudget:
    """Sliding one-hour call counter - protects the programme credits from loops/bugs."""

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self._stamps: deque[float] = deque()

    def check(self) -> None:
        now = time.monotonic()
        while self._stamps and now - self._stamps[0] > 3600:
            self._stamps.popleft()
        if len(self._stamps) >= self.max_calls:
            raise GnaniError(
                f"Local safety limit reached ({self.max_calls} Gnani calls/hour). "
                "Raise GNANI_MAX_CALLS_PER_HOUR in .env if this is intentional.",
                error_type="LOCAL_BUDGET_EXCEEDED",
            )
        self._stamps.append(now)

    @property
    def used(self) -> int:
        now = time.monotonic()
        return sum(1 for s in self._stamps if now - s <= 3600)


def _parse_error(resp: httpx.Response) -> tuple[str, str]:
    """Return (error_type, message) from any of Gnani's documented error shapes."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return "HTTP_ERROR", (resp.text or "")[:200] or f"HTTP {resp.status_code}"
    if isinstance(body, dict):
        det = body.get("detail")
        if isinstance(det, dict):
            return str(det.get("error_code", "ERROR")), str(det.get("message", ""))
        if isinstance(det, list):  # FastAPI-style 422 validation list
            return "VALIDATION_ERROR", "; ".join(str(d.get("msg", d)) for d in det[:3])
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("type", "ERROR")), str(err.get("message", ""))
        if isinstance(err, str):  # 504: {"error": "Gateway Timeout", "code": "UPSTREAM_TIMEOUT", "message": ...}
            return str(body.get("code", err)), str(body.get("message", err))
        if "message" in body:
            return "ERROR", str(body["message"])
    return "ERROR", str(body)[:200]


class GnaniClient:
    def __init__(self, settings: Settings, transport: Optional[httpx.AsyncBaseTransport] = None, budget: Optional[CallBudget] = None):
        self.s = settings
        self._transport = transport
        self.budget = budget or CallBudget(settings.gnani_max_calls_per_hour)
        self._http: Optional[httpx.AsyncClient] = None
        self._http_key: Optional[tuple] = None

    # ------------------------------------------------------------------ plumbing
    def _headers(self, request_id: Optional[str] = None) -> dict[str, str]:
        key = self.s.gnani_key
        if not self.s.gnani_configured or not key:
            raise GnaniNotConfigured()
        h = {"X-API-Key-ID": key}
        if request_id:
            h["X-API-Request-ID"] = request_id
        return h

    def _timeout(self, provider: str) -> httpx.Timeout:
        """Per-call limit: STT and TTS have their own settings, and GNANI_TIMEOUT_S (the old single setting) is still honoured as a ceiling."""
        own = self.s.gnani_tts_timeout_s if provider == "gnani-tts" else self.s.gnani_stt_timeout_s
        return httpx.Timeout(min(own, self.s.gnani_timeout_s), connect=min(self.s.gnani_connect_timeout_s, self.s.gnani_timeout_s))

    def _client(self) -> httpx.AsyncClient:
        """The shared connection pool. It belongs to one event loop and one base URL / transport; if either changes (tests swap the transport, a new loop
        starts) a fresh pool is made and the old one is dropped."""
        key = (asyncio.get_running_loop(), self.s.gnani_base_url, id(self._transport))
        if self._http is None or self._http.is_closed or self._http_key != key:
            self._http = httpx.AsyncClient(
                base_url=self.s.gnani_base_url.rstrip("/"), transport=self._transport,
                limits=httpx.Limits(max_connections=16, max_keepalive_connections=4, keepalive_expiry=KEEPALIVE_S),
            )
            self._http_key = key
        return self._http

    async def aclose(self) -> None:
        """Close the pool (called when the server stops)."""
        client, self._http, self._http_key = self._http, None, None
        if client is not None and not client.is_closed:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass

    async def _send(self, provider: str, model: str, method: str, path: str, units: int, **kwargs) -> tuple[httpx.Response, CallMeta]:
        self.budget.check()
        last_exc: Optional[Exception] = None
        timed_out = False
        started = time.perf_counter()
        attempts = 0
        resp: Optional[httpx.Response] = None
        client = self._client()
        timeout = self._timeout(provider)
        for attempt in range(MAX_ATTEMPTS):
            attempts = attempt + 1
            try:
                resp = await client.request(method, path, timeout=timeout, **kwargs)
                if resp.status_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(BACKOFF_S * (2**attempt))
                    continue
                last_exc = None
                break
            except TIMED_OUT as exc:
                last_exc, timed_out = exc, True
                break
            except RETRY_ON as exc:
                last_exc = exc
                if attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(BACKOFF_S * (2**attempt))
                    continue
        latency = int((time.perf_counter() - started) * 1000)
        if resp is None:
            meta = CallMeta(provider, model, False, None, latency, type(last_exc).__name__ if last_exc else "NETWORK", units, attempts)
            if timed_out:
                raise GnaniError(f"Gnani did not answer within {timeout.read:g} s ({type(last_exc).__name__}).", error_type="TIMEOUT", meta=meta)
            raise GnaniError(
                f"Could not reach Gnani ({type(last_exc).__name__}). Check your internet connection and GNANI_BASE_URL.",
                error_type="NETWORK", meta=meta,
            )
        meta = CallMeta(provider, model, resp.is_success, resp.status_code, latency, None, units, attempts)
        if not resp.is_success:
            etype, msg = _parse_error(resp)
            meta.error_type = etype
            raise GnaniError(msg or f"HTTP {resp.status_code}", status=resp.status_code, error_type=etype, meta=meta)
        return resp, meta

    # ------------------------------------------------------------------ STT
    async def transcribe(
        self,
        audio: bytes,
        *,
        language_code: str,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
        model: Optional[str] = None,
        fmt: Optional[str] = None,
        bias_list: Optional[list[str]] = None,
        bias_score: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> STTResult:
        model = model or self.s.gnani_stt_model
        rid = request_id or uuid.uuid4().hex
        data: dict[str, str] = {"language_code": language_code}
        if model == "prisma-v3.0":
            data["model"] = "prisma-v3.0"  # Prisma v2.5 is the default when `model` is omitted
        fmt = effective_stt_format(model, language_code, fmt or self.s.gnani_stt_format)
        if fmt:
            data["format"] = fmt
        if bias_list and model != "prisma-v3.0":
            data["bias_list"] = json.dumps(bias_list[:100], ensure_ascii=False)
            data["bias_score"] = str(bias_score if bias_score is not None else 1.0)
        files = {"audio_file": (filename, audio, content_type)}
        resp, meta = await self._send(
            "gnani-stt", model, "POST", "/stt/v3", len(audio),
            headers=self._headers(rid), data=data, files=files,
        )
        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            meta.ok = False
            raise GnaniError("Gnani returned a non-JSON STT response", status=resp.status_code, error_type="BAD_RESPONSE", meta=meta) from exc
        if not body.get("success", True):
            meta.ok = False
            raise GnaniError(str(body)[:200], status=resp.status_code, error_type="BAD_RESPONSE", meta=meta)
        out = body.get("output") or {}
        return STTResult(
            transcript=(body.get("transcript") or "").strip(),
            model=str(body.get("model", model)),
            request_id=str(body.get("request_id", rid)),
            processing_time=body.get("processing_time"),
            end_to_end_latency=body.get("end_to_end_latency"),
            detected_language_code=body.get("detected_language_code"),
            literal=out.get("literal") if isinstance(out, dict) else None,
            meta=meta,
            raw={k: v for k, v in body.items() if k != "transcript"},
        )

    # ------------------------------------------------------------------ TTS
    async def synthesize(
        self,
        text: str,
        *,
        language: str,
        voice: str,
        model: Optional[str] = None,
        speed: float = 1.0,
        sample_rate: int = 24000,
    ) -> TTSResult:
        model = model or self.s.gnani_tts_model
        payload = {
            "text": text,
            "voice": voice,
            "model": model,
            "language": language,
            "speed": speed,
            "audio_config": {
                "sample_rate": sample_rate, "num_channels": 1, "sample_width": 2,
                "encoding": "linear_pcm", "container": "wav",
            },
        }
        headers = {**self._headers(), "Content-Type": "application/json"}
        resp, meta = await self._send(
            "gnani-tts", model, "POST", "/api/v1/tts/inference", len(text), headers=headers, json=payload,
        )
        ctype = resp.headers.get("content-type", "audio/wav")
        if "json" in ctype:  # error-ish JSON with 200 would be unexpected; surface it
            meta.ok = False
            raise GnaniError(resp.text[:200], status=resp.status_code, error_type="BAD_RESPONSE", meta=meta)
        if not resp.content:
            meta.ok = False
            raise GnaniError("Gnani returned empty audio", status=resp.status_code, error_type="EMPTY_AUDIO", meta=meta)
        return TTSResult(resp.content, ctype, meta)
