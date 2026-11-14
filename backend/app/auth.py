"""Sessions, current-user dependencies and the helpers the auth router uses.

How a request is judged:
  * The browser holds one HttpOnly cookie with a random secret. The database holds only its SHA-256.
  * Every route (except health, sign-in/up/reset, the landing-page parser and the contact form) needs a valid session.
  * Writes also need the per-session X-CSRF-Token header (the cookie alone is not enough).
  * Owner-only routes need role == "owner".
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .deps import get_db
from .models import AuthSession, AuthToken, User, utcnow

log = logging.getLogger("swara.auth")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
TOUCH_EVERY = timedelta(seconds=60)  # how often "last seen" is written, to keep reads cheap


def err(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


# ---- small helpers -------------------------------------------------------------------------------------------------
def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    return len(email) <= 254 and bool(EMAIL_RE.match(email))


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def cookie_name(settings: Settings) -> str:
    # The __Host- prefix makes browsers refuse the cookie unless it is Secure, host-only and Path=/ .
    return "__Host-swara_session" if settings.secure_cookies else "swara_session"


def public_user(u: User) -> dict:
    """The only shape in which an account ever leaves the server: no password hash, no tokens."""
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
        "email_verified": u.email_verified_at is not None, "created_at": iso(u.created_at), "last_login_at": iso(u.last_login_at),
        "preferences": u.preferences or {},
    }


def lifetimes(settings: Settings, remember: bool) -> tuple[timedelta, timedelta]:
    if remember:
        return timedelta(days=settings.remember_days), timedelta(days=settings.remember_idle_days)
    return timedelta(hours=settings.session_hours), timedelta(minutes=settings.session_idle_minutes)


# ---- sessions ------------------------------------------------------------------------------------------------------
def start_session(db: Session, settings: Settings, response: Response, user: User, *, remember: bool, user_agent: str) -> AuthSession:
    raw = new_secret()
    absolute, _ = lifetimes(settings, remember)
    now = utcnow()
    row = AuthSession(
        public_id=secrets.token_hex(6), user_id=user.id, token_hash=sha256(raw), csrf_token=new_secret(), remember=remember,
        user_agent=(user_agent or "")[:200], created_at=now, last_seen_at=now, expires_at=now + absolute,
    )
    db.add(row)
    user.last_login_at = now
    db.commit()
    response.set_cookie(
        cookie_name(settings), raw, max_age=int(absolute.total_seconds()) if remember else None, httponly=True,
        samesite="lax", secure=settings.secure_cookies, path="/",
    )
    return row


def clear_cookie(settings: Settings, response: Response) -> None:
    response.delete_cookie(cookie_name(settings), path="/", httponly=True, samesite="lax", secure=settings.secure_cookies)


def revoke_all(db: Session, user_id: int, *, except_id: Optional[int] = None) -> int:
    n = 0
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))):
        if s.id != except_id:
            s.revoked_at = utcnow()
            n += 1
    return n


class Principal:
    __slots__ = ("user", "session")

    def __init__(self, user: User, session: AuthSession):
        self.user, self.session = user, session


def resolve_session(db: Session, settings: Settings, raw: Optional[str]) -> tuple[Optional[Principal], str]:
    """(principal, reason). reason is '' on success, else 'none' | 'expired' | 'invalid'."""
    if not raw:
        return None, "none"
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == sha256(raw)))
    if row is None or row.revoked_at is not None:
        return None, "invalid"
    now = utcnow()
    _, idle = lifetimes(settings, row.remember)
    if row.expires_at <= now or row.last_seen_at + idle <= now:
        row.revoked_at = now
        db.commit()
        return None, "expired"
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        row.revoked_at = now
        db.commit()
        return None, "invalid"
    if now - row.last_seen_at > TOUCH_EVERY:
        row.last_seen_at = now
        db.commit()
    return Principal(user, row), ""


def principal_from_cookie(request: Request, db: Session) -> Optional[Principal]:
    settings = request.app.state.settings
    p, _ = resolve_session(db, settings, request.cookies.get(cookie_name(settings)))
    return p


def require_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    settings = request.app.state.settings
    p, reason = resolve_session(db, settings, request.cookies.get(cookie_name(settings)))
    if p is None:
        if reason == "expired":
            raise err(401, "SESSION_EXPIRED", "Your session has ended. Sign in again to continue.")
        raise err(401, "NOT_AUTHENTICATED", "Sign in to continue.")
    if request.method not in SAFE_METHODS:
        given = request.headers.get("x-csrf-token", "")
        if not given or not hmac.compare_digest(given.encode(), p.session.csrf_token.encode()):
            raise err(403, "CSRF_FAILED", "This request could not be verified. Reload the page and try again.")
    request.state.user_id = p.user.id
    return p


def require_owner(p: Principal = Depends(require_user)) -> Principal:
    if p.user.role != "owner":
        raise err(403, "OWNER_ONLY", "Only the shop owner can do this.")
    return p


# ---- one-time link tokens -----------------------------------------------------------------------------------------
def issue_token(db: Session, user: User, purpose: str, hours: int) -> str:
    """Create a single-use token (and retire older unused ones of the same kind). Returns the raw value for the e-mail."""
    now = utcnow()
    for old in db.scalars(select(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None))):
        old.used_at = now
    raw = new_secret()
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=sha256(raw), expires_at=now + timedelta(hours=hours)))
    db.commit()
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> Optional[User]:
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == sha256(raw or ""), AuthToken.purpose == purpose))
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    row.used_at = now
    return user


# ---- roles ---------------------------------------------------------------------------------------------------------
def role_for_new_user(db: Session, settings: Settings, email: str) -> Optional[str]:
    """'owner', 'staff', or None when sign-up is closed for this address.
    The first account (or the address in OWNER_EMAIL) becomes the owner, even when public sign-up is closed."""
    has_owner = (db.scalar(select(func.count(User.id)).where(User.role == "owner")) or 0) > 0
    if not has_owner:
        owner_email = normalise_email(settings.owner_email)
        if not owner_email or email == owner_email:
            return "owner"
    return "staff" if settings.allow_signup else None


def signup_open(db: Session, settings: Settings) -> bool:
    if settings.allow_signup:
        return True
    has_owner = (db.scalar(select(func.count(User.id)).where(User.role == "owner")) or 0) > 0
    return not has_owner
