# Files changed in 2.7.0

Every file that differs between the released 2.6.0 tree and this one, grouped by area. Built by comparing the two trees file by file (53 added, 70 changed, 0 removed; `.env`, databases, `node_modules`, `.venv`, `frontend/dist` and logs are not compared). The reasons for the changes are in [CHANGELOG.md](../CHANGELOG.md); how to update an existing install without touching its `.env` or database is in [UPDATING.md](UPDATING.md) and [MIGRATION_2.7.0.md](MIGRATION_2.7.0.md).

Not in this list because they are not part of the tree: your `.env`, your database and your uploads. The update never writes to them (the database gets new tables the first time 2.7.0 starts, after a backup; see [MIGRATION_2.7.0.md](MIGRATION_2.7.0.md)).

Files that the voice path, the parser and the stock rules live in are **not** in the "changed" lists below: `backend/app/nlu`, `backend/app/gnani`, `services/pipeline.py`, `routers/voice.py`, `routers/ws.py`, `services/speech.py`, `services/audio.py`, `languages.py`, `services/orders.py` and `services/inventory.py` are byte for byte the 2.6.0 files.

### Backend code (4 added, 6 changed, 0 removed)

- added `backend/app/migrations.py`
- added `backend/app/routers/payments.py`
- added `backend/app/services/payments.py`
- added `backend/app/services/razorpay.py`
- changed `backend/app/config.py`
- changed `backend/app/main.py`
- changed `backend/app/models.py`
- changed `backend/app/routers/orders.py`
- changed `backend/app/routers/settings.py`
- changed `backend/app/security.py`

### Backend tests (7 added, 1 changed, 0 removed)

- added `backend/tests/payment_helpers.py`
- added `backend/tests/test_payments_cash_upi.py`
- added `backend/tests/test_payments_history_invoice_analytics.py`
- added `backend/tests/test_payments_migration.py`
- added `backend/tests/test_payments_razorpay.py`
- added `backend/tests/test_payments_refunds.py`
- added `backend/tests/test_payments_security.py`
- changed `backend/tests/conftest.py`

### Frontend code (10 added, 11 changed, 0 removed)

- added `frontend/src/components/payments/PayCharts.tsx`
- added `frontend/src/components/payments/PaymentDialog.tsx`
- added `frontend/src/components/payments/PaymentsSettingsCard.tsx`
- added `frontend/src/components/payments/UpiQr.tsx`
- added `frontend/src/components/payments/badges.tsx`
- added `frontend/src/lib/payments.ts`
- added `frontend/src/pages/Invoice.tsx`
- added `frontend/src/pages/PaymentAnalytics.tsx`
- added `frontend/src/pages/PaymentDetail.tsx`
- added `frontend/src/pages/Payments.tsx`
- changed `frontend/src/App.tsx`
- changed `frontend/src/api/client.ts`
- changed `frontend/src/components/CommandPalette.tsx`
- changed `frontend/src/components/Icons.tsx`
- changed `frontend/src/components/Shell.tsx`
- changed `frontend/src/pages/OrderDesk.tsx`
- changed `frontend/src/pages/Orders.tsx`
- changed `frontend/src/pages/Settings.tsx`
- changed `frontend/src/styles/app.css`
- changed `frontend/src/test/fixtures.ts`
- changed `frontend/src/types.ts`

### Frontend tests (9 added, 2 changed, 0 removed)

- added `frontend/src/components/payments/PaymentDialog.test.tsx`
- added `frontend/src/components/payments/PaymentsSettingsCard.test.tsx`
- added `frontend/src/components/payments/UpiQr.test.tsx`
- added `frontend/src/lib/payments.test.ts`
- added `frontend/src/pages/Invoice.test.tsx`
- added `frontend/src/pages/Orders.payment.test.tsx`
- added `frontend/src/pages/PaymentAnalytics.test.tsx`
- added `frontend/src/pages/PaymentDetail.test.tsx`
- added `frontend/src/pages/Payments.test.tsx`
- changed `frontend/src/components/shell.test.tsx`
- changed `frontend/src/pages/OrderDesk.test.tsx`

### Frontend build files (0 added, 2 changed, 0 removed)

- changed `frontend/package-lock.json`
- changed `frontend/package.json`

### Scripts (3 added, 5 changed, 0 removed)

- added `scripts/check_update_in_place.py`
- added `scripts/migrate_db.py`
- added `scripts/take_payment_screenshots.py`
- changed `scripts/build_evaluation_summary.py`
- changed `scripts/build_report.py`
- changed `scripts/build_verification_summary.py`
- changed `scripts/demo_activity.py`
- changed `scripts/e2e_browser.py`

### Documentation (8 added, 24 changed, 0 removed)

- added `docs/CHANGED_FILES_2.7.0.md`
- added `docs/MIGRATION_2.7.0.md`
- added `docs/PAYMENTS_API.md`
- added `docs/PAYMENT_SECURITY_AUDIT.md`
- added `docs/PAYMENT_TESTING.md`
- added `docs/RAZORPAY_SETUP.md`
- added `docs/diagrams/payments.png`
- added `docs/report-figures/fig-payments.png`
- changed `docs/API.md`
- changed `docs/ARCHITECTURE.md`
- changed `docs/DATABASE.md`
- changed `docs/DESIGN.md`
- changed `docs/EVALUATION.md`
- changed `docs/LIMITATIONS.md`
- changed `docs/PROJECT_REPORT.docx`
- changed `docs/PROJECT_REPORT.md`
- changed `docs/PROJECT_REPORT.pdf`
- changed `docs/SECURITY.md`
- changed `docs/TESTING.md`
- changed `docs/TEST_REPORT_2.6.0.md`
- changed `docs/UPDATING.md`
- changed `docs/VERIFICATION_REPORT.md`
- changed `docs/diagrams/datamodel.png`
- changed `docs/diagrams/system.png`
- changed `docs/diagrams/workflow.png`
- changed `docs/openapi.json`
- changed `docs/report-data/demo_activity.json`
- changed `docs/report-figures/fig-demo-mix.png`
- changed `docs/report-figures/fig-demo-sales.png`
- changed `docs/report-figures/fig-latency.png`
- changed `docs/report/PROJECT_REPORT.template.md`
- changed `docs/report/ai-performance-page.png`

### Test logs (0 added, 10 changed, 0 removed)

- changed `docs/test-results/backend_pytest.txt`
- changed `docs/test-results/backend_pytest.xml`
- changed `docs/test-results/backend_pytest_clean_unzip.txt`
- changed `docs/test-results/dependency_audits.txt`
- changed `docs/test-results/e2e_browser_clean_unzip.txt`
- changed `docs/test-results/e2e_browser_controls.txt`
- changed `docs/test-results/e2e_browser_main.txt`
- changed `docs/test-results/frontend_build.txt`
- changed `docs/test-results/frontend_vitest.txt`
- changed `docs/test-results/update_in_place_check.txt`

### Screenshots (10 added, 3 changed, 0 removed)

- added `docs/screenshots/40-payment-choose.png`
- added `docs/screenshots/41-payment-upi-qr.png`
- added `docs/screenshots/42-payments.png`
- added `docs/screenshots/43-payment-detail.png`
- added `docs/screenshots/44-payment-analytics.png`
- added `docs/screenshots/45-invoice.png`
- added `docs/screenshots/46-print-invoice.png`
- added `docs/screenshots/47-payment-settings.png`
- added `docs/screenshots/48-phone-payment-upi-qr.png`
- added `docs/screenshots/49-phone-payments.png`
- changed `docs/screenshots/02-order-desk.png`
- changed `docs/screenshots/36-ai-performance.png`
- changed `docs/screenshots/37-phone-ai-performance.png`

### Evaluation results (2 added, 2 changed, 0 removed)

- added `eval/results/nlu_eval_v270_check.json`
- added `eval/results/nlu_failures_v270_check.json`
- changed `eval/results/evaluation_summary.json`
- changed `eval/results/verification_summary.json`

### Project files (0 added, 4 changed, 0 removed)

- changed `.env.example`
- changed `CHANGELOG.md`
- changed `README.md`
- changed `THIRD_PARTY_NOTICES.md`
