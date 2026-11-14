# Updating an existing install to 2.7.0

This page covers the update to **2.7.0** (payments, refunds and invoices) and, for a shop still on 2.5.0, the 2.6.0 changes it passes through. The database change in 2.7.0 has its own page: [MIGRATION_2.7.0.md](MIGRATION_2.7.0.md).

This update keeps your **`.env` file, your Gnani key, your database, your users, orders and inventory**. It never requests the Gnani key, never writes a secret into the project,
and never resets the database. Read "What the update changes" once, then follow the steps.

## What the update changes (and what it does not)

| Thing | Effect of the update |
|---|---|
| `.env` | **Not touched.** It is not in the ZIP, and `setup.bat` only creates one when none exists |
| Gnani key | **Not touched.** It stays in your `.env`; the update never reads, prints or asks for it |
| Database (`backend\data\swara.db`) | **Kept.** On first start the app writes a copy to `backend\data\backups\`, then **adds four new tables** (`payments`, `payment_events`, `refunds`, `invoices`) and a small `schema_migrations` record. From 2.5.0 it also adds one column, `api_calls.attempts` (existing rows get 1). No table is dropped, no existing row is rewritten, no data is re-seeded over yours. Existing orders show "Not recorded" for payment until someone records one |
| Users, passwords, roles | **Unchanged.** Owner and staff accounts, password hashes and sessions are not modified |
| Orders, order lines, stock, price, customers, stock ledger | **Unchanged** |
| Spoken-reply cache (`backend\data\tts_cache`) | Kept. Entries stay valid (the cache key did not change) |
| `eval\results\live_verification.json` (written by `verify_gnani.bat`) | Not in the ZIP, so a copy you made is not overwritten |
| Code, built frontend, documents | Replaced by the 2.7.0 versions |
| Payment settings | **Not added for you.** `.env` is not replaced, so the new payment lines are not in it until you add them. Cash and the shop's own UPI QR need none. Razorpay stays **off** until you add keys, and live mode is never switched on by the update |

Going back to 2.6.0 is safe too: it ignores the new tables, and the same database opened in the real 2.6.0 code in the check described in [PAYMENT_TESTING.md](PAYMENT_TESTING.md). Going back to 2.5.0 was **not** tried against a 2.7.0 database (see "Going back").

## Steps (Windows)

1. **Stop the app.** Close the `start.bat` window.
2. **Make a copy of your data**, so there is always a way back. In File Explorer, copy these two items from your project folder to somewhere else (a USB stick, another folder):
   - the file `.env`
   - the folder `backend\data` (it holds `swara.db`)
3. **Put the new files in place.** Either:
   - **extract the ZIP over your existing project folder**, choosing "Replace the files in the destination". The ZIP contains no `.env` and no database, so neither is replaced. The empty
     `backend\data` folder inside the ZIP does not remove what is in yours; **or**
   - extract the ZIP into a **new** folder, then copy your `.env` and your `backend\data` folder into it (so `backend\data\swara.db` is in the new folder).
4. **Run `setup.bat`.** It is safe to run again: it keeps your `.env`, installs the packages listed in `backend\requirements.txt` (unchanged since 2.5.0), installs the front-end packages when Node.js is installed (2.7.0 adds one small one, `qrcode-generator`, which draws the UPI QR in the browser with no outside service), rebuilds the screens when
   Node.js is installed (otherwise it uses the screens already in the ZIP), and runs the normal first-run seeding, which only **adds demo rows that are missing** and never overwrites a row
   (the app does the same on every start). It does not reset the database.
5. **Run `start.bat`** and sign in with your existing owner or staff account. The first start makes the backup and adds the payment tables. It prints nothing; the checks below show that it happened.
   (Want to see exactly what will happen first? Before this step run `backend\.venv\Scripts\python.exe scripts\migrate_db.py`. It changes nothing. Run it again afterwards and it says there is nothing to do.)
6. **Check it** (below).

Do **not** run `python scripts\seed_db.py --reset`, and do not delete `backend\data`. Those are the only ways to lose data, and nothing in the update needs them.

## Check that nothing was lost

Before step 3 and after step 5, count the records. With the app stopped, in the project folder:

```
backend\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('file:backend/data/swara.db?mode=ro', uri=True); print({t: c.execute('select count(*) from '+t).fetchone()[0] for t in ('users','orders','products','customers')})"
```

The numbers must be the same before and after (the app may add rows only when you use it). The migration itself makes the same comparison, over more tables, and stops with an error if anything differs. The `mode=ro` part opens the file read-only, so this command cannot change anything.

In the app, after signing in:
- **Dashboard** and **Orders** show your orders; **Inventory** shows your stock.
- **Settings** shows "Key set …" with the last four characters of your key (the key itself is never shown). If it says "No key yet", your `.env` was not carried over: copy it back from your backup.
- Open `http://localhost:8000/api/health`: it reports `"version": "2.7.0"`.
- **Payments** (sidebar, under Sales) opens and is empty until a payment is recorded. Your existing orders say **Not recorded** in their Payment column; that does not mean unpaid.
- As the owner, **Payment analytics** (under Insights) and **Voice diagnostics** open. Payment analytics shows zero until payments are recorded; it never counts orders with no payment as money received.
- `backend\data\backups\` holds `swara-before-2.7.0-<date>.db`, the copy made before the tables were added. Keep it until you are happy.
- Open an order, choose **Take payment**: Cash works straight away; **UPI QR code** says to add the shop's UPI ID in Settings; **Razorpay Checkout** says the keys are not set. Those two being off is correct until you set them up ([RAZORPAY_SETUP.md](RAZORPAY_SETUP.md)).

## Settings (environment) migration

**You do not have to change anything in `.env`.** Every existing variable keeps its meaning, with one exception for a setting you may have raised.

**Payments (2.7.0):** also nothing to change. The optional payment variables (`PAYMENT_MODE`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_UPI_QR`, `UPI_VPA`, `UPI_PAYEE_NAME`, `PAYMENT_PENDING_MINUTES`) are listed in [MIGRATION_2.7.0.md](MIGRATION_2.7.0.md) and in `.env.example`. Never paste a key or secret into a chat or a message; they belong in your own `.env` only.

**Voice (2.6.0):** new, optional variables (leave them out to use the defaults; they are listed, commented out, in `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `GNANI_STT_TIMEOUT_S` | `20` | Seconds to wait for a speech-to-text answer (1 to 120) |
| `GNANI_TTS_TIMEOUT_S` | `15` | Seconds to wait for a spoken-reply answer (1 to 120) |
| `GNANI_CONNECT_TIMEOUT_S` | `5` | Seconds to wait for a connection to open (1 to 120) |

Changed meaning:

| Variable | Before 2.6.0 | From 2.6.0 |
|---|---|---|
| `GNANI_TIMEOUT_S` (default `40`) | The only time limit, applied to every call, and a timed-out call was tried **three** times | A **ceiling**: no single limit above may exceed it. A call that is sent and gets no answer in time is **not** repeated; a failure to connect, and `429`, `500`, `502`, `503`, `504`, are still tried up to three times |

What this means for you:
- If your `.env` has no `GNANI_TIMEOUT_S`, nothing changes except that a hung service is now reported after 20 s rather than after up to two minutes.
- If your `.env` sets `GNANI_TIMEOUT_S` **below 20**, that lower value now applies to both speech services (the ceiling wins). That is what you set, so it is respected.
- If your `.env` sets `GNANI_TIMEOUT_S` **above 20** (to give a slow connection more time), the speech-to-text limit is now 20 s. To keep a longer wait, add `GNANI_STT_TIMEOUT_S=40` (and keep `GNANI_TIMEOUT_S` at 40 or more).

Editing `.env` by hand: save it as UTF-8. Windows Notepad's "UTF-8 with BOM" is also read correctly from 2.6.0. The Settings page writes `.env` safely: the file is replaced in one step, other lines
and comments are kept, so a crash cannot leave a half-written file.

## Things you will notice after updating

- **Payments (2.7.0):** a confirmed order offers **Take payment** (cash, UPI QR, Razorpay); a **Payments** page with search and filters; a **receipt** for any order with a numbered invoice you can print; owner-only **refunds** and **Payment analytics**. The order desk's **Next customer** works with or without a payment. A UPI QR for the shop's own UPI ID is always marked **Not verified** until a person confirms it. The invoice says it is not a GST tax invoice.
- **Orders:** a Payment column, and an order with collected money cannot be cancelled until it is refunded.

**From 2.6.0:**

- **Order desk:** the bill appears before the spoken reply, a short silence now sends the recording ("Send when I stop talking", on by default; untick it to tap twice as before),
  a recording that could not be sent is kept with **Try again**, and an open bill comes back after a reload or after visiting another page.
- **Analytics and other lists:** the "Demo data" switch in the top bar now starts **off** for a shop that has recorded orders of its own, and **on** only for a shop with none (so a fresh install still
  has something to look at). If you have ever used the switch, **your choice is kept**. Nothing is deleted either way: the generated demo rows are still in the database, and the switch brings them back.
- **Voice diagnostics** (owner only): where the time goes for spoken orders and how the Gnani calls are doing. Staff accounts do not see it, and the server refuses them if they type the address.

## Going back

1. Stop the app. 2. Put the older files back in place (or extract the old ZIP into a new folder). 3. Keep using the same `.env` and `backend\data`. 2.6.0 does not know the payment tables and simply leaves them alone (tried: the real 2.6.0 code opened a database upgraded to 2.7.0 and listed every order). 2.5.0 was not tried against a 2.7.0 database; it does not read those tables either, but that is reasoning, not a test, so keep the copy of the database from before the update; payments recorded in 2.7.0 stay in the database and reappear if you update again. If you also want the database exactly as it was, restore the copy you made in step 2
(or the one in `backend\data\backups\`); that also drops anything you recorded since. Details: [MIGRATION_2.7.0.md](MIGRATION_2.7.0.md).

## If something looks wrong

- **"Port 8000 is already in use":** a copy of the old version is still running. Close its window, or `set PORT=8001` then run `start.bat`.
- **The screens look like the old version:** the browser kept the old files. Press Ctrl+F5.
- **Settings says "No key yet":** the update did not touch your key; the `.env` in the folder you started is not the one that holds it. Copy your backed-up `.env` into the project folder and restart.
- **Sign-in does not accept the owner password:** the update does not touch passwords. If the password is simply forgotten, see the recovery steps in [AUTHENTICATION.md](AUTHENTICATION.md) (`scripts\auth_admin.py`); that is a separate action you run yourself, on your own machine.
- Anything else: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
