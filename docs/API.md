# API reference

The backend is a FastAPI app. The running app serves a searchable reference of every route at **`/docs`** (a small local page: it loads nothing from the internet and works under the strict content-security policy) and the machine-readable schema at **`/openapi.json`**; `/redoc` redirects to `/docs`. A copy of the schema is committed as [`openapi.json`](openapi.json) (exported from the code, 72 operations on 66 paths plus the WebSocket, version 2.6.0). Set `API_DOCS=false` in `.env` to switch the page and the schema off on a public server. A WebSocket endpoint, `/ws/voice`, is described below because OpenAPI cannot express it.

## Conventions

- **JSON in, JSON out.** Money is integer paise (`unit_price_paise`, `line_total_paise`, `total_paise`). Quantities are decimal strings in carts (`"2.000"`) and numbers in lists.
- **Errors** use one envelope: `{"detail": {"code": "NOT_CONFIGURED", "message": "..."}}`. FastAPI validation errors (422) keep their list form. The client maps both to a readable message.
- **Who may call what.** Every route needs a signed-in session except the short public list in the next section. The session is the `swara_session` cookie (`HttpOnly`, `SameSite=Lax`; `__Host-swara_session` over https). Routes marked *owner* additionally need the shop-owner role and answer `403 OWNER_ONLY` to staff. Without a session: `401 NOT_AUTHENTICATED`, or `401 SESSION_EXPIRED` when the session existed and has ended.
- **CSRF.** Every `POST`, `PUT`, `PATCH` and `DELETE` on a signed-in route must send the header `X-CSRF-Token` with the value returned by sign-in, sign-up or `GET /api/auth/session` (`403 CSRF_FAILED` otherwise). A browser request whose `Origin` is another website is refused (`403 BAD_ORIGIN`). Command-line clients that send no `Origin` are judged by session and token alone.
- **Rate limit.** Per client IP, default 60 requests per minute, `429` after that.
- **CSV exports** (`/api/orders/export.csv`, `/api/inventory/export.csv`, `/api/customers/export.csv`). `Content-Type: text/csv; charset=utf-8` with a byte-order mark so Excel reads Gujarati and Hindi correctly, CRLF line ends, times in IST, money in rupees to two decimals, `Content-Disposition: attachment; filename="swara-<what>-<date>.csv"`, `Cache-Control: no-store`. A text cell that starts with `=`, `+`, `-` or `@` (or a tab or carriage return) is written with a leading apostrophe so a spreadsheet cannot run it as a formula. At most 20,000 rows; a longer result is cut and answered with `X-Export-Truncated: true`.
- **Audio uploads.** `multipart/form-data`, field `audio`. Accepted: WAV, MP3, OGG, FLAC, AAC, M4A (checked by content, not file name). Max 8 MB and 30 s. WebM is rejected with an explanation.
- **Times** are ISO-8601 UTC; the UI converts to IST. Analytics group by **IST** day, week (Monday start) and month.
- **Pagination.** List endpoints take `page` and `page_size` (or `limit` and `offset` for orders) and return `total`, so the UI never needs the whole table. Status or stock counts for the tabs come back with the page (`counts`).
- **`include_synthetic`.** Orders, customers and analytics accept `include_synthetic=false` to leave out the generated demo rows (the "Demo data" switch in the UI). Every order and customer row carries `is_synthetic`.
- **`price_basis` and `source`.** Products say where their price (`demo` for the 65 curated staples, `shop` for a price the shopkeeper typed) and the product itself (`curated`, `off_india`, `manual`) came from.

## Endpoints

| Method | Path | What it does | Access | Needs |
|---|---|---|---|---|
| `GET` | `/api/health` | Liveness (`app`: "SWARA AI", `status`, `version`), DB check, product count, whether a Gnani key is configured, the shop name (`store_name`) and whether it is still the built-in demo name (`store_name_is_default`) | open |  |
| `POST` | `/api/text/parse` | Run the language engine on a sentence **without** touching any session or stock (used by the landing-page demo). Optional `language` (a language key) is a hint for text understanding | open |  |
| `POST` | `/api/text/turn` | One conversational turn from typed text; creates or continues a session; `speak=true` also returns Timbre audio. Optional `language`: the language chosen in the selector, used as a hint (422 `BAD_LANGUAGE` / `LANGUAGE_DISABLED` for a bad or switched-off key) | signed in |  |
| `GET` | `/api/languages` | The language registry: for each of the 11 languages its names, Prisma `language_code`, Timbre `language`, chosen and default voice, the voices Gnani documents for it, whether it is switched on, how far its text understanding is trusted (`tested` or `authored`), a sample sentence, and the **live verification** of its four checks (`tts`, `stt_code`, `stt_loopback`, `stt_human`: `passed`, `failed`, `skipped`, `simulated` or `not_run`). Also `modes` (auto-detect and mixed: available only on Prisma v3.0, with the reason when not), the switched-off list, links to the Gnani pages the table was built from, and where the verification file came from | signed in |  |
| `POST` | `/api/voice/turn` | One turn from audio (multipart `audio`, `language` = a language key, or `auto`/`mixed` on Prisma v3.0 only, `session_id`, `speak_reply`): Prisma → pipeline → optional Timbre. The response's `stt.language_code` is the code that was sent. With `speak_reply=false` the reply comes back without audio and the voice is asked for separately (`POST /api/turns/{turn_id}/speak`). A request that Gnani received and did not answer in time is `504 TIMEOUT` and is not repeated; a failure before it was accepted, `429` or `5xx` is tried up to three times | signed in | Gnani key |
| `POST` | `/api/turns/{turn_id}/speak` | Speak the reply of one stored assistant turn. No body: Timbre is asked to say **only the text the server stored for that turn**, in the language stored with it, never text sent by the caller. Used by the Order desk, which shows the written reply first and asks for the voice after. Returns `{turn_id, audio: {audio_id, audio_url, tts_ms, cached, error}, timings}`; when the voice cannot be made (no key, language switched off, Gnani refused or timed out) the answer is still HTTP 200 with `audio.error` set and no `audio_url`, and the written reply is already saved. `404` for an unknown turn or one that is not an assistant reply, `410 TOO_OLD` after one hour. Asking again for the same reply is served from the audio cache | signed in | Gnani key |
| `POST` | `/api/turns/{turn_id}/client-timing` | The browser reports what it measured for one spoken turn, apart from the server's own timing: `capture_ms` (length of the recording), `end_to_reply_ms` (end of speech to the reply on screen), `end_to_audio_ms` (end of speech to the voice starting), `upload_bytes`, `endpoint` (`manual`, `auto` or `live`: how the end of speech was decided). Every field is optional and bounded, unknown fields are refused (422), an empty body is a `404`. Stored in `turns.detail.client`. `404` for an unknown turn or one that is not an assistant reply | signed in |  |
| `GET` | `/api/diagnostics/voice` | **Voice diagnostics.** `hours` (1 to 720, default 168). Median and 95th-percentile time per step (audio check, speech to text, understanding, database, processing, spoken reply, server total), the Gnani calls (counts, failed by error type, retried, cached replies), the browser-reported times, typed-order timing, the ten slowest turns and the time limits in force. A figure with no data is `null` and the page shows "Not measured yet"; turns saved before 2.6.0 carry no timing and are left out | owner |  |
| `GET` | `/api/audio/{audio_id}` | Cached Timbre reply (WAV); id is a 32-hex hash | signed in |  |
| `GET` | `/api/sessions` | Recent sessions with turn counts and phase (`limit`) | signed in |  |
| `POST` | `/api/sessions` | Start an empty session | signed in |  |
| `GET` | `/api/sessions/{session_id}` | Full snapshot: turns, cart, pending question | signed in |  |
| `POST` | `/api/sessions/{session_id}/confirm` | Confirm the order now (same as saying yes); atomic stock decrement. May attach a customer | signed in |  |
| `POST` | `/api/sessions/{session_id}/cart` | Edit the open bill by hand: `{product_id, qty, mode: "set"\|"add"}`. Same stock rules as speech; more than the stock is refused, not clamped |  |  |
| `GET` | `/api/products` | Plain list; filters `q` (name or alias), `category`, `status` (`ok`/`low`/`out`). Kept for compatibility; the Inventory screen uses the paginated `/api/inventory` | signed in |  |
| `POST` | `/api/products` | Create a product (immediately orderable, aliases included) | owner |  |
| `GET` | `/api/products/{product_id}` | One product | signed in |  |
| `PATCH` | `/api/products/{product_id}` | Edit price, reorder level, aliases, name, active flag | owner |  |
| `POST` | `/api/products/{product_id}/restock` | Add stock (`qty` > 0); writes a stock movement | owner |  |
| `GET` | `/api/inventory` | **Paginated** inventory: `q`, `category`, `status`, `source`, `sort`, `page`, `page_size`; returns `counts` per stock status and `stock_value_paise` per row | signed in |  |
| `GET` | `/api/inventory/export.csv` | The stock list as CSV, for the same filters (`q`, `category`, `status`, `source`, `sort`) as `/api/inventory` | signed in |  |
| `GET` | `/api/inventory/alerts` | Products at or under their reorder level, `severity` `low` or `out` | signed in |  |
| `GET` | `/api/inventory/categories` | Categories with counts | signed in |  |
| `GET` | `/api/inventory/movements` | Latest stock movements (restock, sale, cancellation); not shown in the UI | signed in |  |
| `GET` | `/api/orders` | Paged order list with line items. Filters `status`, `channel`, `language`, `customer_id`, `q` (customer name, or an order number / code such as `SW-261110-3033`), `include_synthetic`, `sort`, `limit`, `offset`; returns per-status `counts` | signed in |  |
| `GET` | `/api/orders/export.csv` | Orders as CSV, one row per bill line, for the same filters as `/api/orders` | signed in |  |
| `GET` | `/api/orders/{order_id}` | One order with line items | signed in |  |
| `POST` | `/api/orders/{order_id}/status` | `fulfilled` or `cancelled` (cancel restocks exactly once) | owner |  |
| `GET` | `/api/customers` | Customers with order count, spend, average basket, last order; `q`, `sort`, `include_synthetic`, `page`, `page_size` | signed in |  |
| `GET` | `/api/customers/export.csv` | Customers as CSV (names and phone numbers), for `q`, `sort`, `include_synthetic` | owner |  |
| `GET` | `/api/customers/{customer_id}` | One customer with recent orders and top items | signed in |  |
| `POST` | `/api/customers` | Create a customer (name, optional phone, language, notes) | owner |  |
| `PATCH` | `/api/customers/{customer_id}` | Edit a customer | owner |  |
| `GET` | `/api/catalog` | Search the public product catalogue (5,325 items): `q`, `category`, `brand`, `unit`, `sort`, `page`, `page_size`; each row says whether it is already `in_shop` | signed in |  |
| `GET` | `/api/catalog/facets` | Categories, brands and units with counts, for the filters | signed in |  |
| `GET` | `/api/catalog/source` | Provenance of the catalogue from `data/sources/MANIFEST.json`: origin, licence, attribution, retrieval date, limitations | signed in |  |
| `GET` | `/api/catalog/{item_id}` | One item with the **raw** source values, the transformation steps applied and suggested spoken aliases | signed in |  |
| `POST` | `/api/catalog/{item_id}/import` | Add the item to the shop. `price_paise` is required (the catalogue has no prices); `stock`, `reorder_level`, `cost_paise` optional. 409 `ALREADY_IMPORTED` if it is already in the shop, 404 for an unknown item | owner |  |
| `GET` | `/api/search` | Command-bar search across products, customers, orders and the catalogue (`q`, `limit`) | signed in |  |
| `GET` | `/api/analytics/overview` | KPIs and chart series for a window (`days`, `include_synthetic`), computed from the orders table at request time | signed in |  |
| `GET` | `/api/analytics/sales` | Sales series by `grain` (`day`, `week`, `month`) for `periods` periods (caps 366 / 104 / 36), with a `partial` flag on the period that contains today | signed in |  |
| `GET` | `/api/analytics/demand` | Per-product velocity, days of cover, suggested reorder, trend vs the earlier window (withheld unless the earlier window is comparable) | signed in |  |
| `GET` | `/api/analytics/inventory` | Stock valuation at selling price (and at cost where a cost is recorded), by category, out-of-stock list, count of demo vs shop prices, items with no sales | signed in |  |
| `GET` | `/api/analytics/latency` | p50/p95 per service from the `api_calls` log and NLU timings from turns | signed in |  |
| `GET` | `/api/analytics/stock-movement` | Opening, added, returned, sold, written-off and current stock per product over `days` (1 to 365), read from the stock ledger, plus a daily in/out series valued at the current selling price. Demo orders never touched the shelf, so a fresh shop shows no movement | signed in |  |
| `GET` | `/api/evaluation` | The stored evaluation summary (`eval/results/evaluation_summary.json`) with, when their files exist, the test record (`verification`) and local HTTP timings (`api_latency`). `available: false` and the command to create it when the file is missing | signed in |  |
| `GET` | `/api/settings` | Public settings: masked key hint, models, voices, Evon status, limits. Never the key | signed in |  |
| `PUT` | `/api/settings` | Change the shop name (`store_name`: 2 to 80 characters, letters/numbers/spaces and `& ' . , - ( ) / + @`; written to `.env` as `STORE_NAME` so it survives a restart), STT model/format/bias, a voice per language (`tts_voice_<key>`, validated against the documented Timbre v2.5 list for that language: 422 `BAD_VOICE`), `disabled_languages` (a list of language keys; written to `.env` as `DISABLED_LANGUAGES`; English cannot be switched off: 422 `LANGUAGE_REQUIRED`), speed | owner |  |
| `PUT` | `/api/settings/gnani-key` | Store the key in `.env` (validated, write-only) | owner |  |
| `POST` | `/api/settings/test-gnani` | 2 real calls for one language (`?language=<key>`, default `en`): Timbre speaks that language's sample sentence, Prisma transcribes it. The result says `loopback: true` and carries the codes used. Refuses an unknown or switched-off language (422) | owner | Gnani key |
| `POST` | `/api/noise/preview` | Return a degraded copy of a WAV (`kind`, `snr_db`, `telephony`) with `X-Measured-SNR-dB`; no Gnani call | signed in |  |
| `POST` | `/api/noise/run` | Baseline + up to 8 degraded versions, each through Prisma, with WER/CER if `reference_text` is given | signed in | Gnani key |

### Accounts and contact

JSON bodies reject unknown fields (`422`). Passwords are 10 to 128 characters (rules in `AUTHENTICATION.md`). **Access** is `open` (no session), `signed in`, or `owner`.

| Method | Path | What it does | Access |
|---|---|---|---|
| `GET` | `/api/auth/config` | What the sign-in screens need: `signup_open`, `has_owner`, `owner_email_set`, `email_configured`, `verification_required`, password length limits, session lifetimes | open |
| `GET` | `/api/auth/session` | `{authenticated: false}` for a visitor, or the user, `csrf_token` and session details. Never an error for a visitor, so the app can ask on every start | open |
| `POST` | `/api/auth/signup` | `{full_name, email, password, confirm_password?, accept_terms}`. `201` with the user and a CSRF token (signed in at once), or `{verification_required: true}` when e-mail verification is on. `409` if the address exists, `403 SIGNUP_CLOSED` if sign-up is closed | open, rate limited |
| `POST` | `/api/auth/login` | `{email, password, remember}`. `200` with the user and CSRF token and the cookie. `401 INVALID_CREDENTIALS` (same for a wrong password and an unknown address), `429` while locked out, `403 EMAIL_NOT_VERIFIED`, `403 ACCOUNT_DISABLED` | open, rate limited |
| `POST` | `/api/auth/logout` | Ends this session on the server and clears the cookie. Needs `X-CSRF-Token` when a session exists; with no session it just clears the cookie | open |
| `POST` | `/api/auth/forgot` | `{email}`. Always the same neutral answer; sends a one-use link only when e-mail is set up and the address has an account. Says so when e-mail is not set up | open, rate limited |
| `POST` | `/api/auth/reset` | `{token, password, confirm_password?}`. One use, 1 hour. Ends every session of that person | open, rate limited |
| `POST` | `/api/auth/verify-email` | `{token}`. One use, 24 hours | open, rate limited |
| `POST` | `/api/auth/resend-verification` | `{email}`. Neutral answer | open, rate limited |
| `GET` | `/api/auth/me` | The signed-in user and session | signed in |
| `PATCH` | `/api/auth/profile` | `{full_name?, language?}`; `language` is one of the 11 language keys (422 `BAD_LANGUAGE` otherwise) | signed in |
| `POST` | `/api/auth/change-password` | `{current_password, new_password}`. Ends the person's other sessions | signed in |
| `GET` | `/api/auth/sessions` | This person's signed-in devices: id, readable device name ("Chrome on Windows"), times, `current`. No IP, token or hash | signed in |
| `POST` | `/api/auth/sessions/revoke-others` | Sign out everywhere except here | signed in |
| `DELETE` | `/api/auth/sessions/{id}` | Sign out one device | signed in |
| `GET` | `/api/auth/users` | The team | owner |
| `POST` | `/api/auth/users/{user_id}/active` | `{active}`; turning someone off also ends their sessions. The owner cannot be turned off | owner |
| `POST` | `/api/contact` | Landing-page contact form: `{name, email, topic, message}` (message 10 to 2,000 characters; a hidden `website` field is a bot trap). Saved in the database; e-mailed to `CONTACT_TO` only when e-mail works. The reply says which happened | open, rate limited |
| `GET` | `/api/contact/messages` | The inbox | owner |
| `POST` | `/api/contact/messages/{id}/handled` | Mark one handled | owner |
| `WS` | `/ws/voice` | Live speech streaming; the handshake needs the session cookie (close code 4401 without one, 1008 for a foreign origin) | signed in |

There is deliberately no delete endpoint for products, orders or customers: a cancelled order restocks, an inactive product is hidden, and history is kept.

### Payments, refunds and invoices (2.7.0)

The full reference, with request bodies, statuses, error codes and the webhook rules, is [PAYMENTS_API.md](PAYMENTS_API.md). The routes:

| Method | Path | Access |
|---|---|---|
| `GET` | `/api/payments/config` | owner, staff (owners also see whether each secret is set, never its value) |
| `GET` | `/api/payments`, `/api/payments/{id}`, `/api/orders/{id}/payments` | owner, staff |
| `POST` | `/api/orders/{id}/payments` (start; sends the way and an optional request key, never an amount) | owner, staff |
| `POST` | `/api/payments/{id}/cash`, `/confirm-upi`, `/razorpay/verify`, `/refresh`, `/cancel` | owner, staff |
| `POST` | `/api/payments/{id}/refunds`, `/api/refunds/{id}/refresh` | **owner only** |
| `GET` | `/api/payments/analytics` | **owner only** |
| `GET` | `/api/orders/{id}/invoice` | owner, staff |
| `POST` | `/api/payments/webhooks/razorpay` | no session: the Razorpay signature is the credential; refused while no webhook secret is set |

Orders from `GET /api/orders` carry a `payment` summary (`status: "none"` when nothing is recorded). `PUT /api/settings` (owner) takes `upi_vpa` and `upi_payee_name`.

## Examples (real responses from the running app)

### `POST /api/text/turn`

```json
{ "text": "mane 2 kilo chawal ane 1 litre doodh joie" }
```

```json
{
  "session_id": "5c85529efa804a48ad38",
  "transcript": "mane 2 kilo chawal ane 1 litre doodh joie",
  "language": "gu",
  "reply_text": "2 કિલો ચોખા અને 1 લીટર દૂધ ઉમેર્યું. અત્યાર સુધીનું કુલ ₹172. બીજું કંઈ જોઈએ છે?",
  "reply_lang": "gu",
  "phase": "collecting",
  "awaiting": "more_items",
  "pending": null,
  "cart": {
    "lines": [
      { "sku": "RICE-REGULAR", "name_en": "Rice",  "name_gu": "ચોખા", "qty": "2.000", "unit": "kg",
        "unit_price_paise": 5800, "line_total_paise": 11600, "assumed": false, "in_stock": 120.0 },
      { "sku": "MILK", "name_en": "Milk", "name_gu": "દૂધ", "qty": "1.000", "unit": "l",
        "unit_price_paise": 5600, "line_total_paise": 5600, "assumed": false, "in_stock": 90.0 }
    ],
    "total_paise": 17200
  },
  "order": null,
  "low_stock_alerts": [],
  "timings": { "stt_ms": null, "nlu_ms": 0.4, "tts_ms": null },
  "audio": null
}
```

(`parse`, `events` and turn ids omitted here for length; the full shape is `TurnResponse` in `frontend/src/types.ts`.) `phase` is `collecting`, `confirming`, `completed` or `cancelled`. `pending` is non-null when the assistant asked a question (`kind`: `choose_product`, `need_qty`, …) and carries the `options` to choose from.

### `POST /api/text/parse` (stateless)

```json
{ "text": "dedh kilo cheeni aur aadha litre tel" }
```

Resolves to Sugar 1.5 kg and Groundnut Oil 0.5 l, language `hinglish`. The *oil* line has `assumed_default: true` because "tel" is ambiguous and the shop default was used; the reply says so: *"Maine Groundnut Oil liya hai; badalna ho to dusra naam boliye."* The bill total is `16150` paise.

### `GET /api/products?q=milk`

```json
[ { "id": 26, "sku": "MILK", "name_en": "Milk", "category": "Dairy & Bakery", "unit": "l",
    "price_paise": 5600, "stock": 90.0, "reorder_level": 30.0,
    "aliases": ["milk", "doodh", "dudh", "dood", "દૂધ", "दूध"], "stock_status": "ok" } ]
```

### `GET /api/inventory/alerts`

```json
[ { "product_id": 9, "sku": "SABUDANA", "name": "Sabudana", "unit": "kg", "stock": 0.0, "reorder_level": 8.0, "severity": "out" } ]
```

### `GET /api/analytics/sales?grain=week&periods=3`

```json
{ "grain": "week", "periods": 3, "include_synthetic": true,
  "series": [
    { "period": "2026-10-26", "revenue_paise": 6549875, "orders": 181, "avg_basket_paise": 36187, "partial": false },
    { "period": "2026-11-02", "revenue_paise": 6413950, "orders": 176, "avg_basket_paise": 36442, "partial": false },
    { "period": "2026-11-09", "revenue_paise": 773825,  "orders": 26,  "avg_basket_paise": 29762, "partial": true }
  ],
  "totals": { "revenue_paise": 13737650, "orders": 383, "avg_basket_paise": 35868 } }
```

`period` is the first day of the IST period. `partial: true` marks the period that contains today: it is unfinished, so the UI draws it dashed and leaves it out of any comparison. These rows come from the generated demo history; with `include_synthetic=false` they would be empty until real orders exist.

### `GET /api/analytics/demand?days=7` (one product shown)

```json
{ "window_days": 7, "include_synthetic": true,
  "previous_window": { "days": 7, "days_with_orders": 8, "comparable": true },
  "method": "Trailing average of units sold per day over the window. Not a forecast. Suggested reorder tops stock up to 14 days of cover.",
  "products": [ { "product_id": 19, "name": "Tea Leaves (250 g pack)", "unit": "pack", "units_sold": 53.0, "revenue_paise": 636000,
                  "velocity_per_day": 7.571, "stock": 60.0, "days_of_cover": 7.9, "trend_pct": -5.4,
                  "suggested_reorder_qty": 46.0, "status": "ok" } ],
  "stockout_risk": [ "..." ], "rising": [ "..." ], "falling": [ "..." ] }
```

The windows are rolling (the last `days` x 24 hours and the same length before it), so `days_with_orders` counts IST calendar days touched by the earlier window and can be one more than `days`. `trend_pct` is `null` for every product when `comparable` is false (fewer than half of the earlier window's days had an order), instead of a percentage computed from almost nothing.

### `GET /api/catalog?q=parle&page_size=1`

```json
{ "total": 100, "page": 1, "page_size": 1,
  "items": [ { "id": 1163, "ean": "8901719124754", "name": "20-20 Nice - sugar sprinkled coconut biscuits", "brand": "Parle",
               "category": "Biscuits & Sweets", "pack_size": 0.5, "pack_unit": "kg", "pack_label": "500 g",
               "display_name": "Parle 20-20 Nice - sugar sprinkled coconut biscuits 500 g",
               "source_id": "off_india_2026-07-05", "provenance": "transformed", "in_shop": false } ] }
```

There is no price field, because the source has none. `provenance` is `transformed` because `name`, `pack_*` and `category` are derived from the raw values by listed rules; `GET /api/catalog/{id}` returns the raw values (`name_raw`, `quantity_raw`, `off_categories_raw`) beside them.

### `GET /api/customers?page_size=2` (first item)

```json
{ "total": 8, "page": 1, "page_size": 2,
  "items": [ { "id": 6, "name": "Demo Customer F", "notes": "Synthetic demo customer", "is_synthetic": true,
               "orders": 371, "spent_paise": 12739300, "avg_basket_paise": 34337, "last_order_at": "2026-11-10T07:12:00Z" } ] }
```

### `GET /api/search?q=milk&limit=2`

```json
{ "query": "milk",
  "products": [ { "id": 26, "title": "Milk", "subtitle": "Dairy & Bakery · MILK" } ],
  "customers": [], "orders": [],
  "catalog": [ { "id": 2323, "title": "A2 Buffalo Milk", "subtitle": "Sid's Farm · 500 ml" } ], "catalog_total": 346 }
```

(The catalogue list was cut to one item here.)

### `GET /api/orders?limit=1` (envelope, one order trimmed)

```json
{ "total": 3033, "limit": 1, "offset": 0,
  "counts": { "confirmed": 0, "fulfilled": 2893, "cancelled": 140, "all": 3033 },
  "items": [ { "id": 3033, "code": "SW-261110-3033", "status": "fulfilled", "channel": "voice", "language": "hinglish",
               "customer_name": "Demo Customer F", "customer_id": 6, "total_paise": 25900, "is_synthetic": true,
               "created_at": "2026-11-10T07:12:00Z",
               "items": [ { "product_id": 34, "name": "Garlic", "qty": 0.5, "unit": "kg", "unit_price_paise": 18000, "line_total_paise": 9000 } ] } ] }
```

These examples were captured from the running app on a fresh database with the default 120-day demo history, so the figures are generated demo data, not a real shop.

### Error example

```json
{ "detail": { "code": "NOT_CONFIGURED",
              "message": "Gnani API key is not configured. Add GNANI_API_KEY to .env (see README) and restart the backend." } }
```

## WebSocket `/ws/voice`

`ws://localhost:8000/ws/voice?language=gu&session_id=<optional>&speak_reply=true`

With `defer_audio=true` the server sends the `turn` message first and the spoken reply afterwards in an `audio` message (`{"type":"audio","assistant_turn_id","audio":{...},"timings":{"tts_ms","server_ms"}}`). This only changes the order of the two messages; it does not stream audio.

| Direction | Message |
|---|---|
| browser → server | binary frames of 16 kHz mono PCM16 (any size; the server re-frames to 1024 bytes) |
| browser → server | text `{"type":"commit"}` (finalise the current sentence) or `{"type":"end"}` |
| server → browser | `{"type":"ready"}`, `{"type":"speech_start"}`, `{"type":"processing"}` |
| server → browser | `{"type":"turn", ...TurnResponse, "segment":{"id","audio_ms"}}` for each final transcript |
| server → browser | `{"type":"error","code","message"}`, `{"type":"closed"}` |

`language` is a language key (`gu hi en hinglish mr bn ta te kn ml pa`), or `auto`/`mixed` on Prisma v3.0 only. An unknown or switched-off language, or `auto`/`mixed` on v2.5, sends `{"type":"error","code":"BAD_LANGUAGE"|"LANGUAGE_DISABLED"|"AUTO_DETECT_NEEDS_V3","message":...}` and closes the socket with code 1003; nothing is sent upstream and no other language is substituted.
Upstream, the realtime request carries the language in both `lang_code` and `language_code` because Gnani's documentation uses both names.

Same-origin only (the Origin header is checked). Requires a Gnani key. See [MODEL_INTEGRATION.md](MODEL_INTEGRATION.md) for the upstream protocol.

## Language errors

Every route that takes a language answers a language it cannot honour with HTTP 422 and the usual envelope. The code says what is wrong; **no other language is ever substituted.**

| `code` | When | Example message |
|---|---|---|
| `BAD_LANGUAGE` | The value is not one of the 11 keys (or `auto`/`mixed` where those are allowed). Keys are exact: `GU` or ` gu` is refused | `language must be one of [...]` |
| `LANGUAGE_DISABLED` | The language is in `DISABLED_LANGUAGES` | `Marathi is switched off on this server (DISABLED_LANGUAGES).` |
| `AUTO_DETECT_NEEDS_V3` | `auto` or `mixed` while `GNANI_STT_MODEL` is `prisma-v2.5` (one language per request; no auto-detect) | `Automatic language detection is not available on Prisma v2.5 ...` |
| `BAD_VOICE` | `PUT /api/settings` with a voice that is not in Gnani's documented Timbre v2.5 list for that language | |
| `LANGUAGE_REQUIRED` | `PUT /api/settings` tries to switch English off | |

When the language is fine but **Gnani** refuses or fails, the Gnani error is passed on (for example `INVALID_API_KEY`, 429 `RATE_LIMITED`, or a 400 for a code or voice Gnani does not accept) with no fallback provider and no substitute audio.
