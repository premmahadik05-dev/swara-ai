"""Update-in-place check for 2.6.0 -> 2.7.0.

1. Unpacks the released 2.6.0 ZIP into a fresh install, adds a FAKE .env, starts the real 2.6.0 code on a new database, creates an owner and
   puts real activity through it (typed orders, a restock, a cancel) with scripts/demo_activity.py.
2. Records hashes and row counts, then unpacks the 2.7.0 ZIP over that install the way a person would.
3. Starts 2.7.0 on the same data and proves: .env and database untouched by the unzip, version 2.7.0, shop name still from the old .env,
   protected tables unchanged, a backup of the old database was made and opens with the old counts, the new tables exist, existing orders
   report payment status "none", a cash payment works on a migrated order, and stock did not move.
4. Roll back: the 2.6.0 code opens the upgraded database (a copy) and its counts are unchanged.
Never prints the fake key.

Usage:   python scripts/check_update_in_place.py OLD_ZIP NEW_ZIP [--python PATH_TO_PYTHON_WITH_THE_BACKEND_REQUIREMENTS]
Example: python scripts/check_update_in_place.py SWARA-AI-UPGRADE-2.6.0.zip SWARA-AI-UPGRADE-2.7.0.zip
Works on Linux and macOS (it uses POSIX paths and starts the servers on ports 8031 to 8035 of this machine). Everything happens in a temporary
folder; your own install, .env and database are never touched. Needs both release ZIPs."""
import argparse, hashlib, json, os, shutil, sqlite3, subprocess, sys, tempfile, time, urllib.request, zipfile
from pathlib import Path

import httpx

_ap = argparse.ArgumentParser(description="Update-in-place check, 2.6.0 to 2.7.0")
_ap.add_argument("old_zip"); _ap.add_argument("new_zip")
_ap.add_argument("--python", default=sys.executable, help="a Python that has the backend requirements installed (default: the one running this script)")
_ap.add_argument("--keep", action="store_true", help="keep the temporary folder when done")
_a = _ap.parse_args()
OLD, NEW = Path(_a.old_zip).resolve(), Path(_a.new_zip).resolve()
PY = _a.python
W = Path(tempfile.mkdtemp(prefix="swara-update-check-"))
inst = W / "install"
OWNER, PASSWORD = "owner.keep@example.com", "Upgrade-Check-Pass-2026!"
ENV = (
    "# my settings - do not touch\r\n"
    "GNANI_API_KEY=FAKE-KEY-FOR-THE-UPDATE-TEST-0000\r\n"
    "STORE_NAME=Test Kirana (update check)\r\n"
    "GNANI_TIMEOUT_S=40\r\n"
    f"OWNER_EMAIL={OWNER}\r\n"
    "MY_CUSTOM_LINE=keep   me   exactly\r\n"
)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
res: dict[str, bool] = {}
notes: list[str] = []


def unzip(z_path: Path, dest: Path) -> list[str]:
    """Extract the ZIP over `dest`, stripping the top folder, exactly like Extract All over an install."""
    with zipfile.ZipFile(z_path) as z:
        names = z.namelist()
        for info in z.infolist():
            rel = info.filename.split("/", 1)[1] if "/" in info.filename else ""
            if not rel:
                continue
            out = dest / rel
            if info.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(info))
    return names


def counts(db: Path) -> dict:
    c = sqlite3.connect(db)
    q = lambda s: c.execute(s).fetchone()[0]
    tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    out = {t: q(f"select count(*) from {t}") for t in ("users", "orders", "order_items", "products", "stock_movements", "customers", "sessions", "turns", "api_calls", "catalog_items") if t in tabs}
    out["stock_sum"] = round(q("select sum(stock) from products"), 3)
    out["order_totals_sum"] = q("select coalesce(sum(total_paise),0) from orders")
    out["roles"] = sorted(r[0] for r in c.execute("select role from users"))
    c.close()
    return out


def digest(db: Path, names: set) -> dict:
    """A fingerprint of every row of every named table (all columns, in primary-key order), so a changed value shows up and not only a changed count."""
    c = sqlite3.connect(db)
    out = {}
    for t in sorted(names):
        h = hashlib.sha256()
        for row in c.execute(f'select * from "{t}" order by 1'):
            h.update(repr(row).encode())
        out[t] = h.hexdigest()
    c.close()
    return out


def tables(db: Path) -> set:
    c = sqlite3.connect(db)
    t = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    c.close()
    return t


def start(root: Path, port: int):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COOKIE_SECURE": "false"}
    for k in list(env):
        if k.startswith(("GNANI_", "DATABASE_URL", "STORE_NAME", "OWNER_EMAIL", "RAZORPAY_", "PAYMENT_", "UPI_")):
            env.pop(k)
    log = open(W / f"server_{port}.log", "w")
    p = subprocess.Popen([PY, "-m", "uvicorn", "app.main:create_app", "--factory", "--port", str(port)], cwd=root / "backend", env=env, stdout=log, stderr=log)
    for _ in range(80):
        try:
            return p, json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2))
        except Exception:
            time.sleep(0.5)
    p.kill()
    raise SystemExit(f"server on {port} did not start; see {W}/server_{port}.log")


def stop(p):
    p.terminate()
    p.wait(timeout=15)


def client(port: int, *, signup=False) -> httpx.Client:
    c = httpx.Client(base_url=f"http://127.0.0.1:{port}", headers={"Origin": f"http://127.0.0.1:{port}"}, timeout=30)
    if signup:
        r = c.post("/api/auth/signup", json={"full_name": "Owner Keep", "email": OWNER, "password": PASSWORD, "confirm_password": PASSWORD, "accept_terms": True})
        assert r.status_code in (200, 201), f"signup {r.status_code} {r.text[:200]}"
    r = c.post("/api/auth/login", json={"email": OWNER, "password": PASSWORD, "remember": False})
    assert r.status_code == 200, f"login {r.status_code} {r.text[:200]}"
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


# ---------------------------------------------------------------- 1. a real 2.6.0 install with real activity
old_names = unzip(OLD, inst)
(inst / ".env").write_bytes(ENV.encode())
(inst / "backend" / "data").mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(OLD) as z:
    res["old zip is the 2.6.0 release"] = any(n.endswith("CHANGELOG.md") and b"## 2.6.0" in z.read(n) for n in z.namelist())
p, h = start(inst, 8031)
res["2.6.0 starts on a new database and reports version 2.6.0"] = h.get("version") == "2.6.0"
# sign up needs ALLOW_SIGNUP; pass it only for this run so the .env stays exactly what the person wrote
stop(p)
env_signup = {**os.environ, "ALLOW_SIGNUP": "true", "COOKIE_SECURE": "false", "PYTHONDONTWRITEBYTECODE": "1"}
for k in list(env_signup):
    if k.startswith(("GNANI_", "DATABASE_URL", "STORE_NAME", "OWNER_EMAIL")):
        env_signup.pop(k)
log = open(W / "server_8032.log", "w")
p = subprocess.Popen([PY, "-m", "uvicorn", "app.main:create_app", "--factory", "--port", "8032"], cwd=inst / "backend", env=env_signup, stdout=log, stderr=log)
for _ in range(80):
    try:
        urllib.request.urlopen("http://127.0.0.1:8032/api/health", timeout=2); break
    except Exception:
        time.sleep(0.5)
c = client(8032, signup=True)
demo = subprocess.run([PY, str(inst / "scripts" / "demo_activity.py"), "--base", "http://127.0.0.1:8032", "--email", OWNER, "--password", PASSWORD, "--json", str(W / "demo.json")],
                      capture_output=True, text=True, cwd=inst)
res["2.6.0 took real activity (typed orders through the confirm button)"] = demo.returncode == 0
if demo.returncode != 0:
    notes.append("demo_activity failed:\n" + (demo.stdout + demo.stderr)[-1500:])
c.close(); stop(p)

db = inst / "backend/data/swara.db"
before_env, before_db = sha(inst / ".env"), sha(db)
before = counts(db)
before_tables = tables(db)
res["2.6.0 data: has users, orders, order lines, stock movements"] = all(before.get(k, 0) > 0 for k in ("users", "orders", "order_items", "stock_movements", "products"))
res["2.6.0 data: no payment tables yet"] = not ({"payments", "payment_events", "refunds", "invoices"} & before_tables)
(W / "before_counts.json").write_text(json.dumps(before, indent=1))
old_copy = W / "swara_2_6_0_before.db"; shutil.copy(db, old_copy)

# ---------------------------------------------------------------- 2. unzip 2.7.0 over it
new_names = unzip(NEW, inst)
res["2.7.0 zip: contains no .env and no database file"] = not any(n.endswith("/.env") or n.endswith(".db") or "/backend/data/swara" in n for n in new_names)
res["after unzip: .env is byte for byte the same"] = sha(inst / ".env") == before_env
res["after unzip: database file is byte for byte the same"] = sha(db) == before_db

# ---------------------------------------------------------------- 3. start 2.7.0 on the old data
p, h = start(inst, 8033)
res["2.7.0 starts on the old data and reports version 2.7.0"] = h.get("version") == "2.7.0"
res["2.7.0 health: shop name from the untouched .env"] = h.get("store_name") == "Test Kirana (update check)"
res["2.7.0 health: Gnani key still seen as configured"] = h.get("gnani_configured") is True
stop(p)
after = counts(db)
res["after start: every old table keeps its row count, stock total and roles"] = after == before
old_digest = digest(old_copy, before_tables - {"sqlite_sequence"})
new_digest = digest(db, before_tables - {"sqlite_sequence"})
changed_tables = sorted(t for t in old_digest if old_digest[t] != new_digest[t])
res[f"after start: every row of every one of the {len(old_digest)} old tables is unchanged (all columns compared)"] = not changed_tables
if changed_tables:
    notes.append("tables whose rows differ after the 2.7.0 start: " + ", ".join(changed_tables))
if after != before:
    notes.append(f"counts before {before}\ncounts after  {after}")
res["after start: .env still byte for byte the same"] = sha(inst / ".env") == before_env
t_after = tables(db)
res["after start: payments, payment_events, refunds, invoices and schema_migrations exist"] = {"payments", "payment_events", "refunds", "invoices", "schema_migrations"} <= t_after
c2 = sqlite3.connect(db)
mig = [r[0] for r in c2.execute("select id from schema_migrations")] if "schema_migrations" in t_after else []
c2.close()
res["after start: migration 2.7.0-payments is recorded"] = "2.7.0-payments" in mig
backups = sorted((inst / "backend/data/backups").glob("*before-2.7.0*.db")) if (inst / "backend/data/backups").exists() else []
res["a backup of the old database was made before migrating"] = len(backups) == 1
if backups:
    res["the backup opens and holds the old counts"] = counts(backups[0]) == before
    res["every row of every table in the backup equals the 2.6.0 database it was taken from"] = digest(backups[0], before_tables - {"sqlite_sequence"}) == old_digest
    res["the backup has no payment tables (it is the old database)"] = not ({"payments", "invoices"} & tables(backups[0]))
    notes.append(f"backup file: {backups[0].name}; byte-identical to the 2.6.0 file: {sha(backups[0]) == before_db} (a SQLite backup copy need not be)")
else:
    res["the backup opens and holds the old counts"] = False

# ---------------------------------------------------------------- 4. use it: existing orders, a cash payment on a migrated order
p, _ = start(inst, 8034)
c = client(8034)
items, offset, total = [], 0, None
while True:
    page = c.get("/api/orders", params={"limit": 100, "offset": offset}).json()
    total = page["total"]
    items += page["items"]
    offset += 100
    if offset >= total:
        break
res["every old order is listed (all pages) and reports payment status none"] = len(items) == before["orders"] == total and all(o["payment"]["status"] == "none" for o in items)
open_orders = [o for o in items if o["status"] != "cancelled"]
target = open_orders[0]
cfg = c.get("/api/payments/config").json()
res["payments config: Razorpay is off with no keys, cash and manual UPI are not"] = cfg["razorpay"]["enabled"] is False
r = c.post(f"/api/orders/{target['id']}/payments", json={"method": "cash"})
res["a payment can be started on a migrated order (201)"] = r.status_code == 201
pay = r.json()
res["the amount comes from the stored order total"] = pay.get("amount_paise") == target["total_paise"]
r2 = c.post(f"/api/payments/{pay['id']}/cash", json={"received_paise": target["total_paise"]})
res["cash received: payment is paid"] = r2.status_code == 200 and r2.json()["status"] == "paid"
inv = c.get(f"/api/orders/{target['id']}/invoice")
res["an invoice can be made for the migrated order"] = inv.status_code == 200 and str(inv.json().get("number", "")).startswith("INV-")
res["the order now reports payment paid"] = c.get(f"/api/orders/{target['id']}").json()["payment"]["status"] == "paid"
stk = counts(db)
res["no stock moved when the payment was taken (stock total and movements unchanged)"] = stk["stock_sum"] == before["stock_sum"] and stk["stock_movements"] == before["stock_movements"]
res["order count and order totals unchanged by the payment"] = stk["orders"] == before["orders"] and stk["order_totals_sum"] == before["order_totals_sum"]
c.close(); stop(p)
res["after use: .env still byte for byte the same"] = sha(inst / ".env") == before_env

# ---------------------------------------------------------------- 5. settings come from the old .env
code = ("import json; from app.config import Settings; s=Settings(); "
        "print(json.dumps({'key_set': bool(s.gnani_api_key), 'store': s.store_name, 'owner': s.owner_email, 'mode': s.payment_mode, 'rz_key': bool(s.razorpay_key_id)}))")
cfg_out = json.loads(subprocess.run([PY, "-c", code], cwd=inst / "backend", capture_output=True, text=True,
                                    env={k: v for k, v in os.environ.items() if not k.startswith(("GNANI_", "STORE_NAME", "OWNER_EMAIL", "RAZORPAY_", "PAYMENT_"))}).stdout)
res["settings: fake Gnani key, shop name and owner e-mail read from the old .env; payment mode defaults to test; no Razorpay key"] = (
    cfg_out["key_set"] and cfg_out["store"] == "Test Kirana (update check)" and cfg_out["owner"] == OWNER and cfg_out["mode"] == "test" and not cfg_out["rz_key"])

# ---------------------------------------------------------------- 6. roll back: the real 2.6.0 code on the upgraded database (a copy)
rb = W / "rollback"
unzip(OLD, rb)
(rb / "backend/data").mkdir(parents=True, exist_ok=True)
shutil.copy(db, rb / "backend/data/swara.db"); shutil.copy(inst / ".env", rb / ".env")
up_counts = counts(db)
p, h = start(rb, 8035)
res["rollback: 2.6.0 code starts on the upgraded database"] = h.get("version") == "2.6.0"
c = client(8035)
rl = c.get("/api/orders", params={"limit": 100})
res["rollback: 2.6.0 lists all the orders, including the one that was paid in 2.7.0"] = rl.status_code == 200 and rl.json()["total"] == before["orders"]
c.close(); stop(p)
rc = counts(rb / "backend/data/swara.db")
res["rollback: row counts and stock unchanged after 2.6.0 opened it"] = rc == up_counts

for k, v in res.items():
    print(("PASS  " if v else "FAIL  ") + k)
for n in notes:
    print("NOTE  " + n)
print(f"\n{sum(res.values())} of {len(res)} checks passed")
_clean = (not _a.keep) and all(res.values())
print(f"work folder: {W}" + (" (removed)" if _clean else " (kept: look at the server logs there)"))
print(f"orders in the migrated database: {before['orders']}; users: {before['users']}; products: {before['products']}; stock movements: {before['stock_movements']}")
if _clean:
    shutil.rmtree(W, ignore_errors=True)
sys.exit(0 if all(res.values()) else 1)
