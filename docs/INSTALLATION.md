# Windows 10/11 install guide

> **Honesty note.** SWARA AI was built and tested on Linux. The `.bat` scripts and these steps were written carefully for Windows
> but **have not been run on a Windows machine yet**. The Python code is portable (pathlib everywhere, no shell calls, wheels exist for every
> dependency), so problems, if any, will be in the scripts or your PATH. The troubleshooting table below covers the likely ones.

## 1. What you need

| Tool | Version | Why | Check |
|---|---|---|---|
| Python | 3.10 or newer (built and tested on 3.13) | backend | `py -3 --version` |
| Node.js | 22 LTS (20.19 or newer also works), *optional* | only to rebuild the frontend or run `dev.bat` | `node -v` |
| VS Code | any | editing; optional | |
| A Gnani API key | | speech recognition and spoken replies | from Gnani, see [GNANI_SETUP.md](GNANI_SETUP.md) |
| Chrome, Edge or Firefox | recent | microphone and WebAudio | |

Python installer: https://www.python.org/downloads/ . **Tick "Add python.exe to PATH".**
No Docker, no WSL, no database server.

## 2. First-time setup

Open the project folder in VS Code (*File → Open Folder*), then open a terminal (*Terminal → New Terminal*, Command Prompt or PowerShell).

```bat
setup.bat
```

What it does, in order:

1. Finds Python 3.10+ (`py -3` or `python`).
2. Creates `backend\.venv` and installs `backend\requirements.txt`.
3. Copies `.env.example` to `.env` if you have no `.env`.
4. If Node.js is installed **and new enough** (20.19+ or 22.12+; the front end's build tool refuses older versions): `npm ci` and `npm run build` in `frontend\`. If Node is missing or too old, it uses the prebuilt `frontend\dist` that ships in the release zip, and tells you which it did. (If there is no prebuilt `dist` either, it stops with a clear message instead of a build error.)
5. Creates the SQLite database `backend\data\swara.db` with the 65 staple products, the 5,325-item public catalogue and about 3,000 generated demo orders (120 days of history). (If you ran an earlier build under the previous product name, the database file it left in `backend\data\` is still found and used, so your shop's data stays. The app only falls back to it when `swara.db` does not exist.)

## 3. Add your Gnani key

Either edit `.env` and set

```
GNANI_API_KEY=your_real_key
```

or start the app and paste it on the **Settings** page (it is written to `.env`, never shown again, and never sent to the browser).

## 4. Prove the key works (about 33 real calls)

```bat
verify_gnani.bat
```

For each of the eleven languages (about 33 calls; add `--langs ta mr` to check only some) this runs four separate checks: **Timbre** speaks a test order, **Prisma** accepts the language code, Prisma transcribes the Timbre audio and the SWARA AI parser reads the transcript, and, if you put a recording of a person at `eval\samples\<key>.wav`, Prisma transcribes that too. It prints a table (one row per language, one column per check, with latencies and error codes) and saves it to `eval\results\gnani_live_<timestamp>.md` and `.json`, plus `eval\results\live_verification.json`, which the app reads to show each language's status. Only measured values are written. See [LANGUAGES.md](LANGUAGES.md).

Add `--stream` to test the realtime WebSocket as well (one more call per language), or `--langs gu hi` for a subset:

```bat
verify_gnani.bat --stream
```

The audio is Timbre output (a clean synthetic voice), not a human recording. For a harder test use the **Noise lab** or `backend\.venv\Scripts\python.exe scripts\evaluate_noise.py`.

## 5. Run the app

```bat
start.bat
```

It starts the server on `http://127.0.0.1:8000` (only your computer can reach it) and opens your browser. Close the window to stop it. If port 8000 is already taken, `start.bat` says so before starting and shows the fix (type `set PORT=8001`, then run `start.bat` again). If `.env` is missing it tells you to run `setup.bat`; the app still starts, but with no Gnani key.

The list of every API route is at `http://127.0.0.1:8000/docs` (a local page; it loads nothing from the internet).

- **Order desk → Tap to talk**: allow the microphone, press the amber button, speak, press again.
- **Order desk → Live stream**: continuous listening through Prisma streaming.
- **Type instead**: the text box works with no key at all.
- **Noise lab**: record one order, add noise, listen, run Prisma on each version.

## 6. Your account: the first sign-in

SWARA AI needs a signed-in person for everything except the landing page, the Terms and the Privacy page. On a fresh install nobody has an
account yet, so:

1. Open `http://localhost:8000` and choose **Get Started Free** (or go to `/sign-up`).
2. Enter your name, e-mail address and a password (at least 10 characters; the page shows a strength guide), tick the Terms box, and create the
   account. **The first account on a new database becomes the shop owner.** The owner can change prices and stock, mark orders, see the team and
   read the contact-form inbox. Everyone who signs up afterwards is *staff*: they can take orders and look things up, not change them.
3. You are signed in for 12 hours, or 2 hours without use. Tick *Keep me signed in on this device* to stay for up to 30 days.

On a computer nobody else can reach, that is all. If the computer is reachable from a network or the internet, read `docs/DEPLOYMENT.md` first: set
`OWNER_EMAIL` in `.env` so only your address can become the owner, and consider `ALLOW_SIGNUP=false`.

**No e-mail is needed, and none is sent**, unless you fill in the `SMTP_*` lines in `.env` (`docs/AUTHENTICATION.md`). So *Forgot password* says that
no e-mail can be sent, and you reset a password from the command line instead:

```bat
backend\.venv\Scripts\python.exe scripts\auth_admin.py list
backend\.venv\Scripts\python.exe scripts\auth_admin.py reset-password --email you@yourshop.in
backend\.venv\Scripts\python.exe scripts\auth_admin.py create-staff --email counter@yourshop.in --name "Counter Staff"
```

The password is typed at the prompt (not shown) and never goes on the command line.

Upgrading from an earlier build that used `ADMIN_TOKEN`: that setting is gone. Create your owner account as above; the data in your database
is kept.

## 7. Run the tests

```bat
test.bat
```

Runs `pytest` (889 tests, about 8 to 10 minutes) and, if Node is installed, `vitest` (383 tests).

## 8. Developer mode

```bat
dev.bat
```

Opens two windows: API with auto-reload on `:8000` and the Vite dev server on `:5173`. Browse to `http://localhost:5173`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Python 3.10 or newer was not found` | Python not on PATH, or only the Microsoft Store stub exists | Reinstall from python.org with *Add to PATH*; open a **new** terminal |
| `pip` cannot download packages | offline or a proxy | connect, or set `HTTPS_PROXY` |
| `Node.js is not installed and there is no prebuilt frontend\dist` | you cloned from Git (dist is not committed) | install Node 22 LTS (or 20.19+), rerun `setup.bat` |
| *Too many failed attempts* when signing in | five wrong passwords for one address (or 25 from one computer) pause sign-in for 15 minutes, even with the right password | wait 15 minutes, or stop and start `start.bat` (the counters are in memory) |
| *Forgot password* says no e-mail was sent | e-mail is not set up (`SMTP_*` in `.env`), so nothing can be sent | reset it with `auth_admin.py reset-password` (section 6) |
| Sign-in says *This request came from another website* (`BAD_ORIGIN`) | you are reaching the app through a proxy that changes the `Host` header | pass the original host, or add the public address to `CORS_ORIGINS` (`docs/DEPLOYMENT.md`) |
| `Port 8000 is already in use` | another program (or a second copy of SWARA AI) is listening there | close it, or use another port: Command Prompt `set PORT=8001` then `start.bat`; PowerShell `$env:PORT=8001` then `.\start.bat` |
| `Your Node.js is too old` in `setup.bat` | Node older than 20.19 (or 22.0-22.11) | install Node 22 LTS to rebuild the front end, or just continue: the prebuilt `frontend\dist` in the zip is used |
| Browser says microphone blocked | permission denied | click the padlock → allow microphone for `localhost` |
| Mic button is greyed out | no key configured | add the key; the button explains this |
| `NOT_CONFIGURED` / `INVALID_API_KEY` in a toast | wrong key | re-paste on Settings; run `verify_gnani.bat` |
| Gnani calls fail with a network error | firewall or proxy blocking `api.vachana.ai` | allow it; the error text says which host |
| `RATE_LIMITED` | the local budget (default 300 Gnani calls per hour) protects your free credits | raise `GNANI_MAX_CALLS_PER_HOUR` in `.env` |
| PowerShell says scripts are disabled | not relevant to `.bat` files; use *Command Prompt* or type `.\setup.bat` | |
| Antivirus quarantines the venv | rare | add the project folder as an exception |

## All the commands in one place

Run these from the project folder in Command Prompt (PowerShell: prefix each with `.\`).

```bat
setup.bat                                  :: once
notepad .env                               :: put your key on the GNANI_API_KEY= line (or add it later in Settings)
verify_gnani.bat                           :: optional: about 33 real Gnani calls, 3 per language, that check each language (docs\GNANI_SETUP.md, docs\LANGUAGES.md)
start.bat                                  :: run the app, http://localhost:8000
dev.bat                                    :: developer mode with hot reload, http://localhost:5173
test.bat                                   :: all tests
backend\.venv\Scripts\python.exe scripts\seed_db.py --reset                     :: reset the demo data (deletes local orders)
backend\.venv\Scripts\python.exe scripts\auth_admin.py reset-password --email you@shop.in :: set a new password for an account
```

Problems that are not in the table above: [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Getting the Gnani key working: [GNANI_SETUP.md](GNANI_SETUP.md).

## Updating or resetting

- Reset demo data: `backend\.venv\Scripts\python.exe scripts\seed_db.py --reset` (deletes local orders and stock changes).
- Remove everything: delete the folder. Nothing is installed system-wide except what you installed yourself.
