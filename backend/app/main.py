"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import brand, models  # noqa: F401  (models: register tables)
from .config import REPO_ROOT, Settings, get_settings
from .db import Base, make_engine, make_session_factory, upgrade_schema
from .gnani.client import GnaniClient
from .auth import require_user
from . import apidocs
from .routers import analytics, auth as auth_router, catalog, contact, customers, diagnostics, evaluation, health, inventory, languages as languages_router, noise, orders, payments as payments_router, search, settings as settings_router, voice, ws
from .security import FailureTracker, OriginGuard, RateLimiter, SecurityHeaders, install_log_redaction
from .seed import seed_all
from .services.catalog import CatalogCache
from .services.payments import PaymentError
from .services.razorpay import RazorpayClient
from . import migrations

VERSION = "2.7.0"


def create_app(settings: Optional[Settings] = None, gnani_transport: Optional[httpx.AsyncBaseTransport] = None,
               razorpay_transport: Optional[httpx.BaseTransport] = None) -> FastAPI:
    settings = settings or get_settings()
    install_log_redaction()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = make_engine(settings.database_url)
        # Versioned, additive changes first (a copy of an existing database is saved beside it before the first one), then the long-standing
        # create_all / upgrade_schema pair, which does nothing for tables and columns that already exist.
        app.state.migration_report = migrations.apply_all(engine, settings.data_dir / "backups")
        Base.metadata.create_all(engine)
        upgrade_schema(engine)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        if settings.seed_on_startup:
            with app.state.session_factory() as db:
                seed_all(db, history_days=settings.demo_history_days)
        yield
        await app.state.gnani.aclose()
        engine.dispose()

    # The built-in /docs and /redoc pages need a CDN and an inline script, which the content-security-policy refuses (blank page). apidocs.py serves
    # the same schema with a local script instead. API_DOCS=false switches the page and /openapi.json off.
    app = FastAPI(
        title=brand.NAME, version=VERSION, lifespan=lifespan, summary=brand.TAGLINE,
        description=f"{brand.DESCRIPTION}\n\nSpeech in and out is provided by Gnani AI Prisma (STT) and Timbre (TTS).",
        docs_url=None, redoc_url=None, openapi_url="/openapi.json" if settings.api_docs else None,
    )
    app.state.settings = settings
    app.state.catalog = CatalogCache()
    app.state.gnani = GnaniClient(settings, transport=gnani_transport)
    app.state.razorpay = RazorpayClient(settings, transport=razorpay_transport)
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.auth_limiter = RateLimiter(settings.auth_rate_per_minute)
    window = settings.login_lockout_minutes * 60
    app.state.login_by_email = FailureTracker(settings.login_max_failures, window)
    app.state.login_by_ip = FailureTracker(settings.login_max_failures * 5, window)
    app.state.forgot_by_email = FailureTracker(3, 15 * 60)

    # Middleware runs last-added first: headers wrap everything, then the cross-site guard, then CORS.
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(OriginGuard)
    app.add_middleware(SecurityHeaders)

    app.add_exception_handler(PaymentError, payments_router.payment_error_handler)

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(_request, exc: StarletteHTTPException):
        detail = exc.detail
        body = {"detail": detail} if isinstance(detail, dict) else {"detail": {"code": f"HTTP_{exc.status_code}", "message": str(detail)}}
        return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    # Open: health, the accounts endpoints (each guards itself), the landing-page parser and the contact form.
    for r in (health.router, auth_router.router, contact.router, voice.public, payments_router.webhooks):  # the webhook has no session: its signature is the credential
        app.include_router(r)
    # Everything else needs a signed-in user (owner-only writes are marked on the individual routes).
    for r in (voice.router, languages_router.router, inventory.router, orders.router, payments_router.router, analytics.router, customers.router, catalog.router,
              search.router, settings_router.router, noise.router, evaluation.router, diagnostics.router):
        app.include_router(r, dependencies=[Depends(require_user)])
    app.include_router(ws.router)  # checks the same session cookie during the handshake
    if settings.api_docs:
        app.include_router(apidocs.router)

    # Serve the built React app from the same port (one-command start on Windows).
    dist = Path(REPO_ROOT / "frontend" / "dist")
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith(("api/", "ws/")):
                raise HTTPException(404, "Not found")
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            # A missing file (a picture, a script, robots.txt) is a 404, not the app: otherwise a broken <img> or <script> quietly
            # receives an HTML page with status 200. Only extension-less paths are app routes handled by the router in the browser.
            if Path(full_path).suffix:
                raise HTTPException(404, "Not found")
            return FileResponse(dist / "index.html")

    return app


app = create_app()
