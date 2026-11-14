"""Accounts: sign up, sign in/out, password reset, e-mail verification, profile, sessions, team (owner)."""
from __future__ import annotations

import hmac
import logging
import re
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth as A
from ..deps import get_db
from ..languages import LANGUAGES
from ..models import AuthSession, User, utcnow
from ..security import auth_rate_limit, client_ip
from ..services import mailer
from ..services.passwords import MAX_LEN, MIN_LEN, PasswordError, check_policy, dummy_verify, hash_password, needs_rehash, verify_password

log = logging.getLogger("swara.auth")
router = APIRouter(prefix="/api/auth", tags=["accounts"])
NAME_RE = re.compile(r"^[^\x00-\x1f\x7f<>]{2,80}$")  # no control characters or angle brackets in a display name
VERIFY_HOURS, RESET_HOURS = 24, 1


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class SignUpIn(Strict):
    full_name: str = Field(max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    confirm_password: Optional[str] = Field(default=None, max_length=256)
    accept_terms: bool = False


class LoginIn(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    remember: bool = False


class EmailIn(Strict):
    email: str = Field(max_length=254)


class TokenIn(Strict):
    token: str = Field(min_length=10, max_length=200)


class ResetIn(Strict):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=256)
    confirm_password: Optional[str] = Field(default=None, max_length=256)


def _known_language(value: str) -> str:
    if value not in LANGUAGES:
        raise ValueError("language must be one of: " + ", ".join(LANGUAGES))
    return value


class ProfileIn(Strict):
    full_name: Optional[str] = Field(default=None, max_length=80)
    language: Optional[Annotated[str, AfterValidator(_known_language)]] = None  # a key from the language registry


class ChangePasswordIn(Strict):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class ActiveIn(Strict):
    active: bool


def _settings(request: Request):
    return request.app.state.settings


def _link(settings, path: str, token: str) -> str:
    return f"{settings.public_url.rstrip('/')}{path}?token={token}"


def _send_link(settings, kind: str, user: User, token: str) -> None:
    """Runs in the background so the answer is as quick for a known address as for an unknown one."""
    path, hours = ("/verify-email", VERIFY_HOURS) if kind == "verify" else ("/reset-password", RESET_HOURS)
    subject, text, html = mailer.link_mail(settings, kind, user.email, user.full_name.split(" ")[0], _link(settings, path, token), hours)
    try:
        mailer.send(settings, user.email, subject, text, html)
        log.info("auth mail sent kind=%s user_id=%s", kind, user.id)
    except mailer.MailError as exc:
        log.warning("auth mail not sent kind=%s user_id=%s reason=%s", kind, user.id, exc)


def _check_new_password(password: str, confirm: Optional[str], email: str, name: str) -> None:
    if confirm is not None and confirm != password:
        raise A.err(422, "PASSWORD_MISMATCH", "The two passwords do not match.")
    try:
        check_policy(password, email=email, full_name=name)
    except PasswordError as exc:
        raise A.err(422, "WEAK_PASSWORD", str(exc)) from exc


def _hash(settings, password: str) -> str:
    return hash_password(password, log2_n=settings.scrypt_log2_n, p=settings.scrypt_p)


def _session_payload(p: A.Principal) -> dict:
    s = p.session
    return {"user": A.public_user(p.user), "csrf_token": s.csrf_token, "session": {"id": s.public_id, "expires_at": A.iso(s.expires_at), "remember": s.remember}}


# ---- public -------------------------------------------------------------------------------------------------------
@router.get("/config")
def config(request: Request, db: Session = Depends(get_db)):
    s = _settings(request)
    has_owner = (db.scalar(select(func.count(User.id)).where(User.role == "owner")) or 0) > 0
    return {
        "signup_open": A.signup_open(db, s), "has_owner": has_owner, "owner_email_set": bool(s.owner_email.strip()), "email_configured": s.smtp_configured,
        "verification_required": s.verification_required, "password": {"min_length": MIN_LEN, "max_length": MAX_LEN},
        "session": {"hours": s.session_hours, "idle_minutes": s.session_idle_minutes, "remember_days": s.remember_days},
    }


@router.post("/signup", status_code=201, dependencies=[Depends(auth_rate_limit)])
def signup(body: SignUpIn, request: Request, response: Response, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    s = _settings(request)
    email = A.normalise_email(body.email)
    name = " ".join(body.full_name.split())
    if not NAME_RE.match(name):
        raise A.err(422, "BAD_NAME", "Enter your full name (2 to 80 characters, no symbols like < or >).")
    if not A.valid_email(email):
        raise A.err(422, "BAD_EMAIL", "Enter a valid e-mail address.")
    if not body.accept_terms:
        raise A.err(422, "TERMS_REQUIRED", "Accept the Terms and Privacy Policy to create an account.")
    _check_new_password(body.password, body.confirm_password, email, name)
    role = A.role_for_new_user(db, s, email)
    if role is None:
        raise A.err(403, "SIGNUP_CLOSED", "Sign-up is closed on this server. Ask the shop owner to add you.")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise A.err(409, "EMAIL_TAKEN", "An account with this e-mail address already exists. Try signing in or resetting the password.")
    now = utcnow()
    user = User(email=email, full_name=name, password_hash=_hash(s, body.password), role=role, terms_accepted_at=now, password_changed_at=now, preferences={})
    db.add(user)
    db.commit()
    log.info("signup user_id=%s role=%s ip=%s", user.id, role, client_ip(request))
    if s.verification_required:
        tasks.add_task(_send_link, s, "verify", user, A.issue_token(db, user, "verify", VERIFY_HOURS))
        return {"verification_required": True, "email": email, "user": None, "csrf_token": None}
    row = A.start_session(db, s, response, user, remember=False, user_agent=request.headers.get("user-agent", ""))
    return {"verification_required": False, "user": A.public_user(user), "csrf_token": row.csrf_token}


@router.post("/login", dependencies=[Depends(auth_rate_limit)])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = _settings(request)
    st = request.app.state
    email = A.normalise_email(body.email)
    ip = client_ip(request)
    wait = max(st.login_by_email.blocked_for(email), st.login_by_ip.blocked_for(ip))
    if wait:
        raise A.err(429, "TOO_MANY_ATTEMPTS", f"Too many failed attempts. Try again in {max(1, round(wait / 60))} minute(s).", retry_after_s=wait)
    user = db.scalar(select(User).where(User.email == email))
    ok = False
    if user is None:
        dummy_verify(body.password, log2_n=s.scrypt_log2_n, p=s.scrypt_p)  # same cost as a real check
    else:
        ok = verify_password(body.password, user.password_hash)
    if not ok:
        st.login_by_email.fail(email)
        st.login_by_ip.fail(ip)
        log.info("login failed ip=%s user_id=%s", ip, user.id if user else None)
        raise A.err(401, "INVALID_CREDENTIALS", "Incorrect e-mail or password.")
    assert user is not None
    if not user.is_active:
        raise A.err(403, "ACCOUNT_DISABLED", "This account has been turned off. Ask the shop owner.")
    if s.verification_required and user.email_verified_at is None:
        raise A.err(403, "EMAIL_NOT_VERIFIED", "Confirm your e-mail address first. Check your inbox for the link.", email=email)
    st.login_by_email.clear(email)
    if needs_rehash(user.password_hash, log2_n=s.scrypt_log2_n, p=s.scrypt_p):
        user.password_hash = _hash(s, body.password)
    row = A.start_session(db, s, response, user, remember=body.remember, user_agent=request.headers.get("user-agent", ""))
    log.info("login ok user_id=%s session=%s", user.id, row.public_id)
    return {"user": A.public_user(user), "csrf_token": row.csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    s = _settings(request)
    p = A.principal_from_cookie(request, db)
    if p is not None:
        # A forged cross-site logout is only a nuisance, but keep the rule uniform: sessions need the CSRF header.
        given = request.headers.get("x-csrf-token", "")
        if not given or not hmac.compare_digest(given.encode(), p.session.csrf_token.encode()):
            raise A.err(403, "CSRF_FAILED", "This request could not be verified. Reload the page and try again.")
        p.session.revoked_at = utcnow()
        db.commit()
        log.info("logout user_id=%s", p.user.id)
    A.clear_cookie(s, response)
    return {"ok": True}


@router.post("/forgot", dependencies=[Depends(auth_rate_limit)])
def forgot(body: EmailIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Always answers the same way, so it cannot be used to find out who has an account."""
    s = _settings(request)
    email = A.normalise_email(body.email)
    tracker = request.app.state.forgot_by_email
    if s.smtp_configured and A.valid_email(email) and not tracker.blocked_for(email):
        tracker.fail(email)
        user = db.scalar(select(User).where(User.email == email))
        if user is not None and user.is_active:
            tasks.add_task(_send_link, s, "reset", user, A.issue_token(db, user, "reset", RESET_HOURS))
    msg = ("If that address has an account, a reset link is on its way. It works once and expires in 1 hour."
           if s.smtp_configured else
           "This server is not set up to send e-mail, so no link was sent. Ask the shop owner to reset the password.")
    return {"email_configured": s.smtp_configured, "message": msg}


@router.post("/reset", dependencies=[Depends(auth_rate_limit)])
def reset(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    s = _settings(request)
    user = A.consume_token(db, body.token, "reset")
    if user is None:
        raise A.err(400, "INVALID_TOKEN", "This link is invalid or has expired. Request a new one.")
    try:
        _check_new_password(body.password, body.confirm_password, user.email, user.full_name)
    except Exception:
        db.rollback()  # a weak password must not use up the link
        raise
    user.password_hash = _hash(s, body.password)
    user.password_changed_at = utcnow()
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()  # they received mail at this address
    revoked = A.revoke_all(db, user.id)
    db.commit()
    request.app.state.login_by_email.clear(user.email)
    log.info("password reset user_id=%s sessions_revoked=%s", user.id, revoked)
    return {"ok": True}


@router.post("/verify-email", dependencies=[Depends(auth_rate_limit)])
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    user = A.consume_token(db, body.token, "verify")
    if user is None:
        raise A.err(400, "INVALID_TOKEN", "This link is invalid or has expired. Request a new one from the sign-in page.")
    user.email_verified_at = user.email_verified_at or utcnow()
    db.commit()
    return {"ok": True}


@router.post("/resend-verification", dependencies=[Depends(auth_rate_limit)])
def resend_verification(body: EmailIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    s = _settings(request)
    email = A.normalise_email(body.email)
    tracker = request.app.state.forgot_by_email
    if s.verification_required and A.valid_email(email) and not tracker.blocked_for("v:" + email):
        tracker.fail("v:" + email)
        user = db.scalar(select(User).where(User.email == email))
        if user is not None and user.is_active and user.email_verified_at is None:
            tasks.add_task(_send_link, s, "verify", user, A.issue_token(db, user, "verify", VERIFY_HOURS))
    return {"ok": True, "message": "If that address is waiting to be confirmed, a new link is on its way."}


# ---- signed in ----------------------------------------------------------------------------------------------------
@router.get("/session")
def soft_session(request: Request, db: Session = Depends(get_db)):
    """What the web app asks on every page load. Unlike /me it answers 200 for a visitor, so a signed-out landing page
    does not fill the browser console with 401 errors."""
    p = A.principal_from_cookie(request, db)
    return {"authenticated": False} if p is None else {"authenticated": True, **_session_payload(p)}


@router.get("/me")
def me(p: A.Principal = Depends(A.require_user)):
    return _session_payload(p)


@router.patch("/profile")
def update_profile(body: ProfileIn, p: A.Principal = Depends(A.require_user), db: Session = Depends(get_db)):
    u = p.user
    if body.full_name is not None:
        name = " ".join(body.full_name.split())
        if not NAME_RE.match(name):
            raise A.err(422, "BAD_NAME", "Enter your full name (2 to 80 characters, no symbols like < or >).")
        u.full_name = name
    if body.language is not None:
        u.preferences = {**(u.preferences or {}), "language": body.language}
    db.commit()
    return {"user": A.public_user(u)}


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request, p: A.Principal = Depends(A.require_user), db: Session = Depends(get_db)):
    s = _settings(request)
    u = p.user
    tracker = request.app.state.login_by_email
    wait = tracker.blocked_for(u.email)
    if wait:
        raise A.err(429, "TOO_MANY_ATTEMPTS", f"Too many failed attempts. Try again in {max(1, round(wait / 60))} minute(s).", retry_after_s=wait)
    if not verify_password(body.current_password, u.password_hash):
        tracker.fail(u.email)
        raise A.err(403, "WRONG_PASSWORD", "The current password is not correct.")
    if body.new_password == body.current_password:
        raise A.err(422, "SAME_PASSWORD", "Choose a password you have not just used.")
    _check_new_password(body.new_password, None, u.email, u.full_name)
    u.password_hash = _hash(s, body.new_password)
    u.password_changed_at = utcnow()
    others = A.revoke_all(db, u.id, except_id=p.session.id)  # a stolen session must not survive a password change
    db.commit()
    tracker.clear(u.email)
    log.info("password changed user_id=%s other_sessions_revoked=%s", u.id, others)
    return {"ok": True, "other_sessions_signed_out": others}


def _describe_agent(ua: str) -> str:
    u = ua or ""
    browser = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if k in u), "Unknown browser")
    system = next((n for k, n in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Mac OS X", "macOS"), ("Linux", "Linux")) if k in u), "unknown system")
    return f"{browser} on {system}"


@router.get("/sessions")
def list_sessions(p: A.Principal = Depends(A.require_user), db: Session = Depends(get_db)):
    now = utcnow()
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == p.user.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now).order_by(AuthSession.last_seen_at.desc()))
    return [{"id": r.public_id, "device": _describe_agent(r.user_agent), "created_at": A.iso(r.created_at), "last_seen_at": A.iso(r.last_seen_at),
             "expires_at": A.iso(r.expires_at), "remember": r.remember, "current": r.id == p.session.id} for r in rows]


@router.post("/sessions/revoke-others")
def revoke_others(p: A.Principal = Depends(A.require_user), db: Session = Depends(get_db)):
    n = A.revoke_all(db, p.user.id, except_id=p.session.id)
    db.commit()
    return {"signed_out": n}


@router.delete("/sessions/{public_id}")
def revoke_session(public_id: str, request: Request, response: Response, p: A.Principal = Depends(A.require_user), db: Session = Depends(get_db)):
    row = db.scalar(select(AuthSession).where(AuthSession.public_id == public_id, AuthSession.user_id == p.user.id))  # only your own
    if row is None or row.revoked_at is not None:
        raise A.err(404, "NOT_FOUND", "That session is not active.")
    row.revoked_at = utcnow()
    db.commit()
    if row.id == p.session.id:
        A.clear_cookie(_settings(request), response)
    return {"ok": True, "current": row.id == p.session.id}


# ---- owner: team ---------------------------------------------------------------------------------------------------
@router.get("/users")
def list_users(_: A.Principal = Depends(A.require_owner), db: Session = Depends(get_db)):
    return [A.public_user(u) | {"is_active": u.is_active} for u in db.scalars(select(User).order_by(User.created_at))]


@router.post("/users/{user_id}/active")
def set_user_active(user_id: int, body: ActiveIn, p: A.Principal = Depends(A.require_owner), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise A.err(404, "NOT_FOUND", "No such account.")
    if u.id == p.user.id:
        raise A.err(422, "SELF_CHANGE", "You cannot turn off your own account.")
    if u.role == "owner":
        raise A.err(422, "OWNER_PROTECTED", "The owner account cannot be turned off here.")
    u.is_active = body.active
    if not body.active:
        A.revoke_all(db, u.id)
    db.commit()
    log.info("account %s by owner_id=%s target=%s", "enabled" if body.active else "disabled", p.user.id, u.id)
    return A.public_user(u) | {"is_active": u.is_active}
