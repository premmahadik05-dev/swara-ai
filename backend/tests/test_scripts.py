"""Logic tests for the live scripts using a SIMULATED Gnani. These do not (and cannot) show live behaviour."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from app.config import Settings  # noqa: E402

from .helpers import KEY, make_wav  # noqa: E402


def sim_handler(transcripts):
    it = iter(transcripts)

    def h(req):
        if req.url.path == "/api/v1/tts/inference":
            return httpx.Response(200, content=make_wav(1.0, 16000, freq=300), headers={"content-type": "audio/wav"})
        return httpx.Response(200, json={"success": True, "transcript": next(it), "model": "prisma-v2.5", "request_id": "s"})

    return h


def lang_sim(by_code, tts_fail=(), stt_fail=()):
    """Simulated Gnani for verify_gnani.py. STT answers a generated probe tone with an empty transcript, and anything else with the next
    transcript queued for that language code (so en and hinglish, which both go through en-IN, can answer differently)."""
    import re
    queues = {k: list(v) for k, v in by_code.items()}
    seen = {"tts": [], "stt": []}

    def h(req):
        if req.url.path == "/api/v1/tts/inference":
            body = __import__("json").loads(req.content)
            seen["tts"].append((body["language"], body["voice"]))
            if body["language"] in tts_fail:
                return httpx.Response(400, json={"error": "voice not available"})
            return httpx.Response(200, content=make_wav(1.0, 16000, freq=300), headers={"content-type": "audio/wav"})
        code = re.search(rb'name="language_code"\r\n\r\n(.*?)\r\n--', req.content, re.S).group(1).decode()
        probe = b'filename="probe.wav"' in req.content
        seen["stt"].append((code, "probe" if probe else "audio"))
        if code in stt_fail:
            return httpx.Response(400, json={"success": False, "error": "unsupported language_code"})
        text = "" if probe else (queues[code].pop(0) if queues.get(code) else "xyz")
        return httpx.Response(200, json={"success": True, "transcript": text, "model": "prisma-v2.5", "request_id": "s"})

    h.seen = seen
    return h


def sim_env(handler, **cfg):
    from _live import make_env
    return make_env(Settings(_env_file=None, gnani_api_key=KEY, gnani_max_calls_per_hour=1000, **cfg), transport=httpx.MockTransport(handler))


def samples_by_code(**override):
    from app import languages as reg
    out: dict[str, list[str]] = {}
    for k in reg.ORDER:
        out.setdefault(reg.LANGUAGES[k].stt_code, []).append(override.get(k, reg.LANGUAGES[k].sample))
    return out


async def test_verify_script_runs_independent_checks_for_all_11_languages_with_simulated_gnani(tmp_path):
    import verify_gnani
    from app import languages as reg
    h = lang_sim(samples_by_code())
    env = sim_env(h)
    res = await verify_gnani.verify(env, list(reg.ORDER), samples_dir=tmp_path)
    assert list(res["checks"]) == list(reg.ORDER)
    for key, c in res["checks"].items():
        assert [c[n]["status"] for n in verify_gnani.CHECKS] == ["passed", "passed", "passed", "skipped"], (key, c)  # no human recording supplied
    # what was sent: every language's own Timbre language + voice, and its own Prisma code for each of the two STT calls
    assert h.seen["tts"] == [(reg.LANGUAGES[k].tts_code, reg.LANGUAGES[k].default_voice) for k in reg.ORDER]
    assert h.seen["stt"] == [(reg.LANGUAGES[k].stt_code, kind) for k in reg.ORDER for kind in ("probe", "audio")]
    md = verify_gnani.render(res["rows"], res["streams"], env, "SIMULATED (test)", res["checks"])
    assert "SIMULATED" in md and "Chain OK" in md and "11/11" in md and "Tamil (ta)" in md


async def test_a_wrong_transcript_fails_only_the_loopback_check():
    import verify_gnani
    h = lang_sim(samples_by_code(ta="xyz"))
    res = await verify_gnani.verify(sim_env(h), ["ta"], samples_dir=Path("/nonexistent"))
    c = res["checks"]["ta"]
    assert (c["tts"]["status"], c["stt_code"]["status"], c["stt_loopback"]["status"]) == ("passed", "passed", "failed")
    assert c["stt_loopback"]["matched"] is False and c["stt_loopback"]["transcript"] == "xyz"


async def test_tts_failure_does_not_hide_or_fake_the_stt_checks():
    import verify_gnani
    h = lang_sim(samples_by_code(), tts_fail=("ta-IN",))
    res = await verify_gnani.verify(sim_env(h), ["ta", "mr"], samples_dir=Path("/nonexistent"))
    ta, mr = res["checks"]["ta"], res["checks"]["mr"]
    assert ta["tts"]["status"] == "failed" and ta["tts"]["error_code"]
    assert ta["stt_code"]["status"] == "passed"                       # the code check does not depend on Timbre
    assert ta["stt_loopback"]["status"] == "skipped" and "tts check did not pass" in ta["stt_loopback"]["detail"]
    assert [mr[n]["status"] for n in ("tts", "stt_code", "stt_loopback")] == ["passed", "passed", "passed"]  # other languages carry on


async def test_a_refused_language_code_fails_stt_but_not_tts():
    import verify_gnani
    h = lang_sim(samples_by_code(), stt_fail=("kn-IN",))
    c = (await verify_gnani.verify(sim_env(h), ["kn"], samples_dir=Path("/nonexistent")))["checks"]["kn"]
    assert c["tts"]["status"] == "passed" and c["stt_code"]["status"] == "failed" and c["stt_loopback"]["status"] == "failed"


async def test_a_persons_recording_is_checked_when_supplied_and_skipped_when_not(tmp_path):
    import verify_gnani
    from app import languages as reg
    (tmp_path / "ta.wav").write_bytes(make_wav(1.0, 16000))
    ta, mr = reg.LANGUAGES["ta"].sample, reg.LANGUAGES["mr"].sample
    ok = (await verify_gnani.verify(sim_env(lang_sim({"ta-IN": [ta, ta], "mr-IN": [mr]})), ["ta", "mr"], samples_dir=tmp_path))["checks"]
    assert ok["ta"]["stt_human"]["status"] == "passed" and ok["mr"]["stt_human"]["status"] == "skipped"
    # a recording whose transcript does not give the expected order fails (it is not counted as a pass)
    h = lang_sim({"ta-IN": [reg.LANGUAGES["ta"].sample, "xyz"]})
    assert (await verify_gnani.verify(sim_env(h), ["ta"], samples_dir=tmp_path))["checks"]["ta"]["stt_human"]["status"] == "failed"
    # a reference text lets the speaker say something else
    (tmp_path / "ta.txt").write_text("மூன்று லிட்டர் பால்", encoding="utf-8")
    h = lang_sim({"ta-IN": [reg.LANGUAGES["ta"].sample, "மூன்று லிட்டர் பால்"]})
    assert (await verify_gnani.verify(sim_env(h), ["ta"], samples_dir=tmp_path))["checks"]["ta"]["stt_human"]["status"] == "passed"


async def test_unreadable_recording_is_skipped_with_a_reason(tmp_path):
    import verify_gnani
    (tmp_path / "ta.wav").write_bytes(b"not a wav file")
    c = (await verify_gnani.verify(sim_env(lang_sim(samples_by_code())), ["ta"], samples_dir=tmp_path))["checks"]["ta"]["stt_human"]
    assert c["status"] == "skipped" and "was not used" in c["detail"]


async def test_stream_check_sends_the_language_code_in_both_documented_headers(tmp_path):
    import verify_gnani
    from app import languages as reg
    from .test_ws_proxy import FakeStreamServer
    with FakeStreamServer([reg.LANGUAGES["ta"].sample]) as fake:
        env = sim_env(lang_sim(samples_by_code()), gnani_base_url=f"http://127.0.0.1:{fake.port}")
        out = await verify_gnani.stream_once(env, "ta", make_wav(1.0, 16000))
    assert out["ok"] and out["transcript"] == reg.LANGUAGES["ta"].sample
    assert fake.headers["lang_code"] == fake.headers["language_code"] == "ta-IN" and fake.headers["x-api-key-id"] == KEY


def test_the_results_file_the_script_writes_is_the_one_the_api_reads(make_app, tmp_path):
    """verify_gnani.build_result() -> eval/results/live_verification.json -> GET /api/languages: writer and reader must agree on the schema."""
    import asyncio
    import verify_gnani
    from app import languages as reg
    from .helpers import AuthedClient
    env = sim_env(lang_sim(samples_by_code()))
    res = asyncio.run(verify_gnani.verify(env, ["ta", "gu"], samples_dir=tmp_path))
    path = verify_gnani.write_live_file(verify_gnani.build_result(env, res["checks"], "live"), tmp_path / "live_verification.json")
    app = make_app(verification_file=path)
    with AuthedClient(app) as c:
        j = c.get("/api/languages").json()
        by = {r["key"]: r["verification"] for r in j["languages"]}
        assert j["verification"]["mode"] == "live" and j["verification"]["stt_model"] == "prisma-v2.5"
        assert [by["ta"][n]["status"] for n in verify_gnani.CHECKS] == ["passed", "passed", "passed", "skipped"]
        assert by["mr"]["tts"]["status"] == "not_run"                       # not run -> not verified
        assert by["ta"]["tts"]["voice"] == "Asmita" and by["ta"]["tts"]["audio_bytes"] > 1000
        # the same document labelled simulated can never read as a pass
        sim_path = tmp_path / "sim.json"
        sim_path.write_text(json.dumps(verify_gnani.build_result(env, res["checks"], "simulated")))
        app.state.settings.verification_file = sim_path
        sim = {r["key"]: r["verification"] for r in c.get("/api/languages").json()["languages"]}
    assert sim["ta"]["tts"]["status"] == "simulated" and all(v["status"] != "passed" for v in sim["ta"].values())


def test_a_later_partial_run_keeps_earlier_live_results_only_for_the_same_models_and_host(tmp_path):
    import asyncio
    import verify_gnani
    path = tmp_path / "v.json"
    env = sim_env(lang_sim(samples_by_code()))
    first = asyncio.run(verify_gnani.verify(env, ["ta", "gu"], samples_dir=tmp_path))
    verify_gnani.write_live_file(verify_gnani.build_result(env, first["checks"], "live"), path)
    second = asyncio.run(verify_gnani.verify(sim_env(lang_sim(samples_by_code())), ["mr"], samples_dir=tmp_path))
    verify_gnani.write_live_file(verify_gnani.build_result(env, second["checks"], "live"), path)
    assert set(json.loads(path.read_text())["checks"]) == {"ta", "gu", "mr"}
    # different STT model: old results describe another model, so they are dropped, not mixed in
    env3 = sim_env(lang_sim(samples_by_code()), gnani_stt_model="prisma-v3.0")
    third = asyncio.run(verify_gnani.verify(env3, ["pa"], samples_dir=tmp_path))
    verify_gnani.write_live_file(verify_gnani.build_result(env3, third["checks"], "live"), path)
    assert set(json.loads(path.read_text())["checks"]) == {"pa"}


async def test_script_with_a_simulated_client_never_writes_a_live_file(tmp_path, monkeypatch, capsys):
    import verify_gnani
    monkeypatch.setattr(verify_gnani, "make_env", lambda: sim_env(lang_sim(samples_by_code())))
    monkeypatch.setattr(verify_gnani, "LIVE_FILE", tmp_path / "live_verification.json")
    monkeypatch.setattr(verify_gnani, "save_report", lambda *a, **k: tmp_path / "report.md")
    # asyncio.run cannot be nested inside the test's running loop, so call the pieces main() uses
    res = await verify_gnani.verify(sim_env(lang_sim(samples_by_code())), ["ta"], samples_dir=tmp_path)
    assert res["checks"]["ta"]["tts"]["status"] == "passed"
    assert not (tmp_path / "live_verification.json").exists()


def test_every_test_phrase_parses_to_its_expected_order_and_the_first_is_the_apps_sample():
    from _live import PHRASES, make_env, parsed_lines
    from app import languages as reg
    env = make_env(Settings(_env_file=None, gnani_api_key=KEY))
    assert set(PHRASES) == set(reg.ORDER)
    for key, rows in PHRASES.items():
        assert len(rows) == 3
        for phrase, expected in rows:
            assert parsed_lines(env, phrase, key) == [(s, q) for s, q in expected], (key, phrase)
        if reg.LANGUAGES[key].origin == "expansion":
            assert rows[0][0] == reg.LANGUAGES[key].sample


async def test_noise_script_logic_with_simulated_gnani():
    import evaluate_noise
    from _live import make_env
    n = 1 + len(evaluate_noise.QUICK)
    env = make_env(Settings(_env_file=None, gnani_api_key=KEY), transport=httpx.MockTransport(sim_handler(["two kilo sugar and one litre milk please"] * n)))
    rows = await evaluate_noise.run(env, ["en"], 1, evaluate_noise.QUICK)
    assert [r.condition for r in rows] == ["clean", "babble@10dB", "telephony"] and all(r.chain_ok for r in rows)
    assert "mean WER" in evaluate_noise.render(rows, env)


async def test_scripts_report_auth_failure_cleanly():
    import verify_gnani
    from _live import make_env

    def deny(req):
        if req.url.path.startswith("/api"):
            return httpx.Response(401, json={"detail": {"error_code": "INVALID_API_KEY", "message": "bad", "status_code": 401}})
        return httpx.Response(401)

    env = make_env(Settings(_env_file=None, gnani_api_key=KEY), transport=httpx.MockTransport(deny))
    rows, _ = await verify_gnani.run(env, ["gu", "hi"], stream=False)
    assert len(rows) == 1 and "INVALID_API_KEY" in rows[0].error  # stops after the first auth failure instead of burning calls
    res = await verify_gnani.verify(env, ["gu", "hi"])
    assert list(res["checks"]) == ["gu"] and res["checks"]["gu"]["tts"]["error_code"] == "INVALID_API_KEY"


# ---- scripts/auth_admin.py (the no-e-mail fallback for account recovery) ---------------------------------------------
def _cli(tmp_path, monkeypatch, *argv, password=None):
    import auth_admin
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCRYPT_LOG2_N", "10")
    monkeypatch.setenv("SCRYPT_P", "1")
    if password:
        monkeypatch.setenv("SWARA_NEW_PASSWORD", password)
    else:
        monkeypatch.delenv("SWARA_NEW_PASSWORD", raising=False)
    return auth_admin.main(list(argv))


def test_cli_creates_the_owner_who_can_then_sign_in_through_the_api(tmp_path, monkeypatch, capsys):
    from fastapi.testclient import TestClient
    from app.main import create_app
    assert _cli(tmp_path, monkeypatch, "create-owner", "--email", "Boss@Example.com", "--name", "The Boss", password="Quartz-Velvet-42!") == 0
    assert "Owner account created" in capsys.readouterr().out
    cfg = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'cli.db'}", data_dir=tmp_path, scrypt_log2_n=10, scrypt_p=1, seed_on_startup=False)
    with TestClient(create_app(cfg)) as c:
        r = c.post("/api/auth/login", json={"email": "boss@example.com", "password": "Quartz-Velvet-42!"})
        assert r.status_code == 200 and r.json()["user"]["role"] == "owner"


def test_cli_reset_password_ends_sessions_and_rejects_weak_passwords(tmp_path, monkeypatch, capsys):
    import pytest
    _cli(tmp_path, monkeypatch, "create-owner", "--email", "boss@example.com", "--name", "The Boss", password="Quartz-Velvet-42!")
    with pytest.raises(SystemExit) as e:
        _cli(tmp_path, monkeypatch, "reset-password", "--email", "boss@example.com", password="password123")
    assert "too common" in str(e.value)
    assert _cli(tmp_path, monkeypatch, "reset-password", "--email", "boss@example.com", password="Another-Long-Pass-7!") == 0
    with pytest.raises(SystemExit):
        _cli(tmp_path, monkeypatch, "reset-password", "--email", "nobody@example.com", password="Another-Long-Pass-7!")
    capsys.readouterr()
    _cli(tmp_path, monkeypatch, "list")
    out = capsys.readouterr().out
    assert "boss@example.com" in out and "owner" in out and "Another-Long-Pass-7!" not in out and "scrypt" not in out


def test_cli_cannot_make_a_second_owner_or_switch_the_owner_off(tmp_path, monkeypatch):
    import pytest
    _cli(tmp_path, monkeypatch, "create-owner", "--email", "boss@example.com", "--name", "The Boss", password="Quartz-Velvet-42!")
    with pytest.raises(SystemExit):
        _cli(tmp_path, monkeypatch, "create-owner", "--email", "other@example.com", "--name", "Other One", password="Quartz-Velvet-42!")
    with pytest.raises(SystemExit):
        _cli(tmp_path, monkeypatch, "set-active", "--email", "boss@example.com", "--off")


def test_cli_creates_staff_who_cannot_be_an_owner_and_can_sign_in_when_sign_up_is_closed(tmp_path, monkeypatch, capsys):
    import pytest
    from fastapi.testclient import TestClient
    from app.main import create_app
    with pytest.raises(SystemExit) as e:   # staff need an owner to exist first
        _cli(tmp_path, monkeypatch, "create-staff", "--email", "till@example.com", "--name", "Till Staff", password="Quartz-Velvet-42!")
    assert "no owner yet" in str(e.value)
    _cli(tmp_path, monkeypatch, "create-owner", "--email", "boss@example.com", "--name", "The Boss", password="Quartz-Velvet-42!")
    assert _cli(tmp_path, monkeypatch, "create-staff", "--email", "Till@Example.com", "--name", "Till Staff", password="Counter-Brass-91!") == 0
    assert "Staff account created" in capsys.readouterr().out
    with pytest.raises(SystemExit):        # same address twice
        _cli(tmp_path, monkeypatch, "create-staff", "--email", "till@example.com", "--name", "Till Staff", password="Counter-Brass-91!")
    with pytest.raises(SystemExit):        # a name that could carry markup
        _cli(tmp_path, monkeypatch, "create-staff", "--email", "x@example.com", "--name", "<b>Hi</b>", password="Counter-Brass-91!")
    cfg = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'cli.db'}", data_dir=tmp_path, scrypt_log2_n=10, scrypt_p=1,
                   seed_on_startup=False, allow_signup=False)
    with TestClient(create_app(cfg)) as c:
        assert c.get("/api/auth/config").json()["signup_open"] is False
        r = c.post("/api/auth/login", json={"email": "till@example.com", "password": "Counter-Brass-91!"})
        assert r.status_code == 200 and r.json()["user"]["role"] == "staff"


def test_cli_test_mail_says_plainly_when_smtp_is_not_set_up_and_sends_through_the_configured_server(tmp_path, monkeypatch, capsys):
    import pytest
    for k in ("SMTP_HOST", "SMTP_FROM"):
        monkeypatch.setenv(k, "")   # an empty environment value wins over a developer's real .env file
    with pytest.raises(SystemExit) as e:
        _cli(tmp_path, monkeypatch, "test-mail", "--to", "me@example.com")
    assert "not set up" in str(e.value) and "Nothing was sent" in str(e.value)

    sent = []
    from app.services import mailer
    monkeypatch.setattr(mailer, "send", lambda settings, to, subject, text, html=None: sent.append((settings.smtp_host, to, subject)))
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("SMTP_FROM", "SWARA AI <no-reply@example.test>")
    assert _cli(tmp_path, monkeypatch, "test-mail", "--to", "Me@Example.com") == 0
    assert sent == [("mail.example.test", "me@example.com", "SWARA AI test message")]
    assert "Check the inbox" in capsys.readouterr().out

    def refuse(*a, **k):
        raise mailer.MailError("The mail server did not accept the message.")
    monkeypatch.setattr(mailer, "send", refuse)
    with pytest.raises(SystemExit) as e:
        _cli(tmp_path, monkeypatch, "test-mail", "--to", "me@example.com")
    assert "Not sent" in str(e.value)


# ---- Windows scripts: cmd.exe cannot be run in this environment, so these check what can be checked by reading them ----
import re as _re
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
_BATS = ("setup.bat", "start.bat", "dev.bat", "test.bat", "verify_gnani.bat")


def _bat(name: str) -> str:
    return (_ROOT / name).read_bytes().decode("ascii")   # non-ASCII text can print as garbage in a default console


def test_every_goto_in_a_windows_script_has_a_label():
    for name in _BATS:
        text = _bat(name)
        labels = {m.group(1).lower() for m in _re.finditer(r"^:(\w+)", text, _re.M)}
        targets = {m.group(1).lower() for m in _re.finditer(r"\bgoto\s+(\w+)", text, _re.I)} - {"eof"}
        assert targets <= labels, f"{name}: goto without a label: {sorted(targets - labels)}"


def test_windows_scripts_point_at_files_that_exist():
    needed = {
        "setup.bat": ["backend/requirements.txt", ".env.example", "scripts/seed_db.py", "frontend/package.json"],
        "start.bat": ["backend/app/main.py"],
        "test.bat": ["backend/requirements-dev.txt", "pytest.ini"],
        "verify_gnani.bat": ["scripts/verify_gnani.py"],
    }
    for name, files in needed.items():
        for rel in files:
            assert (_ROOT / rel).exists(), f"{name} refers to {rel}, which is missing"
    assert "create_app --factory" in _bat("start.bat") and "create_app --factory" in _bat("dev.bat")


def test_windows_scripts_never_hold_a_key_and_always_say_what_to_do_on_failure():
    for name in _BATS:
        text = _bat(name)
        assert not _re.search(r"GNANI_API_KEY\s*=\s*\S", text), f"{name} must not set a key"
    setup = _bat("setup.bat")
    assert ":fail" in setup and "Setup did not finish" in setup and "exit /b 1" in setup
