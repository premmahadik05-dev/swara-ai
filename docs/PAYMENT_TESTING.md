# Payment testing report (release 2.7.0)

This report lists what was actually run on 11 November 2026 in the build environment, what each run showed, and what was **not** checked. Every number below comes from a log in [`docs/test-results/`](test-results); nothing here is an estimate. Where a test could only be done against a stand-in, it says so.

**The one thing to read first:** no payment in this report went through Razorpay. The build environment has no Razorpay account and no network route to Razorpay. Every Razorpay test ran against a stand-in (`FakeRazorpay` in `backend/tests/payment_helpers.py`) that answers the handful of REST calls the app makes, from state each test controls. That proves the app builds the requests it should and reacts correctly to the answers the stand-in gives. It does not prove that Razorpay's servers answer in exactly that shape. The checklist at the end of [RAZORPAY_SETUP.md](RAZORPAY_SETUP.md) is how you close that gap with your own test keys.

## Results at a glance

| Check | Result | Log |
|---|---|---|
| Backend test suite (whole project, including every test that existed before 2.7.0) | **1,103 passed, 0 failed, 0 skipped**, 13 min 33 s; 95% line coverage (6,349 statements, 297 not executed). 5 warnings, none from a payment test (one Starlette deprecation notice, and unclosed-database resource warnings in two older tests) | [backend_pytest.txt](test-results/backend_pytest.txt), [.xml](test-results/backend_pytest.xml) |
| of which written for payments | **158 tests in 6 files** (cash and UPI 25, history, invoices and analytics 17, migration 9, Razorpay 60, refunds 27, security 20). The other 945 are the tests that existed in 2.6.0, run unchanged | same |
| Frontend unit tests (Vitest) | **513 passed in 50 files** | [frontend_vitest.txt](test-results/frontend_vitest.txt) |
| TypeScript check and production build | no type errors; build succeeds | [frontend_build.txt](test-results/frontend_build.txt) |
| Real browser (Chromium), main run, empty database | **221 of 221 checks passed**, of which 61 are new in 2.7.0 (62 new check names; one replaces the old width sweep) and every one of them is about payments, refunds, invoices, permissions or the payment screens; no unexpected console errors, warnings, failed requests or HTTP errors | [e2e_browser_main.txt](test-results/e2e_browser_main.txt) |
| Real browser, click-every-button audit | **4 of 4 checks passed**: 10 enabled buttons on 6 public pages and 221 on 15 signed-in pages (the payment pages included) were clicked and each did something; every link on 21 pages goes somewhere real; no unexpected console error, warning or failed request | [e2e_browser_controls.txt](test-results/e2e_browser_controls.txt) |
| The same backend suite and browser run from a clean unzip of the 2.7.0 ZIP | **1,103 passed, 0 failed** (13 min 9 s) and **221 of 221 checks passed** | [backend_pytest_clean_unzip.txt](test-results/backend_pytest_clean_unzip.txt), [e2e_browser_clean_unzip.txt](test-results/e2e_browser_clean_unzip.txt) |
| Update of a 2.6.0 install in place (the released 2.6.0 code and the data it made) | **34 of 34 checks passed** (`scripts/check_update_in_place.py`): the released 2.6.0 ZIP was unpacked, the real 2.6.0 code created data (6 typed orders on top of the app's generated demo data, 3,071 orders in all), the 2.7.0 ZIP was unzipped over it, and 2.7.0 started on that data. The unzip left `.env` and the database byte for byte unchanged; after the start every row of the 13 existing tables was identical (all columns compared), a backup was made that matched the old data row for row, the new tables existed, every old order reported "no payment", a cash payment and an invoice worked on a migrated order without moving stock, and the real 2.6.0 code then opened the upgraded database and listed all the orders | [update_in_place_check.txt](test-results/update_in_place_check.txt) |
| Dependency audits | `npm audit`: 0 vulnerabilities. `pip-audit`: none known. Advisory databases change daily | [dependency_audits.txt](test-results/dependency_audits.txt) |

Coverage of the payment code in that run: `services/payments.py` 96%, `routers/payments.py` 99%, `services/razorpay.py` 91%, `migrations.py` 96%, `models.py` 100%. The lines not executed are mostly defensive branches for provider replies the stand-in never produces.

## What was tested, by what you asked for

Test names are in the files listed; the junit file has every name.

| Area | Where | What it shows |
|---|---|---|
| **Cash** | `test_payments_cash_upi.py`, browser | Pending until a person records it; the amount received, the change, who and when are stored; less than the bill is refused and the payment stays pending; recording twice records once; an amount over twenty times the bill plus 1,000 rupees (a slip) is refused on screen and by the server |
| **UPI QR (manual)** | `test_payments_cash_upi.py`, browser | Needs the shop's UPI ID first; shows amount and bill number; labelled "Not verified"; never paid until a person confirms with a reference **and** says they can see the money; stored as unverified; listed as unverified in history and analytics |
| **Razorpay test flow** | `test_payments_razorpay.py` | Order made on the server for the server-side total; error cases (network, timeout, bad key, rate limit, provider error, rejection) leave no payment behind and say why; checkout confirmation, authorised then captured, failed then retried, pending then checked by asking Razorpay, cancelled then late success flagged |
| **Signature verification** | `test_payments_razorpay.py`, `test_payments_security.py` | A correct signature is still checked against Razorpay's own record before "paid"; a wrong signature, a wrong secret, a signature for another order or payment, a replayed signature, and a "genuinely signed" payment Razorpay does not know are all refused. The signature construction in the test helper is written out separately from the app code, so the tests do not just agree with themselves |
| **Webhooks** | `test_payments_razorpay.py`, `test_payments_refunds.py`, browser | Bad or missing signature refused and changes nothing; refused outright while no webhook secret is set; the same event twice processed once; a redelivery with a new event id changes nothing; failed-then-captured and captured-then-failed orderings end paid; non-JSON and oversized bodies refused; personal data in a body is not stored; unknown events acknowledged and ignored |
| **Duplicate payment** | `test_payments_cash_upi.py`, `test_payments_razorpay.py` | Same idempotency key returns the same payment; one open payment per order enforced by the database itself; a paid order cannot be paid again; a double tap does not create a second provider order; a second capture for a paid order is flagged, not recorded twice |
| **Amount mismatch** | `test_payments_razorpay.py`, `test_payments_security.py` | A different amount from Razorpay, from a webhook or from a QR payment is not marked paid and is flagged; the amount due always comes from the server-side order total whatever the browser sends |
| **Failed and pending** | `test_payments_razorpay.py` | A failed payment is recorded as failed and the shop can try again; a pending payment is checked by asking Razorpay and stays pending if unpaid; if Razorpay cannot be reached nothing changes |
| **Refunds** | `test_payments_refunds.py`, browser | Owner only; partial refunds add up and cannot pass what was paid, in code and in the database; a Razorpay refund is pending until Razorpay reports it processed; the same request or webhook twice counts the money once; a failed refund can be retried; a late "pending" or "failed" report cannot undo a processed refund; cash refunds are labelled "recorded by the owner, not confirmed by a payment provider"; a fully refunded order can then be cancelled and stock comes back |
| **Permissions** | `test_payments_cash_upi.py`, `test_payments_refunds.py`, browser | Staff can take payments but not refund, see payment analytics or change the UPI ID (403 from the server, not only a hidden button); nothing in the payment API works signed out; writes need the CSRF token; a request from another website is refused |
| **Voice and typed order regression** | `test_payments_cash_upi.py` plus the 945 older tests | An order with no payment works exactly as before; seeded demo orders report payment "none" and no payment figure is invented; cancelling an unpaid order restocks as before; payment attempts and retries never change stock; a voice-channel order is paid the same way. The whole older suite, including the voice path, language and order-integrity tests, ran unchanged and passed |
| **Database migration and persistence** | `test_payments_migration.py`, update check | An older database is backed up first, gets the four new tables, and nothing else changes; runs once; a failing migration leaves the data alone and is retried; the app starts on an older database and existing accounts and orders still work; data written after the migration survives a restart; the command line tool checks without changing, then applies with a backup; no cascading deletes |
| **Secrets and configuration** | `test_payments_security.py` | `.env.example` holds only empty placeholders and keeps the Gnani lines; no Razorpay credential or secret name in the frontend source; none hard-coded in the backend; secrets hidden when settings are printed and never in logs, even when Razorpay refuses the key; Razorpay and live mode never switch on by themselves; the content-security policy allows Razorpay only when it is on; payment responses are not cached; the Gnani settings are untouched |
| **Invoices and analytics** | `test_payments_history_invoice_analytics.py`, browser | Unique, repeatable numbers, also under simultaneous requests; the shop name is kept as it was on the day; never claims to be a GST invoice; analytics are summed from real rows, count only confirmed refunds and paid payments, show empty days as zero, and report manual UPI separately |
| **Screens** | Vitest, browser | Success is shown only from a server reply; the payment window, history, detail, analytics, invoice (print copy renders to a PDF, hidden again afterwards) and Settings card; light theme only; no horizontal scrolling on 6 public and 14 signed-in pages at seven widths from 320 to 1440 px |

## How the test double was kept honest

- It is a plain `httpx.MockTransport` handler; the app's own Razorpay client runs against it unchanged, so the real request building, headers, retries and error mapping are exercised.
- Signatures in the tests are computed by helper code written out separately in `payment_helpers.py`, not imported from the app, so a mistake in the app's own signature code cannot make the tests agree with it by accident.
- Tests that stand in for "Razorpay says X" are named for the behaviour they check. A few tests were each run against a deliberately broken copy of the code to confirm they fail when the rule is removed: the check that keeps secret names out of the frontend, and the payment window's resume screen. That was done by hand while building; it is not part of the shipped suite, and it was **not** done for every payment test.

## What was not verified

- **Anything against the real Razorpay service**: order creation, Checkout in a browser (the script is loaded on demand from `https://checkout.razorpay.com/v1/checkout.js`, an address written from documentation as remembered), real webhook delivery and headers, real refunds, and the optional Razorpay UPI QR. Field names and endpoints were written from Razorpay's public documentation as remembered while building and not checked against a live account.
- **Live mode.** It was only tested as a refusal (it does not start without live keys and `PAYMENT_MODE=live`). No live key was used.
- **A real phone scanning the UPI QR code**, and any real bank.
- **Payment webhook rate limiting.** The webhook endpoint is public and not rate limited; it is protected by its signature check (documented in [PAYMENT_SECURITY_AUDIT.md](PAYMENT_SECURITY_AUDIT.md)).
- **GST.** The invoice is a receipt. No merchant tax details exist and no tax is calculated.
- **The Windows start scripts** and **Gnani live speech** were not run in this build environment, as for earlier releases (see [LIMITATIONS.md](LIMITATIONS.md)).
- **Load.** No payment load test was run; the invoice-number and one-open-payment rules were tested with simultaneous requests, not at volume.

## Re-running it

```
python -m pytest backend/tests/test_payments_*.py        # the 158 payment tests
python -m pytest                                          # everything
cd frontend && npx vitest run && npm run build
python scripts/e2e_browser.py http://localhost:8000 --db <throw-away db> --owner-email <owner> --skip-controls
```

Use a throw-away database for the browser run: it creates real orders and payments in it.
