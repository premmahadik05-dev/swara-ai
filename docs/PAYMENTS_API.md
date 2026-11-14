# Payments API (2.7.0)

Cash, UPI and Razorpay payments for an existing order, payment history, refunds, invoices and payment analytics.
The machine-readable list of routes is [openapi.json](openapi.json) (a test fails if it is out of date). This page says what each route is for, who may call it, and what can go wrong.

## Conventions

- **Money is always an integer number of paise** (`amount_paise: 17200` is ₹172). Currency is `INR`.
- **Sign-in:** the HttpOnly session cookie, exactly as for the rest of the API. Every unsafe request (`POST`, `PUT`, `PATCH`, `DELETE`) also needs the `X-CSRF-Token` header (the value is in `GET /api/auth/session` as `csrf_token`).
  The one route that needs neither is the Razorpay webhook, whose credential is its signature.
- **Roles:** *owner* and *staff* may start and finish payments and read history and invoices. Only the *owner* may refund, read payment analytics, and set the shop's UPI ID. The server enforces this; hiding a button in the screen is not the control.
- **Errors** have one shape: `{"detail": {"code": "ALREADY_PAID", "message": "A plain sentence", ...}}`. Codes are listed at the end.
- **Rate limit:** the routes that start or change a payment share the app's per-address limit (HTTP 429 when exceeded).
- **The amount is never taken from the client.** Starting a payment sends only the way (`method`) and an optional `idempotency_key`; the amount is the order's total as held by the server at that moment.

## Statuses

| Payment `status` | Meaning |
|---|---|
| `pending` | Started, not finished. At most one per order (a database rule, not only a check in code) |
| `paid` | Cash recorded by a person, a UPI QR confirmed by a person, or Razorpay confirmed it |
| `failed` | Razorpay reported a failure, or a capture failed. The order can be paid again |
| `cancelled` | Closed by a person, or closed automatically when its order was cancelled |
| `partially_refunded` | Some of a paid amount has been refunded (the refund is **processed**, not just asked for) |
| `refunded` | All of it |

An order with no payment in this app reports `none` ("Not recorded"). That is **not** the same as unpaid: shops took cash before payments existed here, and those orders are left exactly as they were.

| `verification` | `verified` | Meaning |
|---|---|---|
| `cash` | false | A person recorded cash received. No provider is involved |
| `manual` | false | A person confirmed a UPI QR for the shop's own UPI ID. **Not verified by any provider** and labelled that way everywhere |
| `signature` / `webhook` / `provider` | true | Razorpay confirmed it (a valid checkout signature plus a lookup at Razorpay, or a valid signed webhook) |

`attention` is set when the owner should look, and is never cleared or fixed silently:

| Flag | Meaning |
|---|---|
| `amount_mismatch` | Razorpay reports an amount (or order, or currency) different from the bill. The payment is **not** marked paid |
| `duplicate_collection` | Money was collected for an order that already has a paid payment. A second Razorpay capture is **not** recorded as a new payment; the owner refunds it in the Razorpay dashboard |
| `late_payment` | Razorpay reports a payment as captured after the app had closed that payment as failed or cancelled |
| `order_cancelled` | Money was collected for an order that is cancelled |
| `refund_mismatch` | A refund reported as processed would have taken the total refunded above the amount paid; only what was left was recorded |

## Routes

### Configuration

`GET /api/payments/config` (owner, staff) returns which ways of paying are available now and why not, if not:

```json
{"mode": "test", "currency": "INR", "gst_configured": false,
 "methods": {"cash": {"available": true, "reason": null},
             "upi": {"available": true, "mode": "manual", "reason": null},
             "razorpay": {"available": false, "reason": "Razorpay keys are not set. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env."}},
 "razorpay": {"enabled": false, "key_id": null, "test_mode": true}, "pending_minutes": 30}
```

The owner also gets `owner`: whether each secret **is set** (never the value), the webhook URL, and the shop's UPI ID and payee name. The key **secret** and webhook **secret** are never returned to anyone.

### History

| Route | Who | Notes |
|---|---|---|
| `GET /api/payments` | owner, staff | Query: `status`, `method`, `q` (payment code, bill code, customer or reference), `since`, `until` (India dates, inclusive), `include_synthetic`, `attention`, `sort` (`newest`, `oldest`, `amount_high` or `amount_low`), `limit` (1-100), `offset`. Returns `total`, `counts` per status (which honour every filter except `status`) and `items` |
| `GET /api/payments/{id}` | owner, staff | One payment with its `refunds` and its `events` (the audit trail, oldest first) |
| `GET /api/orders/{order_id}/payments` | owner, staff | The order's payments and a `summary` (`status`, `paid_paise`, `refunded_paise`, `method`, `payment_id`, `pending_payment_id`). Orders list `payment` with the same summary |
| `GET /api/payments/analytics?days=30` | **owner** | Sums from the `payments` and `refunds` tables only. See below |

### Starting and finishing a payment

`POST /api/orders/{order_id}/payments` body `{"method": "cash" | "upi" | "razorpay", "idempotency_key": "optional, up to 64 characters"}`

- Creates a `pending` payment for the order's server-side total and answers **201**.
- The same `idempotency_key` again, or asking again while a payment of the same way is already open, answers **200** with that payment instead of a second one. The same key with a different way or order answers **409 `IDEMPOTENCY_CONFLICT`**.
- An order that is already paid answers **409 `ALREADY_PAID`**; a cancelled one **409 `ORDER_CANCELLED`**; one with another way already open **409 `PAYMENT_IN_PROGRESS`**; a total of zero **409 `NOTHING_TO_PAY`**.
- `upi` needs a valid UPI ID in Settings (or Razorpay's own QR switched on), else **409 `UPI_NOT_SET_UP`**; `razorpay` needs working keys, else **409 `RAZORPAY_OFF`**.
- For Razorpay the reply includes `checkout`: the public key id, the Razorpay order id and the amount, which is all the browser needs to open Checkout. Nothing else about the keys is sent.
- Starting a payment **does not touch stock**. Stock was taken once when the order was confirmed; no payment, retry or refund changes it.

| Route | Body | What it does |
|---|---|---|
| `POST /api/payments/{id}/cash` | `{"received_paise": 50000}` | Records cash received. Less than the bill: **422 `CASH_SHORT`**. An obvious slip (over 20 times the bill plus ₹1,000): **422 `CASH_TOO_MUCH`**. Records who did it and when. Change is worked out, not stored as money |
| `POST /api/payments/{id}/confirm-upi` | `{"reference": "UTR412345678"}` | A person confirms they **saw the money** for a manual UPI QR. The reference (4 to 40 letters, digits, `-`, `_`, `/`, space) is kept. The payment is `paid` but `verified: false`, `verification: "manual"`. Wrong kind of payment: **409 `WRONG_METHOD`**; bad reference: **422 `BAD_REFERENCE`** |
| `POST /api/payments/{id}/razorpay/verify` | the three values Checkout returned: `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature` | Checks the signature, then asks Razorpay for the payment and compares amount, currency and order. **Paid only if all of it holds.** A bad signature answers **400 `BAD_SIGNATURE`**: the attempt is written to the audit trail and the payment is not changed. The browser's own "success" is never used. The same confirmation delivered twice returns the same paid payment and records nothing again |
| `POST /api/payments/{id}/refresh` | none | Asks the provider about a `pending` Razorpay payment (or provider QR) and records what Razorpay says. A cash or manual UPI payment cannot be refreshed |
| `POST /api/payments/{id}/cancel` | `{"reason": "optional"}` | Closes a payment that is still `pending`. Only a payment that is still waiting can be closed: anything else (paid, failed, already cancelled) is **409 `NOT_PENDING`**; refund a paid one instead |

Recording cash or confirming a UPI payment on a payment that is already paid is refused with **409 `ALREADY_PAID`** and records nothing a second time.

### Refunds (owner only)

`POST /api/payments/{id}/refunds` body `{"amount_paise": 1000, "reason": "Item returned", "idempotency_key": "optional"}`

- `amount_paise` left out refunds everything that is left. A reason is required (**422 `REASON_REQUIRED`**). More than what is left: **422 `REFUND_TOO_LARGE`** (the message says how much is left).
- **Razorpay payment:** the server calls Razorpay's refund API. The refund is recorded as `pending` (**"Waiting for Razorpay to confirm"**) and becomes `processed` only when Razorpay says so (reply to the call, a `refund.processed` webhook, or `POST /api/refunds/{id}/refresh`). A failed refund is `failed` and frees that amount to be tried again. The payment status moves to `partially_refunded` or `refunded` only for processed money.
- **Cash or manual UPI payment:** there is no provider to call. The owner returns the money by hand and the app **records** that, as `kind: "manual"`, `status: "processed"`, labelled "Recorded by the owner. Not confirmed by a payment provider."
- **Duplicate protection:** `idempotency_key` is 8 to 64 characters from letters, digits and `. _ : -` (**422 `BAD_IDEMPOTENCY_KEY`** otherwise). The same key again returns the original refund (HTTP 200) and does nothing more; the same key for a different refund is **409 `IDEMPOTENCY_CONFLICT`**. The screens send one key per refund attempt, so a double click is one refund. A call with **no** key gets a fresh random key, so it is a new refund each time, limited only by what is left. Money that is waiting for Razorpay counts as already used, so the code never lets refunded plus waiting money exceed the amount paid; a database check also stops the refunded total passing the amount.
- Staff get **403**.

`POST /api/refunds/{id}/refresh` asks Razorpay about a `pending` refund and records the answer.

### Invoices

`GET /api/orders/{order_id}/invoice` (owner, staff) returns the invoice, creating it the first time it is asked for. The number is `INV-<year>-<six digits>`, issued once and the same on every later call (a database uniqueness rule on year and sequence; a clash between two simultaneous first requests is retried).
A cancelled order with no invoice has none: **409 `ORDER_CANCELLED`**. The shop name is stored as it was on the day.

It carries the shop, the customer (name, and phone when known), the items with quantities and unit prices, `subtotal_paise`, `discount_paise`, `total_paise`, the payment (way, status, reference, who confirmed it, the amount refunded) and `tax_note`.
**It is not a GST tax invoice:** no merchant tax details are configured (`gst_configured: false`), no tax is calculated, and `tax_note` says so. The app makes no GST compliance claim.

### Analytics (owner only)

`GET /api/payments/analytics?days=30&include_synthetic=true` returns `kpis` (`collected_paise`, `refunds_paise`, `net_paise`, `paid_count`, `average_paise`, `cash_paise`, `upi_paise`, `razorpay_paise`, `upi_manual_paise` (the part of UPI that a person confirmed, not a provider),
`pending_count`, `pending_paise`, `failed_count`, `failed_paise`, `refund_count`, `refunds_waiting_count`, `refunds_waiting_paise`, `needs_attention`), `by_method`, and `daily`, `weekly` and `monthly` series split by way paid.
Every number is summed from the database rows; a period with no payments is zero, and orders with no payment recorded are not counted as money received. Cancelled and failed payments are not collected money.

### Razorpay webhook (no sign-in)

`POST /api/payments/webhooks/razorpay`

- Needs `RAZORPAY_WEBHOOK_SECRET`. Without it every call is refused with **503 `WEBHOOK_NOT_CONFIGURED`**.
- The signature in `X-Razorpay-Signature` is checked (HMAC-SHA256, constant-time comparison) over the **exact bytes received**, before anything in the body is read. A missing or wrong signature answers **400 `BAD_SIGNATURE`** and nothing is recorded as paid. The body is limited to 256 KiB (**413**).
- Each event id (`X-Razorpay-Event-Id`) is stored with a uniqueness rule, so a **redelivered event is acknowledged with 200 and changes nothing**.
- A `payment.captured` (or `payment.authorized`, `order.paid`, `qr_code.credited`) is applied only after the same checks as `razorpay/verify`: the order id must be the one the server created, the amount must equal the amount due, the currency must be INR. A mismatch is flagged `amount_mismatch` and the payment is not marked paid.
- A capture that arrives after the payment was closed (`late_payment`), for a cancelled order (`order_cancelled`) or for an order that is already paid (`duplicate_collection`) is recorded in the audit trail and flagged for the owner. It is never hidden, and it never changes the order or its stock. A Razorpay payment id that is already attached to another record is ignored and logged.
- `refund.created`, `refund.processed` and `refund.failed` update the matching refund.

## What is logged

Every change of a payment is a row in `payment_events`: the source (webhook, checkout, a person, the system), the status before and after, whether a signature was valid, who did it, and a one-line message.
**Card numbers, card details, UPI PINs and secrets are never stored or logged.** A payment holds Razorpay's ids, the amounts, and for manual UPI the reference number a person typed. The shop's own UPI ID is stored with the payment it was shown for; a customer's UPI ID is not stored.

## Error codes

| HTTP | Code | When |
|---|---|---|
| 400 | `BAD_SIGNATURE` | The checkout or webhook signature does not match |
| 400 | `BAD_PAYLOAD` | The webhook body is not usable |
| 403 | (auth) | A staff account called an owner-only route |
| 404 | `ORDER_NOT_FOUND`, `PAYMENT_NOT_FOUND`, `REFUND_NOT_FOUND` | No such order, payment or refund |
| 409 | `ALREADY_PAID`, `PAYMENT_IN_PROGRESS`, `NOTHING_TO_PAY`, `ORDER_CANCELLED`, `PAID_ORDER` | Order state forbids it. `PAID_ORDER`: cancelling an order that still holds collected money (refund first) |
| 409 | `NOT_PENDING`, `WRONG_METHOD`, `IDEMPOTENCY_CONFLICT`, `NO_PROVIDER_PAYMENT` | The payment is not in a state or of a kind this call works on |
| 409 | `NOT_REFUNDABLE`, `NOTHING_TO_REFUND` | Not paid, or fully refunded already |
| 409 | `RAZORPAY_OFF`, `UPI_NOT_SET_UP` | That way is not set up (the message says how to set it up) |
| 413 | `PAYLOAD_TOO_LARGE` | Webhook body over 256 KiB |
| 422 | `BAD_METHOD`, `BAD_IDEMPOTENCY_KEY`, `BAD_REFERENCE`, `CASH_SHORT`, `CASH_TOO_MUCH`, `REASON_REQUIRED`, `REFUND_TOO_LARGE` | A value is not acceptable (the message says which) |
| 429 | (rate limit) | Too many requests from one address |
| 502 | `RAZORPAY_BAD_REPLY` | Razorpay answered in a way the app cannot use. Nothing is recorded as paid |
| 503 | `WEBHOOK_NOT_CONFIGURED`, `INVOICE_BUSY` | Webhook secret not set; or an invoice number could not be reserved (try again) |

## Changes to existing routes

- Orders in `GET /api/orders` and `GET /api/orders/{id}` now carry a `payment` summary. An order with no payment shows `status: "none"`.
- Cancelling an order (`POST /api/orders/{id}/status` to `cancelled`) is refused with **409 `PAID_ORDER`** while collected money has not been refunded, and closes a payment that is still waiting. Orders with no payments behave exactly as before.
- `PUT /api/settings` (owner) accepts `upi_vpa` and `upi_payee_name` (an empty string removes them). Payment secrets are **not** accepted there.
- The voice and typed ordering routes are unchanged.
