# Migrating to 2.7.0 (payments)

2.7.0 adds payments, refunds and invoices to the app you already run. It is an **upgrade in place**: nothing was rebuilt, the voice-ordering path is unchanged, and your `.env`, Gnani key, database, users, orders, customers and inventory are kept.
The step-by-step update is in [UPDATING.md](UPDATING.md). This page is about the **database change** and how to check it.

## What changes in the database

Four **new tables** and their indexes are created. **No existing table or column is altered, renamed, emptied or deleted, and no row is rewritten.**

| New table | Holds |
|---|---|
| `payments` | One row per attempt to pay an order: way (cash, UPI, Razorpay), status, the amount due (paise), what was received, who recorded it and when, provider ids, and a flag when the owner should look |
| `payment_events` | The audit trail of every change to a payment: source, status before and after, who, whether a signature was valid. Ids, amounts and statuses only; never card data, secrets or signatures |
| `refunds` | Refunds against a payment: amount, status (waiting, processed, failed), reason, who started it, the provider's refund id |
| `invoices` | One numbered invoice per order, made the first time it is asked for; the shop name as it was that day |
| `schema_migrations` | A one-row-per-migration record, so a migration runs once (created by the migration code; the id is `2.7.0-payments`) |

Rules the new tables carry in the database itself (not only in code): an amount must be above zero; refunded money cannot exceed the amount paid; at most **one open payment per order**; Razorpay ids and request keys are unique; invoice numbers are unique per year. The tables point at `orders` and `users` with ordinary foreign keys and **no cascading deletes**, so removing an order cannot silently remove its payment history.

**Existing orders keep working with no payment recorded.** They show "Not recorded" (not "unpaid": shops took cash before payments existed here). No payment, invoice or refund is made for them unless a person starts one.
**Stock is not touched by payments.** Stock still moves exactly once, when an order is confirmed or cancelled, as before. A payment retry, a repeated webhook or a refund cannot deduct it again.

## How the migration runs

- **Automatically, on every start.** The app checks `schema_migrations`; if `2.7.0-payments` is not recorded it runs it, and does nothing on later starts. You do not have to run anything.
- **Before it touches an existing database,** it writes a consistent copy to `backend\data\backups\<name>-before-2.7.0-<timestamp>.db` using SQLite's own backup method (safe while the app is running). A **brand-new** database has nothing to protect and gets no copy.
- **It proves nothing was lost.** It counts the rows of `users`, `customers`, `products`, `orders`, `order_items`, `stock_movements`, `sessions`, `turns` and `api_calls` before and after, and stops with an error if any number differs.
- **If it fails,** the data is left alone, the migration is not recorded, and it is tried again on the next start.

## Check first, if you want to (changes nothing)

With the app stopped, from the project folder:

```
backend\.venv\Scripts\python.exe scripts\migrate_db.py
```

It lists the tables it would create and the row counts that must stay the same, and exits without changing the database (exit code 1 means "changes are pending"; 0 means nothing to do). `.env` is read, never written.
To run it yourself, with the backup, instead of letting the app do it at start:

```
backend\.venv\Scripts\python.exe scripts\migrate_db.py --apply
```

To try it on a copy first: `--database C:\path\to\copy-of-swara.db`.

## Settings you may add (all optional)

The four payment lines are in `.env.example`, empty or commented out. **Your `.env` is not replaced**, so they are not there until you add them. Cash and the shop's own UPI QR need none of them.

| Variable | Default | Meaning |
|---|---|---|
| `PAYMENT_MODE` | `test` | `test` or `live`. Live also needs live keys and is never switched on by the update |
| `RAZORPAY_KEY_ID` | empty | Razorpay is **off** until this and the key secret are set |
| `RAZORPAY_KEY_SECRET` | empty | Secret. Server only |
| `RAZORPAY_WEBHOOK_SECRET` | empty | Secret. Without it the webhook endpoint refuses every call |
| `RAZORPAY_UPI_QR` | `false` | Use Razorpay's own dynamic UPI QR instead of the shop's own UPI ID |
| `UPI_VPA`, `UPI_PAYEE_NAME` | empty | The shop's UPI ID for the manual QR. The owner can also set these in Settings, which writes them to `.env` |
| `PAYMENT_PENDING_MINUTES` | `30` | A waiting payment older than this is shown as stale (never closed on its own) |
| `PUBLIC_URL` | `http://localhost:8000` | Used to show the webhook address in Settings; set it to the address Razorpay can reach |

Every `GNANI_*` setting is exactly as it was.

## Going back to 2.6.0

2.6.0 does not know the new tables and leaves them alone, so the same database opens in 2.6.0:

1. Stop the app. 2. Put the 2.6.0 files back (or extract the old ZIP into a new folder). 3. Keep your `.env` and `backend\data`.

Payments recorded in 2.7.0 stay in the database, unseen by 2.6.0, and appear again if you update once more. If you want the database exactly as it was before the update, copy the file from `backend\data\backups\` over `swara.db` while the app is stopped. **That also removes every order and customer made after the update**, so use it only if you have made none, or accept losing them.

## What was checked, and what was not

The checks that exist for this migration are in the automated tests (`backend/tests/test_payments_migration.py`): an older database is backed up, gains the tables and changes nothing else; the migration runs once; a failing migration leaves the data alone; the app starts on an older database and existing accounts and orders still work; data written afterwards survives a restart; the command-line tool checks without changing, then applies with a backup; nothing in the migration can delete or change existing data.
On top of those, `scripts/check_update_in_place.py` performs the whole update on a database created by the **released 2.6.0 code**: it unzips the 2.7.0 ZIP over a 2.6.0 install, checks that `.env` and the database are untouched by the unzip, starts 2.7.0, compares every row of every old table and the backup against the old database, takes a cash payment on a migrated order, and opens the upgraded database with the 2.6.0 code again. Its log, 34 of 34 checks passed, is [update_in_place_check.txt](test-results/update_in_place_check.txt); the other results are in [PAYMENT_TESTING.md](PAYMENT_TESTING.md). You can run it yourself with both release ZIPs: `python scripts/check_update_in_place.py SWARA-AI-UPGRADE-2.6.0.zip SWARA-AI-UPGRADE-2.7.0.zip`.
Not checked: an update on Windows (the build environment is Linux), a database that was edited by hand, and going back to 2.5.0 from a 2.7.0 database.
