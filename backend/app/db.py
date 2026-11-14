"""SQLAlchemy engine/session helpers.  SQLite for local use; any SQLAlchemy URL (e.g. PostgreSQL) works."""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _rec):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            if ":memory:" not in url:
                cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


# Columns added after v1.0. SQLite databases created by that version are upgraded in place on startup
# (ALTER TABLE ... ADD COLUMN), so nobody has to delete their data. Other databases should use real migrations.
ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "products": [("brand", "VARCHAR(80) DEFAULT ''"), ("ean", "VARCHAR(14)"), ("source", "VARCHAR(16) DEFAULT 'manual'"),
                 ("source_ref", "VARCHAR(80)"), ("price_basis", "VARCHAR(8) DEFAULT 'shop'"), ("cost_paise", "INTEGER")],
    "orders": [("customer_id", "INTEGER")],
    "sessions": [("customer_id", "INTEGER")],
    "api_calls": [("attempts", "INTEGER DEFAULT 1")],
}


def upgrade_schema(engine: Engine) -> list[str]:
    """Add any missing columns listed in ADDED_COLUMNS. Returns what was added (for logging and tests)."""
    from sqlalchemy import inspect, text

    added: list[str] = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in ADDED_COLUMNS.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols:
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added.append(f"{table}.{name}")
    return added
