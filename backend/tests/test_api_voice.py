"""Voice endpoint with a *simulated* Gnani (MockTransport). Validates our plumbing, upload guards, caching and error mapping."""
from __future__ import annotations

import httpx
import pytest

from .helpers import AuthedClient, KEY, make_wav


class FakeGnani:
    """Documented-shape simulator. STT returns whatever ``transcript`` is set to; TTS returns a short WAV."""

    def __init__(self, transcript="2 kilo chini aur 1 litre doodh", stt_status=200, stt_body=None):
        self.transcript, self.stt_status, self.stt_body = transcript, stt_status, stt_body
        self.stt_calls = self.tts_calls = 0
        self.last_stt_headers = None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.path == "/stt/v3":
            self.stt_calls += 1
            self.last_stt_headers = dict(req.headers)
            if self.stt_status != 200:
                return httpx.Response(self.stt_status, json=self.stt_body)
            return httpx.Response(200, json={"success": True, "transcript": self.transcript, "model": "prisma-v2.5",
                                             "request_id": "sim-1", "processing_time": 0.2, "end_to_end_latency": 0.4})
        if req.url.path == "/api/v1/tts/inference":
            self.tts_calls += 1
            return httpx.Response(200, content=make_wav(0.3, 24000), headers={"content-type": "audio/wav"})
        return httpx.Response(404)


@pytest.fixture
def fake():
    return FakeGnani()


@pytest.fixture
def vclient(make_app, fake):
    app = make_app(gnani_api_key=KEY, gnani_max_calls_per_hour=1000)
    app.state.gnani._transport = httpx.MockTransport(fake)
    with AuthedClient(app) as c:
        yield c


def post_voice(c, wav=None, **form):
    form.setdefault("language", "hi")
    return c.post("/api/voice/turn", files={"audio": ("order.wav", wav or make_wav(1.5), "audio/wav")}, data=form)


def test_voice_turn_end_to_end(vclient, fake):
    r = post_voice(vclient)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["transcript"] == "2 kilo chini aur 1 litre doodh"
    assert j["cart"]["total_paise"] == 2 * 4600 + 5600
    assert j["stt"]["model"] == "prisma-v2.5" and j["stt"]["language_code"] == "hi-IN" and j["stt"]["request_id"] == "sim-1"
    assert j["timings"]["stt_ms"] is not None and j["timings"]["tts_ms"] is not None
    assert fake.last_stt_headers["x-api-key-id"] == KEY
    a = vclient.get(j["audio"]["audio_url"])
    assert a.status_code == 200 and a.headers["content-type"] == "audio/wav" and a.content[:4] == b"RIFF"
    assert KEY not in r.text


def test_identical_reply_is_served_from_tts_cache(vclient, fake):
    post_voice(vclient)
    first = fake.tts_calls
    post_voice(vclient)  # new session -> identical reply text -> cache hit
    assert fake.tts_calls == first and first >= 1


def test_voice_turn_continues_the_same_session_and_confirms(vclient, fake):
    j = post_voice(vclient).json()
    sid = j["session_id"]
    fake.transcript = "bas itna hi"
    assert post_voice(vclient, session_id=sid).json()["phase"] == "confirming"
    fake.transcript = "haan"
    j = post_voice(vclient, session_id=sid).json()
    assert j["order"] and j["order"]["channel"] == "voice"


def test_every_gnani_call_is_logged_with_latency(vclient):
    post_voice(vclient)
    lat = vclient.get("/api/analytics/latency").json()
    assert lat["gnani-stt"]["calls"] == 1 and lat["gnani-stt"]["ok"] == 1 and lat["gnani-stt"]["p50_ms"] is not None
    assert lat["gnani-tts"]["calls"] >= 1 and lat["nlu"]["turns"] >= 1


def test_silence_returns_no_speech_reply(vclient, fake):
    fake.transcript = ""
    j = post_voice(vclient).json()
    assert j["no_speech"] is True and j["reply_text"]


@pytest.mark.parametrize("status,body,http,code", [
    (401, {"detail": {"error_code": "INVALID_API_KEY", "message": "bad", "status_code": 401}}, 502, "INVALID_API_KEY"),
    (429, {"detail": {"error_code": "RATE_LIMITED", "message": "slow", "status_code": 429}}, 429, "RATE_LIMITED"),
    (402, {"detail": {"error_code": "PAYMENT_REQUIRED", "message": "credit", "status_code": 402}}, 402, "PAYMENT_REQUIRED"),
    (400, {"success": False, "error": {"type": "UNSUPPORTED_AUDIO_FORMAT", "message": "no"}}, 422, "UNSUPPORTED_AUDIO_FORMAT"),
])
def test_gnani_errors_are_mapped_to_clear_http_errors(make_app, status, body, http, code):
    fake = FakeGnani(stt_status=status, stt_body=body)
    app = make_app(gnani_api_key=KEY)
    app.state.gnani._transport = httpx.MockTransport(fake)
    with AuthedClient(app) as c:
        r = post_voice(c)
    assert r.status_code == http
    d = r.json()["detail"]
    assert d["code"] == code and d["message"] and KEY not in r.text


def test_voice_without_key_is_503_with_instructions(client):
    r = post_voice(client)
    assert r.status_code == 503
    assert "GNANI_API_KEY" in r.json()["detail"]["message"]


# ------------------------------------------------------------------ upload guards
def test_oversize_upload_rejected(make_app):
    with AuthedClient(make_app(gnani_api_key=KEY, max_upload_bytes=50_000)) as c:
        assert post_voice(c, wav=make_wav(5.0)).status_code == 413


def test_webm_rejected_with_actionable_message(vclient):
    webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
    r = vclient.post("/api/voice/turn", files={"audio": ("x.webm", webm, "audio/webm")}, data={"language": "gu"})
    assert r.status_code == 415 and "WAV" in r.json()["detail"]["message"]


def test_non_audio_rejected_even_if_content_type_lies(vclient):
    r = vclient.post("/api/voice/turn", files={"audio": ("x.wav", b"<html>not audio at all</html>", "audio/wav")}, data={"language": "gu"})
    assert r.status_code == 415


def test_audio_longer_than_30s_rejected_before_calling_gnani(vclient, fake):
    r = post_voice(vclient, wav=make_wav(31.0, 8000))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "MAX_AUDIO_DURATION_EXCEEDED"
    assert fake.stt_calls == 0


def test_too_short_audio_rejected(vclient, fake):
    assert post_voice(vclient, wav=make_wav(0.05)).status_code == 422 and fake.stt_calls == 0


@pytest.mark.parametrize("lang", ["xx", "'; drop", "GU", "gu-IN"])
def test_bad_language_rejected(vclient, lang):
    assert post_voice(vclient, language=lang).status_code == 422


def test_bad_session_id_rejected(vclient):
    assert post_voice(vclient, session_id="../../etc/passwd").status_code == 422


def test_audio_endpoint_blocks_path_traversal_and_unknown_ids(client):
    for bad in ["..%2F..%2Fetc%2Fpasswd", "x" * 32, "../secret", "a" * 31, "G" * 32]:
        assert client.get(f"/api/audio/{bad}").status_code in (404, 422)
