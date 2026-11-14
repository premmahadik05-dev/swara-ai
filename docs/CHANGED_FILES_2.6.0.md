# Files changed in 2.6.0

Every file that differs between the 2.5.0 release tree and this one, grouped by area. Built by comparing the two trees file by file (56 added, 61 changed, 0 removed; `.env`, databases, `node_modules`, `.venv`, `frontend/dist` and logs are not compared). The reasons for the changes are in [CHANGELOG.md](../CHANGELOG.md); how to update an existing install without touching its `.env` or database is in [UPDATING.md](UPDATING.md).

Not in this list because they are not part of the tree: your `.env`, your database and your uploads. The update never writes to them.

### Backend code (2 added, 10 changed, 0 removed)

- added `backend/app/routers/diagnostics.py`
- added `backend/app/services/diagnostics.py`
- changed `backend/app/config.py`
- changed `backend/app/db.py`
- changed `backend/app/gnani/client.py`
- changed `backend/app/main.py`
- changed `backend/app/models.py`
- changed `backend/app/routers/settings.py`
- changed `backend/app/routers/voice.py`
- changed `backend/app/routers/ws.py`
- changed `backend/app/services/apilog.py`
- changed `backend/app/services/pipeline.py`

### Backend tests (1 added, 1 changed, 0 removed)

- added `backend/tests/test_release_260.py`
- changed `backend/tests/test_ws_proxy.py`

### Frontend code (2 added, 13 changed, 0 removed)

- added `frontend/src/lib/openSession.ts`
- added `frontend/src/pages/Diagnostics.tsx`
- changed `frontend/src/App.tsx`
- changed `frontend/src/api/client.ts`
- changed `frontend/src/components/CommandPalette.tsx`
- changed `frontend/src/components/Shell.tsx`
- changed `frontend/src/components/charts.tsx`
- changed `frontend/src/lib/audio.ts`
- changed `frontend/src/lib/scope.tsx`
- changed `frontend/src/pages/Analytics.tsx`
- changed `frontend/src/pages/OrderDesk.tsx`
- changed `frontend/src/pages/Settings.tsx`
- changed `frontend/src/styles/ui.css`
- changed `frontend/src/test/fixtures.ts`
- changed `frontend/src/types.ts`

### Frontend tests (3 added, 7 changed, 0 removed)

- added `frontend/src/lib/openSession.test.ts`
- added `frontend/src/pages/Diagnostics.test.tsx`
- added `frontend/src/pages/OrderDesk.voice.test.tsx`
- changed `frontend/src/components/shell.test.tsx`
- changed `frontend/src/lib/audio.test.ts`
- changed `frontend/src/pages/Analytics.test.tsx`
- changed `frontend/src/pages/Customers.test.tsx`
- changed `frontend/src/pages/Dashboard.test.tsx`
- changed `frontend/src/pages/Orders.test.tsx`
- changed `frontend/src/pages/Settings.test.tsx`

### Frontend build files (1 added, 2 changed, 0 removed)

- added `frontend/tsconfig.tsbuildinfo`
- changed `frontend/package-lock.json`
- changed `frontend/package.json`

### Scripts (0 added, 3 changed, 0 removed)

- changed `scripts/build_verification_summary.py`
- changed `scripts/e2e_browser.py`
- changed `scripts/take_screenshots.py`

### Documentation (4 added, 10 changed, 0 removed)

- added `docs/CHANGED_FILES_2.6.0.md`
- added `docs/PERFORMANCE_REPORT.md`
- added `docs/TEST_REPORT_2.6.0.md`
- added `docs/UPDATING.md`
- changed `docs/API.md`
- changed `docs/ARCHITECTURE.md`
- changed `docs/DESIGN.md`
- changed `docs/EVALUATION.md`
- changed `docs/GNANI_SETUP.md`
- changed `docs/MODEL_INTEGRATION.md`
- changed `docs/SECURITY.md`
- changed `docs/TESTING.md`
- changed `docs/VERIFICATION_REPORT.md`
- changed `docs/openapi.json`

### Test logs (1 added, 9 changed, 0 removed)

- added `docs/test-results/update_in_place_check.txt`
- changed `docs/test-results/backend_pytest.txt`
- changed `docs/test-results/backend_pytest.xml`
- changed `docs/test-results/backend_pytest_clean_unzip.txt`
- changed `docs/test-results/dependency_audits.txt`
- changed `docs/test-results/e2e_browser_clean_unzip.txt`
- changed `docs/test-results/e2e_browser_controls.txt`
- changed `docs/test-results/e2e_browser_main.txt`
- changed `docs/test-results/frontend_build.txt`
- changed `docs/test-results/frontend_vitest.txt`

### Screenshots (39 added, 0 changed, 0 removed)

- added `docs/screenshots/01-landing.png`
- added `docs/screenshots/02-order-desk.png`
- added `docs/screenshots/03-dashboard.png`
- added `docs/screenshots/04-analytics.png`
- added `docs/screenshots/05-orders.png`
- added `docs/screenshots/06-order-details.png`
- added `docs/screenshots/07-customers.png`
- added `docs/screenshots/08-inventory.png`
- added `docs/screenshots/09-catalogue.png`
- added `docs/screenshots/10-catalogue-provenance.png`
- added `docs/screenshots/11-conversations.png`
- added `docs/screenshots/12-noise-lab.png`
- added `docs/screenshots/13-settings.png`
- added `docs/screenshots/14-landing-security.png`
- added `docs/screenshots/15-print-bill.png`
- added `docs/screenshots/16-tablet-dashboard.png`
- added `docs/screenshots/17-phone-dashboard.png`
- added `docs/screenshots/18-phone-order-desk.png`
- added `docs/screenshots/19-sign-in.png`
- added `docs/screenshots/20-sign-up.png`
- added `docs/screenshots/21-account.png`
- added `docs/screenshots/22-phone-sign-in.png`
- added `docs/screenshots/23-language-selector.png`
- added `docs/screenshots/24-languages-card.png`
- added `docs/screenshots/25-landing-voice.png`
- added `docs/screenshots/26-landing-recognition.png`
- added `docs/screenshots/27-landing-orders.png`
- added `docs/screenshots/28-landing-analytics.png`
- added `docs/screenshots/29-landing-demo.png`
- added `docs/screenshots/30-landing-languages.png`
- added `docs/screenshots/31-landing-technology.png`
- added `docs/screenshots/32-landing-tablet.png`
- added `docs/screenshots/33-landing-phone.png`
- added `docs/screenshots/34-landing-phone-menu.png`
- added `docs/screenshots/35-landing-phone-orders.png`
- added `docs/screenshots/36-ai-performance.png`
- added `docs/screenshots/37-phone-ai-performance.png`
- added `docs/screenshots/38-voice-diagnostics.png`
- added `docs/screenshots/39-phone-voice-diagnostics.png`

### Evaluation results (2 added, 3 changed, 0 removed)

- added `eval/results/nlu_eval_v260_check.json`
- added `eval/results/nlu_failures_v260_check.json`
- changed `eval/results/api_latency.json`
- changed `eval/results/evaluation_summary.json`
- changed `eval/results/verification_summary.json`

### Project files (1 added, 3 changed, 0 removed)

- added `.coverage`
- changed `.env.example`
- changed `CHANGELOG.md`
- changed `README.md`
