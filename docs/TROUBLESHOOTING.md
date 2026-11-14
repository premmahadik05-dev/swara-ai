# Troubleshooting

Start with the three checks that answer most questions, then find your symptom below. Installation problems on Windows (Python not found, `pip`
offline, Node too old, port busy) are in the table at the end of [INSTALLATION.md](INSTALLATION.md).

## Three quick checks

1. **Is the server up?** Open `http://localhost:8000/api/health`. A healthy server answers with `"status":"ok"`, `"db":"ok"`, the product count,
   the version, and `"gnani_configured": true` or `false`. If the page does not load, the server is not running: start it with `start.bat` and read the
   window it opens (that window is the server's log).
2. **Which mode is it in?** The Order desk says **Typing only** until a Gnani key is set. *Typing only* is not a fault: typed orders use the same
   engine as spoken ones. Voice starts when `gnani_configured` is `true` and the key is accepted (step 3).
3. **Does the key work?** Settings → **Test connection** (2 calls), or `verify_gnani.bat` (about 33 calls, eleven languages, or `--langs ta mr` for some). See [GNANI_SETUP.md](GNANI_SETUP.md).

## Signing in

| Symptom | Cause | What to do |
|---|---|---|
| *Wrong e-mail or password* for an account you are sure of | Check the caps lock and any trailing space. The message is the same for a wrong password and an unknown address on purpose | Try again; if you forgot it, see below |
| *Too many failed attempts* | Five wrong passwords for one address (or 25 from one computer) pause sign-in for 15 minutes, even with the right password | Wait 15 minutes, or restart the server (the counters are in memory) |
| *Forgot password* says no e-mail can be sent | `SMTP_*` is not set in `.env`, so the app cannot send mail and says so | Reset it on the command line: `backend\.venv\Scripts\python.exe scripts\auth_admin.py reset-password --email you@yourshop.in` |
| Signed out suddenly, with a message | A session ends after 12 hours, or 2 hours without use (30 days if you ticked *Keep me signed in*). Changing your password signs out your other devices | Sign in again; you are returned to the page you were on |
| `BAD_ORIGIN` (*This request came from another website*) | You reach the app through a proxy or an address that does not match the `Host` the app sees | Use `http://localhost:8000`, or follow *Behind a reverse proxy* in [DEPLOYMENT.md](DEPLOYMENT.md) |
| `CSRF_FAILED` after a long idle tab | The page's token belongs to an old session | Reload the page |
| I am staff and cannot change prices or export customers | By design: staff can take orders and read numbers; the owner changes stock, prices, settings and exports customer data | Ask the owner, or have the owner create your account as owner |
| The wrong person became the owner | The **first** account on a new database is the owner | Set `OWNER_EMAIL` in `.env` before you expose the app (see [AUTHENTICATION.md](AUTHENTICATION.md)) |

## Voice and Gnani

| Symptom | Cause | What to do |
|---|---|---|
| The microphone button is greyed out, "Typing only" | No Gnani key configured | Add `GNANI_API_KEY` to `.env` or paste it on Settings, then reload |
| *This browser cannot record audio* | Browsers allow the microphone only on `localhost` or on an `https://` address. `http://192.168.x.x:8000` from another device is not allowed | Use `localhost` on the same computer, or serve the app over https ([DEPLOYMENT.md](DEPLOYMENT.md)) |
| Browser says the microphone is blocked | Permission was denied for this site | Click the padlock beside the address, allow the microphone, reload |
| `INVALID_API_KEY` (*Gnani rejected the API key*) | Wrong or expired key | Paste the key again on Settings; check with **Test connection** |
| `NOT_CONFIGURED` | The request needs a key and none is set | As above |
| *Could not reach Gnani* / network error | A firewall or proxy blocks `api.vachana.ai`, or you are offline | Allow that host; typed orders keep working |
| `RATE_LIMITED` | Gnani limited the key, or the local safety limit (`GNANI_MAX_CALLS_PER_HOUR`, default 300) was reached | Wait, or raise the local limit in `.env` |
| Prisma hears a different language than the customer speaks | Prisma v2.5 takes **one language per request** | Pick the customer's language in *Customer speaks* before pressing the microphone |
| The words are right but the item is wrong or missing | The parser could not match the name | Say the product the way the shop lists it, add an alias to the item, or add the item; unmatched names become a question, not a wrong order |
| Spoken replies are silent | The browser blocked autoplay, or *Speak replies* is off | Press the page once, tick *Speak replies*; check the volume |

## Data and screens

| Symptom | Cause | What to do |
|---|---|---|
| The dashboard is empty or shows "Demo data" | A fresh database carries generated demo history; the **Demo data** switch in the top bar hides it | Turn the switch off to see only real orders |
| Numbers in the app look like another shop's | They are generated demo data (clearly labelled) | Reset or replace: `backend\.venv\Scripts\python.exe scripts\seed_db.py --reset` deletes local demo orders and stock changes |
| *Not enough earlier data to compare* on a chart | The earlier period is incomplete, so the page does not invent a percentage | It appears once there is enough history |
| `database is locked` | Two server processes are using the same file, or a backup tool is holding it | Keep one server per database file; stop the app before copying the file |
| A new version says a column is missing | Rare: an old database file and an interrupted start | Start once more; `upgrade_schema()` adds the missing columns on startup. If it persists, restore your backup |
| The shop name will not save | The name has a character the app refuses (for example `#`), or `.env` is read-only | The message names the problem; make `.env` writable |
| CSV shows odd characters in Excel | Excel guessed the wrong encoding | The file is UTF-8 with a byte-order mark and normally opens correctly by double-click; otherwise use *Data → From Text/CSV* and choose UTF-8 |
| A CSV stops at 20,000 rows | The export cap | The page says so and the response carries `X-Export-Truncated`; narrow the filter or export by period |
| **Print bill** prints the whole page | A browser extension or an old cached page | Reload (Ctrl+F5); in the print window choose *Save as PDF* to check before using paper |
| Pictures on the landing page are missing | The front end was built without the pictures in `frontend/public/shots/` | Rebuild with `npm run build` (see [DEVELOPMENT.md](DEVELOPMENT.md)) |

## Build and tests

| Symptom | Cause | What to do |
|---|---|---|
| `npm run build` says Node is too old | The build tool (Vite 7) needs Node 20.19+ or 22.12+ | Install Node 22 LTS. Without Node you can still run the prebuilt `frontend\dist` |
| `pytest` is slow the first time | About 537 tests, several with deliberate delays; about 8 minutes | Run one file: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_saas_api.py` |
| A test mentions the old product name or a dark theme and fails | Guard tests: they scan the repository so those cannot return | The failure lists the file and line to change |
| Browser checks cannot run | They need Playwright and Chromium: `pip install playwright` then `playwright install chromium` | See *What the browser checks cover* in [TESTING.md](TESTING.md) |
| Warnings at the end of the test run | Two known ones: Starlette's `httpx` notice and an unclosed test database in one e-mail test | They do not fail anything; see [TESTING.md](TESTING.md) |

## When you report a problem

Include: the version (`/api/health` → `version`), what you clicked, the exact message, and the last lines of the server window. **Do not paste
`.env`, your Gnani key, SMTP password, session cookie or a database file.**
