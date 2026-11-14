from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.main import create_app
from app.nlu.lexicon import Lexicon
from app.seed import seed_products
from .helpers import OWNER, STAFF, AuthedClient, register
from .payment_helpers import KEY_ID, KEY_SECRET, WEBHOOK_SECRET, FakeRazorpay
from app.services.catalog import load_views


@pytest.fixture
def make_app(tmp_path):
    """Factory for isolated apps (own SQLite file, no .env, no real Gnani key unless asked)."""

    def _make(**overrides):
        cfg = dict(
            database_url=f"sqlite:///{tmp_path / 'test.db'}", data_dir=tmp_path, gnani_api_key=None,
            rate_limit_per_minute=100000, auth_rate_per_minute=100000, scrypt_log2_n=10, scrypt_p=1, gnani_max_calls_per_hour=1000, seed_on_startup=True,
            demo_history_days=30,   # the long default makes every test seed ~4x the rows; tests that need more history ask for it
        )
        cfg.update(overrides)
        return create_app(Settings(_env_file=None, **cfg))

    return _make


@pytest.fixture
def client(make_app):
    """Signed in as the shop owner (the first account on a fresh database)."""
    with AuthedClient(make_app()) as c:
        yield c


@pytest.fixture
def anon(make_app):
    """Nobody signed in."""
    with TestClient(make_app()) as c:
        yield c


@pytest.fixture
def staff(make_app):
    """Signed in as a staff member; the owner account exists but is not signed in on this client."""
    with TestClient(make_app()) as c:
        assert register(c).status_code == 201
        c.cookies.clear()
        c.headers.pop("X-CSRF-Token", None)
        assert register(c, STAFF).status_code == 201
        yield c


@pytest.fixture(scope="session")
def catalog_views(tmp_path_factory):
    d = tmp_path_factory.mktemp("lex")
    eng = make_engine(f"sqlite:///{d / 'lex.db'}")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as db:
        seed_products(db)
        db.commit()
        views = load_views(db)
    eng.dispose()
    return views


@pytest.fixture(scope="session")
def lexicon(catalog_views):
    return Lexicon(list(catalog_views.values()))


@pytest.fixture(scope="session")
def sku_by_id(catalog_views):
    return {pid: v.sku for pid, v in catalog_views.items()}


@pytest.fixture
def fake_rzp():
    return FakeRazorpay()


@pytest.fixture
def make_pay_app(tmp_path, fake_rzp, monkeypatch):
    """Factory for apps with Razorpay switched on in TEST mode against FakeRazorpay (no network). Pass razorpay_key_id="" etc. to switch it off."""
    monkeypatch.setattr("app.routers.settings.ENV_FILE", tmp_path / ".env")  # a UPI ID saved from Settings must never touch the real .env

    def _make(**overrides):
        cfg = dict(
            database_url=f"sqlite:///{tmp_path / 'test.db'}", data_dir=tmp_path, gnani_api_key=None, rate_limit_per_minute=100000, auth_rate_per_minute=100000,
            scrypt_log2_n=10, scrypt_p=1, gnani_max_calls_per_hour=1000, seed_on_startup=True, demo_history_days=30,
            razorpay_key_id=KEY_ID, razorpay_key_secret=KEY_SECRET, razorpay_webhook_secret=WEBHOOK_SECRET, payment_mode="test",
        )
        cfg.update(overrides)
        return create_app(Settings(_env_file=None, **cfg), razorpay_transport=fake_rzp.transport)

    return _make


@pytest.fixture
def pc(make_pay_app):
    """Owner and staff accounts exist; the client is signed in as the OWNER. Razorpay is on (test mode, fake provider). Use as_staff(pc) / as_owner(pc) to switch."""
    with TestClient(make_pay_app()) as c:
        assert register(c, OWNER).status_code == 201
        c.cookies.clear()
        c.headers.pop("X-CSRF-Token", None)
        assert register(c, STAFF).status_code == 201
        c.cookies.clear()
        c.headers.pop("X-CSRF-Token", None)
        from .helpers import login
        assert login(c, OWNER).status_code == 200
        yield c
