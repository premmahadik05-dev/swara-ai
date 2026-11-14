# Branding audit: the rename to SWARA AI

**Product name:** SWARA AI. **Tagline:** Every Voice. Smarter Commerce.
**Previous names:** DukaanMitra, Dukaan Mitra. **Done:** 10 Nov 2026. **App version:** 1.1.0 at the time (unchanged by the rename; the accounts and landing-page work later made it 2.0.0).

This report says what was found, what was changed, what was deliberately kept and why, and what was actually run to check it. Everything in the "Verified" section was executed in the build environment (Linux, Python 3.13, Node 22) and its output is saved in [`docs/test-results/`](test-results). Anything not run is listed under "Not verified".

## 1. Summary

- The product is called **SWARA AI** everywhere a person or a tool can see it: the app, the landing page, page titles, the favicon and icons, the API docs and health endpoint, the README and every document, the report (PDF and DOCX), the diagrams, the screenshots, the Windows scripts and the package metadata.
- The logo was **redrawn twice**. The first version (five concentric strands, "SWARA" with a smaller, lighter "AI", a black sidebar and black icon tiles) was judged too busy and too dark, and was replaced. The current logo is three tapered gold ribbons forming an S, with the wordmark **exactly "SWARA AI"** in one weight, one size and one colour. Nothing the product ships is a black surface (see section 4).
- The existing project was preserved: no feature was removed, no API route, schema, migration or test was dropped. Old browser settings, an existing database file and previously issued order numbers still work (section 3).
- A repository-wide guard test (`backend/tests/test_branding.py`) fails if the old name reappears in source, scripts or docs outside the files listed in section 3.

## 2. Where the old name was found, and what was done

Method: case-insensitive search of the whole repository (excluding `node_modules`, `.venv`, build output and binary files) for `dukaan[ _.-]*mitra`, `DM-` and `dukaan`, repeated after every round of edits; the text of the built frontend (`frontend/dist`), the PDF and the DOCX was searched separately, since a text search of the repository does not read them.

| Area | What was there | Done |
|---|---|---|
| Frontend UI | Sidebar and landing logo, hero and About copy, footer, page titles (`<title>` and the per-page title), Open Graph tags, error messages ("Cannot reach the SWARA AI server") | Replaced; official tagline and descriptions in `frontend/src/lib/brand.ts` |
| Frontend assets | favicon, touch icon, manifest, share image | Replaced with the new logo (`frontend/public/`) |
| Frontend metadata | `package.json` / `package-lock.json` name | `swara-frontend` |
| Backend | FastAPI title, summary and description (so Swagger/ReDoc show SWARA AI), `/api/health` now returns `"app": "SWARA AI"`, WebSocket logger name | Replaced; wording in `backend/app/brand.py` |
| Order numbers | Codes were built from the product's initials (`DM-261110-33`) | New orders read `SW-261110-33`. The prefix is computed from the id, not stored, so every existing order shows the new prefix; **old `DM-` numbers are still accepted in search** and on the order lookup |
| Config | `.env.example` header and comments, default database file name | `swara.db` for new installs; see section 3 for existing databases |
| Windows scripts | `setup.bat`, `start.bat`, `dev.bat`, `test.bat`, `verify_gnani.bat`: window titles and messages | Renamed; CRLF line endings kept (a test checks this) |
| Scripts | docstrings, the data pipeline's HTTP User-Agent, screenshot script's storage key | Renamed |
| Documentation | README, API, ARCHITECTURE, DATA, DESIGN, EVON, INSTALLATION, the demo walkthrough, TESTING, PROJECT_REPORT (Markdown, PDF, DOCX), `openapi.json` | Renamed and rewritten where the text described the old logo or palette |
| Diagrams | The system and workflow diagrams had generic labels | Re-rendered with "SWARA AI web app" and "SWARA AI backend"; the four PNGs in `docs/diagrams` are the new renders |
| Screenshots | 18 curated captures, from an 84-capture run (at the time of the rebrand; the set was retaken later with the sign-in screens and now has 22, picked from a 56-capture run of the final 2.1 build) | Retaken from the running app after the final change; light theme only (the dark-theme examples were removed with the dark theme) |
| GitHub references | No repository URL exists in the code | Nothing to rename |
| Docker / deployment config | None exists (the project runs without Docker by design) | Nothing to rename |
| Login, sign-up, onboarding | **None existed at the time of the rebrand.** Accounts were added afterwards (see [AUTHENTICATION.md](AUTHENTICATION.md)) and use the same logo and tokens | The sign-in, sign-up and recovery screens carry the SWARA AI mark; nothing was invented for the rebrand checklist |

## 3. Kept on purpose

| Where | What | Why |
|---|---|---|
| `backend/app/config.py` | If a database file from before the rename exists and the new one does not, it is used | An existing shop must not lose its orders because of a rename. New installs get `swara.db` |
| `frontend/src/lib/legacy.ts` (+ test) | Copies theme, demo-data switch and sidebar state from the old browser-storage keys to the new ones, once, without overwriting (a leftover shared admin token is deleted, not copied: accounts replaced it) | Same reason: a person's settings survive |
| `frontend/index.html` | Reads the old theme key once before first paint | Avoids a one-frame flash for a returning person |
| `backend/app/routers/orders.py`, `search.py` | Accept `DM-` as well as `SW-` order codes | A number a shopkeeper has already written down or printed must still find the order |
| `backend/app/nlu/vocab.py` | The Hindi word "dukaan" (shop) | It is vocabulary the language engine recognises in customers' sentences, not a brand reference |
| `backend/tests/test_branding.py`, `frontend/src/pages/Landing.test.tsx` | The old name in a regular expression | The tests assert that it does not appear |
| This file | The old name | It is the record of the rename |

## 4. Logo and brand decisions

- **Name.** The logo contains only "SWARA AI". It is never written as "SWARA" alone, and nothing is added to it. A test checks that every logo file is labelled exactly "SWARA AI" and that the wordmark is two outlined words in a single colour.
- **Mark.** Three tapered gold ribbons that follow an S curve (built from true parallel offsets of one centre line), a voice waveform bent into a letter. A bolder two-ribbon version is used below about 40 px (sidebar, tab icon).
- **Typography.** Geist SemiBold capitals, converted to outlines so no SVG depends on a font. Geist is SIL OFL 1.1.
- **Palette.** Ink `#242424` (the wordmark and all text; this was Luxury Black `#0B0B0D` until the light-only revision of 10 Nov 2026), Champagne Gold `#D6B574` (the mark, as a gradient down to a deeper gold so it holds on light surfaces), Ivory `#F7F5EF`.
- **No black surfaces.** The sidebar is ivory; the app icons are white, ivory or gold; the share card is ivory; the manifest and browser theme colour are ivory. **The optional dark theme and the reversed logo were removed** in the light-only revision (10 Nov 2026): there is no dark mode, no "system" mode, no theme setting and no dark logo file, and a browser or system set to dark does not change the page. Primary buttons are champagne gold with ink text (7.92:1), not black.
- **Contrast.** The name is Ink (14.24:1 on ivory). The gold mark is a graphic: its gradient runs from 1.6:1 (pale end) to 5.1:1 (deep end) on ivory. The measured figures are in [DESIGN.md](DESIGN.md).
- **Deliverables** in [`brand/`](../brand): horizontal logo, standalone S, compact S, square app icon (white, ivory, gold and one-colour), favicon (SVG and ICO), share card, full-colour and one-colour (Ink) variants, SVG and transparent PNG, a contact sheet (`preview.png`) and usage rules ([brand/README.md](../brand/README.md)). All are generated by `scripts/brand/build_logo.py` from one geometry definition.

## 5. Verified (executed in the build environment)

*These are the figures from the day of the rebrand. The current test counts and logs, after the accounts and landing-page work, are in [TESTING.md](TESTING.md).*

| Check | Result |
|---|---|
| Backend `pytest` (whole suite, with coverage) | **314 passed**, 0 failed, 4 min 13 s on a 2-core machine; 92% line coverage (3,542 statements, 278 not executed). Log: [backend_pytest.txt](test-results/backend_pytest.txt) |
| Frontend `vitest` | **156 passed** in 22 files. Log: [frontend_vitest.txt](test-results/frontend_vitest.txt) |
| Frontend `tsc --noEmit` (strict) and `vite build` | Both exit 0. Log: [frontend_build.txt](test-results/frontend_build.txt) |
| Repository scan for the old name (`test_branding.py`) | Passes: only the files in section 3 contain it |
| Built frontend, PDF and DOCX searched for the old name | The text of the repository, the PDF and the DOCX contain the old name only in the files listed in section 3. The built frontend contains it only as the compiled migration code and the one-time theme-key read (the built forms of `legacy.ts` and `index.html`). The four diagram PNGs and 18 screenshots were re-rendered, not searched |
| The running app, in headless Chromium | Landing header and footer, sidebar (full and collapsed rail), phone header, page titles, favicon and touch icon files, share card: all show "SWARA AI" in the new logo on light surfaces. 84 captures (3 sizes, 2 themes, 14 pages) with **no console error, failed request or HTTP error** |
| `GET /api/health` and the OpenAPI document | Report `"app": "SWARA AI"`; `docs/openapi.json` regenerated |
| Clean-unzip smoke test of the final ZIP | Unzipped into an empty folder, seeded the demo database (65 products, 8 customers, 3,033 orders, 5,325 catalogue items) and started it with the command `start.bat` uses. `/api/health` returns `"app": "SWARA AI"`; the catalogue total is 5,325; analytics returns 200; the OpenAPI title and summary are SWARA AI and the tagline; a typed Gujarati-Hinglish order confirmed in one call returned order `SW-261110-3034` (₹172); the frontend serves the SWARA AI page title and all seven icon, card and manifest files return 200. It ran with the build environment's existing Python environment, so a fresh `pip install` was not repeated |
| Lint | The project has no ESLint or Ruff configuration. The strict TypeScript check is the front-end lint. A one-off `ruff check --isolated --select F,E9` (pyflakes errors and syntax errors) over `backend/` and `scripts/` found no undefined names or syntax errors; its only findings are 10 unused imports in older files, which were left alone (the unused imports in files created for this rename were removed) |

## 6. Not verified

- **Live Gnani calls** (Prisma speech recognition, Timbre spoken replies): no network route to Gnani and no API key in the build environment. The simulator tests cover the documented request and response shapes only.
- **Microphone capture** in a real browser: no audio hardware.
- **The Windows `.bat` scripts**: built on Linux. Their line endings and text were checked, not their execution.
- Python versions other than 3.13; PostgreSQL (only SQLite was run); browsers other than Chromium; a screen reader, axe or Lighthouse.
- **The logo in print, on an operating system's icon grid, or in a trademark search.** The favicon was checked by eye at 16, 32 and 48 px.
- That the tab icon looks right in every browser's tab strip: it is a transparent gold S, checked on a light and a dark browser tab strip in Chromium only (the strip belongs to the browser, not to the product).

## 7. Files changed (by area)

- **Logo and brand kit (new):** `brand/` (18 SVGs including the share card, transparent PNGs, `favicon.ico`, `preview.png`, `README.md`), `scripts/brand/build_logo.py`, `scripts/brand/render_preview.py`.
- **Frontend:** `components/Logo.tsx` and the generated `components/logoPaths.ts` (new), `lib/brand.ts` and `lib/legacy.ts` (new), `styles/tokens.css`, `styles/app.css`, `styles/ui.css`, `components/Shell.tsx`, `pages/Landing.tsx`, `lib/theme.tsx`, `index.html`, `public/` icons and manifest, `package.json`, `package-lock.json`, and the tests that assert titles, storage keys, order codes and the logo.
- **Backend:** `app/brand.py` (new), `app/main.py`, `app/routers/health.py`, `app/config.py`, `app/models.py`, `app/routers/orders.py`, `app/routers/search.py`, `app/routers/ws.py`, `tests/test_branding.py` (new), `tests/test_dialogue_api.py`.
- **Scripts and config:** the five `.bat` files, `.env.example`, `scripts/*.py` docstrings, the screenshot script's storage key, the data pipeline's User-Agent.
- **Documentation:** README, all files in `docs/`, the PDF and DOCX report, the diagrams and screenshots.

## 8. Remaining limitations

- Orders and customers in the app are generated demo data and labelled as such; the product catalogue (5,325 products, Open Food Facts) has no prices.
- The input-border contrast (1.6:1) is below WCAG's 3:1 for form-control boundaries; it was that way before the rename and was left alone (see DESIGN.md).
- On a phone the app's top bar shows the menu button; the logo is at the top of the slide-in menu, as before.
- The old database file name, browser-storage keys and `DM-` order search are honoured indefinitely; remove `legacy.ts` and the fallbacks when no old installs remain.
