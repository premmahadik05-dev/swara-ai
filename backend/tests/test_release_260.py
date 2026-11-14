"""Release 2.6.0: the voice-path changes (pooled connection, per-call timeouts, reply-first voice, stage timing, owner diagnostics), the atomic .env
writer and the in-place database upgrade. Gnani is a local simulator (httpx.MockTransport); nothing here talks to the real service."""
from __future__ import annotations

import json
from datetime import timedelta

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

from app.db import Base, make_engine, make_session_factory, upgrade_schema
from app.gnani import client as gnani_client
from app.gnani.client import GnaniError
from app.models import ApiCall, Order, Product, Turn, User, utcnow
from app.services import diagnostics as diag
from .helpers import KEY, STAFF, AuthedClient, make_wav, register


class Sim:
    """A Gnani simulator whose behaviour each test sets. Records every request it receives."""

    def __init__(self, transcript="2 kilo chini aur 1 litre doodh"):
        self.transcript = transcript
        self.stt_calls = self.tts_calls = 0
        self.tts_texts: list[str] = []
        self.stt_script: list = []      # one item per STT call: an Exception to raise, an int status to return, or None for success
        self.tts_script: list = []

    def _next(self, script):
        return script.pop(0) if script else None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.path == "/stt/v3":
            self.stt_calls += 1
            step = self._next(self.stt_script)
            if isinstance(step, Exception):
                raise step
            if isinstance(step, int):
                return httpx.Response(step, json={"success": False, "error": {"type": "SIM_ERROR", "message": "simulated"}})
            return httpx.Response(200, json={"success": True, "transcript": self.transcript, "model": "prisma-v2.5", "request_id": "sim", "processing_time": 0.1})
        if req.url.path == "/api/v1/tts/inference":
            self.tts_calls += 1
            self.tts_texts.append(json.loads(req.content)["text"])
            step = self._next(self.tts_script)
            if isinstance(step, Exception):
                raise step
            if isinstance(step, int):
                return httpx.Response(step, json={"success": False, "message": "simulated"})
            return httpx.Response(200, content=make_wav(0.3, 24000), headers={"content-type": "audio/wav"})
        return httpx.Response(404)


@pytest.fixture
def sim():
    return Sim()


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    """Retries wait 0.25 s and 0.5 s in real use; the tests do not need to."""
    monkeypatch.setattr(gnani_client, "BACKOFF_S", 0.0)


@pytest.fixture
def vclient(make_app, sim):
    app = make_app(gnani_api_key=KEY, gnani_max_calls_per_hour=1000)
    app.state.gnani._transport = httpx.MockTransport(sim)
    with AuthedClient(app) as c:
        yield c


def voice(c, wav=None, **form):
    form.setdefault("language", "hi")
    return c.post("/api/voice/turn", files={"audio": ("order.wav", wav or make_wav(1.5), "audio/wav")}, data=form)


def db_of(client):
    return client.app.state.session_factory()


# ---------------------------------------------------------------- the Gnani client: pooled connection, timeouts, retries
class TestGnaniClient:
    def test_one_pool_is_reused_for_every_call(self, vclient, sim):
        pools = set()
        for _ in range(4):
            assert voice(vclient).status_code == 200
            pools.add(id(vclient.app.state.gnani._http))
        assert len(pools) == 1 and sim.stt_calls == 4

    def test_a_closed_pool_is_replaced_on_the_next_call(self, vclient, sim):
        voice(vclient)
        first = vclient.app.state.gnani._http
        vclient.portal.call(vclient.app.state.gnani.aclose)
        assert vclient.app.state.gnani._http is None and first.is_closed
        assert voice(vclient).status_code == 200
        assert vclient.app.state.gnani._http is not first

    def test_a_read_timeout_is_not_retried_and_says_so(self, vclient, sim):
        sim.stt_script = [httpx.ReadTimeout("slow")]
        r = voice(vclient)
        assert r.status_code == 504, r.text
        assert r.json()["detail"]["code"] == "TIMEOUT"
        assert "took too long" in r.json()["detail"]["message"] and "bill has not changed" in r.json()["detail"]["message"]
        assert sim.stt_calls == 1                                    # the slow request is not sent a second time
        with db_of(vclient) as db:
            row = db.scalars(select(ApiCall).where(ApiCall.provider == "gnani-stt")).one()
        assert (row.ok, row.error_type, row.attempts) == (False, "ReadTimeout", 1)      # the log keeps the exception name; the caller is told TIMEOUT

    def test_a_timeout_leaves_the_open_bill_alone(self, vclient, sim):
        first = vclient.post("/api/text/turn", json={"text": "2 kilo chini", "language": "hi"}).json()
        sim.stt_script = [httpx.ReadTimeout("slow")]
        assert voice(vclient, session_id=first["session_id"]).status_code == 504
        snap = vclient.get(f"/api/sessions/{first['session_id']}").json()
        assert snap["cart"]["total_paise"] == first["cart"]["total_paise"]

    def test_a_connection_failure_is_retried_on_a_fresh_connection_and_the_tries_are_logged(self, vclient, sim):
        sim.stt_script = [httpx.ConnectError("refused"), httpx.ConnectError("refused")]
        assert voice(vclient).status_code == 200
        assert sim.stt_calls == 3
        with db_of(vclient) as db:
            assert db.scalars(select(ApiCall.attempts).where(ApiCall.provider == "gnani-stt")).one() == 3

    def test_a_busy_service_is_retried_but_a_bad_request_is_not(self, vclient, sim):
        sim.stt_script = [503]
        assert voice(vclient).status_code == 200 and sim.stt_calls == 2
        sim.stt_calls = 0
        sim.stt_script = [400]
        assert voice(vclient).status_code in (400, 422, 502) and sim.stt_calls == 1

    def test_giving_up_after_three_connection_failures_reports_a_network_error(self, vclient, sim):
        sim.stt_script = [httpx.ConnectError("x")] * 3
        r = voice(vclient)
        assert r.status_code == 504 and r.json()["detail"]["code"] == "NETWORK"
        assert sim.stt_calls == 3

    def test_speech_to_text_and_text_to_speech_have_their_own_limits_and_the_old_setting_is_a_ceiling(self, make_app):
        g = make_app(gnani_api_key=KEY, gnani_stt_timeout_s=20, gnani_tts_timeout_s=15, gnani_connect_timeout_s=5, gnani_timeout_s=40).state.gnani
        assert (g._timeout("gnani-stt").read, g._timeout("gnani-tts").read, g._timeout("gnani-stt").connect) == (20, 15, 5)
        capped = make_app(gnani_api_key=KEY, gnani_stt_timeout_s=20, gnani_tts_timeout_s=15, gnani_connect_timeout_s=5, gnani_timeout_s=8).state.gnani
        assert (capped._timeout("gnani-stt").read, capped._timeout("gnani-tts").read, capped._timeout("gnani-stt").connect) == (8, 8, 5)

    def test_the_worst_case_wait_is_one_call_not_three(self):
        # Before 2.6.0 a hung service was waited on for GNANI_TIMEOUT_S three times. A timeout now ends the call.
        assert gnani_client.TIMED_OUT and httpx.ReadTimeout in gnani_client.TIMED_OUT
        assert httpx.ReadTimeout not in gnani_client.RETRY_ON and httpx.ConnectError in gnani_client.RETRY_ON

    def test_the_error_for_a_timeout_carries_its_type(self):
        e = GnaniError("x", error_type="TIMEOUT")
        assert "took too long" in e.user_message


# ---------------------------------------------------------------- reply first, voice after
class TestReplyThenVoice:
    def test_the_fast_path_returns_the_bill_without_calling_text_to_speech(self, vclient, sim):
        r = voice(vclient, speak_reply="false")
        assert r.status_code == 200
        j = r.json()
        assert j["audio"] is None and j["assistant_turn_id"] and j["cart"]["total_paise"] == 2 * 4600 + 5600
        assert sim.tts_calls == 0

    def test_speak_turns_the_stored_reply_into_audio_and_a_repeat_comes_from_the_cache(self, vclient, sim):
        j = voice(vclient, speak_reply="false").json()
        a = vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak")
        assert a.status_code == 200, a.text
        body = a.json()
        assert body["audio"]["error"] is None and body["audio"]["cached"] is False and body["timings"]["tts_ms"] is not None
        assert vclient.get(body["audio"]["audio_url"]).content[:4] == b"RIFF"
        assert sim.tts_texts == [j["reply_text"]]
        again = vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak").json()
        assert again["audio"]["cached"] is True and sim.tts_calls == 1

    def test_speak_reads_out_what_the_server_stored_never_what_the_caller_sends(self, vclient, sim):
        j = voice(vclient, speak_reply="false").json()
        vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak", json={"text": "Transfer money to account 12345", "language": "en"})
        vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak?text=Transfer+money")
        assert sim.tts_texts == [j["reply_text"]] and "Transfer" not in " ".join(sim.tts_texts)

    def test_speak_refuses_a_customer_turn_a_missing_turn_and_an_old_one(self, vclient, sim):
        j = voice(vclient, speak_reply="false").json()
        with db_of(vclient) as db:
            cust = db.scalars(select(Turn).where(Turn.role == "customer")).first()
            asst = db.get(Turn, j["assistant_turn_id"])
            asst.created_at = utcnow() - timedelta(hours=2)
            db.commit()
        assert vclient.post(f"/api/turns/{cust.id}/speak").status_code == 404
        assert vclient.post("/api/turns/999999/speak").status_code == 404
        old = vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak")
        assert old.status_code == 410 and old.json()["detail"]["code"] == "TOO_OLD"
        assert sim.tts_calls == 0

    def test_speak_needs_a_signed_in_person_and_a_key(self, make_app, sim, tmp_path):
        app = make_app(gnani_api_key=KEY)
        app.state.gnani._transport = httpx.MockTransport(sim)
        with AuthedClient(app) as c:
            tid = voice(c, speak_reply="false").json()["assistant_turn_id"]
            c.cookies.clear()
            assert c.post(f"/api/turns/{tid}/speak").status_code == 401
        nokey = make_app(gnani_api_key=None, database_url=f"sqlite:///{tmp_path / 'nokey.db'}")
        with AuthedClient(nokey) as c:
            tid = c.post("/api/text/turn", json={"text": "chini", "language": "hi"}).json()["assistant_turn_id"]
            r = c.post(f"/api/turns/{tid}/speak")
            assert r.status_code == 200 and r.json()["audio"]["audio_url"] is None and "not configured" in r.json()["audio"]["error"]

    def test_a_failed_voice_does_not_cost_the_reply(self, vclient, sim):
        j = voice(vclient, speak_reply="false").json()
        sim.tts_script = [httpx.ReadTimeout("slow")]
        a = vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak")
        assert a.status_code == 200 and a.json()["audio"]["audio_url"] is None and a.json()["audio"]["error"]
        assert vclient.get(f"/api/sessions/{j['session_id']}").json()["cart"]["total_paise"] == j["cart"]["total_paise"]

    def test_the_old_path_still_works_for_callers_that_want_the_voice_in_the_same_reply(self, vclient, sim):
        j = voice(vclient, speak_reply="true").json()
        assert j["audio"]["audio_url"] and sim.tts_calls == 1

    def test_a_recording_with_no_speech_returns_a_full_reply_and_leaves_the_bill_as_it_was(self, vclient, sim):
        first = vclient.post("/api/text/turn", json={"text": "2 kilo chini", "language": "hi"}).json()
        sim.transcript = ""
        r = voice(vclient, session_id=first["session_id"], speak_reply="false")
        assert r.status_code == 200
        j = r.json()
        assert j["no_speech"] is True and j["transcript"] == "" and j["audio"] is None
        assert j["cart"]["total_paise"] == first["cart"]["total_paise"] and len(j["cart"]["lines"]) == len(first["cart"]["lines"])
        assert j["assistant_turn_id"] and j["timings"]["stt_ms"] is not None and j["order"] is None
        # the apology can be spoken like any other reply
        assert vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak").json()["audio"]["error"] is None

    def test_no_speech_with_no_open_bill_starts_an_empty_one(self, vclient, sim):
        sim.transcript = ""
        j = voice(vclient, speak_reply="false").json()
        assert j["no_speech"] is True and j["cart"]["lines"] == [] and j["cart"]["total_paise"] == 0 and j["session_id"]


class TestClientTiming:
    def _turn(self, vclient):
        return voice(vclient, speak_reply="false").json()["assistant_turn_id"]

    def test_stores_what_the_browser_measured_beside_the_server_times(self, vclient):
        tid = self._turn(vclient)
        r = vclient.post(f"/api/turns/{tid}/client-timing", json={"capture_ms": 2100, "end_to_reply_ms": 1350, "upload_bytes": 48000, "endpoint": "auto"})
        assert r.status_code == 200 and r.json() == {"ok": True}
        vclient.post(f"/api/turns/{tid}/client-timing", json={"end_to_audio_ms": 2400})
        with db_of(vclient) as db:
            d = db.get(Turn, tid).detail
        assert d["client"] == {"capture_ms": 2100, "end_to_reply_ms": 1350, "upload_bytes": 48000, "endpoint": "auto", "end_to_audio_ms": 2400}
        assert d["timing"]["mode"] == "voice"             # the server's own times are untouched

    @pytest.mark.parametrize("body", [
        {"end_to_reply_ms": -1}, {"end_to_reply_ms": 10**9}, {"capture_ms": "soon"}, {"endpoint": "shouting"}, {"secret": "x"}, {"upload_bytes": 10**10},
    ])
    def test_refuses_values_that_make_no_sense(self, vclient, body):
        assert vclient.post(f"/api/turns/{self._turn(vclient)}/client-timing", json=body).status_code == 422

    def test_refuses_an_empty_report_a_missing_turn_and_a_customer_turn(self, vclient):
        tid = self._turn(vclient)
        assert vclient.post(f"/api/turns/{tid}/client-timing", json={}).status_code == 404
        assert vclient.post("/api/turns/999999/client-timing", json={"capture_ms": 5}).status_code == 404
        with db_of(vclient) as db:
            cust = db.scalars(select(Turn).where(Turn.role == "customer")).first().id
        assert vclient.post(f"/api/turns/{cust}/client-timing", json={"capture_ms": 5}).status_code == 404

    def test_needs_a_signed_in_person(self, vclient):
        tid = self._turn(vclient)
        vclient.cookies.clear()
        assert vclient.post(f"/api/turns/{tid}/client-timing", json={"capture_ms": 5}).status_code == 401


# ---------------------------------------------------------------- stage timing is recorded with every turn
class TestStageTiming:
    def test_a_spoken_turn_stores_each_stage_and_they_add_up(self, vclient, sim):
        j = voice(vclient, speak_reply="false").json()
        vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak")
        with db_of(vclient) as db:
            tm = db.get(Turn, j["assistant_turn_id"]).detail["timing"]
        assert tm["mode"] == "voice" and tm["stt_attempts"] == 1
        for k in ("validate_ms", "stt_ms", "nlu_ms", "db_ms", "process_ms", "tts_ms", "server_ms"):
            assert k in tm and tm[k] >= 0, k
        assert tm["server_ms"] == pytest.approx(tm["validate_ms"] + tm["stt_ms"] + tm["process_ms"] + tm["tts_ms"], abs=0.5)

    def test_a_typed_turn_is_marked_as_typed_and_has_no_speech_stages(self, vclient):
        tid = vclient.post("/api/text/turn", json={"text": "2 kilo chini", "language": "hi"}).json()["assistant_turn_id"]
        with db_of(vclient) as db:
            tm = db.get(Turn, tid).detail["timing"]
        assert tm["mode"] == "text" and "stt_ms" not in tm and tm["process_ms"] >= 0

    def test_a_retried_speech_call_is_recorded_on_the_turn(self, vclient, sim):
        sim.stt_script = [503]
        tid = voice(vclient, speak_reply="false").json()["assistant_turn_id"]
        with db_of(vclient) as db:
            assert db.get(Turn, tid).detail["timing"]["stt_attempts"] == 2

    def test_asking_for_the_voice_twice_adds_its_time_once(self, vclient, sim):
        tid = voice(vclient, speak_reply="false").json()["assistant_turn_id"]
        vclient.post(f"/api/turns/{tid}/speak")
        with db_of(vclient) as db:
            once = db.get(Turn, tid).detail["timing"]["server_ms"]
        vclient.post(f"/api/turns/{tid}/speak")
        with db_of(vclient) as db:
            assert db.get(Turn, tid).detail["timing"]["server_ms"] == once

    def test_the_session_snapshot_names_the_customer_so_a_reload_can_restore_the_bill(self, vclient):
        c = vclient.post("/api/customers", json={"name": "Ramesh Shah", "phone": "9876500001"})
        assert c.status_code in (200, 201), c.text
        j = vclient.post("/api/text/turn", json={"text": "2 kilo chini", "language": "hi", "customer_id": c.json()["id"]}).json()
        assert vclient.get(f"/api/sessions/{j['session_id']}").json()["customer_id"] == c.json()["id"]


# ---------------------------------------------------------------- owner diagnostics
class TestDiagnostics:
    def test_only_the_owner_can_read_it(self, make_app):
        with AuthedClient(make_app()) as owner:
            assert owner.get("/api/diagnostics/voice").status_code == 200
            owner.cookies.clear(); owner.headers.pop("X-CSRF-Token", None)
            assert owner.get("/api/diagnostics/voice").status_code == 401
            assert register(owner, STAFF).status_code == 201
            r = owner.get("/api/diagnostics/voice")
            assert r.status_code == 403

    def test_an_empty_shop_gets_nothing_measured_and_no_zeros(self, client):
        d = client.get("/api/diagnostics/voice").json()
        assert d["voice"]["turns"] == 0 and d["voice"]["tts_cached_share"] is None
        assert d["voice"]["stages"]["stt_ms"] == {"n": 0, "p50": None, "p95": None, "max": None, "mean": None}
        assert all(v is None for v in d["voice"]["stage_share_of_median"].values())
        assert d["browser_reported"]["turns"] == 0 and d["browser_reported"]["end_to_reply_ms"]["p50"] is None
        assert d["gnani"]["stt"]["calls"] == 0 and d["gnani"]["stt"]["p50"] is None and d["slowest"] == []

    def test_counts_and_medians_match_the_rows_behind_them(self, vclient, sim):
        ids = []
        for _ in range(3):
            j = voice(vclient, speak_reply="false").json()
            vclient.post(f"/api/turns/{j['assistant_turn_id']}/speak")
            ids.append(j["assistant_turn_id"])
        vclient.post("/api/text/turn", json={"text": "chini", "language": "hi"})
        sim.stt_script = [503, 503, 503]                      # three tries, all refused: one failed call, never a turn
        assert voice(vclient).status_code >= 500
        vclient.post(f"/api/turns/{ids[0]}/client-timing", json={"end_to_reply_ms": 900, "endpoint": "auto"})
        vclient.post(f"/api/turns/{ids[1]}/client-timing", json={"end_to_reply_ms": 1100, "endpoint": "manual"})

        d = vclient.get("/api/diagnostics/voice").json()
        assert d["voice"]["turns"] == 3 and d["voice"]["by_mode"] == {"voice": 3, "stream": 0}
        assert d["typed"]["turns"] == 1
        with db_of(vclient) as db:
            stt = sorted(db.get(Turn, i).detail["timing"]["stt_ms"] for i in ids)
            calls = list(db.scalars(select(ApiCall).where(ApiCall.provider == "gnani-stt")))
        assert d["voice"]["stages"]["stt_ms"]["n"] == 3 and d["voice"]["stages"]["stt_ms"]["p50"] == pytest.approx(stt[1], abs=0.1)
        s = d["gnani"]["stt"]
        assert (s["calls"], s["ok"], s["errors"], s["retried"]) == (4, 3, 1, 1) and len(calls) == 4
        assert s["error_types"] and s["error_types"][0]["count"] == 1
        assert d["gnani"]["tts"]["calls"] == 1                # the three replies are the same sentence: one synthesis, two cache hits
        b = d["browser_reported"]
        assert b["turns"] == 2 and b["end_to_reply_ms"]["p50"] == 1000 and b["end_to_reply_ms"]["n"] == 2
        assert {e["kind"] for e in b["endpoints"]} == {"auto", "manual"}
        assert d["voice"]["tts_cached_share"] == pytest.approx(2 / 3, abs=1e-4)
        shares = d["voice"]["stage_share_of_median"]
        assert 0 < sum(v for v in shares.values() if v is not None) <= 1.001

    def test_the_slowest_turns_are_listed_longest_first_and_capped_at_ten(self, vclient):
        for _ in range(12):
            voice(vclient, speak_reply="false")
        rows = vclient.get("/api/diagnostics/voice").json()["slowest"]
        assert len(rows) == 10 and [r["server_ms"] for r in rows] == sorted((r["server_ms"] for r in rows), reverse=True)

    def test_a_cached_reply_is_counted_as_cached(self, vclient):
        for _ in range(2):
            tid = voice(vclient, speak_reply="false").json()["assistant_turn_id"]
            vclient.post(f"/api/turns/{tid}/speak")
        assert vclient.get("/api/diagnostics/voice").json()["voice"]["tts_cached_share"] == 0.5

    def test_the_window_is_limited_to_what_makes_sense(self, client):
        assert client.get("/api/diagnostics/voice?hours=0").json()["window_hours"] == 1
        assert client.get("/api/diagnostics/voice?hours=999999").json()["window_hours"] == 720
        assert client.get("/api/diagnostics/voice?hours=24").json()["window_hours"] == 24

    def test_older_turns_fall_outside_a_short_window(self, vclient):
        tid = voice(vclient, speak_reply="false").json()["assistant_turn_id"]
        with db_of(vclient) as db:
            db.get(Turn, tid).created_at = utcnow() - timedelta(hours=30)
            db.commit()
        assert vclient.get("/api/diagnostics/voice?hours=24").json()["voice"]["turns"] == 0
        assert vclient.get("/api/diagnostics/voice?hours=48").json()["voice"]["turns"] == 1

    def test_it_never_shows_the_key_and_reports_the_limits_in_force(self, make_app, sim):
        app = make_app(gnani_api_key=KEY, gnani_stt_timeout_s=20, gnani_timeout_s=10)
        app.state.gnani._transport = httpx.MockTransport(sim)
        with AuthedClient(app) as c:
            voice(c, speak_reply="false")
            raw = c.get("/api/diagnostics/voice").text
            d = json.loads(raw)
        assert KEY not in raw and "SECRET" not in raw
        assert d["config"]["gnani_configured"] is True and d["config"]["stt_timeout_s"] == 10 and d["config"]["tts_timeout_s"] == 10
        assert d["budget"]["max_per_hour"] == 1000 and d["budget"]["calls_last_hour"] >= 1

    def test_turns_written_before_2_6_0_have_no_timing_and_are_left_out_rather_than_counted_as_zero(self, client):
        with db_of(client) as db:
            from app.models import ConversationSession
            sess = ConversationSession(id="old-session")
            db.add(sess)
            db.flush()
            db.add(Turn(session_id="old-session", role="assistant", text="ok", language="hi", input_mode="voice", detail={"events": []}))
            db.commit()
        d = client.get("/api/diagnostics/voice").json()
        assert d["voice"]["turns"] == 0 and d["voice"]["stages"]["server_ms"]["n"] == 0


class TestPercentiles:
    def test_matches_numpy_linear_interpolation(self):
        rng = np.random.default_rng(7)
        for n in (1, 2, 3, 10, 57):
            vals = [float(x) for x in rng.integers(1, 5000, n)]
            for p in (50, 95):
                assert diag.percentile(vals, p) == pytest.approx(float(np.percentile(vals, p)), abs=0.06)

    def test_edges(self):
        assert diag.percentile([], 50) is None
        assert diag.percentile([42.0], 95) == 42.0
        assert diag.summary([]) == {"n": 0, "p50": None, "p95": None, "max": None, "mean": None}
        assert diag.summary([10, None, 30]) == {"n": 2, "p50": 20.0, "p95": 29.0, "max": 30.0, "mean": 20.0}


# ---------------------------------------------------------------- the .env writer
class TestEnvWriter:
    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        from app.routers import settings as s
        p = tmp_path / ".env"
        monkeypatch.setattr(s, "ENV_FILE", p)
        return s, p

    def test_changes_only_the_keys_it_is_given(self, env):
        s, p = env
        original = "# my settings\nSTORE_NAME=Patel Kirana\n\nGNANI_STT_MODEL=prisma-v2.5\nOWNER_EMAIL=me@example.com\n"
        p.write_text(original, encoding="utf-8")
        s._write_env({"GNANI_API_KEY": "sk-test-123"})
        assert p.read_text(encoding="utf-8") == original + "GNANI_API_KEY=sk-test-123\n"
        s._write_env({"GNANI_API_KEY": "sk-test-456", "GNANI_STT_MODEL": "prisma-v3.0"})
        assert p.read_text(encoding="utf-8") == "# my settings\nSTORE_NAME=Patel Kirana\n\nGNANI_STT_MODEL=prisma-v3.0\nOWNER_EMAIL=me@example.com\nGNANI_API_KEY=sk-test-456\n"

    def test_reads_a_file_that_starts_with_a_byte_order_mark(self, env):
        s, p = env
        p.write_bytes(b"\xef\xbb\xbfGNANI_API_KEY=old\nSTORE_NAME=Shop\n")        # Windows Notepad saves UTF-8 this way
        s._write_env({"GNANI_API_KEY": "new"})
        assert p.read_text(encoding="utf-8") == "GNANI_API_KEY=new\nSTORE_NAME=Shop\n"     # the first key was found, not duplicated

    def test_creates_the_file_when_there_is_none(self, env):
        s, p = env
        s._write_env({"STORE_NAME": "New Shop"})
        assert p.read_text(encoding="utf-8") == "STORE_NAME=New Shop\n" or p.read_text(encoding="utf-8") == 'STORE_NAME="New Shop"\n'

    def test_a_failure_part_way_keeps_the_old_file_and_leaves_no_temporary_file(self, env, monkeypatch):
        import os
        s, p = env
        p.write_text("GNANI_API_KEY=keep-me\nSTORE_NAME=Shop\n", encoding="utf-8")
        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            s._write_env({"GNANI_API_KEY": "lost"})
        assert p.read_text(encoding="utf-8") == "GNANI_API_KEY=keep-me\nSTORE_NAME=Shop\n"
        assert [f.name for f in p.parent.iterdir()] == [".env"]

    def test_a_value_with_spaces_or_quotes_survives_a_round_trip(self, env):
        s, p = env
        s._write_env({"STORE_NAME": 'Patel "Kirana" & Co'})
        from dotenv import dotenv_values
        assert dotenv_values(p)["STORE_NAME"] == 'Patel "Kirana" & Co'


# ---------------------------------------------------------------- updating an existing install
class TestUpgradeInPlace:
    @staticmethod
    def build_v250(path):
        """A database as 2.5.0 left it: the current tables, minus the 2.6.0 column, with a shop's real records in it."""
        from app.models import OrderItem
        from app.seed import seed_products
        eng = make_engine(f"sqlite:///{path}")
        Base.metadata.create_all(eng)
        with make_session_factory(eng)() as db:
            seed_products(db)
            db.add_all([
                User(email="prem@example.com", full_name="Prem Mahadik", role="owner", password_hash="scrypt$keep$me", is_active=True),
                User(email="staff@example.com", full_name="Staff Member", role="staff", password_hash="scrypt$keep$too", is_active=True),
            ])
            db.flush()
            p = db.scalars(select(Product).limit(1)).one()
            for i in range(5):
                o = Order(status="confirmed", channel="voice", language="gu", total_paise=1000 * (i + 1), is_synthetic=False)
                db.add(o)
                db.flush()
                db.add(OrderItem(order_id=o.id, product_id=p.id, product_name=p.name_en, qty=1, unit=p.unit, unit_price_paise=1000 * (i + 1), line_total_paise=1000 * (i + 1)))
            db.add(ApiCall(provider="gnani-stt", model="prisma-v2.5", ok=True, status_code=200, latency_ms=900, units=10))
            db.commit()
        with eng.begin() as c:
            c.execute(text("ALTER TABLE api_calls DROP COLUMN attempts"))
        eng.dispose()

    @staticmethod
    def snapshot(path):
        eng = create_engine(f"sqlite:///{path}")
        with eng.connect() as c:
            out = {
                "users": c.execute(text("SELECT email, role, password_hash FROM users ORDER BY id")).all(),
                "orders": c.execute(text("SELECT id, total_paise, status, created_at FROM orders ORDER BY id")).all(),
                "stock": c.execute(text("SELECT sku, stock, price_paise FROM products ORDER BY id")).all(),
                "items": c.execute(text("SELECT order_id, product_id, line_total_paise FROM order_items ORDER BY id")).all(),
            }
        eng.dispose()
        return out

    def test_the_new_column_is_added_and_nothing_else_changes(self, tmp_path, make_app):
        db_path = tmp_path / "shop.db"
        self.build_v250(db_path)
        before = self.snapshot(db_path)
        assert len(before["users"]) == 2 and len(before["orders"]) == 5
        app = make_app(database_url=f"sqlite:///{db_path}", seed_on_startup=False)
        with TestClient(app):            # start and stop the app: the startup sequence is what upgrades the file
            pass
        after = self.snapshot(db_path)
        assert after == before                                     # every account, order, line, price and stock level is exactly as it was
        eng = create_engine(f"sqlite:///{db_path}")
        with eng.connect() as c:
            cols = [r[1] for r in c.execute(text("PRAGMA table_info(api_calls)"))]
            attempts = c.execute(text("SELECT attempts FROM api_calls")).scalars().all()
        eng.dispose()
        assert "attempts" in cols and attempts == [1]              # the old row gets the honest default: one try

    def test_a_second_start_changes_nothing(self, tmp_path):
        db_path = tmp_path / "shop.db"
        self.build_v250(db_path)
        eng = create_engine(f"sqlite:///{db_path}")
        assert upgrade_schema(eng) == ["api_calls.attempts"]
        assert upgrade_schema(eng) == []
        eng.dispose()

    def test_old_calls_without_a_try_count_are_counted_as_one_try_in_diagnostics(self, tmp_path, make_app):
        db_path = tmp_path / "shop.db"
        self.build_v250(db_path)
        app = make_app(database_url=f"sqlite:///{db_path}", seed_on_startup=False)
        with TestClient(app) as c:
            from app.models import User as U
            with app.state.session_factory() as db:
                assert db.scalar(select(func.count(U.id))) == 2
            # The owner row exists but its password is not ours: sign in through a fresh account is not possible once an owner exists,
            # so read the diagnostics service directly, which is what the route calls.
            with app.state.session_factory() as db:
                d = diag.voice_diagnostics(db, app.state.settings, 0, hours=24 * 30)
        assert d["gnani"]["stt"]["calls"] == 1 and d["gnani"]["stt"]["retried"] == 0

    def test_the_update_never_touches_the_env_file_or_the_database_file_itself(self, tmp_path, make_app):
        db_path = tmp_path / "shop.db"
        self.build_v250(db_path)
        env = tmp_path / ".env"
        env.write_text("GNANI_API_KEY=real-looking-but-fake\nSTORE_NAME=Shop\n", encoding="utf-8")
        env_before = env.read_bytes()
        with TestClient(make_app(database_url=f"sqlite:///{db_path}", seed_on_startup=False)):
            pass
        assert env.read_bytes() == env_before and db_path.exists()
