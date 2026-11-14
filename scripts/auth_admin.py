"""Account administration from the command line, for when the web app cannot do it (no e-mail set up, locked out, first install).

    python scripts/auth_admin.py list
    python scripts/auth_admin.py create-owner --email you@example.com --name "Your Name"
    python scripts/auth_admin.py create-staff --email counter@example.com --name "Counter Staff"   (needed when ALLOW_SIGNUP=false)
    python scripts/auth_admin.py reset-password --email you@example.com
    python scripts/auth_admin.py set-active --email staff@example.com --off
    python scripts/auth_admin.py sign-out-all --email you@example.com
    python scripts/auth_admin.py test-mail --to you@example.com        (sends one real message with the SMTP_* settings from .env)

Passwords are asked for on the terminal (not echoed) or taken from the SWARA_NEW_PASSWORD environment variable; they are never
printed and are not accepted as command-line arguments, because those end up in shell history.
"""
from __future__ import annotations

import argparse
import contextlib
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402,F401
from app.auth import normalise_email, revoke_all, valid_email  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Base, make_engine, make_session_factory  # noqa: E402
from app.models import User, utcnow  # noqa: E402
from app.routers.auth import NAME_RE  # noqa: E402
from app.services.passwords import PasswordError, check_policy, hash_password  # noqa: E402


def ask_password(email: str, name: str, *, confirm: bool = True) -> str:
    pw = os.environ.get("SWARA_NEW_PASSWORD") or getpass.getpass("New password: ")
    if confirm and not os.environ.get("SWARA_NEW_PASSWORD") and getpass.getpass("Repeat it: ") != pw:
        raise SystemExit("The two passwords differ. Nothing was changed.")
    try:
        check_policy(pw, email=email, full_name=name)
    except PasswordError as exc:
        raise SystemExit(f"{exc} Nothing was changed.") from exc
    return pw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SWARA AI account administration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show every account (no secrets)")
    c = sub.add_parser("create-owner", help="create the shop owner account")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    st = sub.add_parser("create-staff", help="create a staff account (the way to add people when sign-up is closed with ALLOW_SIGNUP=false)")
    st.add_argument("--email", required=True)
    st.add_argument("--name", required=True)
    r = sub.add_parser("reset-password", help="set a new password and sign the person out everywhere")
    r.add_argument("--email", required=True)
    a = sub.add_parser("set-active", help="turn an account on or off")
    a.add_argument("--email", required=True)
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--on", action="store_true")
    g.add_argument("--off", action="store_true")
    m = sub.add_parser("test-mail", help="send one test message with the SMTP settings in .env, to check they work")
    m.add_argument("--to", required=True)
    o = sub.add_parser("sign-out-all", help="end every session of one person")
    o.add_argument("--email", required=True)
    args = ap.parse_args(argv)

    s = Settings()
    if args.cmd == "test-mail":
        from app.services import mailer
        if not valid_email(normalise_email(args.to)):
            raise SystemExit("That e-mail address does not look valid.")
        if not s.smtp_configured:
            raise SystemExit("E-mail is not set up: SMTP_HOST and SMTP_FROM are both needed in .env. Nothing was sent.")
        try:
            mailer.send(s, normalise_email(args.to), "SWARA AI test message",
                        "This is a test message from SWARA AI. If you can read it, your SMTP settings work.")
        except mailer.MailError as exc:
            raise SystemExit(f"Not sent: {exc} (the server log has the error type; passwords are never printed)") from exc
        print(f"Test message handed to {s.smtp_host}:{s.smtp_port} for {normalise_email(args.to)}. Check the inbox (and spam).")
        return 0
    s.data_dir.mkdir(parents=True, exist_ok=True)
    eng = make_engine(s.database_url)
    Base.metadata.create_all(eng)
    with contextlib.ExitStack() as stack:
        stack.callback(eng.dispose)        # release the database file when the command ends (the session closes first)
        db = stack.enter_context(make_session_factory(eng)())
        if args.cmd == "list":
            users = list(db.scalars(select(User).order_by(User.created_at)))
            if not users:
                print("No accounts yet. The first person to sign up in the app becomes the owner.")
            for u in users:
                print(f"{u.id:>3}  {u.role:<5}  {'on ' if u.is_active else 'OFF'}  {u.email}  ({u.full_name})  last sign-in: {u.last_login_at or 'never'}")
            return 0
        email = normalise_email(args.email)
        u = db.scalar(select(User).where(User.email == email))
        if args.cmd in ("create-owner", "create-staff"):
            role = "owner" if args.cmd == "create-owner" else "staff"
            if not valid_email(email):
                raise SystemExit("That e-mail address does not look valid.")
            if u is not None:
                raise SystemExit("An account with that e-mail already exists. Use reset-password instead.")
            has_owner = db.scalar(select(User).where(User.role == "owner")) is not None
            if role == "owner" and has_owner:
                raise SystemExit("An owner already exists. Only one owner is supported.")
            if role == "staff" and not has_owner:
                raise SystemExit("There is no owner yet. Create the owner first (create-owner).")
            name = " ".join(args.name.split())
            if not NAME_RE.match(name):
                raise SystemExit("Enter a full name of 2 to 80 characters, without symbols like < or >.")
            pw = ask_password(email, name)
            now = utcnow()
            db.add(User(email=email, full_name=name, role=role, terms_accepted_at=now, password_changed_at=now,
                        password_hash=hash_password(pw, log2_n=s.scrypt_log2_n, p=s.scrypt_p), preferences={}))
            db.commit()
            print(f"{role.capitalize()} account created for {email}.")
            return 0
        if u is None:
            raise SystemExit("No account has that e-mail address (run `list` to see them).")
        if args.cmd == "reset-password":
            u.password_hash = hash_password(ask_password(email, u.full_name), log2_n=s.scrypt_log2_n, p=s.scrypt_p)
            u.password_changed_at = utcnow()
            n = revoke_all(db, u.id)
            db.commit()
            print(f"Password changed for {email}; {n} session(s) ended.")
        elif args.cmd == "set-active":
            if u.role == "owner" and args.off:
                raise SystemExit("The owner account cannot be turned off.")
            u.is_active = bool(args.on)
            if args.off:
                revoke_all(db, u.id)
            db.commit()
            print(f"{email} is now {'on' if args.on else 'off'}.")
        elif args.cmd == "sign-out-all":
            n = revoke_all(db, u.id)
            db.commit()
            print(f"{n} session(s) ended for {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
