"""Payments 2.7.0: the database migration. A database made by 2.6.0 (no payment tables) must come through with every user, order, customer and stock row
untouched, be backed up first, and migrate only once. These tests build a 2.6.0-shaped file by dropping the five new tables from a real database.
The real 2.6.0 program creating the database is checked separately in docs/PAYMENT_TESTING.md (update-in-place run)."""
from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app import migrations
from app.config import Settings
from app.db import make_engine
from app.main import create_app
from .helpers import OWNER, STAFF, login, register
from .payment_helpers import KEY_ID, KEY_SECRET, WEBHOOK_SECRET, new_order

NEW_TABLES = ("payments", "payment_events", "refunds", "invoices", "schema_migrations")
ROOT = Path(__file__).resolve().parents[2]


def settings_for(db_path: Path, **kw) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{db_path}", data_dir=db_path.parent, gnani_api_key=None, rate_limit_per_minute=100000, auth_rate_per_minute=100000,
                    scrypt_log2_n=10, scrypt_p=1, seed_on_startup=True, demo_history_days=30, **kw)


# Signing in legitimately writes last_login_at, so for accounts the check covers everything that identifies a person or lets them in.
USER_COLUMNS = "id, email, full_name, role, password_hash, is_active, email_verified_at, terms_accepted_at, created_at, password_changed_at"


def checksum(db_path: Path) -> dict[str, str]:
    """A hash of every row of every protected table, so 'the same count' cannot hide a changed value."""
    out = {}
    con = sqlite3.connect(db_path)
    try:
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in migrations.PROTECTED_TABLES:
            if t in have:
                cols = USER_COLUMNS if t == "users" else "*"
                rows = con.execute(f"SELECT {cols} FROM {t} ORDER BY 1").fetchall()
                out[t] = f"{len(rows)}:{hashlib.sha256(repr(rows).encode()).hexdigest()}"
    finally:
        con.close()
    return out


def tables(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


@pytest.fixture
def old_db(tmp_path):
    """A database with an owner, a staff member, seeded demo data and two real orders, shaped like 2.6.0 (the payment tables removed)."""
    path = tmp_path / "shop.db"
    with TestClient(create_app(settings_for(path))) as c:
        assert register(c, OWNER).status_code == 201
        new_order(c)
        new_order(c, "1 litre doodh")
        c.cookies.clear(); c.headers.pop("X-CSRF-Token", None)
        assert register(c, STAFF).status_code == 201
    con = sqlite3.connect(path)
    for t in ("refunds", "payment_events", "invoices", "payments", "schema_migrations"):
        con.execute(f"DROP TABLE {t}")
    con.commit()
    con.close()
    assert not set(NEW_TABLES) & tables(path)
    return path


def test_migrating_an_older_database_backs_it_up_adds_the_tables_and_changes_nothing_else(old_db, tmp_path):
    before = checksum(old_db)
    assert before["users"].startswith("2:") and before["orders"].startswith("2:") or int(before["orders"].split(":")[0]) >= 2
    engine = make_engine(f"sqlite:///{old_db}")
    assert [m.id for m in migrations.needs_changes(engine)] == ["2.7.0-payments"]
    backups = tmp_path / "bk"
    report = migrations.apply_all(engine, backups)
    engine.dispose()
    assert report.applied == ["2.7.0-payments"] and report.fresh is False and report.backup is not None and report.backup.parent == backups
    assert set(NEW_TABLES) <= tables(old_db)
    assert checksum(old_db) == before                                                     # every protected row identical, not just the counts
    assert checksum(report.backup) == before and not {"payments", "refunds", "invoices"} & tables(report.backup)   # the copy is the 2.6.0 database
    con = sqlite3.connect(old_db)
    assert con.execute("SELECT id FROM schema_migrations").fetchall() == [("2.7.0-payments",)]
    assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert con.execute("SELECT COUNT(*) FROM payments").fetchone() == (0,)
    con.close()


def test_the_migration_runs_once_and_a_second_start_makes_no_new_backup(old_db, tmp_path):
    engine = make_engine(f"sqlite:///{old_db}")
    first = migrations.apply_all(engine, tmp_path / "bk")
    second = migrations.apply_all(engine, tmp_path / "bk")
    engine.dispose()
    assert first.applied and second.applied == [] and second.backup is None
    assert len(list((tmp_path / "bk").iterdir())) == 1


def test_a_brand_new_database_needs_no_backup_and_gets_every_table(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'new.db'}")
    report = migrations.apply_all(engine, tmp_path / "bk")
    assert report.fresh is True and report.backup is None and not (tmp_path / "bk").exists()
    assert {"orders", "users", "payments", "refunds", "invoices", "payment_events", "schema_migrations"} <= set(inspect(engine).get_table_names())
    assert migrations.apply_all(engine, tmp_path / "bk").applied == []
    engine.dispose()


def test_a_failing_migration_leaves_the_data_alone_is_not_recorded_and_is_tried_again(old_db, tmp_path, monkeypatch):
    before = checksum(old_db)

    def boom(_engine):
        raise RuntimeError("simulated failure part-way")
    failing = migrations.Migration("2.7.0-payments", "x", boom, ("payments",))
    monkeypatch.setattr(migrations, "MIGRATIONS", (failing,))
    engine = make_engine(f"sqlite:///{old_db}")
    with pytest.raises(RuntimeError):
        migrations.apply_all(engine, tmp_path / "bk")
    assert checksum(old_db) == before and migrations.applied_ids(engine) == set()
    assert len(list((tmp_path / "bk").iterdir())) == 1                                   # the copy was made before anything was attempted
    monkeypatch.undo()
    assert migrations.apply_all(engine, tmp_path / "bk").applied == ["2.7.0-payments"]
    engine.dispose()


def test_the_app_starts_on_an_older_database_and_every_existing_account_and_order_still_works(old_db, tmp_path):
    before = checksum(old_db)
    cfg = settings_for(old_db, razorpay_key_id=KEY_ID, razorpay_key_secret=KEY_SECRET, razorpay_webhook_secret=WEBHOOK_SECRET)
    with TestClient(create_app(cfg)) as c:
        assert login(c, OWNER).status_code == 200                                          # the same password still works
        orders = c.get("/api/orders", params={"limit": 100}).json()
        assert orders["total"] >= 2 and all(o["payment"]["status"] == "none" for o in orders["items"])
        assert (old_db.parent / "backups").is_dir() and len(list((old_db.parent / "backups").iterdir())) == 1
        mine = next(o for o in orders["items"] if o["channel"] == "text" and not o["is_synthetic"])
        p = c.post(f"/api/orders/{mine['id']}/payments", json={"method": "cash"}).json()
        paid = c.post(f"/api/payments/{p['id']}/cash", json={"received_paise": mine["total_paise"]}).json()
        assert paid["status"] == "paid" and c.get(f"/api/orders/{mine['id']}/invoice").json()["number"].startswith("INV-")
        assert login(c, STAFF).status_code == 200
    after = checksum(old_db)
    for t in ("users", "customers", "products", "order_items", "stock_movements", "orders"):
        assert after[t] == before[t], t
    with TestClient(create_app(cfg)) as c:                                                  # a second start: nothing is applied again and the payment is still there
        login(c, OWNER)
        assert c.get("/api/payments").json()["total"] == 1
    assert len(list((old_db.parent / "backups").iterdir())) == 1


def test_data_written_after_the_migration_survives_a_restart(tmp_path):
    path = tmp_path / "keep.db"
    cfg = settings_for(path, razorpay_key_id=KEY_ID, razorpay_key_secret=KEY_SECRET, razorpay_webhook_secret=WEBHOOK_SECRET)
    with TestClient(create_app(cfg)) as c:
        register(c, OWNER)
        o = new_order(c)
        p = c.post(f"/api/orders/{o['id']}/payments", json={"method": "cash"}).json()
        c.post(f"/api/payments/{p['id']}/cash", json={"received_paise": o["total_paise"]})
        c.post(f"/api/payments/{p['id']}/refunds", json={"reason": "Customer returned goods", "amount_paise": 100})
        number = c.get(f"/api/orders/{o['id']}/invoice").json()["number"]
    with TestClient(create_app(cfg)) as c:
        login(c, OWNER)
        d = c.get(f"/api/payments/{p['id']}").json()
        assert d["status"] == "partially_refunded" and d["refunded_paise"] == 100 and len(d["events"]) == 4
        assert c.get(f"/api/orders/{o['id']}/invoice").json()["number"] == number


def load_cli():
    spec = importlib.util.spec_from_file_location("migrate_db_cli", ROOT / "scripts" / "migrate_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_command_line_tool_checks_without_changing_then_applies_with_a_backup(old_db, tmp_path, capsys):
    cli = load_cli()
    before = checksum(old_db)
    assert cli.main(["--database", str(old_db), "--backup-dir", str(tmp_path / "bk")]) == 1          # pending changes, dry run
    out = capsys.readouterr().out
    assert "Pending: 2.7.0-payments" in out and "Dry run" in out and "orders=" in out
    assert not {"payments", "refunds"} & tables(old_db) and not (tmp_path / "bk").exists() and checksum(old_db) == before
    assert cli.main(["--database", str(old_db), "--backup-dir", str(tmp_path / "bk"), "--apply"]) == 0
    out = capsys.readouterr().out
    assert "Backup written:" in out and "unchanged" in out and "payments" in tables(old_db) and checksum(old_db) == before
    assert cli.main(["--database", str(old_db), "--backup-dir", str(tmp_path / "bk")]) == 0
    assert "Already up to date" in capsys.readouterr().out
    assert cli.main(["--database", str(tmp_path / "missing.db")]) == 0
    assert "Nothing to migrate" in capsys.readouterr().out


def test_nothing_in_the_migration_can_delete_or_change_existing_data():
    """Reads the migration code: it may only create tables and indexes."""
    src = (ROOT / "backend" / "app" / "migrations.py").read_text(encoding="utf-8").upper()
    for word in ("DROP ", "DELETE ", "TRUNCATE", "ALTER TABLE", "UPDATE "):
        assert word not in src, word
    models_src = (ROOT / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    assert "ondelete=\"CASCADE\"" not in models_src.split("class Payment(")[1]        # a deleted order can never silently delete its money records


def test_the_payment_tables_point_at_orders_without_cascading_deletes(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'fk.db'}")
    migrations.apply_all(engine, None)
    insp = inspect(engine)
    for t in ("payments", "invoices"):
        fks = insp.get_foreign_keys(t)
        assert any(fk["referred_table"] == "orders" for fk in fks)
        assert not any((fk.get("options") or {}).get("ondelete", "").upper() == "CASCADE" for fk in fks)
    idx = {i["name"]: i for i in insp.get_indexes("payments")}
    assert idx["uq_payments_one_pending_per_order"]["unique"] == 1
    with engine.connect() as conn:
        sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='uq_payments_one_pending_per_order'")).scalar()
    assert "WHERE status = 'pending'" in sql
    engine.dispose()
