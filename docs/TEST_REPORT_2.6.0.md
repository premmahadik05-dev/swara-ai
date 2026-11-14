# Test report: SWARA AI 2.6.0

What was run for this release, what it showed, what was added, and what could **not** be run. Every number comes from a log in [`test-results/`](test-results), written by the command shown, or from a result file in [`../eval/results/`](../eval/results). Nothing is estimated. The wider picture (languages, security, the full verification matrix) is in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md); how the suites are organised is in [TESTING.md](TESTING.md).

**Environment (all runs):** Linux, 2 CPU cores, Python 3.13.18, Node 22.23.4 / npm 10.9.9, Chromium driven by Playwright 1.63.0, 11 Nov 2026.
**No run was made on Windows, against live Gnani, or with a microphone.** Every Gnani response in every automated test and in every timing in this release is simulated.

## 1. Results at a glance

| Suite | 2.5.0 | 2.6.0 | Log |
|---|---|---|---|
| Backend `pytest` | 889 passed | **945 passed**, 0 failed, 10 min 7 s; **95% line coverage** (5,175 statements, 252 not executed; was 4,971 and 249) | [backend_pytest.txt](test-results/backend_pytest.txt), [.xml](test-results/backend_pytest.xml) |
| Frontend `vitest` | 383 in 38 files | **431 passed** in 41 files, 0 failed | [frontend_vitest.txt](test-results/frontend_vitest.txt) |
| `tsc --noEmit` (strict) and `vite build` | clean | clean | [frontend_build.txt](test-results/frontend_build.txt) |
| Real browser, main run | 148 of 148 | **160 of 160**, no unexpected console error, warning, failed request or HTTP error | [e2e_browser_main.txt](test-results/e2e_browser_main.txt) |
| Real browser, button and link audit | 4 of 4 | **4 of 4**: 220 enabled buttons clicked (10 on 6 public pages, 210 on 13 signed-in pages), every link on all 19 pages goes somewhere real | [e2e_browser_controls.txt](test-results/e2e_browser_controls.txt) |
| Dependency audits | none found | `npm audit` 0 vulnerabilities; `pip-audit` none found (11 Nov 2026, 12:16 UTC). No dependency was added or changed | [dependency_audits.txt](test-results/dependency_audits.txt) |
| Clean unzip of the release ZIP | 889 backend, 148 browser | **160 of 160** browser checks and **945 passed** (95% coverage, 9 min 31 s) in the backend suite, both from an unzipped copy of the ZIP on an empty database. The delivered ZIP differs from the tested unzip only in the documents and logs that record this run | [backend_pytest_clean_unzip.txt](test-results/backend_pytest_clean_unzip.txt), [e2e_browser_clean_unzip.txt](test-results/e2e_browser_clean_unzip.txt) |
| Update in place (2.5.0 install, fake `.env`, real 2.5.0 database) | not done | **15 of 15 checks passed** on a copy of a 2.5.0 database made in this environment (2 users, 352 orders, 65 products) with a placeholder `.env`: `.env` and database file byte for byte unchanged by the unzip and by starting 2.6.0, one column added, every count unchanged, the old timeout setting read as a ceiling, and 2.5.0 starts again on the upgraded database. No real `.env`, key or shop database was used | [update_in_place_check.txt](test-results/update_in_place_check.txt) |
| Lint | not run | **Not run.** There is still no ESLint or other linter configuration; type-checking is the only static check | |

## 2. What was added for this release

The brief asked for tests of the voice workflow, the typed workflow, multilingual parsing, inventory validation, confirm and cancel, owner and staff permissions, Gnani failures, database persistence and performance measurement. Most of those were already covered by the 889 tests that existed; the table says which file covers what now and what is new.

| Area | Where it is covered | New in 2.6.0 |
|---|---|---|
| Voice workflow (audio in, reply, optional voice) | `test_api_voice.py`, `test_ws_proxy.py`, `test_release_260.py` | Reply first and voice after (`/api/turns/{id}/speak` speaks only the stored text, 404 for a customer turn or a missing one, 410 after an hour, a failed voice keeps the reply); a recording with no speech returns a full reply and leaves the open bill as it was; the old one-request path still works; the WebSocket `defer_audio` order |
| Typed workflow and dialogue | `test_dialogue_api.py`, `test_cart_edit.py`, `test_saas_api.py` | A typed turn is marked typed and has no speech stages |
| Multilingual parsing | `test_nlu_parser.py`, `test_languages_nlu.py`, `test_branded_nlu.py`, `test_languages_registry.py`, `test_languages_api.py` | Unchanged: no language was added or altered. Still typed text only |
| Inventory validation, confirm and cancel, no oversell, no duplicate order | `test_order_integrity.py`, `test_api_admin.py` | Unchanged; the same suite passes on the changed pipeline. A frontend test checks that the bill is put back from the server after a reload |
| Owner and staff permissions | `test_auth.py`, `test_security.py` | `GET /api/diagnostics/voice` is owner-only (staff 403, visitors 401); the speak and client-timing routes need a session; the route inventory test knows the three new routes |
| Gnani failures | `test_gnani_contract.py`, `test_api_voice.py`, `test_release_260.py` | One pooled connection reused and replaced when closed; a request that was sent and not answered is `TIMEOUT` (504) and **not repeated**; a connection failure is retried on a fresh connection and the tries are logged; `429`/`5xx` are retried and a bad request is not; separate speech-to-text and text-to-speech limits with the old setting as a ceiling; the worst-case wait is one call, not three |
| Database persistence | `test_seed.py`, `test_exports_and_shop.py`, `test_release_260.py` | The new `attempts` column is added without changing anything else and a second start changes nothing; old rows count as one try; the update never touches the `.env` file or the database file itself; `.env` is written in one step, other lines kept, a byte-order mark read |
| Performance measurement | `test_release_260.py`, `scripts/bench_voice_path.py`, `scripts/benchmark_api.py` | Every stage of a spoken turn is stored and adds up; a retried speech call is recorded; asking for the voice twice adds its time once; diagnostics counts and medians match the rows behind them; percentiles match NumPy's linear interpolation; turns saved before 2.6.0 are left out, not counted as zero |
| The browser side | `Diagnostics.test.tsx` (9), `OrderDesk.voice.test.tsx` (11), `openSession.test.ts` (9), `audio.test.ts` (more cases), `shell.test.tsx`, `Settings.test.tsx`, `Analytics.test.tsx` | Voice diagnostics page (owner only, "Not measured yet", period switch, tables in a scroll wrapper); the Order desk states, no-speech message, offline message, retry with the recording kept; silence trimming and automatic end of speech; the Demo data default; the "so far" line on the Analytics tiles |
| The real browser | `scripts/e2e_browser.py` | Voice diagnostics: link for the owner, none for staff, a 403 from the API for staff, a plain notice instead of timings, "Not measured yet", no horizontal scroll on phones; the Demo data default after a real order |

New file: `backend/tests/test_release_260.py` (53 tests, all with a simulated Gnani), plus three tests in `test_ws_proxy.py` for the realtime socket's `defer_audio` order (the turn first, a failed voice still follows it, and the old shape without the option). The backend count went from 889 to 945 (+56). The frontend went from 383 to 431 (+48: 29 in three new files, `Diagnostics.test.tsx`, `OrderDesk.voice.test.tsx` and `openSession.test.ts`, and 19 added to `audio.test.ts`, `shell.test.tsx`, `Analytics.test.tsx` and `Settings.test.tsx`).

## 3. What the testing found

Found and fixed during this release (a fuller list is in [CHANGELOG.md](../CHANGELOG.md)):

1. **A recording with no speech could blank the open bill.** The reply to a silent recording carried no bill, so the screen showed an empty one. Found while writing the voice-path tests. The server now returns the open bill and the screen leaves it alone.
2. **A hung speech service held a request for up to 121.5 s** at the defaults and was reported as a network error: a sent-and-unanswered call was tried three times. Now it is one call, at most 20 s (speech to text) or 15 s (text to speech), reported as `TIMEOUT`.
3. **The Settings page could leave `.env` half-written** if the process died while rewriting it, and a Windows byte-order mark could hide the first key. Now one atomic replace; other lines kept.
4. **Voice diagnostics scrolled sideways on a phone** (89 px too wide at 320, 49 at 360, 19 at 390). Found by the real-browser width sweep; a unit test did not catch it. Fixed, and the sweep and a unit test now guard it.
5. **A shop on its first day saw ₹0 and 0 orders in the first three Analytics tiles** above charts showing that day's orders. Found by looking at the screenshots. The tiles keep counting complete periods and now show the unfinished one beside them.

Failures that were in the tests or documents and not in the product (all fixed before the final runs): five frontend tests assumed the old Demo data default; the Settings tests needed a router for a new link; the committed `docs/openapi.json` and `eval/results/evaluation_summary.json` carried the old version number; a sentence in the documents tripped the wording guard; and the browser script's first version of the new checks raced the sidebar render and treated a deliberate 403 as unexpected. Two full runs were lost to how they were run, not to the product: a frontend build started while the backend suite was running removed `frontend/dist` and produced two `StaticFiles` errors, and a browser run hit the script's time cap in the button audit. Both were rerun clean (and the build must not be started while the backend suite runs).

## 4. Performance measurements

See [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md) for the method and every figure. In short, on a **local stand-in with stated delays (simulated, not Gnani)**:

- connections opened for 20 calls: 20 before, 1 now;
- reply on screen for one spoken turn: 1350.7 ms before, 659.6 ms now (the voice is asked for after the reply is shown; the time until the voice is ready is about the same);
- a hung service: a spoken order was held 4529 ms before, 1020 ms now, with the stand-in's short limits; at the real defaults the worst case falls from 121.5 s to 20 s (calculated from the limits, not measured);
- typed orders on the real server, 2.5.0 and 2.6.0 back to back on 3,101-order databases: one typed turn p50 7.10 ms / p95 9.73 ms against 7.32 / 10.49; text parse 5.11 / 6.45 against 5.34 / 7.04; confirming an order 12.62 / 17.07 against 12.50 / 16.96. **No regression.** The analytics overview moved from 38.1 / 78.8 to 40.0 / 100.3 ms; its 95th percentile varies between runs on this machine and no analytics query was changed.

No real speech latency was measured, because no key and no route to Gnani exist here.

## 5. What could not be run or completed

- **Live Gnani, for any of the eleven languages.** No key, no route. So no real speech-to-text accuracy, no real latency, no check that a language code or voice is accepted. Every language is still "Not verified live".
- **A microphone, and a real shop's noise.** The recorder's silence trimming and automatic end of speech were tested on synthetic audio and in jsdom only.
- **Windows.** The setup scripts were built on Linux. Tests check their structure; `cmd.exe` was not run.
- **Safari, Firefox, a screen reader, axe, Lighthouse, a real phone.** Chromium (headless) only.
- **More than one server process.** The no-duplicate-order guarantee depends on one process and is documented as a limit.
- **The generated project report** (`PROJECT_REPORT.*`) was not regenerated; it was the 2.5.0 report at that release, and has since been regenerated for 2.7.0.
- **Streaming.** Nothing in this release streams speech or replies faster than the Gnani REST calls return; the app does not claim it.
