"""Every language through the HTTP API, with Gnani SIMULATED (httpx.MockTransport / a local fake streaming server).

These tests are MOCKED, not live. They prove OUR side for each language: the Prisma ``language_code`` and Timbre ``language`` + ``voice``
we send are the registry's, a transcript becomes the right order, the reply comes back in the same language, a refused or failing
language produces a clear error and no substitute language, and nothing but the registry decides what is on offer. They cannot show that
Gnani's service accepts a code, recognises speech or has a voice today - that is ``scripts/verify_gnani.py`` with a real key
(results are shown by GET /api/languages only after such a run).
"""
from __future__ import annotations

import json
import re

import httpx
import pytest

from app import languages as reg

from .helpers import AuthedClient, KEY, make_wav
from .test_ws_proxy import FakeStreamServer, collect, pcm_of

NEW = ("mr", "bn", "ta", "te", "kn", "ml", "pa")
PRICE_2_SUGAR_1_MILK = 2 * 4600 + 5600  # the seeded SUGAR and MILK prices


class Sim:
    """Records every request Gnani would have received and answers like the documented API."""

    def __init__(self, transcript="", stt_status=200, stt_body=None, tts_status=200, tts_body=None):
        self.transcript, self.stt_status, self.stt_body, self.tts_status, self.tts_body = transcript, stt_status, stt_body, tts_status, tts_body
        self.stt: list[dict] = []
        self.tts: list[dict] = []

    @staticmethod
    def field(req: httpx.Request, name: str) -> str | None:
        m = re.search(rb'name="' + name.encode() + rb'"\r\n\r\n(.*?)\r\n--', req.content, re.S)
        return m.group(1).decode("utf-8") if m else None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.path == "/stt/v3":
            self.stt.append({"code": self.field(req, "language_code"), "model": self.field(req, "model"), "format": self.field(req, "format"),
                             "bias": self.field(req, "bias_list"), "key": req.headers.get("x-api-key-id")})
            if self.stt_status != 200:
                return httpx.Response(self.stt_status, json=self.stt_body or {"success": False, "error": "x"})
            return httpx.Response(200, json={"success": True, "transcript": self.transcript, "model": "prisma-v2.5", "request_id": "sim-1",
                                             "processing_time": 0.2, "end_to_end_latency": 0.4})
        if req.url.path == "/api/v1/tts/inference":
            body = json.loads(req.content)
            self.tts.append({"language": body["language"], "voice": body["voice"], "model": body["model"], "text": body["text"]})
            if self.tts_status != 200:
                return httpx.Response(self.tts_status, json=self.tts_body or {"error": "x"})
            return httpx.Response(200, content=make_wav(0.3, 24000), headers={"content-type": "audio/wav"})
        return httpx.Response(404)


def client(make_app, sim, **cfg):
    app = make_app(gnani_api_key=KEY, gnani_max_calls_per_hour=1000, **cfg)
    app.state.gnani._transport = httpx.MockTransport(sim)
    return AuthedClient(app)


def post_voice(c, language, wav=None, **form):
    return c.post("/api/voice/turn", files={"audio": ("order.wav", wav or make_wav(1.5), "audio/wav")}, data={"language": language, **form})


# --------------------------------------------------------------------------- voice turn: STT in, order, TTS out - every language
@pytest.mark.parametrize("key", reg.ORDER)
def test_voice_turn_per_language_mocked(make_app, key):
    lang = reg.LANGUAGES[key]
    sim = Sim(transcript=lang.sample)
    with client(make_app, sim) as c:
        r = post_voice(c, key)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["cart"]["total_paise"] == PRICE_2_SUGAR_1_MILK, (key, j["cart"])
        assert j["language"] == key and j["reply_lang"] == key
        assert j["stt"]["language_code"] == lang.stt_code
        assert j["audio"]["audio_id"] and j["audio"]["voice"] == lang.default_voice
        assert c.get(j["audio"]["audio_url"]).content[:4] == b"RIFF"
    assert [s["code"] for s in sim.stt] == [lang.stt_code] and sim.stt[0]["key"] == KEY
    assert sim.tts == [{"language": lang.tts_code, "voice": lang.default_voice, "model": "timbre-v2.5", "text": j["reply_text"]}]


@pytest.mark.parametrize("key", reg.ORDER)
def test_text_turn_with_spoken_reply_per_language_mocked(make_app, key):
    """The TTS half on its own: typed text in, Timbre called with this language's code and voice."""
    lang = reg.LANGUAGES[key]
    sim = Sim()
    with client(make_app, sim) as c:
        r = c.post("/api/text/turn", json={"text": lang.sample, "speak": True, "language": key})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["reply_lang"] == key and j["audio"]["error"] is None
    assert sim.stt == []  # no speech-to-text call for typed text
    assert len(sim.tts) == 1 and sim.tts[0]["language"] == lang.tts_code and sim.tts[0]["voice"] == lang.default_voice


def test_a_voice_chosen_in_settings_is_the_one_sent_to_timbre(make_app):
    sim = Sim()
    with client(make_app, sim, tts_voice_ta="Trisha", tts_voice_gu="Veera") as c:
        c.post("/api/text/turn", json={"text": reg.LANGUAGES["ta"].sample, "speak": True, "language": "ta"})
        c.post("/api/text/turn", json={"text": reg.LANGUAGES["gu"].sample, "speak": True, "language": "gu"})
    assert [(t["language"], t["voice"]) for t in sim.tts] == [("ta-IN", "Trisha"), ("gu-IN", "Veera")]


@pytest.mark.parametrize("key,script", [("ta", "tamil"), ("bn", "bengali"), ("mr", "devanagari"), ("pa", "gurmukhi"), ("ml", "malayalam"), ("en", "latin")])
def test_stt_bias_words_are_product_names_in_the_selected_languages_script(make_app, key, script):
    from app.nlu.normalize import SCRIPT_KEY_BY_NAME, dominant_script

    sim = Sim(transcript="")
    with client(make_app, sim, gnani_stt_bias=True) as c:
        assert post_voice(c, key, speak_reply="false").status_code == 200
    words = json.loads(sim.stt[0]["bias"])
    assert words and len(words) <= 100
    want = SCRIPT_KEY_BY_NAME.get(script, "latin")
    assert all(dominant_script(w) == want for w in words), (key, words[:8])


# --------------------------------------------------------------------------- a whole order, spoken in each new language
FLOW = {
    "mr": ("बस एवढेच", "होय कन्फर्म करा"), "bn": ("ব্যস", "হ্যাঁ কনফার্ম করুন"), "ta": ("போதும்", "ஆம் உறுதிப்படுத்துங்கள்"),
    "te": ("చాలు", "అవును కన్ఫర్మ్ చేయండి"), "kn": ("ಸಾಕು", "ಹೌದು ಕನ್ಫರ್ಮ್"), "ml": ("മതി", "അതെ സ്ഥിരീകരിക്കുക"),
    "pa": ("ਬੱਸ", "ਹਾਂ ਜੀ ਕਨਫਰਮ ਕਰੋ"), "en": ("that's all", "yes confirm"),
}


@pytest.mark.parametrize("key", FLOW)
def test_full_order_in_each_language_is_saved_with_that_language(make_app, key):
    done, confirm = FLOW[key]
    with client(make_app, Sim()) as c:
        sid = None
        for text in (reg.LANGUAGES[key].sample, done, confirm):
            r = c.post("/api/text/turn", json={"text": text, "session_id": sid, "language": key})
            assert r.status_code == 200, r.text
            sid = r.json()["session_id"]
            assert r.json()["reply_lang"] == key
        code = r.json()["order"]["code"]
        assert r.json()["phase"] == "completed" and code
        rows = c.get("/api/orders", params={"language": key, "q": code}).json()  # the demo history already holds English orders, so find ours by its code
        assert rows["total"] == 1 and rows["items"][0]["language"] == key and rows["items"][0]["total_paise"] == PRICE_2_SUGAR_1_MILK


# --------------------------------------------------------------------------- unsupported / disabled / unavailable: clear errors, no substitute
def test_disabled_language_is_refused_before_any_gnani_call(make_app):
    sim = Sim(transcript="x")
    with client(make_app, sim, disabled_languages="mr,ta") as c:
        for call in (lambda: post_voice(c, "mr"), lambda: c.post("/api/text/turn", json={"text": "hello", "language": "ta"}),
                     lambda: c.post("/api/text/parse", json={"text": "hello", "language": "ta"})):
            r = call()
            assert r.status_code == 422 and r.json()["detail"]["code"] == "LANGUAGE_DISABLED", r.text
    assert sim.stt == [] and sim.tts == []


def test_a_disabled_language_never_gets_a_voice_reply(make_app):
    """Typed text in a switched-off language is still read (nothing is sent anywhere), but no voice is generated for it."""
    sim = Sim()
    with client(make_app, sim, disabled_languages="ta") as c:
        r = c.post("/api/text/turn", json={"text": reg.LANGUAGES["ta"].sample, "speak": True})
        assert r.status_code == 200
        a = r.json()["audio"]
    assert a["audio_id"] is None and "switched off" in a["error"] and sim.tts == []


@pytest.mark.parametrize("mode", ["auto", "mixed"])
def test_auto_modes_are_refused_on_prisma_v25_not_silently_gujarati(make_app, mode):
    sim = Sim(transcript="x")
    with client(make_app, sim) as c:
        r = post_voice(c, mode)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "AUTO_DETECT_NEEDS_V3"
    assert sim.stt == []


def test_auto_and_mixed_are_sent_as_documented_on_prisma_v3(make_app):
    sim = Sim(transcript="")
    with client(make_app, sim, gnani_stt_model="prisma-v3.0") as c:
        assert post_voice(c, "auto", speak_reply="false").status_code == 200
        assert post_voice(c, "mixed", speak_reply="false").status_code == 200
    assert [(s["code"], s["model"], s["format"]) for s in sim.stt] == [("indic-auto", "prisma-v3.0", None), ("gu-IN,en-IN", "prisma-v3.0", "codemix")]


@pytest.mark.parametrize("bad", ["klingon", "GU", "gu-IN", "gu;drop"])
def test_unknown_language_is_a_422_with_a_reason(make_app, bad):
    sim = Sim()
    with client(make_app, sim) as c:
        r = post_voice(c, bad)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "BAD_LANGUAGE" and "language must be one of" in r.json()["detail"]["message"]
    assert sim.stt == []


def test_gnani_refusing_a_language_code_surfaces_its_error_and_tries_nothing_else(make_app):
    sim = Sim(stt_status=400, stt_body={"success": False, "error": {"message": "unsupported language_code"}})
    with client(make_app, sim) as c:
        r = post_voice(c, "kn")
    assert r.status_code == 422 and r.json()["detail"]["code"]
    assert [s["code"] for s in sim.stt] == ["kn-IN"], "must not retry with another language"
    assert sim.tts == []


def test_a_failing_voice_keeps_the_text_reply_and_does_not_switch_voice_or_language(make_app):
    sim = Sim(tts_status=400, tts_body={"error": "voice not available"})
    with client(make_app, sim) as c:
        r = c.post("/api/text/turn", json={"text": reg.LANGUAGES["ml"].sample, "speak": True, "language": "ml"})
        j = r.json()
    assert r.status_code == 200 and j["reply_text"] and j["audio"]["audio_id"] is None and j["audio"]["error"]
    assert len(sim.tts) == 1 and sim.tts[0]["language"] == "ml-IN"


def test_no_gnani_key_means_text_still_works_and_voice_says_so(make_app):
    with AuthedClient(make_app()) as c:
        r = c.post("/api/text/turn", json={"text": reg.LANGUAGES["pa"].sample, "speak": True, "language": "pa"})
        assert r.status_code == 200 and r.json()["audio"]["audio_id"] is None and "not configured" in r.json()["audio"]["error"]
        r = post_voice(c, "pa")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "NOT_CONFIGURED"


# --------------------------------------------------------------------------- GET /api/languages
def test_languages_endpoint_needs_sign_in(anon):
    assert anon.get("/api/languages").status_code == 401


def test_languages_endpoint_lists_the_registry_in_order_with_honest_status(make_app, tmp_path):
    app = make_app(gnani_api_key=KEY, verification_file=tmp_path / "missing.json")
    with AuthedClient(app) as c:
        r = c.get("/api/languages")
        assert r.status_code == 200
        j = r.json()
        assert KEY not in r.text
        assert [row["key"] for row in j["languages"]] == list(reg.ORDER) and j["default"] == "gu"
        by = {row["key"]: row for row in j["languages"]}
        assert by["ta"]["stt_code"] == "ta-IN" and by["ta"]["voice"] == "Asmita" and "Asmita" in by["ta"]["voices"]
        assert by["gu"]["nlu_status"] == "tested" and by["pa"]["nlu_status"] == "authored"
        assert by["hinglish"]["stt_code"] == "en-IN" and by["hinglish"]["tts_code"] == "hi-en"
        assert j["verification"]["mode"] == "none"
        for row in j["languages"]:
            assert {c: v["status"] for c, v in row["verification"].items()} == {"tts": "not_run", "stt_code": "not_run", "stt_loopback": "not_run", "stt_human": "not_run"}
        assert all(not m["available"] and m["reason"] for m in j["modes"]) and j["stt_model"] == "prisma-v2.5"
        assert j["docs"]["checked_on"] == reg.DOCS_CHECKED_ON


def test_auto_modes_become_available_on_prisma_v3(make_app):
    with AuthedClient(make_app(gnani_stt_model="prisma-v3.0")) as c:
        assert all(m["available"] and m["reason"] is None for m in c.get("/api/languages").json()["modes"])


def test_disabled_languages_are_marked_not_hidden(make_app):
    with AuthedClient(make_app(disabled_languages="bn")) as c:
        j = c.get("/api/languages").json()
    assert j["disabled"] == ["bn"] and {r["key"]: r["enabled"] for r in j["languages"]}["bn"] is False and len(j["languages"]) == 11


def _vfile(tmp_path, mode, checks):
    p = tmp_path / "live_verification.json"
    p.write_text(json.dumps({"schema": 1, "generated_at": "2026-11-10T10:00:00Z", "mode": mode, "stt_model": "prisma-v2.5", "tts_model": "timbre-v2.5", "checks": checks}))
    return p


def test_live_results_are_shown_per_check_only_when_the_run_was_live(make_app, tmp_path):
    p = _vfile(tmp_path, "live", {"ta": {"tts": {"status": "passed", "latency_ms": 812, "voice": "Asmita"}, "stt_code": {"status": "failed", "error_code": "HTTP_400"}}})
    with AuthedClient(make_app(verification_file=p)) as c:
        j = c.get("/api/languages").json()
    ta = {r["key"]: r for r in j["languages"]}["ta"]["verification"]
    assert j["verification"]["mode"] == "live" and ta["tts"]["status"] == "passed" and ta["stt_code"]["status"] == "failed"
    assert ta["stt_loopback"]["status"] == "not_run" and ta["stt_human"]["status"] == "not_run"


def test_a_simulated_results_file_can_never_read_as_passed(make_app, tmp_path):
    p = _vfile(tmp_path, "simulated", {"ta": {"tts": {"status": "passed"}}})
    with AuthedClient(make_app(verification_file=p)) as c:
        j = c.get("/api/languages").json()
    assert j["verification"]["mode"] == "simulated"
    assert {r["key"]: r for r in j["languages"]}["ta"]["verification"]["tts"]["status"] == "simulated"


@pytest.mark.parametrize("content", ["not json", "[]", '{"checks": 5}', '{"mode": "live", "checks": {"ta": {"tts": {"status": "PASSED!!"}}}}'])
def test_a_damaged_or_odd_results_file_reads_as_nothing_verified(make_app, tmp_path, content):
    p = tmp_path / "v.json"
    p.write_text(content)
    with AuthedClient(make_app(verification_file=p)) as c:
        j = c.get("/api/languages").json()
    assert all(r["verification"]["tts"]["status"] == "not_run" for r in j["languages"])


# --------------------------------------------------------------------------- settings: per-language voices, switching a language off, connection test
@pytest.fixture
def owner(make_app, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routers.settings.ENV_FILE", tmp_path / ".env")
    sim = Sim(transcript="two kilo rice and one litre milk")
    with client(make_app, sim) as c:
        c.sim = sim
        yield c


def test_voice_per_language_is_validated_against_that_languages_catalogue(owner):
    assert owner.put("/api/settings", json={"tts_voice_ta": "Trisha", "tts_voice_mr": "Ishaan"}).status_code == 200
    v = owner.get("/api/settings").json()["voices"]
    assert v["ta"] == "Trisha" and v["mr"] == "Ishaan" and v["pa"] == "Mehuli" and set(reg.ORDER) <= set(v)
    for field, bad in (("tts_voice_ta", "Asmita2"), ("tts_voice_pa", "Nalini"), ("tts_voice_gu", "Zahira")):
        r = owner.put("/api/settings", json={field: bad})
        assert r.status_code == 422 and r.json()["detail"]["code"] == "BAD_VOICE", (field, r.text)


def test_languages_can_be_switched_off_and_on_again_by_the_owner(owner):
    r = owner.put("/api/settings", json={"disabled_languages": ["mr", "bn", "mr"]})
    assert r.status_code == 200 and r.json()["languages"]["disabled"] == ["bn", "mr"]
    rows = {x["key"]: x["enabled"] for x in owner.get("/api/languages").json()["languages"]}
    assert rows["mr"] is False and rows["bn"] is False and rows["ta"] is True
    assert post_voice(owner, "mr").status_code == 422
    assert owner.put("/api/settings", json={"disabled_languages": []}).status_code == 200
    assert all(x["enabled"] for x in owner.get("/api/languages").json()["languages"])


def test_english_and_unknown_keys_cannot_be_switched_off(owner):
    r = owner.put("/api/settings", json={"disabled_languages": ["en"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "LANGUAGE_REQUIRED"
    r = owner.put("/api/settings", json={"disabled_languages": ["xx"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "BAD_LANGUAGE"


@pytest.mark.parametrize("key", ["ta", "gu", "pa"])
def test_connection_test_checks_the_chosen_language_and_says_it_is_a_loopback(owner, key):
    lang = reg.LANGUAGES[key]
    r = owner.post(f"/api/settings/test-gnani?language={key}")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["language"] == key and j["loopback"] is True and j["phrase"] == lang.sample
    assert owner.sim.tts[-1]["language"] == lang.tts_code and owner.sim.stt[-1]["code"] == lang.stt_code


def test_connection_test_defaults_to_english_and_refuses_bad_choices(owner):
    assert owner.post("/api/settings/test-gnani").json()["phrase"] == "two kilo rice and one litre milk"
    for bad in ("klingon", "auto"):
        assert owner.post(f"/api/settings/test-gnani?language={bad}").status_code == 422
    owner.put("/api/settings", json={"disabled_languages": ["kn"]})
    assert owner.post("/api/settings/test-gnani?language=kn").json()["detail"]["code"] == "LANGUAGE_DISABLED"


# --------------------------------------------------------------------------- customers / orders accept every registry language
def test_customer_language_accepts_any_registry_key_and_nothing_else(make_app):
    with AuthedClient(make_app()) as c:
        for key in ("", *reg.ORDER):
            r = c.post("/api/customers", json={"name": f"Cust {key or 'none'}", "language": key})
            assert r.status_code in (200, 201), (key, r.text)
        for bad in ("klingon", "GU"):
            assert c.post("/api/customers", json={"name": "Bad", "language": bad}).status_code == 422


# --------------------------------------------------------------------------- realtime proxy: language code per language (local fake server)
@pytest.mark.parametrize("key", ["gu", "mr", "ta", "pa", "hinglish"])
def test_realtime_proxy_sends_the_language_code_in_both_documented_header_names(make_app, key):
    lang = reg.LANGUAGES[key]
    with FakeStreamServer([lang.sample]) as fake:
        app = make_app(gnani_api_key=KEY, gnani_base_url=f"http://127.0.0.1:{fake.port}")
        with AuthedClient(app) as c, c.websocket_connect(f"/ws/voice?language={key}&speak_reply=false") as ws:
            ready = ws.receive_json()
            assert ready["type"] == "ready" and ready["language_code"] == lang.stt_code
            ws.send_bytes(pcm_of(1.0))
            ws.send_text(json.dumps({"type": "commit"}))
            turn = next(m for m in collect(ws) if m["type"] == "turn")
            assert turn["language"] == key and turn["cart"]["total_paise"] == PRICE_2_SUGAR_1_MILK
    assert fake.headers["lang_code"] == fake.headers["language_code"] == lang.stt_code and fake.headers["x-api-key-id"] == KEY


@pytest.mark.parametrize("qs,cfg,code", [
    ("language=mr", {"disabled_languages": "mr"}, "LANGUAGE_DISABLED"),
    ("language=auto", {}, "AUTO_DETECT_NEEDS_V3"),
    ("language=klingon", {}, "BAD_LANGUAGE"),
])
def test_realtime_proxy_refuses_disabled_and_auto_on_v25_before_connecting(make_app, qs, cfg, code):
    app = make_app(gnani_api_key=KEY, gnani_base_url="http://127.0.0.1:9", **cfg)
    with AuthedClient(app) as c, c.websocket_connect(f"/ws/voice?{qs}") as ws:
        m = ws.receive_json()
        assert m["type"] == "error" and m["code"] == code, (qs, m)
