"""Additive, idempotent database migrations.

This project has never used a migration framework: tables are created on start and a few columns are added in place (db.upgrade_schema).
Payments (2.7.0) add whole new tables, so they get a small recorded migration instead:

  * Nothing existing is altered, renamed, emptied or deleted. A migration may only CREATE tables and indexes.
  * Before the first migration touches an existing SQLite database, a consistent copy of it is written to ``<data dir>/backups`` (SQLite's own
    backup API, safe while the app is running). A fresh database has nothing to protect and gets no copy.
  * Each applied migration is recorded in ``schema_migrations``; running again does nothing.
  * ``protected_counts`` lets a caller (the CLI, the tests) prove that users, orders, products, customers and stock rows are the same
    before and after.

The same function runs on every start, so updating needs no separate step; ``scripts/migrate_db.py`` is the explicit, checkable way to run it.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine

from .db import Base
from . import models

log = logging.getLogger("swara.migrations")

# Tables whose row counts must never change because of a migration.
PROTECTED_TABLES = ("users", "customers", "products", "orders", "order_items", "stock_movements", "sessions", "turns", "api_calls")


@dataclass(frozen=True)
class Migration:
    id: str
    description: str
    apply: Callable[[Engine], None]
    creates: tuple[str, ...]  # tables it creates, for the dry-run report


def _payments(engine: Engine) -> None:
    tables = [models.Payment.__table__, models.PaymentEvent.__table__, models.Refund.__table__, models.Invoice.__table__]
    Base.metadata.create_all(engine, tables=tables)


MIGRATIONS: tuple[Migration, ...] = (
    Migration("2.7.0-payments", "Payments, refunds, invoices and the payment audit trail (new tables and indexes only)", _payments,
              ("payments", "payment_events", "refunds", "invoices")),
)


@dataclass
class Report:
    applied: list[str]
    backup: Optional[Path]
    fresh: bool


def _ensure_ledger(engine: Engine) -> None:
    Base.metadata.create_all(engine, tables=[models.SchemaMigration.__table__])


def applied_ids(engine: Engine) -> set[str]:
    if not inspect(engine).has_table("schema_migrations"):
        return set()
    with engine.connect() as conn:
        return {r[0] for r in conn.execute(select(models.SchemaMigration.id))}


def pending(engine: Engine) -> list[Migration]:
    """Migrations not yet recorded as applied on this database."""
    done = applied_ids(engine)
    return [m for m in MIGRATIONS if m.id not in done]


def needs_changes(engine: Engine) -> list[Migration]:
    """Migrations that would create something (as opposed to only writing their ledger entry)."""
    have = set(inspect(engine).get_table_names())
    done = applied_ids(engine)
    return [m for m in MIGRATIONS if m.id not in done and not set(m.creates) <= have]


def protected_counts(engine: Engine) -> dict[str, int]:
    have = set(inspect(engine).get_table_names())
    out: dict[str, int] = {}
    with engine.connect() as conn:
        for t in PROTECTED_TABLES:
            if t in have:
                out[t] = int(conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() or 0)
    return out


def sqlite_path(engine: Engine) -> Optional[Path]:
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def backup_sqlite(engine: Engine, folder: Path, label: str) -> Optional[Path]:
    """A consistent copy of the SQLite file (the backup API, not a file copy, so a running app and its WAL are handled). None when there is no file."""
    src = sqlite_path(engine)
    if src is None or not src.exists() or src.stat().st_size == 0:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = folder / f"{src.stem}-before-{label}-{stamp}{src.suffix or '.db'}"
    n = 1
    while dest.exists():
        n += 1
        dest = folder / f"{src.stem}-before-{label}-{stamp}-{n}{src.suffix or '.db'}"
    source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return dest


def apply_all(engine: Engine, backup_dir: Optional[Path] = None) -> Report:
    """Apply every migration this database lacks. Safe to call on every start."""
    tables = set(inspect(engine).get_table_names())
    fresh = "orders" not in tables  # nothing of a shop's yet: there is nothing to protect
    todo = needs_changes(engine)
    backup: Optional[Path] = None
    if todo and not fresh and backup_dir is not None:
        backup = backup_sqlite(engine, backup_dir, todo[0].id.split("-")[0])
        if backup:
            log.info("Database copy written before migrating: %s", backup)
    if fresh:  # a new database: build every table in dependency order (payments point at orders), then record the migrations as applied
        Base.metadata.create_all(engine)
    before = protected_counts(engine)
    applied: list[str] = []
    _ensure_ledger(engine)
    done = applied_ids(engine)
    for m in MIGRATIONS:
        if m.id in done:
            continue
        have = set(inspect(engine).get_table_names())
        if not set(m.creates) <= have:
            m.apply(engine)
        with engine.begin() as conn:
            conn.execute(models.SchemaMigration.__table__.insert().values(id=m.id, description=m.description, applied_at=models.utcnow()))
        applied.append(m.id)
        log.info("Migration applied: %s", m.id)
    after = protected_counts(engine)
    if before != after:  # pragma: no cover - a migration that creates tables cannot do this; the check is the guarantee
        raise RuntimeError(f"A migration changed existing rows ({before} -> {after}). Restore the copy in {backup}." if backup else "A migration changed existing rows.")
    return Report(applied=applied, backup=backup, fresh=fresh)
