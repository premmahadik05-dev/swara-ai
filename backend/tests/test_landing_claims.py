"""The Security section of the public page quotes numbers and behaviour. They must be the ones the code really uses.

If someone changes a default in config.py, or removes the check a sentence relies on, this fails until the page is corrected,
so the landing page cannot drift into promising something the server no longer does.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
CONTENT = (ROOT / "frontend" / "src" / "pages" / "landing" / "content.ts").read_text(encoding="utf-8")
APP = ROOT / "backend" / "app"


def _security_text() -> str:
    m = re.search(r"export const SECURITY:.*?\n\]\n", CONTENT, re.S)
    assert m, "SECURITY list not found in content.ts"
    return m.group(0)


def test_numbers_on_the_page_are_the_config_defaults():
    text = _security_text()
    s = Settings(_env_file=None)
    words = {5: "five"}
    assert f"{words[s.login_max_failures]} wrong passwords" in text
    assert f"pauses for {s.login_lockout_minutes} minutes" in text
    assert f"{s.session_hours} hours, or after {s.session_idle_minutes // 60} hours without use" in text


def test_a_normal_session_is_the_one_described_not_the_remember_me_one():
    s = Settings(_env_file=None)
    assert s.session_idle_minutes % 60 == 0 and s.session_hours == 12      # the sentence says "12 hours / 2 hours" without hedging


def test_passwords_really_use_scrypt_and_the_cookie_is_httponly():
    pw = (APP / "services" / "passwords.py").read_text(encoding="utf-8")
    auth = (APP / "auth.py").read_text(encoding="utf-8")
    assert "scrypt" in pw.lower() and "scrypt" in _security_text()
    assert "httponly=True" in auth and "HttpOnly" in _security_text()
    assert "sha256" in auth.lower()                                       # "the server keeps only a hash of it"


def test_password_change_signs_out_other_devices_as_the_page_says():
    router = (APP / "routers" / "auth.py").read_text(encoding="utf-8")
    assert "revoke_all(db, u.id, except_id=p.session.id)" in router
    assert "signs out every other device" in _security_text()


def test_staff_really_cannot_create_edit_or_export_customers():
    src = (APP / "routers" / "customers.py").read_text(encoding="utf-8")
    for route in ('@router.post("", ', '@router.patch("/{customer_id}", ', '@router.get("/export.csv", '):
        line = next(l for l in src.splitlines() if l.startswith(route))
        assert "require_owner" in line, line


def test_the_page_makes_no_claim_it_cannot_back():
    text = _security_text() + CONTENT[CONTENT.index("SECURITY_LIMITS"):]
    assert not re.search(r"SOC ?2|ISO ?27001|GDPR|HIPAA|PCI|certified|bank-grade|military|unhackable|end-to-end|encrypted at rest", text, re.I)
    # and it says so about the things that are not there
    assert "no two-factor" in text and "not had an independent security audit" in text
    assert not list(APP.rglob("*totp*")) and "pyotp" not in (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()
