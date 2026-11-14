"""Security helpers: in-memory rate limiters, response headers (CSP etc.), cross-site request guard, input guards."""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

AUDIO_ID_RE = re.compile(r"^[a-f0-9]{32}$")


class RateLimiter:
    """Sliding-window limiter keyed by client IP (single process: fine for one shop on one machine, see docs/DEPLOYMENT.md)."""

    MAX_KEYS = 20000

    def __init__(self, per_window: int, window_s: float = 60):
        self.per_minute = per_window  # name kept: the settings page and tests read it
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _gc(self, now: float) -> None:
        if len(self._hits) > self.MAX_KEYS:
            for k in [k for k, q in self._hits.items() if not q or now - q[-1] > self.window_s]:
                del self._hits[k]
            if len(self._hits) > self.MAX_KEYS:
                self._hits.clear()

    def hit(self, key: str, message: str = "Too many requests. Please slow down.") -> None:
        now = time.monotonic()
        self._gc(now)
        q = self._hits[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.per_minute:
            retry = max(1, int(self.window_s - (now - q[0])) + 1)
            raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": message, "retry_after_s": retry},
                                headers={"Retry-After": str(retry)})
        q.append(now)


class FailureTracker:
    """Counts failures per key inside a window. Used so repeated wrong passwords are slowed down the same way
    whether or not the e-mail address belongs to an account (no way to tell accounts apart by being blocked)."""

    MAX_KEYS = 20000

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window_s = limit, window_s
        self._f: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque:
        q = self._f[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        if not q:
            self._f.pop(key, None)
            if len(self._f) > self.MAX_KEYS:
                self._f.clear()
            return deque()
        return q

    def blocked_for(self, key: str) -> int:
        """Seconds until the key may try again, 0 when it is not blocked."""
        now = time.monotonic()
        q = self._prune(key, now)
        return max(1, int(self.window_s - (now - q[0])) + 1) if len(q) >= self.limit else 0

    def fail(self, key: str) -> None:
        now = time.monotonic()
        self._prune(key, now)
        self._f[key].append(now)

    def clear(self, key: str) -> None:
        self._f.pop(key, None)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    request.app.state.limiter.hit(client_ip(request))


def auth_rate_limit(request: Request) -> None:
    """Separate, stricter bucket for sign-in, sign-up, password reset and the contact form."""
    request.app.state.auth_limiter.hit(client_ip(request), "Too many attempts from this device. Wait a minute and try again.")


UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginGuard(BaseHTTPMiddleware):
    """Refuse state-changing API calls that a browser says came from another site. A request with no Origin header
    (curl, scripts, tests) is not a browser cross-site request and is judged by the session and CSRF token instead."""

    async def dispatch(self, request, call_next):
        if request.method in UNSAFE and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin != "null":
                allowed = set(request.app.state.settings.cors_list)
                if urlparse(origin).netloc != request.headers.get("host", "") and origin not in allowed:
                    return JSONResponse({"detail": {"code": "BAD_ORIGIN", "message": "This request came from another website and was refused."}}, status_code=403)
            elif origin == "null":
                return JSONResponse({"detail": {"code": "BAD_ORIGIN", "message": "This request came from another website and was refused."}}, status_code=403)
        return await call_next(request)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        # Razorpay Checkout (a payment window from checkout.razorpay.com) is allowed ONLY while Razorpay is switched on in .env. Otherwise nothing
        # outside this site may run scripts, open frames or take payments, exactly as in 2.6.0.
        rzp = bool(getattr(request.app.state.settings, "razorpay_enabled", False))
        h.setdefault("Permissions-Policy", "microphone=(self), camera=(), geolocation=(), payment=(self \"https://checkout.razorpay.com\" \"https://api.razorpay.com\"), usb=()" if rzp
                     else "microphone=(self), camera=(), geolocation=(), payment=(), usb=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups" if rzp else "same-origin")
        path = request.url.path
        if path.startswith("/api/") and "audio" not in path:
            h.setdefault("Cache-Control", "no-store")
        if request.app.state.settings.secure_cookies:
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        if "text/html" in h.get("content-type", ""):
            host = request.headers.get("host", "")
            h.setdefault("Content-Security-Policy", csp(host, razorpay=rzp))
        return resp


RAZORPAY_SCRIPT = "https://checkout.razorpay.com"
RAZORPAY_FRAMES = "https://api.razorpay.com https://checkout.razorpay.com"
RAZORPAY_CONNECT = "https://api.razorpay.com https://lumberjack.razorpay.com https://checkout.razorpay.com"
RAZORPAY_IMG = "https://*.razorpay.com https://rzp.io"


def csp(host: str, razorpay: bool = False) -> str:
    """Policy for the built web app. No inline scripts; inline styles are allowed because React sets style attributes. With ``razorpay`` the few
    Razorpay addresses Checkout needs are added to script, frame, connect and image sources, and nothing else changes."""
    ws = f"ws://{host} wss://{host}" if host else ""
    return "; ".join([
        "default-src 'self'", "script-src 'self'" + (f" {RAZORPAY_SCRIPT}" if razorpay else ""), "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:" + (f" {RAZORPAY_IMG}" if razorpay else ""),
        "font-src 'self' data:", f"connect-src 'self' {ws}{' ' + RAZORPAY_CONNECT if razorpay else ''}".strip(), "media-src 'self' blob: data:", "object-src 'none'",
        "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'", "manifest-src 'self'",
    ] + ([f"frame-src {RAZORPAY_FRAMES}"] if razorpay else []))


def mask_key(key: str | None) -> str | None:
    if not key:
        return None
    return f"{'•' * 8}{key[-4:]}" if len(key) > 8 else "••••"


class RedactTokens(logging.Filter):
    """Keep one-time links out of the server log.

    The e-mail links look like /reset-password?token=... . The server's access log would write that whole address, and anyone who can read the log
    could use an unused link until it expires. This replaces the value, in place, before the line is written."""

    PATTERN = re.compile(r"(token=)[^&\s\"']+", re.I)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self.PATTERN.sub(r"\1[redacted]", a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = self.PATTERN.sub(r"\1[redacted]", record.msg)
        return True


def install_log_redaction() -> None:
    """Attach the filter to the access logger once (create_app may run many times, for instance in tests)."""
    log = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactTokens) for f in log.filters):
        log.addFilter(RedactTokens())
