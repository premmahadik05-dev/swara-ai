# Razorpay test-mode setup

SWARA AI 2.7.0 can take payments in three ways: **cash**, **a UPI QR code for the shop's own UPI ID** (confirmed by a person), and **Razorpay** (UPI, cards and netbanking, confirmed by Razorpay).
Cash and the shop's own UPI QR work with no setup at all beyond typing the UPI ID in Settings. This page is only about Razorpay, and **only about Razorpay's test mode**.

**Read this first**

- Nothing here was run against Razorpay. This release was built and tested with a **stand-in for Razorpay** (a mock HTTP transport that returns the replies the code expects), because the build environment
  cannot reach Razorpay and no Razorpay account was available. The first real test-mode payment is yours to make, using the checklist at the end of this page. Treat anything that fails there as a finding to report, not as something that was verified.
- Never paste a Razorpay key or secret into a chat, an e-mail, a screenshot or a support message. Keys go in your own `.env` file and nowhere else. SWARA AI never asks for them in the browser.
- **Live mode is off and stays off until you switch it on yourself** (see "Going live" at the end). Nothing in this release turns it on.

## What you need

| Thing | Where it goes | Notes |
|---|---|---|
| Key ID (starts with `rzp_test_`) | `RAZORPAY_KEY_ID` in `.env` | Public. The browser needs it to open Checkout |
| Key secret | `RAZORPAY_KEY_SECRET` in `.env` | **Private.** Stays on the server. Never shown in the app, never sent to the browser |
| Webhook secret | `RAZORPAY_WEBHOOK_SECRET` in `.env` | **Private.** You choose it when you create the webhook in the Razorpay dashboard |
| `PAYMENT_MODE=test` | `.env` | Already the default. Test keys only work in test mode |

`.env.example` has these four lines, empty, so you can see where they go. It never contains a real value, and your existing `.env` is not overwritten by an update: you add the lines yourself.

## Steps

1. **Make a Razorpay account and stay in test mode.** The Razorpay dashboard has a Test/Live switch. Use Test.
2. **Generate a test API key** in the dashboard (the menu is under account settings, "API keys"; names and positions change, so follow Razorpay's own documentation if yours differs).
   Razorpay shows the key secret once. Copy it straight into `.env`; do not keep it anywhere else.
3. **Edit `.env` on the shop computer** (a text editor is fine; Settings in the app does not write payment secrets, on purpose):

   ```
   PAYMENT_MODE=test
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxx
   RAZORPAY_KEY_SECRET=...your test key secret...
   RAZORPAY_WEBHOOK_SECRET=...a long random phrase you choose...
   ```

   Leave every `GNANI_*` line exactly as it is.
4. **Restart the app** (close the `start.bat` window and run it again). The secrets are read once, at start.
5. **Open Settings, then the Payments card** (owner only). It should say "Razorpay is ready" with the mode (test), show the key ID, and say **Set on the server (never shown)** or **Not set** for the two secrets (never the values).
   If it says why Razorpay is off, fix that line. The most common one: the key ID does not start with `rzp_test_` while `PAYMENT_MODE` is `test`.
6. **Create the webhook** (so Razorpay can tell the app about payments even if the browser tab is closed). In the Razorpay dashboard, add a webhook:
   - **URL:** the address shown in the Payments card (it ends in `/api/payments/webhooks/razorpay`). Razorpay must be able to reach it from the internet over HTTPS, so a shop computer needs a public address or a tunnelling tool you trust. A webhook that cannot reach the app does not break payments: the app also confirms a payment itself by asking Razorpay (see "How a payment is confirmed"), it just learns about it later.
   - **Secret:** the same phrase you put in `RAZORPAY_WEBHOOK_SECRET`.
   - **Events:** `payment.authorized`, `payment.captured`, `payment.failed`, `order.paid`, `refund.created`, `refund.processed`, `refund.failed` (add `qr_code.credited` only if you use Razorpay's own UPI QR, below).
7. **Take a test payment.** Order desk, confirm an order, **Take payment**, **Razorpay Checkout**, **Open Razorpay Checkout**. Use the test payment details from Razorpay's documentation ("test card details" and test UPI IDs). Do not use a real card or a real UPI PIN in test mode.

## How a payment is confirmed

The screen never decides that a payment worked. In order:

1. The server creates the Razorpay order **for the bill total it holds itself** (the browser only says which order and which way). The amount cannot be changed from the browser.
2. Razorpay Checkout opens in the browser and returns three values to the page. The page sends them to the server and shows nothing yet.
3. The server checks the **signature** (HMAC-SHA256 over `order_id|payment_id` with the key secret), then **asks Razorpay** for the payment and compares the amount, the currency and the order. Only then is the payment marked paid and verified.
4. Separately, the **webhook** (a signed message from Razorpay) can confirm the same payment. It is accepted only if its signature over the raw bytes is valid, each event id is processed once, and the same checks apply. If both arrive, the payment is recorded once.
5. If the amount, order or currency does not match, the payment is **not** marked paid. It is flagged for the owner (`amount_mismatch`) and shown under "Needs a look".

A refund works the same way: the owner starts it, the server calls Razorpay, and the refund stays **Waiting** until Razorpay says it is processed. The screen never says "Refunded" on its own.

## Razorpay's own UPI QR (optional)

By default the **UPI QR code** option shows a QR for **the shop's own UPI ID**. It cannot see the money, so a person must check the bank or UPI app and confirm it; until then it is shown as **Not verified**, in the payment, on the invoice and in the analytics.

If Razorpay has switched on QR codes for your account, set `RAZORPAY_UPI_QR=true` in `.env`. The app then asks Razorpay for a QR for the exact amount and the payment **confirms itself** (via the webhook, or by asking Razorpay every few seconds while the dialog is open). This path was written from Razorpay's documentation and tested only with the stand-in; check it in test mode before relying on it.

## Test-mode checklist (do this once, with your own test keys)

| # | Do this | You should see |
|---|---|---|
| 1 | Settings, Payments card | "Razorpay is ready", mode test, key ID shown, both secrets "Set on the server (never shown)" |
| 2 | Confirm a typed order, Take payment, Razorpay Checkout, pay with Razorpay's test details | The dialog says "Payment received" **after** the server confirmed it, the payment shows **Paid** and **Confirmed by Razorpay** |
| 3 | Close the dialog while Razorpay is still open, then reopen it from the order | It resumes the same payment; there is not a second one |
| 4 | Fail a test payment on purpose (Razorpay's test details include a failing card) | The payment shows **Failed** with a reason; the order can be paid again |
| 5 | Payment detail, **Refund** a part of it | A refund is listed as **Waiting**, then **Refunded** once Razorpay confirms (use "Check status" if the webhook cannot reach you) |
| 6 | Dashboard, Webhooks, look at the delivery log | Deliveries answered `200`. A redelivered event changes nothing |
| 7 | Stock | The order's stock was taken **once**, when the order was confirmed, not by any payment or retry |

If a step does not match, the useful things to send are the payment code (`PAY-...`), the Activity list on the payment page, and the server log lines for it. **Never send keys or secrets.**

## Going live (not done here, and not done for you)

Live payments move real money. The app will not use live keys unless **both** are true: `PAYMENT_MODE=live` in `.env` **and** the key ID starts with `rzp_live_`. A live key with `PAYMENT_MODE=test`, or a test key with `PAYMENT_MODE=live`, is refused with the reason, so a live key cannot be used by accident.
Before switching: complete the checklist above with test keys, complete Razorpay's own account activation, read [PAYMENT_SECURITY_AUDIT.md](PAYMENT_SECURITY_AUDIT.md) (especially "Not verified"), and decide who is allowed to refund (only the owner can).
This release makes no claim that a live payment has ever been made with it.

## Troubleshooting

| Message in Settings or the dialog | Meaning |
|---|---|
| "Razorpay keys are not set" | `RAZORPAY_KEY_ID` or `RAZORPAY_KEY_SECRET` is empty, or the app was not restarted after editing `.env` |
| "PAYMENT_MODE is test but the key id does not start with rzp_test_" | You pasted a live key while in test mode (or the reverse) |
| Webhook shows "Not set up" or answers 503 | `RAZORPAY_WEBHOOK_SECRET` is empty. The app refuses every webhook until it is set |
| Dashboard shows webhook deliveries failing with 400 | The secret in the dashboard is different from the one in `.env` |
| A payment stays **Waiting** after the customer paid | Press **Check with Razorpay** on the payment. If Razorpay says it is not captured, nothing is recorded |
| "Needs a look" on a payment | The money or the order did not match what the app expected (amount, order, a late payment, or a second payment for an order already paid). Read the reason on the payment page; it is never fixed silently |
