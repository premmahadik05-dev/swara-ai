# Accounts and sign-in

SWARA AI has real accounts. Every page of the app except the landing page, the Terms, the Privacy page and the sign-in screens
needs a signed-in person, and the server enforces it on every API route. The browser does not decide who is signed in; it only
shows what the server says.

This page says what exists, how to set it up, what is **not** built, and what was and was not checked.

## What exists

| Screen | Address | What it does |
|---|---|---|
| Sign up | `/sign-up` | Name, e-mail, password (strength guide, show/hide), confirm, Terms checkbox. Ends on a "Your account is ready" screen that says which role the person got. |
| Sign in | `/sign-in` | E-mail, password (show/hide), "Keep me signed in on this device for 30 days", a link to forgot-password. Returns the person to the page they asked for (`?next=`). |
| Forgot password | `/forgot-password` | Asks for an e-mail address. Sends a link **only when e-mail is set up**; otherwise says so plainly. |
| Reset password | `/reset-password?token=...` | Choose a new password from an e-mailed link (one use, 1 hour). Ends every session of that person. |
| Verify e-mail | `/verify-email?token=...` | Confirms an address from an e-mailed link (one use, 24 hours). |
| Account | `/account` | Name, change password, the devices signed in (with "sign out" per device and "sign out everywhere else"). The owner also sees the team (turn people on or off) and the contact inbox. |
| Sign out | sidebar button | Ends the server-side session and clears the cookie. |

Protected routes send a visitor to `/sign-in?next=<where they were going>`. An off-site `next` value is ignored. When a session ends
while the app is open (expired, signed out on another device, account turned off) the next request returns `401`, the app signs the
person out and the sign-in page says "Your session has ended".

## One shop, two roles

SWARA AI is a **single-shop** application: one database is one shop. There is no multi-tenant separation, and there are no
organisations. People have one of two roles.

| | Owner | Staff |
|---|---|---|
| Take orders (typed or voice), edit the open bill, confirm | yes | yes |
| See dashboard, orders, customers, inventory, analytics, catalogue | yes | yes |
| Add or edit products, restock, change prices | yes | no |
| Mark orders fulfilled or cancelled | yes | no |
| Add or edit customers | yes | no |
| Import catalogue items into the shop | yes | no |
| Settings (Gnani key, voices, models) | yes | read only |
| Team list, turn accounts on or off | yes | no |
| Contact-form inbox | yes | no |
| Own profile, password, devices | yes | yes |

The UI hides what a role cannot use, but that is only a convenience: the server refuses with `403 OWNER_ONLY` regardless. The
real-browser run checks this (a staff account's team request is answered `403`).

**Who becomes the owner.** By default the first account created is the owner (fine on your own computer). If `OWNER_EMAIL` is set,
only an account with exactly that address becomes the owner and everyone else is staff. There is only ever one owner.

> **If this server is reachable from the internet**, do not leave the first-owner rule to chance: whoever opens the sign-up page
> first becomes the owner. Create the owner yourself right after the first start, or set `OWNER_EMAIL` before the first start.

**Who may sign up.** `ALLOW_SIGNUP=true` (default) lets anyone who can reach the page make a staff account. For a shop that does not
want that, set `ALLOW_SIGNUP=false`: the form closes as soon as an owner exists (before that, it stays open so the owner can be
created), and the owner adds staff from the command line:

```
backend\.venv\Scripts\python.exe scripts\auth_admin.py create-staff --email counter@yourshop.in --name "Counter Staff"
```

(the password is asked for on the terminal and is never echoed or accepted as an argument). There is no "invite by e-mail" or "add a
person" screen in the app; that is a known gap, listed in `LIMITATIONS.md`.

## How a session works

- **Cookie.** `swara_session` (`__Host-swara_session` when the site is served over https). `HttpOnly`, `SameSite=Lax`, `Path=/`, and
  `Secure` when `PUBLIC_URL` starts with `https://` (or `COOKIE_SECURE=true`). The cookie holds a random secret; the database stores only
  its SHA-256, so a copy of the database cannot be turned back into a working cookie.
- **Lifetimes.** A normal session ends 12 hours after sign-in or after 2 hours without use, whichever comes first. With "Keep me signed in":
  30 days, or 7 days without use. All four numbers are settings (`SESSION_HOURS`, `SESSION_IDLE_MINUTES`, `REMEMBER_DAYS`, `REMEMBER_IDLE_DAYS`).
  A normal session is a *session cookie* (gone when the browser closes); a remembered one is a persistent 30-day cookie.
- **CSRF.** Each session has its own random token. Every `POST`, `PUT`, `PATCH` and `DELETE` to a protected route must send it in the
  `X-CSRF-Token` header (the app does this), or the server answers `403 CSRF_FAILED`. On top of that, a browser request whose
  `Origin` is another website is refused (`403 BAD_ORIGIN`), for the sign-in screens as well.
- **Sign out** revokes the session row on the server (not just the cookie in the browser). Changing or resetting a password revokes
  every other session of that person.
- **WebSocket** (`/ws/voice`) checks the same cookie during the handshake. No valid session, no voice proxy, and no Gnani spend.
- **Expiry** is decided by the server using timestamps in the `auth_sessions` table. A request with an expired session gets
  `401 SESSION_EXPIRED`; with no or an unknown session, `401 NOT_AUTHENTICATED`.

## Passwords

Hashed with scrypt from the Python standard library (no extra dependency): a random salt per password, cost `N=2^15, r=8, p=3`
(settings `SCRYPT_LOG2_N`, `SCRYPT_P`; the cost is stored with each hash so it can be raised later). Plain passwords are never stored or
logged.

Rules, enforced by the **server** (the strength meter on the page is only a guide): at least 10 and at most 128 characters; no leading or
trailing spaces; not on the built-in list of very common passwords; at least four different characters; must not contain the e-mail name or
equal the person's name. There is no forced "one capital, one symbol" rule, because long passwords are stronger than clever ones. There is
**no check against leaked-password databases** (that needs an outside service), and **no two-factor sign-in**.

## Brute-force protection

- Sign-in, sign-up, forgot/reset, resend-verification and the contact form share a per-IP limit (`AUTH_RATE_PER_MINUTE`, default 20 a minute).
- After 5 wrong passwords for one e-mail address, or 25 from one IP address, further sign-ins are refused for 15 minutes, **even with the
  right password** (`LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_MINUTES`). A successful sign-in clears that address's count.
- Wrong password and unknown address give the **same** message and take comparable time (a dummy hash is computed for unknown addresses).
- **These counters live in the memory of one server process.** A restart clears them, and running several copies of the server gives each its own
  count. For a single shop on one process this is fine; see `DEPLOYMENT.md` for what to do otherwise.

## E-mail: what needs it, and how to set it up

E-mail is **optional**. Without it the app works completely, and says honestly what it cannot do:

| Feature | With SMTP set up | Without SMTP |
|---|---|---|
| Verification e-mail at sign-up | Sent; sign-in is refused until the address is confirmed (unless `REQUIRE_EMAIL_VERIFICATION=false`) | Not required (it could never be completed) |
| Forgot password | A one-use link valid for 1 hour is e-mailed | The page says "This server is not set up to send e-mail, so no link was sent. Ask the shop owner to reset the password." The owner runs `auth_admin.py reset-password`. |
| Contact-form messages | Saved, and also e-mailed to `CONTACT_TO` if set | Saved; the owner reads them in Account → Messages. The form tells the sender "saved on this server". |

**Setting it up.** In `.env` set all of these (SMTP counts as configured only when `SMTP_HOST` **and** `SMTP_FROM` are filled in):

```
SMTP_HOST=smtp.yourprovider.com
SMTP_PORT=587
SMTP_USER=your-smtp-username
SMTP_PASSWORD=your-smtp-password-or-app-password
SMTP_FROM=SWARA AI <no-reply@yourdomain.com>
SMTP_SECURITY=starttls
PUBLIC_URL=https://your-real-address
CONTACT_TO=owner@yourdomain.com
```

- `SMTP_SECURITY`: `starttls` (port 587, the usual choice), `ssl` (port 465), or `none` (only for a mail catcher on your own computer).
- `SMTP_FROM` must be an address your provider allows you to send from; most providers reject others. For mail to reach inboxes rather
  than spam, the sending domain needs SPF and DKIM set up with that provider. That is done at your DNS host, not in this app.
- `PUBLIC_URL` is what goes into the links in the e-mails. It is **never** taken from the request, so a forged `Host` header cannot
  point a reset link at another site. Set it to the real https address before turning e-mail on.
- Then check it: `backend\.venv\Scripts\python.exe scripts\auth_admin.py test-mail --to you@yourdomain.com`. It prints either that the
  message was handed to the mail server, or why not. The server log records only the *kind* of failure, never a password.

Delivery runs in a background task, so a slow mail server does not make the page hang. If the mail server refuses a message, the person
still sees the same neutral screen (to avoid revealing whether an address has an account) and the failure is in the server log.

**What was tested.** The message building (with a guard against line breaks in addresses and subjects) and the reset, verification,
resend and contact-notification flows end to end, against a small SMTP server the tests start on `127.0.0.1` (`SMTP_SECURITY=none`, no
login). **What was not tested:** a real mail provider, and the `starttls`, `ssl` and SMTP-login (`SMTP_USER` / `SMTP_PASSWORD`) code paths,
because they need a server with a certificate and credentials. They use Python's standard `smtplib` in the usual way, but "should work" is
not "was shown to work". Run `auth_admin.py test-mail` once with your own details and trust that, not this page.

## Social sign-in (Google, Microsoft, ...) is not built

There is **no OAuth / "Sign in with Google" login**, and there is no button for it, because nothing in the app could make it work
without credentials this project does not have. Adding it later needs, from you: an OAuth client ID and secret from the provider's
console, an approved redirect address on your real domain (`https://your-address/api/auth/oauth/<provider>/callback`), and new backend
routes (authorization-code flow with PKCE, state and nonce checks, mapping the provider's verified e-mail to an account). None of that
exists today; do not expect it from configuration alone.

## When someone is locked out, or there is no e-mail

All of this runs on the computer that hosts the app, with the backend's Python:

```
backend\.venv\Scripts\python.exe scripts\auth_admin.py list
backend\.venv\Scripts\python.exe scripts\auth_admin.py create-owner --email you@yourshop.in --name "Your Name"
backend\.venv\Scripts\python.exe scripts\auth_admin.py reset-password --email you@yourshop.in
backend\.venv\Scripts\python.exe scripts\auth_admin.py set-active --email staff@yourshop.in --off
backend\.venv\Scripts\python.exe scripts\auth_admin.py sign-out-all --email you@yourshop.in
```

Anyone who can run these on the host already controls the database; they add no new power. A lock-out from repeated wrong passwords also
ends by itself after 15 minutes, or immediately by restarting the server (the counters are in memory).

## Data kept about accounts

`users` (e-mail, display name, password hash, role, active flag, timestamps, small UI preferences), `auth_sessions` (hashed cookie secret, CSRF
token, device description, times, whether remembered), `auth_tokens` (hashed one-use link tokens), `contact_messages` (what a visitor typed).
The device list in Account shows a short readable description such as "Chrome on Windows", the time last used, and which one is "This device".
It never shows a full IP address, a token, a hash or a cookie.

## What was checked

- The 889 backend tests include the whole accounts layer: hashing and policy, sign-up/sign-in/out, lock-out, expiry (idle and absolute), CSRF,
  origin guard, owner-only routes (`OWNER_ONLY`), reset and verification tokens (single use, expiry, replaced by newer ones), session list and
  revoke, e-mail wording, the command-line tool, and that every protected route answers `401` without a session.
- The 335 frontend tests include the sign-in, sign-up, forgot/reset, account, guard and landing components.
- `scripts/e2e_browser.py` drives a real Chromium against the running server on a throw-away database: wrong password and unknown e-mail
  (same message), validation, existing-address refusal, staff sign-up and what staff cannot see or call, cookie flags (HttpOnly, SameSite=Lax,
  session cookie versus a 30-day one, not readable from JavaScript), sign-out then protected routes and the back button, lock-out, `?next=`
  return and the off-site `?next=` refusal, the contact form reaching the owner's inbox, a wrong current password, and **session expiry**
  (the server-side expiry time of the owner's sessions is moved into the past in the SQLite file, then the app is used and must sign the person
  out and say so). These checks are part of the script's current run: 105 of 105 passed on the final build (the same script also covers the 2.1 features and the API reference page). See `docs/test-results/`.
- **Not verified:** a real SMTP provider (and the STARTTLS, SSL and SMTP-login paths, see above); sign-in over https with a real certificate (the cookie logic for `Secure` and `__Host-` is unit-tested,
  but the browser run used plain http on localhost); Safari and Firefox (only Chromium was driven); password managers and screen readers.
