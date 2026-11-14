"""Check or apply the database changes of this release (payments, refunds, invoices) without starting the app.

    python scripts/migrate_db.py                 show what would change and the row counts that must stay the same (changes nothing)
    python scripts/migrate_db.py --apply         copy the database to backups/, add the new tables, then prove the counts did not change
    python scripts/migrate_db.py --database PATH use another SQLite file instead of the one in .env / the default

The app runs the same migration on every start, so this command is optional: use it to see exactly what will happen first, or to migrate a copy.
Nothing existing is altered, renamed, emptied or deleted: a migration here only CREATES tables and indexes. The .env file is read, never written.
Exit code: 0 = nothing to do or done, 1 = changes are pending (without --apply), 2 = something went wrong.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import inspect  # noqa: E402

from app import migrations, models  # noqa: E402,F401
from app.config import Settings  # noqa: E402
from app.db import make_engine  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SWARA AI database migration (check or apply)")
    ap.add_argument("--apply", action="store_true", help="back up, then migrate (default is a dry run that changes nothing)")
    ap.add_argument("--database", help="path to a SQLite file to use instead of DATABASE_URL")
    ap.add_argument("--backup-dir", help="where the copy goes (default: <data dir>/backups)")
    args = ap.parse_args(argv)

    s = Settings()
    url = f"sqlite:///{Path(args.database).resolve().as_posix()}" if args.database else s.database_url
    engine = make_engine(url)
    try:
        path = migrations.sqlite_path(engine)
        if path is not None and not path.exists():
            print(f"No database at {path} yet. Nothing to migrate: the app creates a new one on first start.")
            return 0
        have = set(inspect(engine).get_table_names())
        fresh = "orders" not in have
        todo = migrations.needs_changes(engine)
        counts = migrations.protected_counts(engine)
        print(f"Database: {path or engine.url.render_as_string(hide_password=True)}")
        print("Rows that must not change: " + (", ".join(f"{t}={n}" for t, n in counts.items()) or "none (new database)"))
        if not todo:
            print("Already up to date. Nothing to do.")
            return 0
        for m in todo:
            print(f"Pending: {m.id} - {m.description}")
            print("         creates: " + ", ".join(t for t in m.creates if t not in have))
        if not args.apply:
            print("\nDry run: nothing was changed. Run again with --apply to back up and migrate.")
            return 1
        backup_dir = Path(args.backup_dir) if args.backup_dir else s.data_dir / "backups"
        report = migrations.apply_all(engine, backup_dir)
        after = migrations.protected_counts(engine)
        if report.backup:
            print(f"Backup written: {report.backup}")
        elif fresh:
            print("New database: nothing to back up.")
        print("Applied: " + ", ".join(report.applied))
        print("Rows after: " + ", ".join(f"{t}={n}" for t, n in after.items()))
        if after != counts and not fresh:
            print("ERROR: row counts changed. Restore the backup above and report this.", file=sys.stderr)
            return 2
        print("Done. Existing users, orders, customers and stock are unchanged.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
