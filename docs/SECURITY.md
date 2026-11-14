# Security review

This is the record of a security review done while turning SWARA AI into a signed-in, multi-user product. It lists what was found, what was changed,
what was **checked by running something** and what is **left as a known risk**. It is not a penetration test and not a certification. Nobody outside the
project has reviewed it.

## What we protect, and from whom

- **The shop's data**: orders, customers (names and phone numbers if recorded), prices, stock, and the person accounts.
- **Secrets**: the Gnani API key and the SMTP password (in `.env`, server side only), password hashes, session cookies.
- **Money**: a stranger must not be able to burn the Gnani credits (they are the shop's cost), or change prices and stock.
- Threats considered: a stranger on the internet, a signed-in staff member doing more than they should, another website tricking a signed-in browser,
  a stolen copy of the database or backup, a typo-squatting or vulnerable dependency.
- Not considered: a malicious owner, someone with administrator access to the server, physical access, denial-of-service at network scale.

## What was found and fixed

| # | Finding in the previous version | Change |
|---|---|---|
| 1 | Almost every API route was open to anyone who could reach the port; writes were guarded only by an optional shared `ADMIN_TOKEN` | Real accounts. Every route needs a session except an explicit short list (below). Owner-only routes check the role on the **server**. The shared token is removed. `test_route_inventory_every_api_route_is_guarded_or_deliberately_public` fails the build if a new route is added without a decision. |
| 2 | No CSRF defence | A per-session CSRF token is required on every `POST`/`PUT`/`PATCH`/`DELETE` (`403 CSRF_FAILED` otherwise), and browser requests whose `Origin` is another site are refused (`403 BAD_ORIGIN`). Cookies are `SameSite=Lax`. |
| 3 | The live-voice WebSocket accepted anyone, so a stranger could spend Gnani credits | The handshake needs the same session cookie, and refuses a foreign `Origin`. |
| 4 | No brute-force protection (there was nothing to brute-force) | Per-address and per-IP sign-in lock-out, a per-IP limit on the sign-in family and the contact form, uniform "Incorrect e-mail or password" (same text and similar time for unknown addresses), single-use hashed reset tokens, and at most 3 reset requests per address per 15 minutes. |
| 5 | No security headers; an inline script in `index.html` made a strict policy impossible | A content-security-policy without inline scripts, `nosniff`, `DENY` framing, `no-referrer`, a narrow `Permissions-Policy`, `no-store` on API responses, HSTS on https. The theme script is now an external file. |
| 6 | Unknown paths with a file extension (`/assets/missing.js`) returned the app's HTML with status 200 | They return `404`. (Page routes still fall back to the app so refresh works.) |
| 7 | `npm audit` reported **8** vulnerabilities (2 critical, 1 high, 5 moderate), among them `react-router` in the shipped code | `react-router-dom` 6.30.6 → 7.18.5, `vite` 5.4 → 7.3.8, `vitest` 2.1 → 4.1.12 (and `@testing-library/dom` added as an explicit dev dependency). `npm audit`: **0 vulnerabilities**. 247 frontend tests, the type check, the production build and the browser run were repeated on the new versions. Raises the Node version needed to *rebuild* the front end to 20.19+ / 22.12+ (running the app needs no Node). |
| 8 | The landing-page "try it" endpoint (`POST /api/text/parse`) answers anyone with this shop's item names, prices and stock | Rate-limited, stores nothing, and now switchable: `PUBLIC_DEMO=false` makes it require a sign-in (`403 DEMO_OFF`); the landing page then says the demo is switched off. The default stays `true` because the supplied database is a synthetic demo shop. **A real shop should set it to `false`.** |

## Added in 2.1

- **CSV exports** (`/api/orders|inventory|customers/export.csv`). A cell that starts with `=`, `+`, `-` or `@` (or a tab or carriage return) is written with a leading apostrophe, so a customer or product name typed as `=HYPERLINK(...)` cannot run when the file is opened in Excel or Sheets. The customer file (names and phone numbers) is owner-only and refused for staff with `403`; every export is `no-store`, goes through the normal session and rate limit, and is capped at 20,000 rows. Covered by `backend/tests/test_exports_and_shop.py`, and in a real browser by `scripts/e2e_browser.py`.
- **The shop name** is written to `.env`, so what may be typed is narrow: letters, marks and digits in any script plus ``space & ' . , - ( ) / + @``, 2 to 80 characters. `#`, quotes, `$`, backslashes and line breaks are refused with a message, because in a dotenv file they would start a comment, end a value, expand a variable or add a setting. Only the owner may change it.
- **The landing page's Security section** is checked against the code: `backend/tests/test_landing_claims.py` fails if a number it quotes (five tries, 15 minutes, 12 hours, 2 hours idle) stops matching the defaults in `config.py`, or if a claimed behaviour (scrypt, HttpOnly cookie, other sessions ended on a password change, owner-only customer routes) is removed.

## Added in 2.5 (order integrity, error leakage, the new evaluation route)

A line-by-line pass over the order path found no oversell or duplicate-order defect, so nothing in the order code was changed; the checks below are now tests rather than reading.

- **Stock can only be sold once.** `create_order` takes each line with `UPDATE ... WHERE stock >= qty`, puts back any lines it already took if one fails, and writes the order and its ledger rows in the same commit. `test_two_buyers_cannot_both_take_the_last_unit` starts two threads with separate database sessions against one unit on the shelf: exactly one order is saved, the other is refused as `InsufficientStock`, stock ends at 0 and the ledger has one `order` row.
- **Pressing Confirm twice makes one order.** After the bill is saved the dialogue is in the `completed` phase, so a second "confirm" or "yes" starts nothing (`test_pressing_confirm_twice_makes_one_order_and_takes_stock_once`, `test_saying_yes_again_after_the_order_is_saved_does_not_repeat_it`). Two presses arriving at the same moment also made one order (`test_two_simultaneous_confirm_presses_on_one_bill_make_one_order`; 15 extra trials in a throw-away script gave one order every time). **Why that holds is a limit, not a lock:** the confirm handler is `async` and does its database work on the single event loop, so two requests are handled one after the other. There is no row lock or version number on the session record. Run one server process (the supported setup). With several worker processes, two presses could in principle both read the "confirming" state; stock would still never go negative, but two orders could be saved for one bill. A deployment with several workers needs a version column on the session row first.
- **A crash shows nothing.** An unhandled exception returns a bare `500` with no stack trace, file path, exception text or API key (`test_an_unexpected_server_error_shows_no_traceback_path_or_key`). Handled errors use the `{detail: {code, message}}` envelope.
- **`GET /api/evaluation`** serves the stored evaluation summary to signed-in people only (it is in the route inventory test). It reads one fixed file path chosen in code, takes no input from the request, and returns `available: false` when the file is missing or is not valid JSON.
- **CORS** allows only the configured origins and no credentials (`test_cors_allows_only_configured_origins`); a cookie-carrying request from another site is refused by the origin guard.

## Added in 2.6 (voice path, diagnostics, updating)

Found and fixed in this release's review (the first one is a defect; the rest are hardening):

- **A recording with no speech could blank the open bill.** The reply to a silent recording carried no bill, and the Order desk drew it as an empty one. The server now returns the open bill
  with that reply and the screen leaves the bill alone (`test_a_recording_with_no_speech_returns_a_full_reply_and_leaves_the_bill_as_it_was`, `OrderDesk.voice.test.tsx`).
- **A hung speech service held a request for up to two minutes** (three tries of the 40 s limit), and was then reported as a network error. A call that was sent and got no answer now stops
  after its own limit (20 s speech to text, 15 s text to speech) as `TIMEOUT`, is not repeated, and says the bill has not changed.
- **`.env` could be left half-written.** The Settings page rewrote `.env` in place, so a crash or full disk part-way through could lose the Gnani key, and a Windows byte-order mark could hide the first
  key. The file is now written to a temporary file next to it and renamed over it in one step; other lines and comments are kept; a failure leaves the old file and no temporary file
  (`TestEnvWriter`).

New surfaces, and how each is bounded:

- **`POST /api/turns/{id}/speak`** speaks the text the server **stored** for that assistant turn. It accepts no text from the caller, so it cannot be used to read arbitrary text out on the shop's Gnani
  credits (`test_speak_reads_out_what_the_server_stored_never_what_the_caller_sends`). It refuses a customer turn or an unknown id (404) and a reply older than an hour (410), needs a session, is covered by the
  per-device rate limit and the hourly call budget, and repeating it is served from the audio cache.
- **`POST /api/turns/{id}/client-timing`** stores times the browser measured. It refuses unknown fields, negative or absurd values and an unknown endpoint name (422), and only accepts assistant turns. The values
  are browser-reported and shown as such; a signed-in person could post false ones, which would only distort the diagnostics page, never an order.
- **`GET /api/diagnostics/voice`** is owner-only (anonymous 401, staff 403, both tested), reads rows the app already wrote, never returns the key, and is on the route inventory test's guarded list.
- **The open-bill memory** keeps only a session id in the tab's `sessionStorage` (cleared when the tab closes, ignored after six hours or if it is not the expected shape). The bill itself stays on the server
  behind the sign-in; a stored id on its own opens nothing.
- **Updating** never reads, prints or requests the Gnani key, never overwrites `.env` and never resets the database; the only schema change is one added column ([UPDATING.md](UPDATING.md)).

## Added in 2.7 (payments)

The payment module has its own report: [PAYMENT_SECURITY_AUDIT.md](PAYMENT_SECURITY_AUDIT.md). In short: Razorpay secrets live only in `.env` and are never sent to the browser, shown or logged; a payment is marked paid only by the server, after a valid signature **and** a lookup at Razorpay, with the amount, currency and order compared with what the server holds; the webhook is accepted only with a valid signature over the raw body, each event once; refunds, payment analytics and the UPI settings are owner only; the content-security policy lets Razorpay's domains in only while Razorpay is switched on; and live mode needs live keys **and** `PAYMENT_MODE=live`. **Not verified:** anything against the real Razorpay service. **Known residual risk:** the webhook endpoint is public and not rate limited (it is protected by its signature check); put a proxy limit in front of it if the app is exposed to the internet.

## Review checklist (2.5.0): each topic, where it lives, how it was checked

This is the whole review in one table, so a reader can see what was looked at. "Tested" means an automated test; "browser" means the real-browser run; "read" means the code was read and no test pins it down.

| Topic | What the code does | How it was checked |
|---|---|---|
| Password hashing | scrypt (RFC 7914), a per-password salt, constant-time comparison; an unknown e-mail costs the same time as a wrong password | tested (`test_auth.py`) |
| Authentication and sessions | A random secret in an HttpOnly cookie, only its SHA-256 hash stored; absolute and idle expiry; sign-out ends the server-side session; a password change ends the other sessions | tested; browser (cookie flags, expiry, sign-out then back button) |
| Authorisation, protected routes | Every API route needs a session except a short deliberate list; owner-only routes check the role on the server | tested (the route inventory test fails if a route is added unguarded); browser (a staff account gets 403) |
| Input validation | Pydantic models; unknown fields are refused on sign-up (a role cannot be smuggled in); quantities, stock and prices are checked (more than stock is refused, not clamped); the shop name is restricted because it is written to `.env` | tested |
| SQL injection | SQLAlchemy with bound parameters. The one string-built statement is the start-up schema upgrade (`ALTER TABLE ... ADD COLUMN` in `db.py`), whose table, column and type come from a constant in the code and never from a request | tested (injection strings are stored and returned as text); read (a search for raw SQL in `backend/app` found only that one) |
| Cross-site scripting | The front end renders what people type as text (no `innerHTML`, `dangerouslySetInnerHTML`, `eval`); a content-security-policy without inline scripts | tested (a script string comes back as data); read; the landing and app pages checked for inline scripts in the browser run |
| CSRF and CORS | Per-session CSRF token on every write, Origin check, `SameSite=Lax`; CORS only for configured origins, no credentials | tested |
| Rate limiting and lock-out | Per-address and per-IP lock-out on failed sign-ins; a per-IP limit on sign-in-type requests (20 a minute by default) and the contact form; counters live in one process's memory | tested; browser (lock-out; the run itself met the limit once) |
| Environment and secrets | The Gnani key and SMTP password only in `.env` or the server-side settings; never in a response, a log line, the front end or a screenshot; the key is write-only on the Settings page | tested (the key never appears in any GET, in `repr` or in settings output); a secrets scan of the tree (docs/VERIFICATION_REPORT.md) |
| CSV injection | A cell starting `=`, `+`, `-`, `@`, tab or carriage return is written with a leading apostrophe; the customer export is owner-only | tested; browser (a real download) |
| Uploads | Audio is identified from its first bytes, not the client's `Content-Type`; a size limit (413), a format check (415), a duration limit and WAV-only for the Noise lab | tested (`test_api_voice.py`) |
| Transactions and inventory consistency | An order's stock decrements, the order and its ledger rows are one commit; each line is taken with `UPDATE ... WHERE stock >= qty`; a cancel returns stock once | tested (`test_order_integrity.py`, `test_api_admin.py`) |
| Duplicate orders | After the bill is saved the dialogue is `completed`, so a second Confirm starts nothing; two simultaneous presses make one order | tested. **Relies on one event loop in one process** (see below) |
| Error leakage | An unhandled error returns a bare 500; handled errors use one envelope with a code and a message | tested |
| Dependencies | `npm audit` and `pip-audit` | run (docs/test-results/dependency_audits.txt) |

## Deliberately public endpoints

`GET /api/health` (app name, version, database ok, number of products, whether a Gnani key is configured; never a key), `GET /api/auth/config` and
`GET /api/auth/session` (what the sign-in screens need), `POST /api/auth/{signup,login,logout,forgot,reset,verify-email,resend-verification}` (each guards
itself), `POST /api/contact` (rate limited, with a hidden honeypot field), `POST /api/text/parse` (see finding 8), and, from 2.7.0, `POST /api/payments/webhooks/razorpay` (no session; refused unless the Razorpay signature over the raw body is valid, and refused outright while no webhook secret is set). Everything else answers `401` without a session.

## What was checked by running it

- **Backend tests**: the accounts and security tests are in `tests/test_auth.py`, `tests/test_security.py` and `tests/test_scripts.py`. They cover the route
  inventory, owner-only refusal for staff and visitors, CSRF and origin refusal, WebSocket refusal, SQL-injection and script strings stored as plain text, that the
  API key never appears in any `GET` response, the uniform error envelope, the headers, HSTS and the `__Host-` cookie on https, path traversal on static files.
- **Real browser** (`scripts/e2e_browser.py`, Chromium, throw-away database): cookie flags as seen by a browser, the session cookie not readable from
  JavaScript, owner-only calls refused for a staff account with `403`, protected pages refused and redirected, sign-out then the back button, lock-out, an off-site
  `?next=` ignored, session expiry. Console and network were watched throughout: no console errors or warnings, no failed requests, no unexpected HTTP errors.
- **Dependencies**: `npm audit` 0 vulnerabilities (all dependencies, including development tools), and `pip-audit -r backend/requirements.txt` "No known
  vulnerabilities found", both run on the day of packaging. Advisory databases change daily; re-run both before you deploy. The backend requirements are
  version ranges, not a lock file, so a fresh install may resolve newer versions than the ones tested; `docs/TESTING.md` lists the versions that were.
- **Response headers** inspected on the running server for the landing page, an app route, an API route and a built asset.
- **Unsafe browser APIs**: the front end has no `dangerouslySetInnerHTML`, `innerHTML`, `eval` or `new Function` outside tests, so what people type (a contact message,
  a customer name) is always rendered as text.

## Known risks and trade-offs (not fixed; read before you deploy)

1. **First-owner takeover.** With the defaults, whoever creates the first account is the owner. On a reachable server, create the owner first or set `OWNER_EMAIL`.
2. **Open sign-up by default.** `ALLOW_SIGNUP=true` lets anyone make a staff account (which can take orders and read orders, customers and stock). Set it to `false`
   when your staff exist.
3. **Sign-up reveals that an e-mail address is registered** ("an account with this e-mail already exists"). Sign-in and forgot-password do not. This is the usual trade-off
   against people being unable to tell why sign-up failed; removing it would need e-mail verification to be mandatory, which needs working e-mail.
4. **Lock-out and rate-limit counters are in memory, in one process.** A restart clears them; several processes each have their own. An attacker who can make many
   different addresses fail from one IP is stopped by the per-IP limit, but a distributed attack is not. A visitor can also lock a *known* address out for 15 minutes
   by guessing wrongly (a denial-of-service trade-off every lock-out has).
5. **No two-factor sign-in, no password-breach check, no sign-in alerts, no audit log** of who changed what. Passwords are checked only against a built-in list of common ones.
6. **No e-mail change flow.** A person's e-mail address cannot be changed in the app; there is no way to add or remove people from the app other than turning accounts on or
   off (`create-staff` from the command line adds them).
7. **The contact inbox has no size limit or clean-up.** Each message is capped at 2,000 characters and the form is rate limited, but nothing deletes old messages.
8. **Style policy is `'unsafe-inline'`** (React and the charts write `style` attributes). Scripts are not affected.
9. **Secrets in `.env` are plain text.** Normal for this kind of local tool; protect the file (see `DEPLOYMENT.md`). The Settings page can write the Gnani key into `.env`
   (owner only, write-only, never read back).
10. **Session cookies are not bound to an IP or device**, so a stolen cookie works until it expires or is revoked. The Account page lets a person end other sessions.
11. **No external review, no fuzzing, no automated scanner run** (OWASP ZAP and similar were not used).
12. **Downloaded CSV files are outside the app's control.** The customer export holds phone numbers. It is owner-only, but nothing records who exported what (there is no audit log).
13. **Server logs contain IP addresses** for sign-ups and failed sign-ins. The app's code does not log passwords or session cookies (checked by reading the code, not by an automated scan of every log line), and the web server's access log writes the address of a reset or verification link with `token=[redacted]` (a log filter in `app/security.py`, covered by `test_one_time_links_are_redacted_in_the_access_log`). The filter covers uvicorn's access log only; a reverse proxy in front of the app keeps its own access log and must be configured to drop query strings for `/reset-password` and `/verify-email`.

## Reporting a problem

There is no public security contact and no bounty yet. Before SWARA AI is offered to shops other than your own, publish a monitored address for vulnerability reports and put it here. Until then, report a problem to whoever runs the installation (the owner).
