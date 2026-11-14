"""Accounts and sessions. Everything goes through the real endpoints and the real database; nothing is mocked except
the mail server (a local socket sink, see SmtpSink: it is not a real mail provider)."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuthSession, AuthToken, ContactMessage, User, utcnow
from app.services import mailer
from app.services.passwords import (PasswordError, check_policy, dummy_verify, hash_password, needs_rehash, strength,
                                    verify_password)

from .helpers import OWNER, STAFF, SmtpSink, login, register


@pytest.fixture
def sink():
    s = SmtpSink()
    yield s
    s.close()


def smtp_cfg(sink, **kw):
    return dict(smtp_host="127.0.0.1", smtp_port=sink.port, smtp_security="none", smtp_from="SWARA AI <no-reply@example.com>",
                public_url="http://shop.test", **kw)


def db_rows(client, model):
    with client.app.state.session_factory() as db:
        return list(db.scalars(select(model)))


def wait_for_mail(sink, n=1, seconds=3.0):
    end = time.time() + seconds
    while len(sink.messages) < n and time.time() < end:
        time.sleep(0.02)
    return len(sink.messages) >= n


# ---- configuration -------------------------------------------------------------------------------------------------
def test_public_config_describes_the_server_without_secrets(anon):
    c = anon.get("/api/auth/config").json()
    assert c["owner_email_set"] is False and "boss" not in str(c)    # only whether it is set, never the address
    assert c["signup_open"] is True and c["has_owner"] is False and c["email_configured"] is False and c["verification_required"] is False
    assert c["password"] == {"min_length": 10, "max_length": 128}
    assert "smtp" not in str(c).lower() or "smtp_" not in str(c)


# ---- sign up -------------------------------------------------------------------------------------------------------
def test_first_account_is_the_owner_and_is_signed_in(anon):
    r = register(anon)
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["role"] == "owner" and body["user"]["email"] == "owner@example.com" and body["csrf_token"]
    assert "password" not in str(body).lower().replace("password_changed", "")
    assert anon.get("/api/auth/me").json()["user"]["full_name"] == "Test Owner"
    assert anon.get("/api/auth/config").json()["has_owner"] is True


def test_later_accounts_are_staff(anon):
    register(anon)
    anon.cookies.clear()
    assert register(anon, STAFF).json()["user"]["role"] == "staff"


def test_cookie_is_httponly_samesite_and_session_only_by_default(anon):
    r = register(anon)
    sc = r.headers["set-cookie"].lower()
    assert "swara_session=" in sc and "httponly" in sc and "samesite=lax" in sc and "path=/" in sc
    assert "max-age" not in sc and "secure" not in sc    # plain-http local use: no Secure flag, and a session cookie


def test_https_deployment_uses_a_secure_host_prefixed_cookie(make_app):
    with TestClient(make_app(public_url="https://shop.example")) as c:
        sc = register(c).headers["set-cookie"].lower()
        assert sc.startswith("__host-swara_session=") and "secure" in sc and "httponly" in sc


def test_password_is_stored_only_as_a_scrypt_hash(anon):
    register(anon)
    (u,) = db_rows(anon, User)
    assert u.password_hash.startswith("scrypt$") and OWNER["password"] not in u.password_hash
    assert verify_password(OWNER["password"], u.password_hash) and not verify_password("wrong", u.password_hash)
    assert u.email == "owner@example.com" and u.terms_accepted_at is not None


def test_session_secret_is_stored_only_as_a_hash(anon):
    register(anon)
    (s,) = db_rows(anon, AuthSession)
    raw = anon.cookies.get("swara_session")
    assert raw and raw not in (s.token_hash, s.csrf_token) and len(s.token_hash) == 64


@pytest.mark.parametrize("over,code", [
    ({"email": "not-an-email"}, "BAD_EMAIL"), ({"email": "a@b"}, "BAD_EMAIL"), ({"email": "x y@example.com"}, "BAD_EMAIL"),
    ({"full_name": "A"}, "BAD_NAME"), ({"full_name": "<b>Bob</b>"}, "BAD_NAME"), ({"full_name": "   "}, "BAD_NAME"),
    ({"password": "short1!", "confirm_password": "short1!"}, "WEAK_PASSWORD"),
    ({"password": "password123", "confirm_password": "password123"}, "WEAK_PASSWORD"),
    ({"password": "owner@example.com", "confirm_password": "owner@example.com"}, "WEAK_PASSWORD"),
    ({"password": "aaaaaaaaaaaa", "confirm_password": "aaaaaaaaaaaa"}, "WEAK_PASSWORD"),
    ({"password": " leading-space-1A ", "confirm_password": " leading-space-1A "}, "WEAK_PASSWORD"),
    ({"confirm_password": "Different-Pass-1!"}, "PASSWORD_MISMATCH"),
    ({"accept_terms": False}, "TERMS_REQUIRED"),
])
def test_signup_validation(anon, over, code):
    r = register(anon, **over)
    assert r.status_code == 422 and r.json()["detail"]["code"] == code, r.text
    assert db_rows(anon, User) == []


def test_signup_rejects_unknown_fields_so_a_role_cannot_be_smuggled_in(anon):
    register(anon)
    anon.cookies.clear()
    r = register(anon, STAFF, role="owner")
    assert r.status_code == 422
    r = register(anon, STAFF, is_active=True, email_verified_at="2020-01-01")
    assert r.status_code == 422


def test_duplicate_email_is_refused_ignoring_case_and_spaces(anon):
    register(anon)
    anon.cookies.clear()
    r = register(anon, email=" OWNER@Example.com ")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "EMAIL_TAKEN"
    assert len(db_rows(anon, User)) == 1


def test_sign_up_can_be_closed_after_the_owner_exists(make_app):
    with TestClient(make_app(allow_signup=False)) as c:
        assert c.get("/api/auth/config").json()["signup_open"] is True    # the owner can still be created
        assert register(c).status_code == 201
        c.cookies.clear()
        assert c.get("/api/auth/config").json()["signup_open"] is False
        r = register(c, STAFF)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "SIGNUP_CLOSED"


def test_owner_email_setting_decides_who_becomes_owner(make_app):
    with TestClient(make_app(owner_email="Boss@Example.com")) as c:
        assert register(c, STAFF).json()["user"]["role"] == "staff"   # someone else got there first: still only staff
        c.cookies.clear()
        boss = {"full_name": "The Boss", "email": "boss@example.com", "password": "Quartz-Velvet-42!"}
        assert register(c, boss).json()["user"]["role"] == "owner"
        c.cookies.clear()
        assert register(c, OWNER).json()["user"]["role"] == "staff"   # a second owner can never appear


def test_closed_signup_with_owner_email_only_admits_that_address(make_app):
    with TestClient(make_app(allow_signup=False, owner_email="boss@example.com")) as c:
        assert register(c, STAFF).status_code == 403
        boss = {"full_name": "The Boss", "email": "boss@example.com", "password": "Quartz-Velvet-42!"}
        assert register(c, boss).json()["user"]["role"] == "owner"


# ---- sign in -------------------------------------------------------------------------------------------------------
def test_login_logout_and_protected_route_cycle(anon):
    register(anon)
    anon.post("/api/auth/logout")
    anon.cookies.clear()
    anon.headers.pop("X-CSRF-Token")
    assert anon.get("/api/products").status_code == 401
    r = login(anon)
    assert r.status_code == 200 and r.json()["user"]["email"] == "owner@example.com"
    assert anon.get("/api/products").status_code == 200
    assert anon.post("/api/auth/logout").status_code == 200
    assert anon.get("/api/products").status_code == 401


def test_login_normalises_the_email(anon):
    register(anon)
    anon.cookies.clear()
    assert login(anon, OWNER, email="  OWNER@EXAMPLE.COM ").status_code == 200


def test_wrong_password_and_unknown_email_are_indistinguishable(anon):
    register(anon)
    anon.cookies.clear()
    a = anon.post("/api/auth/login", json={"email": OWNER["email"], "password": "Wrong-Password-1!"})
    b = anon.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong-Password-1!"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json() and a.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in a.headers


def test_remember_me_makes_a_persistent_cookie_and_a_longer_session(anon):
    register(anon)
    anon.cookies.clear()
    plain = login(anon, OWNER)
    anon.cookies.clear()
    kept = login(anon, OWNER, remember=True)
    assert "max-age" not in plain.headers["set-cookie"].lower() and "max-age=2592000" in kept.headers["set-cookie"].lower()
    rows = sorted(db_rows(anon, AuthSession), key=lambda s: s.id)
    short, long_ = rows[-2], rows[-1]
    assert (short.expires_at - short.created_at) <= timedelta(hours=12, seconds=5)
    assert (long_.expires_at - long_.created_at) >= timedelta(days=29)


def test_repeated_failures_block_even_the_right_password_for_a_while(make_app):
    with TestClient(make_app(login_max_failures=3)) as c:
        register(c)
        c.cookies.clear()
        for _ in range(3):
            assert c.post("/api/auth/login", json={"email": OWNER["email"], "password": "nope-nope-nope"}).status_code == 401
        r = c.post("/api/auth/login", json={"email": OWNER["email"], "password": OWNER["password"]})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "TOO_MANY_ATTEMPTS" and r.json()["detail"]["retry_after_s"] > 0
        c.app.state.login_by_email.clear(OWNER["email"])       # time passing, in effect
        c.app.state.login_by_ip.clear("testclient")
        assert c.post("/api/auth/login", json={"email": OWNER["email"], "password": OWNER["password"]}).status_code == 200


def test_unknown_addresses_are_throttled_exactly_like_real_ones(make_app):
    with TestClient(make_app(login_max_failures=3)) as c:
        codes = [c.post("/api/auth/login", json={"email": "ghost@example.com", "password": "x" * 12}).status_code for _ in range(5)]
        assert codes == [401, 401, 401, 429, 429]


def test_success_resets_the_failure_count(make_app):
    with TestClient(make_app(login_max_failures=3)) as c:
        register(c)
        c.cookies.clear()
        for _ in range(2):
            c.post("/api/auth/login", json={"email": OWNER["email"], "password": "nope-nope-nope"})
        assert login(c).status_code == 200
        c.cookies.clear()
        for _ in range(2):
            assert c.post("/api/auth/login", json={"email": OWNER["email"], "password": "nope-nope-nope"}).status_code == 401


def test_auth_endpoints_are_rate_limited_per_device(make_app):
    with TestClient(make_app(auth_rate_per_minute=4)) as c:
        codes = [c.post("/api/auth/login", json={"email": "a@example.com", "password": "x" * 12}).status_code for _ in range(6)]
        assert codes[:4] == [401] * 4 and codes[4:] == [429, 429]
        r = c.post("/api/auth/login", json={"email": "a@example.com", "password": "x" * 12})
        assert r.headers["retry-after"].isdigit()


def test_old_hashes_are_upgraded_on_login(make_app):
    with TestClient(make_app()) as c:
        register(c)
        with c.app.state.session_factory() as db:
            u = db.scalar(select(User))
            u.password_hash = hash_password(OWNER["password"], log2_n=10, p=1)
            db.commit()
        c.app.state.settings.scrypt_log2_n = 11
        c.cookies.clear()
        assert login(c).status_code == 200
        (u,) = db_rows(c, User)
        assert u.password_hash.split("$")[1] == str(1 << 11) and verify_password(OWNER["password"], u.password_hash)


# ---- sessions ------------------------------------------------------------------------------------------------------
def test_me_requires_a_session_and_reports_lifetime(anon):
    r = anon.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "NOT_AUTHENTICATED"
    register(anon)
    m = anon.get("/api/auth/me").json()
    assert m["csrf_token"] and m["session"]["expires_at"].endswith("Z") and m["session"]["remember"] is False


def test_soft_session_check_is_200_for_visitors_and_members(anon):
    r = anon.get("/api/auth/session")
    assert r.status_code == 200 and r.json() == {"authenticated": False}
    register(anon)
    j = anon.get("/api/auth/session").json()
    assert j["authenticated"] is True and j["user"]["email"] == "owner@example.com" and j["csrf_token"]
    anon.post("/api/auth/logout")
    assert anon.get("/api/auth/session").json() == {"authenticated": False}


def test_garbage_and_foreign_cookies_are_just_signed_out(anon):
    anon.cookies.set("swara_session", "x" * 43)
    assert anon.get("/api/products").status_code == 401
    anon.cookies.set("swara_session", "")
    assert anon.get("/api/products").status_code == 401


def test_session_ends_after_its_absolute_lifetime(client):
    with client.app.state.session_factory() as db:
        s = db.scalar(select(AuthSession))
        s.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    r = client.get("/api/products")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "SESSION_EXPIRED"
    assert client.get("/api/products").json()["detail"]["code"] == "NOT_AUTHENTICATED"   # it stays dead


def test_session_ends_after_sitting_idle(client):
    with client.app.state.session_factory() as db:
        s = db.scalar(select(AuthSession))
        s.last_seen_at = utcnow() - timedelta(hours=3)
        db.commit()
    assert client.get("/api/products").json()["detail"]["code"] == "SESSION_EXPIRED"


def test_activity_keeps_a_session_alive(client):
    with client.app.state.session_factory() as db:
        s = db.scalar(select(AuthSession))
        s.last_seen_at = utcnow() - timedelta(minutes=90)     # inside the 2 h idle window
        db.commit()
    assert client.get("/api/products").status_code == 200
    (s,) = db_rows(client, AuthSession)
    assert utcnow() - s.last_seen_at < timedelta(minutes=1)


def test_logout_kills_the_server_side_session_not_just_the_cookie(client):
    stolen = client.cookies.get("swara_session")
    client.post("/api/auth/logout")
    with TestClient(client.app) as thief:
        thief.cookies.set("swara_session", stolen)
        assert thief.get("/api/products").status_code == 401


def test_logout_without_a_session_still_succeeds(anon):
    assert anon.post("/api/auth/logout").status_code == 200


def test_list_and_revoke_sessions(client):
    with TestClient(client.app) as phone:
        login(phone, OWNER, **{})
        sessions = client.get("/api/auth/sessions").json()
        assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
        assert all(set(s) == {"id", "device", "created_at", "last_seen_at", "expires_at", "remember", "current"} for s in sessions)
        other = next(s for s in sessions if not s["current"])
        assert client.delete(f"/api/auth/sessions/{other['id']}").status_code == 200
        assert phone.get("/api/products").status_code == 401
        assert client.delete(f"/api/auth/sessions/{other['id']}").status_code == 404


def test_sign_out_everywhere_else(client):
    clients = []
    for _ in range(2):
        c = TestClient(client.app); c.__enter__(); login(c, OWNER); clients.append(c)
    assert client.post("/api/auth/sessions/revoke-others").json()["signed_out"] == 2
    assert all(c.get("/api/products").status_code == 401 for c in clients)
    assert client.get("/api/products").status_code == 200
    for c in clients:
        c.__exit__(None, None, None)


def test_one_person_cannot_see_or_revoke_anothers_sessions(make_app):
    with TestClient(make_app()) as c:
        register(c)
        owner_sessions = c.get("/api/auth/sessions").json()
        c.cookies.clear()
        register(c, STAFF)
        assert len(c.get("/api/auth/sessions").json()) == 1
        assert c.delete(f"/api/auth/sessions/{owner_sessions[0]['id']}").status_code == 404


# ---- profile & password --------------------------------------------------------------------------------------------
def test_profile_update_and_language_preference(client):
    r = client.patch("/api/auth/profile", json={"full_name": "  Ramesh   Patel ", "language": "gu"})
    u = r.json()["user"]
    assert u["full_name"] == "Ramesh Patel" and u["preferences"] == {"language": "gu"}
    assert client.get("/api/auth/me").json()["user"]["preferences"]["language"] == "gu"


@pytest.mark.parametrize("body", [{"full_name": "x"}, {"full_name": "<script>"}, {"language": "klingon"},
                                  {"role": "owner"}, {"email": "new@example.com"}, {"is_active": False}])
def test_profile_rejects_bad_input_and_cannot_change_role_or_email(client, body):
    assert client.patch("/api/auth/profile", json=body).status_code == 422
    u = client.get("/api/auth/me").json()["user"]
    assert u["role"] == "owner" and u["email"] == "owner@example.com"


def test_change_password_needs_the_current_one_and_ends_other_sessions(client):
    with TestClient(client.app) as other:
        login(other, OWNER)
        bad = client.post("/api/auth/change-password", json={"current_password": "wrong-wrong-1", "new_password": "Brand-New-Pass-5!"})
        assert bad.status_code == 403 and bad.json()["detail"]["code"] == "WRONG_PASSWORD"
        weak = client.post("/api/auth/change-password", json={"current_password": OWNER["password"], "new_password": "password123"})
        assert weak.status_code == 422
        same = client.post("/api/auth/change-password", json={"current_password": OWNER["password"], "new_password": OWNER["password"]})
        assert same.status_code == 422 and same.json()["detail"]["code"] == "SAME_PASSWORD"
        ok = client.post("/api/auth/change-password", json={"current_password": OWNER["password"], "new_password": "Brand-New-Pass-5!"})
        assert ok.status_code == 200 and ok.json()["other_sessions_signed_out"] == 1
        assert other.get("/api/products").status_code == 401        # a stolen session does not survive
        assert client.get("/api/products").status_code == 200       # this one stays
    client.cookies.clear()
    assert login(client, OWNER).status_code == 401
    assert login(client, {**OWNER, "password": "Brand-New-Pass-5!"}).status_code == 200


def test_change_password_cannot_be_used_to_guess_the_current_password(make_app):
    with TestClient(make_app(login_max_failures=3)) as c:
        register(c)
        codes = [c.post("/api/auth/change-password", json={"current_password": f"guess-guess-{i}", "new_password": "Brand-New-Pass-5!"}).status_code for i in range(5)]
        assert codes == [403, 403, 403, 429, 429]


# ---- password reset & e-mail verification (against the local mail sink) ---------------------------------------------
def test_forgot_password_without_mail_is_honest_and_sends_nothing(anon):
    register(anon)
    anon.cookies.clear()
    r = anon.post("/api/auth/forgot", json={"email": OWNER["email"]})
    assert r.status_code == 200 and r.json()["email_configured"] is False and "not set up to send e-mail" in r.json()["message"]


def test_full_reset_flow_over_smtp(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink, require_email_verification=False))) as c:
        register(c)
        with TestClient(c.app) as other:
            login(other, OWNER)
            c.cookies.clear()
            r = c.post("/api/auth/forgot", json={"email": "Owner@Example.com"})
            assert r.status_code == 200 and r.json()["email_configured"] is True
            assert wait_for_mail(sink)
            assert sink.messages[0]["to"] == ["<owner@example.com>"] and "no-reply@example.com" in sink.messages[0]["from"]
            link = sink.last_text
            assert "http://shop.test/reset-password?token=" in link and "expires in 1 hours" in link
            token = sink.last_token()
            (t,) = [x for x in db_rows(c, AuthToken) if x.purpose == "reset"]
            assert token not in t.token_hash and len(t.token_hash) == 64      # only the hash is stored
            weak = c.post("/api/auth/reset", json={"token": token, "password": "password123"})
            assert weak.status_code == 422                                   # and a weak password does not burn the link
            ok = c.post("/api/auth/reset", json={"token": token, "password": "A-Fresh-Passphrase-3!", "confirm_password": "A-Fresh-Passphrase-3!"})
            assert ok.status_code == 200
            again = c.post("/api/auth/reset", json={"token": token, "password": "Another-Fresh-One-4!"})
            assert again.status_code == 400 and again.json()["detail"]["code"] == "INVALID_TOKEN"   # single use
            assert other.get("/api/products").status_code == 401             # every old session is gone
            assert login(c, OWNER).status_code == 401
            assert login(c, {**OWNER, "password": "A-Fresh-Passphrase-3!"}).status_code == 200


def test_forgot_for_unknown_address_looks_identical_and_sends_nothing(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink, require_email_verification=False))) as c:
        register(c)
        c.cookies.clear()
        known = c.post("/api/auth/forgot", json={"email": OWNER["email"]}).json()
        unknown = c.post("/api/auth/forgot", json={"email": "ghost@example.com"}).json()
        garbage = c.post("/api/auth/forgot", json={"email": "not an email"}).json()
        assert known == unknown == garbage
        wait_for_mail(sink, 1)
        time.sleep(0.4)
        assert len(sink.messages) == 1 and sink.messages[0]["to"] == ["<owner@example.com>"]   # only the real account got mail


def test_reset_links_are_limited_per_address(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink, require_email_verification=False))) as c:
        register(c)
        c.cookies.clear()
        for _ in range(6):
            c.post("/api/auth/forgot", json={"email": OWNER["email"]})
        wait_for_mail(sink, 3)
        time.sleep(0.4)
        assert len(sink.messages) == 3


def test_a_newer_reset_link_retires_the_older_one(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink, require_email_verification=False))) as c:
        register(c)
        c.cookies.clear()
        c.post("/api/auth/forgot", json={"email": OWNER["email"]}); wait_for_mail(sink, 1); first = sink.last_token()
        c.post("/api/auth/forgot", json={"email": OWNER["email"]}); wait_for_mail(sink, 2); second = sink.last_token()
        assert first != second
        assert c.post("/api/auth/reset", json={"token": first, "password": "Some-Long-Secret-8!"}).status_code == 400
        assert c.post("/api/auth/reset", json={"token": second, "password": "Some-Long-Secret-8!"}).status_code == 200


def test_expired_and_made_up_reset_tokens_are_refused(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink, require_email_verification=False))) as c:
        register(c)
        c.cookies.clear()
        c.post("/api/auth/forgot", json={"email": OWNER["email"]}); wait_for_mail(sink, 1)
        token = sink.last_token()
        with c.app.state.session_factory() as db:
            t = db.scalar(select(AuthToken).where(AuthToken.purpose == "reset"))
            t.expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        assert c.post("/api/auth/reset", json={"token": token, "password": "Some-Long-Secret-8!"}).status_code == 400
        assert c.post("/api/auth/reset", json={"token": "A" * 43, "password": "Some-Long-Secret-8!"}).status_code == 400


def test_a_verify_token_cannot_reset_a_password(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink))) as c:
        register(c, STAFF)       # owner is whoever is first; this is fine, we only need the verify mail
        assert wait_for_mail(sink, 1)
        token = sink.last_token()
        assert c.post("/api/auth/reset", json={"token": token, "password": "Some-Long-Secret-8!"}).status_code == 400


def test_verification_is_enforced_only_when_mail_works(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink))) as c:
        assert c.get("/api/auth/config").json()["verification_required"] is True
        r = register(c)
        assert r.status_code == 201 and r.json()["verification_required"] is True and r.json()["user"] is None
        assert "set-cookie" not in r.headers and c.get("/api/products").status_code == 401
        blocked = login(c)
        assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"
        wrong = c.post("/api/auth/login", json={"email": OWNER["email"], "password": "Wrong-Password-1!"})
        assert wrong.json()["detail"]["code"] == "INVALID_CREDENTIALS"      # the verification state is not leaked to strangers
        assert wait_for_mail(sink, 1) and "Confirm your SWARA AI e-mail" in sink.messages[0]["raw"]
        token = sink.last_token()
        assert c.post("/api/auth/verify-email", json={"token": token}).status_code == 200
        assert c.post("/api/auth/verify-email", json={"token": token}).status_code == 400
        ok = login(c)
        assert ok.status_code == 200 and ok.json()["user"]["email_verified"] is True


def test_resend_verification(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink))) as c:
        register(c)
        wait_for_mail(sink, 1)
        first = sink.last_token()
        assert c.post("/api/auth/resend-verification", json={"email": OWNER["email"]}).status_code == 200
        wait_for_mail(sink, 2)
        assert sink.last_token() != first
        assert c.post("/api/auth/verify-email", json={"token": first}).status_code == 400    # retired by the new one
        assert c.post("/api/auth/resend-verification", json={"email": "ghost@example.com"}).json()["ok"] is True


def test_verification_can_be_switched_off_even_with_mail(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink), require_email_verification=False)) as c:
        r = register(c)
        assert r.json()["verification_required"] is False and c.get("/api/products").status_code == 200
        assert c.get("/api/auth/me").json()["user"]["email_verified"] is False


def test_a_broken_mail_server_does_not_break_sign_up_or_reveal_anything(make_app):
    cfg = dict(smtp_host="127.0.0.1", smtp_port=9, smtp_security="none", smtp_from="no-reply@example.com")
    with TestClient(make_app(**cfg)) as c:
        r = register(c)
        assert r.status_code == 201 and r.json()["verification_required"] is True
        assert c.post("/api/auth/forgot", json={"email": OWNER["email"]}).status_code == 200


def test_smtp_login_uses_the_configured_credentials(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink, smtp_user="mailer", smtp_password="s3cret-smtp-pass"))) as c:
        register(c)
        wait_for_mail(sink, 1)
    assert sink.auth_seen


def test_mailer_refuses_header_injection(make_app):
    from app.config import Settings
    s = Settings(_env_file=None, smtp_host="h", smtp_from="a@b.c")
    with pytest.raises(mailer.MailError):
        mailer.build(s, "victim@example.com\r\nBcc: spy@example.com", "Hi", "text")
    with pytest.raises(mailer.MailError):
        mailer.build(s, "victim@example.com", "Hi\nBcc: spy@example.com", "text")
    with pytest.raises(mailer.MailError):
        mailer.send(Settings(_env_file=None), "a@b.c", "x", "y")    # not configured


# ---- team (owner only) ---------------------------------------------------------------------------------------------
def test_owner_can_list_and_turn_off_staff(make_app):
    app = make_app()
    with TestClient(app) as owner, TestClient(app) as staff:
        register(owner)
        register(staff, STAFF)
        users = owner.get("/api/auth/users").json()
        assert [u["role"] for u in users] == ["owner", "staff"] and not any("hash" in str(u) for u in users)
        sid = users[1]["id"]
        assert staff.get("/api/auth/users").status_code == 403
        assert owner.post(f"/api/auth/users/{sid}/active", json={"active": False}).json()["is_active"] is False
        assert staff.get("/api/products").status_code == 401                      # their session ended at once
        r = login(staff, STAFF)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "ACCOUNT_DISABLED"
        owner.post(f"/api/auth/users/{sid}/active", json={"active": True})
        assert login(staff, STAFF).status_code == 200


def test_owner_cannot_lock_themselves_out(client):
    me = client.get("/api/auth/me").json()["user"]["id"]
    r = client.post(f"/api/auth/users/{me}/active", json={"active": False})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "SELF_CHANGE"
    assert client.post("/api/auth/users/999/active", json={"active": False}).status_code == 404


# ---- contact form --------------------------------------------------------------------------------------------------
CONTACT = {"name": "Meera Shah", "email": "meera@example.com", "topic": "demo", "message": "Can I see this working for my shop in Vadodara?"}


def test_contact_message_is_stored_for_the_owner_and_says_so(anon):
    r = anon.post("/api/contact", json=CONTACT)
    assert r.status_code == 201 and r.json()["forwarded"] is False and "saved on this server" in r.json()["message"]
    (m,) = db_rows(anon, ContactMessage)
    assert m.email == "meera@example.com" and m.topic == "demo"


def test_contact_validation(anon):
    for bad in [{**CONTACT, "email": "nope"}, {**CONTACT, "message": "short"}, {**CONTACT, "name": ""}, {**CONTACT, "topic": "spam"},
                {**CONTACT, "message": "x" * 2001}, {**CONTACT, "extra": 1}]:
        assert anon.post("/api/contact", json=bad).status_code == 422
    assert db_rows(anon, ContactMessage) == []


def test_contact_honeypot_stores_nothing(anon):
    r = anon.post("/api/contact", json={**CONTACT, "website": "http://spam.example"})
    assert r.status_code == 201 and db_rows(anon, ContactMessage) == []


def test_contact_inbox_is_owner_only_and_can_be_marked_handled(make_app):
    app = make_app()
    with TestClient(app) as owner, TestClient(app) as staff:
        register(owner); register(staff, STAFF)
        owner.post("/api/contact", json=CONTACT)
        assert staff.get("/api/contact/messages").status_code == 403
        (m,) = owner.get("/api/contact/messages").json()
        assert m["message"].startswith("Can I see") and m["handled"] is False
        assert owner.post(f"/api/contact/messages/{m['id']}/handled").status_code == 200
        assert owner.get("/api/contact/messages").json()[0]["handled"] is True
        assert owner.post("/api/contact/messages/999/handled").status_code == 404


def test_contact_is_forwarded_by_mail_when_configured(make_app, sink):
    with TestClient(make_app(**smtp_cfg(sink), contact_to="team@example.com")) as c:
        r = c.post("/api/contact", json=CONTACT)
        assert r.json()["forwarded"] is True
        assert wait_for_mail(sink, 1) and "Can I see this working" in sink.messages[0]["raw"] and sink.messages[0]["to"] == ["<team@example.com>"]


# ---- logging & secrets ---------------------------------------------------------------------------------------------
def test_logs_never_contain_passwords_tokens_or_cookies(make_app, sink, caplog):
    caplog.set_level(logging.DEBUG)
    with TestClient(make_app(**smtp_cfg(sink, smtp_user="mailer", smtp_password="s3cret-smtp-pass"))) as c:
        register(c)
        wait_for_mail(sink, 1)
        verify = sink.last_token()
        c.post("/api/auth/verify-email", json={"token": verify})
        login(c)
        c.post("/api/auth/login", json={"email": OWNER["email"], "password": "Wrong-Password-1!"})
        c.post("/api/auth/forgot", json={"email": OWNER["email"]}); wait_for_mail(sink, 2)
        reset = sink.last_token()
        c.post("/api/auth/reset", json={"token": reset, "password": "Logged-Out-Pass-6!"})
        cookie = c.cookies.get("swara_session") or "-"
    text = caplog.text
    for secret in (OWNER["password"], "Wrong-Password-1!", "Logged-Out-Pass-6!", "s3cret-smtp-pass", verify, reset, cookie):
        assert secret not in text, secret
    assert "login failed" in text and "signup user_id=" in text      # but the events are recorded


# ---- password module -----------------------------------------------------------------------------------------------
def test_hash_format_salting_and_verification():
    a, b = hash_password("Correct-Horse-9!", log2_n=10, p=1), hash_password("Correct-Horse-9!", log2_n=10, p=1)
    assert a != b and a.startswith("scrypt$1024$8$1$")
    assert verify_password("Correct-Horse-9!", a) and not verify_password("correct-horse-9!", a)
    assert verify_password("pässwörd-ünïcode-1", hash_password("pässwörd-ünïcode-1", log2_n=10, p=1))


def test_unicode_equivalent_passwords_match():
    assert verify_password("ｐａｓｓｗｏｒｄ-Ｗide-1", hash_password("password-Wide-1", log2_n=10, p=1))   # NFKC


@pytest.mark.parametrize("bad", ["", "plain", "scrypt$x$8$1$AA$AA", "scrypt$1024$8$1$!!$!!", "bcrypt$1$2$3$4$5", "scrypt$4294967296$8$1$AAAA$AAAA", "scrypt$1024$8$99$AAAA$AAAA"])
def test_malformed_or_hostile_stored_hashes_simply_fail(bad):
    assert verify_password("anything-at-all-1", bad) is False


def test_rehash_detection():
    old = hash_password("x" * 12, log2_n=10, p=1)
    assert needs_rehash(old, log2_n=15, p=3) and not needs_rehash(old, log2_n=10, p=1) and needs_rehash("junk", log2_n=10, p=1)
    dummy_verify("whatever", log2_n=10, p=1)    # runs without error


@pytest.mark.parametrize("pw,ok", [
    ("Correct-Horse-9!", True), ("a-long-passphrase-with-words", True), ("short", False), ("x" * 129, False),
    ("Password123", False), ("pass word 123", False), ("Pass word 123 ok!", True), ("1234567890", False), ("1111111111", False),
    ("with\x00nul-byte-12", False), (" padded-pass-123", False),
])
def test_policy(pw, ok):
    try:
        check_policy(pw, email="someone@example.com", full_name="Some One")
        assert ok, pw
    except PasswordError:
        assert not ok, pw


def test_policy_blocks_email_name_and_own_name():
    with pytest.raises(PasswordError):
        check_policy("xx-ramesh-xx-1!", email="ramesh@example.com")
    with pytest.raises(PasswordError):
        check_policy("rameshpatel", full_name="Ramesh Patel")
    check_policy("abc-xyz-123-QQ", email="ab@example.com")     # short local parts are not matched


def test_strength_meter_is_monotone_in_obvious_cases():
    assert strength("") == 0 < strength("abcdefghij") < strength("Abcdefghij1!x") <= strength("Abcdefghij1!x-and-longer-still")
