"""Gnani REST contract tests.

IMPORTANT: these run against ``httpx.MockTransport`` - a *simulator written from Gnani's public
documentation*. They prove that this code sends the documented request shape and handles the
documented error envelopes. They do NOT prove that Gnani's live service behaves this way; that is what
``scripts/verify_gnani.py`` is for (needs a real key and network access).
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.gnani.client import CallBudget, GnaniClient, GnaniError, GnaniNotConfigured

from .helpers import KEY, make_wav


def cfg(**kw) -> Settings:
    kw.setdefault("gnani_api_key", KEY)
    return Settings(_env_file=None, **kw)


def client_for(handler, **kw) -> GnaniClient:
    return GnaniClient(cfg(**kw), transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def _fast(*_a, **_k):
        return None

    monkeypatch.setattr("app.gnani.client.asyncio.sleep", _fast)


STT_OK = {"success": True, "transcript": "ek kilo chini", "model": "prisma-v2.5", "request_id": "r-1",
          "processing_time": 0.31, "end_to_end_latency": 0.52, "detected_language_code": "hi-IN"}


# ------------------------------------------------------------------ STT request shape
async def test_stt_request_shape_prisma_v25():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["req"] = req
        return httpx.Response(200, json=STT_OK)

    res = await client_for(handler).transcribe(make_wav(), language_code="gu-IN")
    req = seen["req"]
    assert req.method == "POST" and req.url.path == "/stt/v3" and req.url.host == "api.vachana.ai"
    assert req.headers["x-api-key-id"] == KEY
    assert req.headers["content-type"].startswith("multipart/form-data")
    body = req.content
    assert b'name="audio_file"' in body and b'name="language_code"\r\n\r\ngu-IN' in body
    assert b'name="model"' not in body  # v2.5 is the default when `model` is omitted
    assert b'name="format"' not in body  # verbatim is the default
    assert res.transcript == "ek kilo chini" and res.request_id == "r-1" and res.processing_time == 0.31
    assert res.meta.ok and res.meta.status_code == 200 and res.meta.attempts == 1


async def test_stt_prisma_v30_sends_model_and_ignores_bias():
    seen = {}

    def handler(req):
        seen["body"] = req.content
        return httpx.Response(200, json={**STT_OK, "model": "prisma-v3.0"})

    c = client_for(handler, gnani_stt_model="prisma-v3.0")
    await c.transcribe(make_wav(), language_code="hi-IN", bias_list=["chini"])
    assert b'name="model"\r\n\r\nprisma-v3.0' in seen["body"]
    assert b"bias_list" not in seen["body"]


async def test_stt_format_and_bias_list_v25():
    seen = {}

    def handler(req):
        seen["body"] = req.content
        return httpx.Response(200, json=STT_OK)

    await client_for(handler).transcribe(make_wav(), language_code="hi-IN", fmt="transcribe", bias_list=["चीनी", "doodh"], bias_score=2.0)
    b = seen["body"]
    assert b'name="format"\r\n\r\ntranscribe' in b
    assert json.dumps(["चीनी", "doodh"], ensure_ascii=False).encode() in b
    assert b'name="bias_score"\r\n\r\n2.0' in b


async def test_stt_bias_list_is_capped_at_100():
    seen = {}

    def handler(req):
        seen["body"] = req.content
        return httpx.Response(200, json=STT_OK)

    await client_for(handler).transcribe(make_wav(), language_code="hi-IN", bias_list=[f"w{i}" for i in range(150)])
    start = seen["body"].index(b"[")
    end = seen["body"].index(b"]", start)
    assert len(json.loads(seen["body"][start:end + 1])) == 100


async def test_stt_empty_transcript_is_returned_not_an_error():
    c = client_for(lambda r: httpx.Response(200, json={**STT_OK, "transcript": ""}))
    assert (await c.transcribe(make_wav(), language_code="gu-IN")).transcript == ""


# ------------------------------------------------------------------ error envelopes
@pytest.mark.parametrize("status,body,etype", [
    (401, {"detail": {"error_code": "INVALID_API_KEY", "message": "bad key", "status_code": 401}}, "INVALID_API_KEY"),
    (401, {"detail": {"error_code": "MISSING_API_KEY", "message": "no key", "status_code": 401}}, "MISSING_API_KEY"),
    (403, {"detail": {"error_code": "SCOPE_NOT_ALLOWED", "message": "scope", "status_code": 403}}, "SCOPE_NOT_ALLOWED"),
    (400, {"success": False, "error": {"type": "MAX_AUDIO_DURATION_EXCEEDED", "message": "too long"}}, "MAX_AUDIO_DURATION_EXCEEDED"),
    (400, {"success": False, "error": {"type": "UNSUPPORTED_AUDIO_FORMAT", "message": "fmt"}}, "UNSUPPORTED_AUDIO_FORMAT"),
    (422, {"detail": [{"msg": "field required", "loc": ["body", "language_code"]}]}, "VALIDATION_ERROR"),
    (400, {"error": "Bad Request", "code": "BAD_THING", "message": "x"}, "BAD_THING"),
])
async def test_stt_documented_error_envelopes(status, body, etype):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(status, json=body)

    with pytest.raises(GnaniError) as ei:
        await client_for(handler).transcribe(make_wav(), language_code="gu-IN")
    assert ei.value.error_type == etype and ei.value.status == status
    assert len(calls) == 1, "4xx must not be retried"
    assert ei.value.meta and not ei.value.meta.ok
    assert KEY not in ei.value.user_message and KEY not in str(ei.value)


async def test_non_json_error_body():
    with pytest.raises(GnaniError) as ei:
        await client_for(lambda r: httpx.Response(400, text="<html>nginx</html>")).transcribe(make_wav(), language_code="gu-IN")
    assert ei.value.error_type == "HTTP_ERROR"


async def test_success_false_with_200_is_an_error():
    c = client_for(lambda r: httpx.Response(200, json={"success": False, "message": "weird"}))
    with pytest.raises(GnaniError) as ei:
        await c.transcribe(make_wav(), language_code="gu-IN")
    assert ei.value.error_type == "BAD_RESPONSE"


async def test_non_json_success_is_an_error():
    with pytest.raises(GnaniError) as ei:
        await client_for(lambda r: httpx.Response(200, text="ok")).transcribe(make_wav(), language_code="gu-IN")
    assert ei.value.error_type == "BAD_RESPONSE"


# ------------------------------------------------------------------ retry policy
@pytest.mark.parametrize("bad", [429, 500, 503, 504])
async def test_retries_documented_statuses_then_succeeds(bad):
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        return httpx.Response(bad, json={"error": "x"}) if n["c"] == 1 else httpx.Response(200, json=STT_OK)

    res = await client_for(handler).transcribe(make_wav(), language_code="gu-IN")
    assert n["c"] == 2 and res.meta.attempts == 2


async def test_gives_up_after_three_attempts():
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        return httpx.Response(503, json={"error": "Service Unavailable", "code": "UPSTREAM", "message": "down"})

    with pytest.raises(GnaniError) as ei:
        await client_for(handler).transcribe(make_wav(), language_code="gu-IN")
    assert n["c"] == 3 and ei.value.status == 503 and ei.value.meta.attempts == 3


async def test_connection_error_is_retried_then_reported_as_network():
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        raise httpx.ConnectError("boom")

    with pytest.raises(GnaniError) as ei:
        await client_for(handler).transcribe(make_wav(), language_code="gu-IN")
    assert n["c"] == 3 and ei.value.error_type == "NETWORK" and ei.value.status is None


# ------------------------------------------------------------------ TTS
async def test_tts_request_shape_and_raw_audio_response():
    seen = {}
    wav = make_wav(0.5, 24000)

    def handler(req):
        seen["req"] = req
        return httpx.Response(200, content=wav, headers={"content-type": "audio/wav"})

    res = await client_for(handler).synthesize("નમસ્તે", language="gu-IN", voice="Falak", speed=1.0, sample_rate=24000)
    req = seen["req"]
    assert req.url.path == "/api/v1/tts/inference" and req.headers["x-api-key-id"] == KEY
    assert req.headers["content-type"].startswith("application/json")
    body = json.loads(req.content)
    assert body["text"] == "નમસ્તે" and body["voice"] == "Falak" and body["model"] == "timbre-v2.5" and body["language"] == "gu-IN"
    assert body["audio_config"] == {"sample_rate": 24000, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"}
    assert res.audio == wav and res.meta.ok and res.meta.units == len("નમસ્તે")


async def test_tts_json_body_with_200_is_surfaced_as_error():
    c = client_for(lambda r: httpx.Response(200, json={"success": False, "message": "voice not found"}))
    with pytest.raises(GnaniError) as ei:
        await c.synthesize("x", language="en-IN", voice="Nope")
    assert ei.value.error_type == "BAD_RESPONSE"


async def test_tts_empty_audio_is_an_error():
    c = client_for(lambda r: httpx.Response(200, content=b"", headers={"content-type": "audio/wav"}))
    with pytest.raises(GnaniError) as ei:
        await c.synthesize("x", language="en-IN", voice="Devika")
    assert ei.value.error_type == "EMPTY_AUDIO"


async def test_tts_error_envelope():
    c = client_for(lambda r: httpx.Response(400, json={"success": False, "message": "text too long"}))
    with pytest.raises(GnaniError) as ei:
        await c.synthesize("x", language="en-IN", voice="Devika")
    assert "text too long" in ei.value.message


# ------------------------------------------------------------------ configuration & budget
async def test_not_configured_makes_no_network_call():
    calls = []
    c = GnaniClient(cfg(gnani_api_key=None), transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json=STT_OK)))
    with pytest.raises(GnaniNotConfigured):
        await c.transcribe(make_wav(), language_code="gu-IN")
    assert calls == []


@pytest.mark.parametrize("placeholder", ["your_gnani_api_key_here", "", "   "])
async def test_placeholder_key_counts_as_not_configured(placeholder):
    assert cfg(gnani_api_key=placeholder).gnani_configured is False


async def test_local_budget_blocks_before_any_http_call():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json=STT_OK)

    c = GnaniClient(cfg(), transport=httpx.MockTransport(handler), budget=CallBudget(2))
    await c.transcribe(make_wav(), language_code="gu-IN")
    await c.transcribe(make_wav(), language_code="gu-IN")
    with pytest.raises(GnaniError) as ei:
        await c.transcribe(make_wav(), language_code="gu-IN")
    assert ei.value.error_type == "LOCAL_BUDGET_EXCEEDED" and len(calls) == 2


def test_secret_is_not_in_repr_or_settings_dump():
    s = cfg()
    assert KEY not in repr(s) and KEY not in str(s.model_dump())
