# Changelog

Versions follow `backend/app/main.py` (`VERSION`) and `frontend/package.json`. What was tested for each release is in
[docs/VERIFICATION_REPORT.md](docs/VERIFICATION_REPORT.md) (the current one) and [docs/TESTING.md](docs/TESTING.md).

## 2.7.0 (11 Nov 2026)

Payment and billing release. It upgrades the existing app: nothing was rebuilt, the voice-ordering path is unchanged, and the Gnani integration and settings are untouched. Updating keeps `.env`,
the Gnani key, the database, users, orders, customers and inventory ([docs/UPDATING.md](docs/UPDATING.md), [docs/MIGRATION_2.7.0.md](docs/MIGRATION_2.7.0.md)); the schema change is four new tables.
**Nothing was run against the real Razorpay service and no live payment was made.** Razorpay was tested against a stand-in; the first real test-mode payment is yours to make
([docs/RAZORPAY_SETUP.md](docs/RAZORPAY_SETUP.md)). No language was added and nothing was run against live Gnani.

### Added
- **Take payment** on a confirmed order (Order desk and Orders): **cash** (amount received, change, who and when), **UPI QR code** for the shop's own UPI ID (always marked **Not verified** until a person confirms it with a bank
  reference), and **Razorpay Checkout** (UPI, cards, netbanking). The browser never says a payment worked: the server verifies the checkout signature, asks Razorpay for the payment and compares amount, currency and order.
  Razorpay is **off** until keys are in `.env`, starts in **test mode**, and live mode is never switched on by the update.
- **Razorpay webhook** (`POST /api/payments/webhooks/razorpay`): signature checked over the raw bytes, each event processed once, the same amount and order checks, refused outright while no webhook secret is set.
- **Payments page** (history with search, way, dates, status, "Needs a look"), a **payment page** (details, refunds, activity trail), owner-only **refunds** (Razorpay's refund API with the refund "Waiting" until Razorpay confirms, or recorded by hand for cash and manual UPI; duplicate-refund protection), and owner-only **Payment analytics** summed from the payment records.
- **Invoices**: a numbered receipt (`INV-year-number`, issued once per order) with items, totals, the way paid, status and reference, printable from the browser. **It is not a GST tax invoice** and says so; no tax is calculated.
- **Payments card in Settings** (owner): mode, whether Razorpay is ready, which secrets are set (never their values), the webhook address, and the shop's UPI ID and payee name.
- **Four new tables** (`payments`, `payment_events`, `refunds`, `invoices`) with database-level rules: positive amounts, refunds within what was paid, one open payment per order, unique provider ids, request keys and invoice numbers. `scripts/migrate_db.py` checks or applies the change (with a backup and a before/after row count).
- New settings (all optional, empty or off by default, in `.env.example`): `PAYMENT_MODE`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_UPI_QR`, `UPI_VPA`, `UPI_PAYEE_NAME`, `PAYMENT_PENDING_MINUTES`.
- New front-end package `qrcode-generator` (MIT), which draws the UPI QR in the browser.
- New documents: [docs/RAZORPAY_SETUP.md](docs/RAZORPAY_SETUP.md), [docs/PAYMENTS_API.md](docs/PAYMENTS_API.md), [docs/PAYMENT_TESTING.md](docs/PAYMENT_TESTING.md), [docs/PAYMENT_SECURITY_AUDIT.md](docs/PAYMENT_SECURITY_AUDIT.md), [docs/MIGRATION_2.7.0.md](docs/MIGRATION_2.7.0.md), [docs/CHANGED_FILES_2.7.0.md](docs/CHANGED_FILES_2.7.0.md).
  Updated: README, UPDATING, ARCHITECTURE, API, DATABASE, SECURITY, TESTING, LIMITATIONS, VERIFICATION_REPORT. `scripts/take_payment_screenshots.py` takes the payment pictures.

### Changed
- **Orders** carry a payment summary, and the Orders list has a Payment column. An order with no payment recorded reads **Not recorded** (not "unpaid"); existing orders are not changed.
- **An order with collected, unrefunded money cannot be cancelled** (409 `PAID_ORDER`; refund it first), and cancelling an order closes a payment that is still waiting. Orders that never had a payment cancel exactly as before.
- **Payments never change stock.** Stock still moves once, when an order is confirmed or cancelled, so a payment retry, a repeated webhook or a refund cannot deduct it twice.
- **Browser security headers follow the setting:** the content-security policy, permissions policy and window-opener policy allow Razorpay's domains only while Razorpay is switched on; with it off they are as in 2.6.0.

### Found by running it, and fixed
- The cash window let an amount through (over 20 times the bill plus ₹1,000) that the server refuses as a slip; it now applies the same rule before sending.
- Reopening a payment flashed the "choose a way to pay" screen for one round trip before resuming the payment in progress.
- A cash payment was labelled "Unverified", the invoice said "not verified by a payment provider" twice, the activity trail called the owner "Staff", and the test-mode note appeared when no Razorpay keys were set. All corrected.

### Documentation corrected in this release
The package first issued as 2.7.0 still carried the 2.5.0 project report. The application version (2.7.0) was right; only the documents were wrong. Corrected, with no change to application code:
- **Project report regenerated** (`docs/PROJECT_REPORT.md`, `.docx`, `.pdf`) for 2.7.0 by `scripts/build_report.py --files`: 23 sections, 14 figures, 14 tables, 48 PDF pages. New Section 11 (payments and billing: cash, hand-confirmed UPI, Razorpay Checkout in test mode against a stand-in, refunds, the invoice receipt, payment analytics) with a payments figure and three payment tables; the test record shows the 2.7.0 counts (1,103 backend, 513 front-end, 221 browser checks, 34 of 34 update-in-place checks).
- **The evaluation results did not change**, so the ten evaluation figures are byte-identical to the ones in the 2.5.0 report; the parser timing (0.138 ms median, 0.213 ms at the 95th percentile) and the demo-shop figures were re-read from the 2.7.0 files. The HTTP response-time table is from the 2.6.0 backend benchmark, which was **not repeated** for 2.7.0, and the report labels it so.
- `scripts/demo_activity.py --payments` records the payment session (four payments, one part refund, one invoice, none through Razorpay) into `docs/report-data/demo_activity.json`; `eval/results/evaluation_summary.json` gained the Payments and UPI QR rows in its technology table.
- Diagrams in `docs/diagrams/` and the data model in `docs/ARCHITECTURE.md` now include the payment tables; `docs/diagrams/payments.png` is new. Screenshots 02, 36 and 37 were retaken.
- README, TESTING, VERIFICATION_REPORT and LIMITATIONS no longer describe the report as a 2.5.0 document. The Razorpay stand-in is described everywhere as written from Razorpay's public documentation **as remembered while building, not checked against a live account**.

### Not verified
Real Razorpay (calls, field names, event names, Checkout, the optional Razorpay UPI QR), live mode, speech through live Gnani, and anything on Windows. See [docs/PAYMENT_SECURITY_AUDIT.md](docs/PAYMENT_SECURITY_AUDIT.md).

## 2.6.0 (11 Nov 2026)

Voice-response, diagnostics and reliability release. It upgrades the existing app; nothing was removed and nothing was rebuilt. **No language was added and nothing was run against live
Gnani**: every language is still "Not verified live", and no real speech latency or accuracy was measured. Updating keeps `.env`, the Gnani key, the database, users, orders and
inventory ([docs/UPDATING.md](docs/UPDATING.md)); the only schema change is one added column.

### Added
- **Reply first, voice after.** The Order desk shows the reply and the bill as soon as the order logic has run, then asks for the spoken reply separately
  (`POST /api/turns/{id}/speak`, which speaks only the text the server stored for that turn). A voice that fails or is slow leaves the written reply on screen. This is **not streaming** and
  does not make speech faster; the live-stream mode (`/ws/voice?defer_audio=true`) sends its `turn` message first and an `audio` message after.
- **Stage timing on every turn** (`turns.detail.timing`: audio check, speech to text, understanding, database, processing, spoken reply, server total, retries, cached or not), and a
  browser-reported record kept apart from it (`POST /api/turns/{id}/client-timing`: speech to reply on screen, speech to voice, length of speech, how the recording ended).
- **Voice diagnostics** (`/diagnostics`, `GET /api/diagnostics/voice`, **owner only**): median and slowest-1-in-20 time per step, the Gnani calls (how many, failed and why, retried), the browser's
  own measurements, the ten slowest turns, and the time limits in force. Everything is read from rows the app wrote; nothing is estimated; empty data reads "Not measured yet".
- **Automatic end of speech.** The recorder cuts silence at both ends before upload and, with "Send when I stop talking" (on by default), ends the recording after a short pause that follows
  speech. Tap to send still works.
- **One state at a time on the Order desk**: Listening, Understanding, Preparing the voice, Replying; a plain message when nothing was heard, when the device is offline, or when the speech
  service is slow; the recording is **kept with Try again** after a failure that may pass.
- **The open bill survives** a reload, a visit to another page or a dropped connection: the tab remembers the bill's id (per tab, six hours at most) and the bill is put back from the server.
- **`scripts/bench_voice_path.py`**: measures connections, reply time and the hung-service case against a local stand-in, on this tree or an older one (`--backend-dir`). Used for
  [docs/PERFORMANCE_REPORT.md](docs/PERFORMANCE_REPORT.md).
- New documents: [docs/UPDATING.md](docs/UPDATING.md) (updating without losing anything; environment migration), [docs/PERFORMANCE_REPORT.md](docs/PERFORMANCE_REPORT.md) (2.5.0 against 2.6.0), and
  [docs/TEST_REPORT_2.6.0.md](docs/TEST_REPORT_2.6.0.md); the list of every changed file is [docs/CHANGED_FILES_2.6.0.md](docs/CHANGED_FILES_2.6.0.md). Updated: ARCHITECTURE, MODEL_INTEGRATION (Gnani integration), GNANI_SETUP, SECURITY, TESTING, VERIFICATION_REPORT, README, `.env.example`.
- Screens re-captured for 2.6.0 (02, 04, 18) and two added (38, 39: Voice diagnostics). `scripts/take_screenshots.py` now sets the Demo data switch on, as the earlier pictures had it. `scripts/build_verification_summary.py` has a row for the 2.6 tests. The browser script checks the Voice diagnostics page and the demo default.
- New optional settings: `GNANI_STT_TIMEOUT_S` (20), `GNANI_TTS_TIMEOUT_S` (15), `GNANI_CONNECT_TIMEOUT_S` (5), all commented out in `.env.example`.

### Changed
- **The Gnani client keeps one pooled connection** instead of opening one per call (20 calls opened 20 connections before, 1 now, on the stand-in).
- **A call that was sent and got no answer in time is reported as `TIMEOUT` (HTTP 504) and is not repeated.** Before, it was repeated up to three times, so a hung service could hold a spoken order for
  up to 121.5 s at the defaults; now it is at most 20 s (speech to text) or 15 s (text to speech). Failures before the request was accepted, and `429`/`5xx`, are still tried up to three times,
  with waits of 0.25 s and 0.5 s (were 0.5 s and 1 s).
- **`GNANI_TIMEOUT_S` is now a ceiling** for the per-call limits. A `.env` that sets it above 20 gets 20 s for speech to text unless `GNANI_STT_TIMEOUT_S` is set too ([docs/UPDATING.md](docs/UPDATING.md)).
- **The Demo data switch starts off for a shop that has recorded orders of its own** (and on only for a shop with none). A choice the person made with the switch is kept. Nothing is deleted.
- **The first three Analytics tiles show the unfinished day beside their totals** ("Today so far: ₹6,435", or "This week so far", "This month so far"), only when that period has orders. The tiles still count complete periods only and the comparisons are unchanged; before, a shop on its first day read ₹0 and 0 orders above charts that showed that day's orders.
- `GET /api/sessions/{id}` includes `customer_id`; `api_calls` gains the `attempts` column (added automatically on start; old rows read as one try).
- `docs/openapi.json` regenerated (63 routes before, 66 now); the evaluation summary was rebuilt for the new version number (its accuracy figures are identical: 244 exact, 19 wrong product,
  21 not recognised, 16 asked which pack).

### Fixed
- **A recording with no speech could blank the open bill on the Order desk.** The reply to a silent recording had no bill in it. The server now returns the open bill with that reply, and the
  screen leaves the bill alone.
- **A hung speech service held a request for up to two minutes** and was reported as a network error (see Changed).
- **The Settings page could leave `.env` half-written** if the process died while rewriting it, and a Windows byte-order mark could hide the first key. The file is now replaced in one step, other lines are
  kept, and a byte-order mark is read correctly.

- **Voice diagnostics scrolled sideways on a phone** (found by the browser width sweep, not by a unit test): its tables now sit in the shared scroll wrapper, the settings table wraps long text and the three-column table's headings wrap. The width sweep now covers the page and a unit test checks the wrapper.

### Reviewed, no change needed
- **Processing stays on the event loop.** `process_turn` takes about 7 to 11 ms; moving it to a thread pool would remove the one-request-at-a-time property that makes pressing Confirm twice make
  one order. Documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Analytics already computes every figure (sales, orders, average bill, trends by day, week and month, top products, stock health, status mix, voice share, language mix, comparisons with the
  period before) from the database on each request, with no stored or typed-in numbers.

### Not done, on purpose
- **No live Gnani call, no real speech latency, no real accuracy, no microphone test, no Windows run.** The build environment cannot reach Gnani, has no key and no audio hardware.
- **No streaming claim.** The REST endpoints return finished results; the app does not pretend otherwise.
- No new dependency, no database reset, and no change to `.env`.

## 2.5.0 (11 Nov 2026)

Evaluation, visualisation and verification release. It adds one screen (AI performance), one report endpoint pair and a stock ledger view, fixes one product-matching defect, and
adds tests that pin down order integrity and error leakage. **No language was added and nothing was run against live Gnani**: every language is still "Not verified live".

### Added
- **AI performance** (`/performance`, signed-in people only): the evaluation of the language engine, read from `eval/results/evaluation_summary.json` through `GET /api/evaluation`.
  Metrics with dataset, method and interpretation; per-language results; a held-out-brand confusion matrix by category and the list of every wrong product; a language-label
  matrix; the robustness curve (precision, recall, F1 and the spread over five random seeds) and what each matching stage adds; typed-order and stock-guard results; the test and
  verification record; the stack and its implementation status; local response times. Anything that was not measured says "Not measured". Every table can be sorted, searched,
  paged and downloaded as CSV; every chart has a table view.
- **`scripts/build_evaluation_summary.py`**: builds that file from the sentence files and the code (about 16 s). `backend/tests/test_evaluation_summary.py` rebuilds it and fails if the
  stored numbers differ from what the code now produces, so a page or a report cannot show a number the code does not reproduce. It also fails if a speech-recognition, word-error-rate
  or speech-latency key appears, because none was measured.
- **`scripts/build_verification_summary.py`**: turns the saved test logs (JUnit XML, Vitest, build, browser runs, audits, parser check) into the "Test and verification record"
  rows, with "Not run" for anything without a log.
- **Stock movement.** `GET /api/analytics/stock-movement` reads the stock ledger (`stock_movements`): per product, opening, added, returned, sold, current and reorder status, plus
  value in and out per day. Shown on Analytics as a chart and a table. Seeded demo orders write no ledger rows, so a fresh database shows an empty table, and says why.
- **Order-status mix** on Analytics (confirmed, fulfilled, cancelled) with a table view.
- **`scripts/demo_activity.py`**: places a few real typed orders, two restocks and one cancellation through the API on a throw-away database, so charts and tables built from the
  ledger have real rows to show (used for the report's demo tables and screenshots).
- **`scripts/build_report.py`** and `docs/report/`: the project report is generated from the result files, so no number in it is typed by hand; it also draws its figures
  (needs `matplotlib`, which is not an app dependency). New: `docs/PROJECT_REPORT.md`, `.docx`, `.pdf` with 22 sections, 13 numbered figures and 11 numbered tables.
- New documents: `docs/INSTALLATION.md` (renamed from `INSTALL_WINDOWS.md`, links fixed) and the generated report in `docs/`.

### Fixed
- **A brand's pack-less alias belonged only to the pack imported first.** "amul butter" quietly became whichever Amul butter pack had been imported first, whatever else the shop stocked. Packs of the same brand now share the alias, so the parser sees several candidates and the dialogue asks which pack (`catalog_items.import_to_shop`; test `test_branded_nlu.py`). Held-out brand results moved from
  252 exact / 25 wrong product / 2 asked which pack (2.3.0 and 2.4.0) to **244 exact / 19 wrong product / 16 asked which pack**, with 21 not recognised in both. Existing shops keep the
  aliases they have; a shop created or re-imported on 2.5.0 gets the corrected ones.
- **The AI performance page scrolled sideways on a phone.** Found by the browser run's width sweep (up to 447 px too wide at 320 px): a filter row would not shrink below its content (`.toolbar .field`) and a long command in an empty-state message could not wrap. Both fixed in `app.css` and `ui.css`; the browser run was repeated on a fresh database (148 of 148).
- `scripts/benchmark_api.py` signs in (it needed to since accounts were added), sends the Origin header and the CSRF token, and covers the new endpoints. It places real orders, so it
  must only be pointed at a throw-away database; its docstring now says so.

### Reviewed, no change needed
- **Order integrity.** A line-by-line pass found no oversell or duplicate-order defect. New `backend/tests/test_order_integrity.py` (4 tests) pins it down, including two threads
  buying one unit and two simultaneous confirm presses. The reason the second press cannot double-save is that the handler runs on one event loop in one process; a multi-worker
  deployment would need a version column on the session row ([docs/SECURITY.md](docs/SECURITY.md), [docs/LIMITATIONS.md](docs/LIMITATIONS.md)).
- **Error leakage.** An unhandled exception returns a bare 500 with no traceback, path, exception text or key (test added).
- **Windows scripts.** Reviewed; three new structure tests (every `goto` has a label, every file a script points at exists, no script holds a key). Still **not run on Windows**.

### Changed in the tooling
- `scripts/e2e_browser.py`: new 2.5.0 checks (AI performance page, CSV download, stock movement, `/performance` in the width sweep) and a sign-in helper that waits out the server's per-minute limit on sign-in requests once before failing.
- `scripts/take_screenshots.py` makes the window as tall as the page up to 16,000 px (was 8,000), so the long AI performance page gets a full-height sidebar.

### Tests
- Backend 889 passed (2.4.0: 864), 95% line coverage. Front end 383 passed (2.4.0: 349), strict TypeScript and the production build clean. Browser run 148 of 148 checks, button and link audit 4 of 4. Browser runs, audits and the record by category:
  [docs/VERIFICATION_REPORT.md](docs/VERIFICATION_REPORT.md).

## 2.4.0 (11 Nov 2026)

Public-site redesign, typography first. **Only the front end changed**: no API route, schema, error code or database table is different (`docs/openapi.json`
differs from 2.3.0 in its version string alone), and the signed-in screens keep their layout. The palette and the one light theme are unchanged.
Live Gnani behaviour is still unverified for all eleven languages, as before.

### Changed
- **Type system.** Display headings are now set in **Newsreader** (a serif with an optical-size axis, SIL OFL 1.1, bundled as `@fontsource-variable/newsreader`; nothing is
  loaded from a font service), at weight 400 and tightened as they grow, with the Noto Sans families of each Indian script listed behind it so a Gujarati or Devanagari
  heading never falls back to a Latin serif. Text and controls stay in Geist. The title (`h1`) of every signed-in page, and of the sign-in, sign-up and legal pages, now
  uses the same serif at weight 500. Small group titles on the landing page went from weight 600 to 500. See [docs/DESIGN.md](docs/DESIGN.md).
- **Landing page rebuilt** (`pages/Landing.tsx`, `pages/landing/`, `styles/landing.css`): a 72 px bar; a hero headed "Commerce that understands every voice." with the eleven
  language names in their own scripts and the real dashboard screenshot; **five product areas, each with its own composition** (typeset sample sentences with the item and quantity
  underlined, four spellings of one item meeting at "Milk", and three arrangements of real screenshots); **How it works**, the live language demo with a four-step strip
  filled in from the parser's real answer and a note that it is a demonstration on typed text; **Languages**, an eleven-row ledger that says what has and has not been
  checked; **Technology** with a four-part architecture line and the real stack; Security and trust; Why SWARA AI; the FAQ; a closing call to action beside the contact form;
  a footer with a link to the API reference (`/docs`).
- Copy uses typographic quotes and apostrophes. The page's meta description now matches the hero.

### Removed
- The product-tour tabs, the six feature cards, the use-case and benefits sections and the "About" navigation entry (the About statement stays, under the hero). No feature of
  the app was removed. No GitHub link was added, because the project has no public repository to point to.

### Tests
- New `backend/tests/test_landing_design.py` (10 tests) reads the real stylesheets and fonts: serif tokens with Indic fallbacks, bundled fonts and no font-service URL, no bold
  headings, no uppercase labels, italic accents, glass or decorative gradients, motion limited to one rise and respecting reduced motion, only palette colours.
- `Landing.test.tsx` rewritten for the new structure (showcase, language ledger, demo strip, technology flow, no unverified claims). The browser run checks the loaded fonts,
  that every font file came from this server, the five showcase areas, the language ledger and the demo strip.
- **Test fault fixed:** the Marathi Order desk check could count the bill lines before the answer arrived (the Confirm order button exists, disabled, on an empty bill). It now waits.
- Totals for this release: 864 backend tests (95% coverage), 349 frontend tests, 139 browser checks plus a 4-check button and link audit; all passed on the final tree (logs in `docs/test-results/`).

## 2.3.0 (10 Nov 2026)

Multilingual voice expansion: the Order desk now offers the ten languages Gnani documents for Prisma v2.5 and Timbre v2.5, plus Hinglish. The original
four languages (Gujarati, Hindi, English, Hinglish) keep working as before. **No language, old or new, was run against live Gnani: the build environment
had no key and no route to Gnani.** Every Gnani response in the automated tests is simulated. See [docs/LANGUAGES.md](docs/LANGUAGES.md).

### Added
- **Seven languages:** Marathi (`mr-IN`), Bengali (`bn-IN`), Tamil (`ta-IN`), Telugu (`te-IN`), Kannada (`kn-IN`), Malayalam (`ml-IN`), Punjabi (`pa-IN`),
  each with its Prisma code, Timbre language value, default voice, text-understanding pack (number words, units, product names, corrections, reply
  templates) and Order desk wording. The language packs were written for this release and unit-tested; **no native speaker has reviewed them** and they have
  not been compared with real Prisma output.
- **Central language registry** (`backend/app/languages.py`): the one table the API, the voice code, the verification script, the Settings page and the
  tests read. Codes and the 42 Timbre v2.5 voice names come from Gnani's documentation (read on 10 Nov 2026) and are checked by a test. Adding a language is
  one entry plus one pack; switching one off is `DISABLED_LANGUAGES=mr,bn` or a switch in Settings.
- **Language selector** on the Order desk: a button showing the current language in its own script and Gnani code, opening a list of every language with an
  honest status ("Not verified live", "Live checked", "Live check failed", "Simulated only", "New in 2.3"). A switched-off language is listed but cannot be
  chosen; Auto-detect says why it is unavailable on Prisma v2.5. New fonts: Noto Sans for Bengali, Tamil, Telugu, Kannada, Malayalam and Gurmukhi.
- `GET /api/languages` (registry, modes, switched-off list, live verification), `language` hint on `/api/text/turn` and `/api/text/parse`, per-language voices
  and `disabled_languages` in `PUT /api/settings`, `?language=` on `POST /api/settings/test-gnani`. New error codes `BAD_LANGUAGE`, `LANGUAGE_DISABLED`,
  `AUTO_DETECT_NEEDS_V3`, `BAD_VOICE`, `LANGUAGE_REQUIRED` ([docs/API.md](docs/API.md)).
- **Settings → Languages and voices** (owner): switch languages on and off, choose a voice per language from the documented list, and run a two-call test
  for one language, labelled as a loopback.
- **Independent live verification** (`scripts/verify_gnani.py`, `verify_gnani.bat`): for every language four separate checks, `tts`, `stt_code`,
  `stt_loopback` and, with a recording you supply at `eval/samples/<key>.wav`, `stt_human`. Results go to `eval/results/live_verification.json`,
  which the app reads. A run that used a simulated transport never writes that file, and a simulated file is never shown as a pass.
- Language-aware product names on the bill (the name in the bill language where the product has one), language names and units in all 11 languages in the
  frontend, language filters on Orders, Customers and the Account preference for all 11, and an "Other languages" colour in the language chart.

### Changed
- **`auto` and `mixed` on Prisma v2.5 are now refused** with `AUTO_DETECT_NEEDS_V3` (HTTP 422, or a socket error 1003). Before this version they were quietly sent as
  Gujarati. Gnani documents no auto-detect for v2.5, so the app no longer pretends. On Prisma v3.0 they work as before (untested live).
- An unknown or switched-off language is refused with a clear error everywhere instead of falling back to another language.
- The realtime WebSocket request carries the language in both `lang_code` and `language_code`, because Gnani's documentation names the header both ways.
- Prisma `bias_list` words are taken in the script of the chosen language (it used to be Latin/Gujarati only).
- The landing page lists all eleven languages, keeps the four proven ones apart from the seven new ones, and says plainly that the new ones are unit-tested
  but not native-reviewed and not checked against real recordings.
- `verify_gnani.bat` now checks eleven languages (about 33 calls), not four (8).

### Fixed (found while verifying)
- The open language list was cut off by the Order-desk card and ran 2 px past the screen edge on a phone; fixed, with a browser check for the phone width.
- A test of the analytics demand trend assumed no product's week-on-week change reaches 1000%; the seeded demo data made that false in the hours after midnight IST. The code was right; the test now asserts what the code guarantees.

### Measured (offline, text only)
- The 288-utterance staples set is unchanged: 100% line F1 and utterance exact, 0 failures, nothing in it is a language the packs add to.
- Held-out branded products (300 templated sentences): **252 exact (84.0%), 25 wrong product (8.3%), 21 not recognised, 2 ambiguous**; 2.2.0 was 251 / 23 / 24 / 2.
  Compared sentence by sentence: "Parle-G" is no longer read as "Parle" plus grams (one sentence became exact; two aimed at another pack size of the same brand now get
  the 100 g pack). A first 2.3.0 run had 29 wrong (9.7%) because short Latin brand words ("Nero", "Raw", "Day", "pohe") sounded like a staple's name in a new
  language; Latin words now reach a native-script name that exists only in a new pack by sound only with a 5+ letter skeleton (`Lexicon.PACK_SOUND_MIN_SKEL`, with a regression test).
- Parser latency with the larger vocabulary: p50 0.15 ms, p95 0.23 ms over 1,440 calls (2.2.0: 0.11 / 0.17 ms). HTTP latencies were not re-run.

### Not verified
- Live Prisma and Timbre for **every** language. Real recognition of a person speaking any of the seven new languages. Native-speaker review of their wording.
- Whether Gnani honours `lang_code` or `language_code` on the realtime socket (both are sent).
- Prisma v3.0 auto-detect and code-mix.

## 2.2.0 (10 Nov 2026)

SWARA AI is now presented and documented as an independent product. No feature was removed.

### Product and wording
- Removed the wording that tied the project to a one-off programme (in the product, the landing page, the README, the docs, the code comments,
  the project report in Markdown, PDF and DOCX, and the built front end). Two documents that were not about the product were deleted;
  `docs/DEMO_VIDEO_SCRIPT.md` is now `docs/DEMO_WALKTHROUGH.md`, reworded as a product demo.
- Kept, on purpose: the technical credits for Gnani Prisma and Timbre, the Gnani API integration notes, and the statement that SWARA AI is
  not affiliated with or endorsed by Gnani.ai (landing-page footer and README). The landing footer now says which model does which job.
- New guard test `backend/tests/test_independent_product.py` fails if that wording comes back in any text file, in `frontend/dist`, or in the
  report DOCX, and checks that the Gnani credits and the non-affiliation line are still there.
- Light theme only is unchanged and still enforced by `test_light_only.py`.

### Security
- The web server's access log no longer records one-time reset and verification tokens: `?token=...` is written as `token=[redacted]`
  (`RedactTokens` in `backend/app/security.py`). Found by reading a real server log; covered by a test.

### Fixed
- **`/docs` was a blank page.** FastAPI's built-in Swagger page needs a script from a CDN and an inline script, both of which the app's strict
  content-security policy (rightly) refuses. It is replaced by a small local API reference (`backend/app/apidocs.py`,
  `backend/app/static/api_reference.js`) that lists every route from `/openapi.json`, with a filter box. It loads nothing from the internet.
  `/redoc` now redirects to it. `API_DOCS=false` switches the page and the schema off.

### Windows scripts (written on Linux, **not run on Windows**)
- `setup.bat` checks that Node.js is new enough for the front-end build (20.19+ or 22.12+) and otherwise falls back to the prebuilt
  `frontend\dist`, saying so, instead of failing in the middle of `npm`.
- `start.bat` says clearly when port 8000 is already in use and how to pick another port, and notes when `.env` is missing.

### Documentation
- New: `docs/DATABASE.md`, `docs/TROUBLESHOOTING.md`, `docs/DEVELOPMENT.md`, `docs/GNANI_SETUP.md` (how to configure the key and prove it works),
  `THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`, `docs/VERIFICATION_REPORT.md`.
- Updated: README, INSTALL_WINDOWS (Node and port checks, one block with every command), API, SECURITY, DEPLOYMENT (`API_DOCS`), ARCHITECTURE,
  TESTING, PROJECT_REPORT, `.env.example`, `docs/openapi.json` (regenerated).

### Developer experience
- The Vite dev server also proxies `/docs`, `/openapi.json` and `/api-reference.js`, so the API reference works from `http://localhost:5173`.

## 2.1.0

- Export CSV on Orders (current filter), Inventory and Customers (owner only): UTF-8 with a byte-order mark, formula-injection guard, IST times,
  a 20,000-row cap that says when it truncates.
- Print bill from an order's drawer.
- Shop name editable by the owner in Settings (shown in the sidebar and on printed bills).
- Setup checklist on a new owner's dashboard, with ticks computed from the shop's data.
- "Security and trust" section on the landing page, including what SWARA AI does not claim.
- Light-only polish pass: landing pictures and documentation screenshots retaken from the light-only app.

## 2.0.0 and earlier

- Real accounts (owner and staff roles enforced by the server), a public landing page, sign-in/sign-up/reset/verify flows, a security review.
- Renamed to SWARA AI with a new logo kit (see [docs/BRANDING_AUDIT.md](docs/BRANDING_AUDIT.md)).
- The voice-ordering core (Gnani Prisma speech recognition, Timbre spoken replies, a deterministic parser for Gujarati, Hindi, English,
  Hinglish and mixed speech), inventory and stock control, orders, customers, analytics and the 5,325-item public product catalogue.
  Earlier version-by-version history was not kept.
