"""Order integrity: a repeated Confirm must not make a second order, and the last unit can only be sold once."""
from __future__ import annotations

import threading
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Order, Product, StockMovement
from app.nlu.dialogue import CartLine
from app.services import orders as order_svc
from app.services.catalog import load_views


def _open_bill(client, text="2 kilo chawal"):
    r = client.post("/api/text/turn", json={"text": text}).json()
    sid = r["session_id"]
    client.post("/api/text/turn", json={"text": "bas itna hi", "session_id": sid})
    return sid


def _stock(client, pid):
    return float(next(i for i in client.get("/api/inventory", params={"page_size": 100}).json()["items"] if i["id"] == pid)["stock"])


def _orders(client):
    return client.get("/api/orders", params={"page_size": 100}).json()


def test_pressing_confirm_twice_makes_one_order_and_takes_stock_once(client):
    sid = _open_bill(client)
    before = _orders(client)["total"]
    first = client.post(f"/api/sessions/{sid}/confirm").json()
    assert first["order"] is not None
    item = first["order"]["items"][0]
    stock_after_first = _stock(client, item["product_id"])
    second = client.post(f"/api/sessions/{sid}/confirm").json()
    assert second["order"] is None or second["order"]["id"] == first["order"]["id"]
    assert _orders(client)["total"] == before + 1
    assert _stock(client, item["product_id"]) == stock_after_first


def test_saying_yes_again_after_the_order_is_saved_does_not_repeat_it(client):
    sid = _open_bill(client)
    done = client.post("/api/text/turn", json={"text": "haan", "session_id": sid}).json()
    assert done["order"] is not None
    count = _orders(client)["total"]
    client.post("/api/text/turn", json={"text": "haan", "session_id": sid})
    client.post("/api/text/turn", json={"text": "confirm", "session_id": sid})
    assert _orders(client)["total"] == count


def test_two_buyers_cannot_both_take_the_last_unit(make_app):
    """Two threads, two database sessions, one unit on the shelf: exactly one order is saved and stock never goes below zero."""
    app = make_app()
    from fastapi.testclient import TestClient  # noqa: F401  (app startup seeds the catalogue)
    with TestClient(app):
        factory = app.state.session_factory
        with factory() as db:
            views = load_views(db)
            pid = next(iter(views))
            p = db.get(Product, pid)
            p.stock = Decimal("1")
            db.commit()
            views = load_views(db)
        results: list[str] = []
        gate = threading.Barrier(2)

        def buy():
            with factory() as db:
                gate.wait()
                try:
                    order_svc.create_order(db, [CartLine(product_id=pid, qty=Decimal("1"))], views, session_id=None, channel="text", language="en")
                    results.append("ok")
                except order_svc.InsufficientStock:
                    results.append("short")

        threads = [threading.Thread(target=buy) for _ in range(2)]
        [t.start() for t in threads]
        [t.join(timeout=30) for t in threads]
        assert sorted(results) == ["ok", "short"]
        with factory() as db:
            assert Decimal(db.scalar(select(Product.stock).where(Product.id == pid))) == 0
            assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.product_id == pid, StockMovement.reason == "order")) == 1
            assert db.scalar(select(func.count()).select_from(Order).where(Order.is_synthetic.is_(False))) == 1


def test_two_simultaneous_confirm_presses_on_one_bill_make_one_order(client):
    """The confirm handler runs its database work on the single event loop, so two presses are handled one after the other.

    This guarantee holds for the supported one-process deployment; docs/SECURITY.md notes what a multi-worker setup would need."""
    for _ in range(5):
        sid = _open_bill(client, "1 kilo chawal")
        before = _orders(client)["total"]
        gate = threading.Barrier(2)

        def press():
            gate.wait()
            client.post(f"/api/sessions/{sid}/confirm")

        threads = [threading.Thread(target=press) for _ in range(2)]
        [t.start() for t in threads]
        [t.join(timeout=30) for t in threads]
        assert _orders(client)["total"] == before + 1
