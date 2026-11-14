# Deploying SWARA AI

SWARA AI is built to run on **one computer, one server process, one SQLite file**: a shop's counter PC, or a small cloud machine for one
shop. `start.bat` does exactly that on Windows. This page is for the step beyond that: putting it on a real address with https so staff can
use it from their phones and other devices.

**Nothing on this page was run on a real server.** The facts about what the app itself does (headers, cookies, limits) were checked on
localhost and are marked as such; the reverse-proxy samples are standard patterns, **not tested here**. Read them as starting points.

## Before it is reachable from the internet: the checklist

1. **Create the owner first, or pin it.** Start the app on a closed network (or before opening the firewall) and create the owner account, or set
   `OWNER_EMAIL=you@yourshop.in` in `.env` before the first start. Otherwise the first visitor to `/sign-up` becomes the owner.
2. **Decide on the public demo.** The landing page's "try it" box calls `POST /api/text/parse` without a sign-in and gets this shop's item names, prices and stock
   back. For a real shop set `PUBLIC_DEMO=false` (the page then says the demo is off). Leave it `true` only for a demo database.
3. **Decide on sign-up.** `ALLOW_SIGNUP=false` once your staff exist (add them with `scripts/auth_admin.py create-staff`). Leaving it `true` means
   anyone who finds the address can make a staff account, which can take orders and read customers.
4. **Set `PUBLIC_URL`** to the real https address, e.g. `PUBLIC_URL=https://orders.yourshop.in`. This turns on the `Secure` and `__Host-` cookie
   flags and the `Strict-Transport-Security` header, and it is the address used in e-mailed links.
5. **Serve it over https only.** The microphone also needs it: browsers allow `getUserMedia` only on `https://` or `localhost`. A phone that
   opens `http://192.168.x.x:8000` on the shop network will sign in and take typed orders, but **cannot use the microphone**.
6. **Set up e-mail** if you want password-reset links and verification (`docs/AUTHENTICATION.md`), and run `auth_admin.py test-mail`.
7. **Put the Gnani key in `.env` on the server**, never in the front end. Set `GNANI_MAX_CALLS_PER_HOUR` to a number you are comfortable paying for.
8. **Run exactly one server process** (see "One process" below).
9. **Back up the database** (see "Data and backups").
10. Rebuild the front end with `PUBLIC_URL` set (see "Search and sharing") if the landing page should be shared on social media.
11. **Decide whether the API reference should be public.** `/docs` and `/openapi.json` list every route. They hold no data and no keys, but a shop that does not want its route list shown sets `API_DOCS=false`.

## Running it

```
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

That is what `start.bat` runs. `127.0.0.1` means "this computer only", which is right when a reverse proxy on the same machine is the public
face. The server serves the API, the WebSocket and the built front end (`frontend/dist`) on the one port; the browser app is called with relative
addresses, so there is no separate front-end host to configure and no cross-site API calls.

Health check for a monitor or load balancer: `GET /api/health` (no sign-in; returns the app name, version, whether the database answers and the
product count; it never returns a secret).

## Behind a reverse proxy (https)

Use any proxy that terminates TLS (Caddy, nginx, a cloud load balancer). Three things matter.

1. **Pass the original `Host` header.** The server refuses a state-changing browser request (sign-in included) whose `Origin` is another website, and
   it judges that by comparing `Origin` with `Host`. A proxy that rewrites `Host` to `127.0.0.1:8000` makes every sign-in fail with `BAD_ORIGIN`.
   Either keep the host (`proxy_set_header Host $host;` in nginx; Caddy does it by default) or list the public origin in
   `CORS_ORIGINS=https://orders.yourshop.in`. The same Host is used for the WebSocket address in the content-security policy.
2. **Pass the visitor's address** (`X-Forwarded-For`). The sign-in lock-out and the rate limits are per visitor address. If the app only ever sees
   the proxy's address, all visitors share one bucket, and a handful of wrong passwords from anyone locks everyone out for 15 minutes. Uvicorn
   already trusts `X-Forwarded-For` from a proxy on `127.0.0.1` (its default). **Checked on localhost with curl:** with the header set to one address,
   20 sign-in attempts a minute from that address were allowed and the 21st got `429 RATE_LIMITED`, while a different forwarded address and a direct
   request were still answered normally. If your proxy is on **another machine**, start uvicorn with `--forwarded-allow-ips=<proxy address>`; do not use
   `*` unless nothing but the proxy can reach the port.
3. **WebSocket upgrade** for `/ws/` (live voice streaming) must be forwarded.

Caddy (the simplest; gets certificates automatically; **not tested here**):

```
orders.yourshop.in {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
```

nginx (**not tested here**; certificates from Let's Encrypt or your provider):

```
server {
    listen 443 ssl http2;
    server_name orders.yourshop.in;
    # ssl_certificate / ssl_certificate_key ...

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    client_max_body_size 10m;                      # audio uploads are limited to 8 MB by the app

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }
    location /assets/ {                            # file names carry a content hash, so they can be cached for a year
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server { listen 80; server_name orders.yourshop.in; return 301 https://$host$request_uri; }
```

## Security headers

**The app already sends these** (checked on localhost; the live server's responses were inspected, and `backend/tests/test_security.py` asserts them):

| Header | Value | Where |
|---|---|---|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws://HOST wss://HOST; media-src 'self' blob: data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; manifest-src 'self'` | every HTML page |
| `X-Content-Type-Options` | `nosniff` | every response |
| `X-Frame-Options` | `DENY` | every response |
| `Referrer-Policy` | `no-referrer` | every response |
| `Permissions-Policy` | `microphone=(self), camera=(), geolocation=(), payment=(), usb=()` | every response |
| `Cross-Origin-Opener-Policy` | `same-origin` | every response |
| `Cache-Control` | `no-store` | every `/api/` response except the audio files |
| `Strict-Transport-Security` | `max-age=31536000` | only when `PUBLIC_URL` is https (or `COOKIE_SECURE=true`) |

The policy has **no inline scripts** and no string evaluation (the interface is light only, so no theme script exists). It does allow inline *styles*, because React sets
`style` attributes on some elements and the charts do too; that is a deliberate, narrow concession and not a script-execution risk.

**You may add at the proxy** (they are not set by the app because they depend on your setup): `Strict-Transport-Security` with `includeSubDomains` (only if
every subdomain is https) and `preload` (only after reading hstspreload.org; it is hard to undo); `Cross-Origin-Resource-Policy: same-origin`;
long-lived caching for `/assets/*` (shown in the nginx sample). Do **not** add `Cache-Control` to `/api/` responses; the app already sets `no-store`.

## One process, and what that means

A few things live only in the memory of the server process: the sign-in lock-out counters, the rate limits (general, and the stricter one for sign-in, sign-up,
reset and the contact form), the forgot-password limiter, the Gnani "calls in the last hour" budget, and a small cache of the product catalogue. Everything
that matters (accounts, sessions, orders, stock, ordering conversations) is in the database. So run **one** uvicorn process (no `--workers 2`, no two copies
behind a load balancer). With more than one:

- each process counts failed sign-ins separately, so an attacker gets N times the attempts;
- a restart (or a new deploy) clears the counters, including the Gnani hourly budget, so the safety valve is per process lifetime, not per real hour;
- SQLite is a single-writer database; several processes writing to it would contend and can return "database is locked".

Because accounts and sessions are in the database, a restart does **not** sign anybody out. If you ever need several processes, the first
steps are PostgreSQL (`DATABASE_URL=postgresql+psycopg://...`, supported by SQLAlchemy but **not exercised by this project's tests**) and moving the counters to
a shared store such as Redis. Neither is done here.

## Data and backups

- The database is one file: `backend/data/swara.db` (or what `DATABASE_URL` says). Orders, stock, customers, accounts, session records and contact messages are in it.
- **Back it up while the app is stopped** by copying `swara.db` (and `swara.db-wal` / `swara.db-shm` if they exist next to it), or use SQLite's own backup
  command from a machine that has the `sqlite3` tool: `sqlite3 swara.db ".backup 'swara-backup.db'"` (safe while the app runs). Keep copies off the machine.
- The `.env` file holds the Gnani key and the SMTP password in plain text. Keep it out of backups that others can read, out of version control (it is in
  `.gitignore`), and readable only by the account that runs the server. The Settings page only ever shows the last four characters of the key.
- Passwords are stored as scrypt hashes and cookies as SHA-256 hashes; a stolen database file does not contain a usable password or cookie. It does
  contain customer names and phone numbers if you recorded them, so treat the file like the personal data it is.
- Server logs contain, for failed sign-ins and sign-ups, the visitor's IP address (with the account id when there is one; successful sign-ins log the account id and a session label). They never contain passwords,
  tokens or cookies. Decide how long to keep them, and say so in your privacy notice; the template Privacy page here is a starting point, not legal advice.

## Search and sharing

The landing page has a title, description, Open Graph and Twitter tags, JSON-LD, a favicon set and a web manifest. `canonical`, `og:url`, `og:image` and
`twitter:image` need an **absolute** address, so they appear only when `PUBLIC_URL` is set **when the front end is built**:

```
set PUBLIC_URL=https://orders.yourshop.in
cd frontend
npm run build
```

Without it those four tags are left out rather than guessed. `robots.txt` lets the landing, Terms and Privacy pages be indexed and keeps crawlers out of the
app, the API and the sign-in screens (signed-in pages also carry a `noindex` tag). There is **no `sitemap.xml`**: with one public page and two legal pages it
adds little, and it needs the real address; add one if you add public pages.

## Performance, honestly

The production build splits the code per page and loads the charts library only on the pages that use it; landing-page screenshots are WebP; the one in the hero loads first and the pictures in the
product showcase load lazily. The fonts (Newsreader, Geist and Noto Sans) are served by the app itself as `woff2` files, never from a font service. Compression and long-lived caching of `/assets/*` are for your proxy to do (samples above); the app itself does
neither. **No Lighthouse, WebPageTest or load test was run for this project**, so there is no score to quote and none is implied.

## Updating

Stop the server, replace the project folder's code (keep `.env` and `backend/data/`), run `setup.bat` (it installs the dependencies again and rebuilds the front
end), start again. New columns and tables are created on start; there is no separate migration tool, so take a backup first.

## Not done

Multi-shop hosting, per-tenant databases, a container image, Kubernetes manifests, a CI pipeline, centralised logging, automatic backups, rate limits shared
across processes, two-factor sign-in, Google/Microsoft sign-in, and any verification on a real internet-facing server. See `docs/LIMITATIONS.md`.
