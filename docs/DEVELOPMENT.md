# Development guide

For people who change SWARA AI's code. To only *run* it, use [INSTALLATION.md](INSTALLATION.md). Architecture is in
[ARCHITECTURE.md](ARCHITECTURE.md); the data model is in [DATABASE.md](DATABASE.md).

## Setup once

Windows (Command Prompt or PowerShell, from the project folder):

```bat
setup.bat
```

That creates `backend\.venv`, installs the backend packages, copies `.env.example` to `.env`, installs and builds the frontend (if Node 20.19+ or 22.12+ is
installed) and creates the demo database. Run it again after pulling changes that touch `requirements.txt` or `package.json`.

macOS and Linux have no `.bat` scripts. The equivalent by hand (this is how the project was built and tested):

```sh
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements-dev.txt
cp .env.example .env
(cd frontend && npm ci && npm run build)
backend/.venv/bin/python scripts/seed_db.py
cd backend && .venv/bin/python -m uvicorn app.main:create_app --factory --port 8000
```

## Everyday commands

| Task | Windows | Notes |
|---|---|---|
| Run the built app | `start.bat` | `http://localhost:8000`, serves `frontend\dist` |
| Develop with hot reload | `dev.bat` | API with auto-reload on `:8000`, Vite on `:5173` (open `http://localhost:5173`; `/api`, `/ws` and the API reference at `/docs` are proxied to the backend) |
| All tests | `test.bat` | pytest, then vitest if Node is installed |
| Backend tests only | `backend\.venv\Scripts\python.exe -m pytest` | one file: add `backend\tests\test_saas_api.py`; one test: add `-k name` |
| Backend coverage | `backend\.venv\Scripts\python.exe -m pytest --cov=backend/app --cov-report=term` | |
| Frontend tests | `cd frontend` then `npm test` | `npm test -- src\pages\Orders.test.tsx` for one file |
| Type-check + production build | `cd frontend` then `npm run build` | `tsc --noEmit` runs first; the build fails on a type error |
| Reset demo data | `backend\.venv\Scripts\python.exe scripts\seed_db.py --reset` | deletes local orders and stock changes |
| Live Gnani check | `verify_gnani.bat` | needs a key; see [GNANI_SETUP.md](GNANI_SETUP.md) |

There is **no ESLint** configuration; type-checking (`tsc`, strict) is the static check.

## Layout

```
backend/app/
  main.py          create_app(): middleware, routers, static front end
  config.py        Settings (pydantic-settings, reads the repo-root .env)
  security.py      CSRF/Origin guard, security headers, rate limits, access-log redaction of one-time tokens
  apidocs.py       the local API reference page at /docs (static/api_reference.js reads /openapi.json)
  auth.py          sessions, roles (require_user, require_owner)
  models.py db.py  SQLAlchemy models, engine, in-place column upgrades
  routers/         one file per area (auth, orders, inventory, customers, catalog, analytics, voice, ws, settings, health, contact …)
  services/        business logic with no HTTP in it (orders, inventory, analytics, export, mailer, passwords, speech, verification …)
  languages.py     the language registry: the one table of languages, Prisma/Timbre codes, voices, samples, switched-off languages
  nlu/             parser, vocabulary, lexicon, dialogue state machine (the "assistant"; no model, fully deterministic)
  nlu/langpacks/   one file per language added in 2.3.0 (number words, units, product names, corrections, reply templates); product_names.py joins them to the 65 staples
  gnani/           the only code that talks to Gnani (client.py), voices
backend/tests/     pytest; one isolated app and SQLite file per test (conftest.make_app)
frontend/src/
  pages/           one file per screen (+ landing/ and auth/)
  components/      shell, tables, drawers, charts, pickers, setup checklist
  lib/ api/        formatting, audio capture, auth context, the API client (GET cache, CSRF header)
  styles/          tokens.css (the one light theme), ui.css, app.css, landing.css
scripts/           seed, auth_admin, verify_gnani, evaluations, screenshots, browser checks, data pipeline, logo build
```

## Rules this code base keeps (tests enforce most of them)

1. **Light theme only.** Colours come from the tokens in `frontend/src/styles/tokens.css`; no dark token, `prefers-color-scheme: dark` rule or literal dark
   colour may be added (`test_light_only.py`).
2. **The product is called SWARA AI.** The previous name must not return (`test_branding.py`), and no event or competition wording may appear anywhere
   (`test_independent_product.py`). Credit to Gnani.ai for Prisma and Timbre stays, with the "not affiliated" line.
3. **Money is integer paise, quantities are `Decimal`.** No floats near money.
4. **The Gnani key stays on the server.** Only `backend/app/gnani/client.py` and the streaming proxy use it. It is never logged, never returned
   (Settings shows the last four characters), never in the frontend bundle.
5. **No invented numbers.** Statistics on screen come from queries; the landing page quotes only things the code does (`test_landing_claims.py`).
   Generated demo data is labelled and can be switched off.
6. **Every write needs the CSRF header and, for owner actions, the owner role,** checked on the server. A hidden button is never the protection.
7. **Everything a person can click must do something.** `scripts/e2e_browser.py --only-controls` clicks every enabled button on every page and fails on
   a dead one.

## Adding things

- **An API route:** add it to the right file in `routers/`, put the logic in `services/`, use `require_user` or `require_owner`, return the standard error
  envelope (`{"detail": {"code": …, "message": …}}`), add tests (success, validation, a staff user for owner routes), add a row to [API.md](API.md), and
  regenerate `docs/openapi.json` (`create_app().openapi()` written as JSON).
- **A database column:** change `models.py`, add the column to `ADDED_COLUMNS` in `db.py` with a default so existing SQLite files upgrade in place, test the
  upgrade, and update [DATABASE.md](DATABASE.md).
- **A screen:** a file in `frontend/src/pages/`, a lazy route, a sidebar entry, loading/empty/error states (reuse the shared components), a Vitest file, and a
  line in the controls audit if it has special controls.
- **A language word or unit:** `nlu/vocab.py` (Gujarati, Hindi, English) or `nlu/langpacks/<key>.py` (the seven added languages); add a line to `eval/utterances.jsonl`
  and run `scripts/evaluate_nlu.py` to see the effect. **Also run `scripts/evaluate_branded.py`** (it rewrites `data/test/branded_results.json`): a new
  alias can turn a sentence that used to be "not recognised" into a confident wrong product, which the 288-utterance set will not show. Compare before and after,
  and record the new numbers in [EVALUATION.md](EVALUATION.md).
- **A language Gnani documents:** see [LANGUAGES.md](LANGUAGES.md#adding-or-removing-a-language). In short: one `Language(...)` entry and its voices in
  `languages.py`, one pack, one line in `frontend/src/lib/languages.ts`, then `python -m pytest backend/tests/test_languages_*.py` and `npx vitest run`. The tests
  loop over the registry, so the new language is covered by the same checks as the others. Update the copy of Gnani's documented codes and voices in
  `test_languages_registry.py` from the current documentation first, or the test only agrees with itself. Mark it **not verified live** until
  `verify_gnani.bat` says otherwise; do not edit `eval/results/live_verification.json` by hand.
- **The API reference file:** after any route or schema change, regenerate `docs/openapi.json` from `create_app().openapi()`; a test compares it with a fresh export.
- **A setting:** `config.py`, `.env.example`, and, if the owner should change it in the app, `routers/settings.py` with owner-only access.

## Before you open a pull request

```bat
test.bat
cd frontend && npm run build
```

and, if you touched the UI, `python scripts\e2e_browser.py` against a throw-away database (see [TESTING.md](TESTING.md); it needs Playwright and
Chromium and writes `.env` while it runs, so use a copy of the project or restore the file). Update the docs a change makes untrue; the tests that scan
the repository will point at some of them.
