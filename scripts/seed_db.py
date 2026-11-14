"""Create tables and load the synthetic demo data.   python scripts/seed_db.py [--reset]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import Settings  # noqa: E402
from app.db import Base, make_engine, make_session_factory  # noqa: E402
from app import models  # noqa: E402,F401
from app.seed import seed_all  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop all tables first (DELETES local data)")
    a = ap.parse_args()
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    eng = make_engine(s.database_url)
    if a.reset:
        Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as db:
        print(seed_all(db, history_days=s.demo_history_days))
    print("database ready:", s.database_url)


if __name__ == "__main__":
    main()
