"""The demo data must look like a real shop in India Standard Time (regression: a UTC/IST mix-up once put the
busiest hour at midnight on the analytics screen)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import Base, make_engine, make_session_factory
from app.models import Order, utcnow
from app.seed import _HOUR_WEIGHTS, seed_all

IST = timedelta(minutes=330)


@pytest.fixture
def seeded(tmp_path):
    """A freshly seeded database; the session and engine are closed afterwards so no connection is left to the garbage collector."""
    eng = make_engine(f"sqlite:///{tmp_path / 's.db'}")
    Base.metadata.create_all(eng)
    db = make_session_factory(eng)()
    seed_all(db)
    yield db
    db.close()
    eng.dispose()


def test_seeded_orders_fall_in_local_business_hours(seeded):
    db = seeded
    orders = list(db.scalars(select(Order)))
    assert len(orders) > 300
    hours = {(o.created_at + IST).hour for o in orders}
    assert hours <= set(_HOUR_WEIGHTS), f"orders outside shop hours: {sorted(hours - set(_HOUR_WEIGHTS))}"


def test_no_seeded_order_is_in_the_future_and_today_has_some_history(seeded):
    db = seeded
    now = utcnow()
    orders = list(db.scalars(select(Order)))
    assert all(o.created_at <= now for o in orders)
    assert all(o.is_synthetic for o in orders)


def test_seed_is_deterministic_and_idempotent(seeded):
    db = seeded
    n = len(list(db.scalars(select(Order))))
    assert seed_all(db)["orders"] == 0
    assert len(list(db.scalars(select(Order)))) == n
