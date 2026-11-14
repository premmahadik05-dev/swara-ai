# Design system ("Counter") and UI notes

<p><img src="../brand/svg/swara-logo-horizontal-light.svg" alt="SWARA AI" height="48"></p>

The interface is a small SaaS-style admin for a shop owner: a sidebar, a top bar with global search, and pages for the dashboard, order desk, orders, customers, inventory, catalogue, analytics, conversations, noise lab and settings. It is built to be read quickly by someone standing at a counter, in two languages of script, on a laptop or a phone.

Screens: [docs/screenshots](screenshots) (real captures from `scripts/take_screenshots.py`, light theme only, desktop 1440 px, tablet 820 px, phone 390 px).

## Principles

1. **The bill is the centrepiece.** The Order desk and the Live page draw the bill as a printed receipt (ruled lines, tabular figures, one large total) because that is what a customer understands. Everything else is quiet.
2. **One accent, used sparingly.** Champagne gold appears only on the brand mark, the voice orb, the active-page marker, the pressed/active states of a few controls and the accent button. Chrome, charts and tables use ink, white, ivory and warm neutrals so data stands out. The product has **one theme, light**: pages and cards are white, the sidebar and inset panels are ivory, and no screen, icon or e-mail is black or dark. There is no dark mode and no setting for one.
3. **Nothing decorative.** No hero gradients, no stock illustrations, no invented numbers. Every figure on screen comes from an API response; if the data is generated, the page says so.
4. **Say where the data came from.** A "Demo" badge on generated rows, a global *Demo data* switch, "Demo price" and "Shop price" badges, and a "sourced / transformed" tag on every catalogue field. See [DATA.md](DATA.md).
5. **Say what is missing.** Empty states say what to do next. Comparisons say "Not enough earlier data to compare" instead of printing a misleading percentage. The unfinished day or week is drawn dashed or hatched and left out of comparisons.

## Tokens (`frontend/src/styles/tokens.css`)

Every colour in the app is a CSS variable; components never hard-code one. There is **one theme: light**. The page declares `color-scheme: light`, so a browser or operating system set to dark does not recolour form controls, scrollbars or the page (a browser test checks this with dark mode emulated, and a Python test fails the build if a dark token, a `data-theme` switch or a `prefers-color-scheme: dark` rule appears). A theme choice saved by an earlier build is deleted on load.

| Role | Value |
|---|---|
| Page and cards | White `#ffffff` |
| Secondary background (sidebar, table headers, inset panels, hover) | Ivory `#f7f5ef`; pressed and selected `#efebe0` |
| Text: primary / body / secondary | Ink `#242424` / `#4a4a4a` / `#686868` |
| Borders | `#eae7df` (cards, dividers); `#d9d4c6` (form controls, secondary buttons) |
| Primary action (button, selected pill) | Champagne gold `#d6b574` with ink text `#242424`; hover `#c9a459` |
| Link / focus ring / gold used as text | `#7a5810` / `#8a6414` / `#7a5810` (gold itself is too pale for text) |
| Status (text on its tint) | ok `#0a6c47` on `#e8f7ef`, warn `#9a4a05` on `#fff4dc`, bad `#b02a1f` on `#fdecea`, info `#1d4fb8` on `#eaf0fd` |
| Veil behind drawers and dialogs | `rgba(247, 245, 239, 0.82)`: light, not a dark scrim |

Type: **Newsreader** for display headings (the landing page, and the title of each page), **Geist** for text and controls, **Geist Mono** for codes, **Noto Sans** for Gujarati, Devanagari, Bengali, Tamil, Telugu, Kannada, Malayalam and Gurmukhi as fallbacks so item names in every supported language render with the same weight as English. All of them are bundled with the app (`@fontsource-variable/*`), so nothing is fetched from a CDN (the Content-Security-Policy allows fonts from this server only). See *Type system* below. Scale 12, 13, 14, 15, 18, 26 px; 28 px for tile figures. Money and quantities use tabular figures. Two radii (10 px, 14 px) and one shadow, used only for floating layers (drawers, dialogs, menus).

## Type system (version 2.4.0)

The brief for the 2.4.0 redesign put typography first: an editorial serif for display headings, a clean sans for the interface, one consistent hierarchy, fonts that may legally be bundled. The colours did not change.

| Role | Face | Why |
|---|---|---|
| Display headings (landing page, page titles in the app) | **Newsreader**, variable, with its optical-size axis | A serif drawn for reading on screens, with a real optical-size axis, so the large hero line is finer and tighter than the same face at 24 px. At weight 400 it reads as editorial without the heaviness of a display bold. SIL Open Font License 1.1 (the licence file ships in the package), served from this server as `@fontsource-variable/newsreader`; see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). |
| Text, controls, small headings | **Geist** | Unchanged. A neutral sans with tabular figures, which the bill and the tables need. |
| Codes, bill amounts | **Geist Mono** | Unchanged. |
| Indian scripts | **Noto Sans** (one variable family per script) | Unchanged. Newsreader has no Indic glyphs, so `--font-display` lists the Noto families after it: a Gujarati or Devanagari heading falls back to a face with the right shapes instead of the browser's default. |

Rules, each checked by `backend/tests/test_landing_design.py`:

- Headings are weight 400 (500 for the app's page titles). No heading on the landing page is bold; small group titles in the sans are 500.
- No italic accent word, no all-capital label, no eyebrow above a heading and no `01 / 02` numbering: the steps of the demonstration and the four parts of the architecture are marked with a rule and a gold dot, not numerals.
- Display sizes: hero `clamp(46px, 6.7vw, 96px)` with tracking -0.032em, section headings `clamp(34px, 4.4vw, 58px)` with -0.026em, the closing call to action up to 80 px; tracking tightens as the size grows. The hero lead is 17 to 19 px at a 1.6 line height and never wider than 40 characters.
- The hero headline sets in three lines at 1440 px (checked in the browser run).

The Newsreader family is only used for headings and short statements. Indian-script text in headings is never faux-bolded or italicised, and the app's tables, forms and the bill remain Geist. The global `h1` rule makes every page title serif, so the printed bill's heading is overridden back to Geist (a receipt is not an editorial page); the sign-in and sign-up titles use the serif at weight 500 and the tagline in their side panel the serif at 400. Headings of level two to four inside the signed-in app stay Geist, deliberately, so the dashboard changes only in its page titles.

## Chart colours and what was verified

Categorical chart colours are `--c1..--c4`, always assigned in the same order and never cycled. In this app they mean the order language (Gujarati = blue, Hindi = orange, Hinglish = green, English = amber); a single-series chart uses blue. Only four hues are validated, so the seven languages added later are drawn in the muted tone, labelled "Other languages" in the legend and told apart by the name beside each bar, never by colour alone.

Computed with the data-viz palette validator (OKLCH lightness band, chroma floor, colour-vision-deficiency separation, contrast against the chart surface), **re-run on 10 Nov 2026** against the real chart surface, white `#ffffff`:

| Colours | Result |
|---|---|
| `#2a78d6 #eb6834 #1baf7a #eda100` | **Pass**: lightness band, chroma, worst adjacent colour-blind separation ΔE 9.1 (protan), normal-vision ΔE 22.9. **Relief needed** on contrast: green is 2.82:1 and amber 2.17:1 against white (below the 3:1 for marks) |

The relief is met the way the method requires: no colour carries meaning alone. Every chart has a **Chart / Table** switch, bars carry their values as text, and multi-colour charts have a legend with the language name.

Text contrast, computed (WCAG 2.x ratio) from the values in `tokens.css` on white, ivory and the pressed/selected surface (10 Nov 2026; the lowest of the three is shown):

| Pair | Contrast |
|---|---|
| Primary text `#242424` | 13.03:1 |
| Body text `#4a4a4a` | 7.44:1 |
| Secondary text `#686868` | 4.68:1 |
| Links and gold-as-text `#7a5810` | 5.46:1 |
| Focus ring `#8a6414` (needs 3:1) | 4.50:1 |
| Primary button label (ink on gold) | 7.92:1; 6.61:1 on the hover colour |
| Status text on its tint (ok, warn, bad, info) | 5.73:1 to 6.42:1 |
| Chart axis labels `#5f5b51` | 6.77:1 |
| Sidebar: primary / body / secondary text (on ivory) | 14.24:1 / 8.13:1 / 5.11:1 |
| The "Typed" bar gray `#8a8578` (a mark, not text) | 3.68:1 |

Gold `#d6b574` on white is only 1.96:1 (1.80:1 on ivory), which is why it is only ever a fill, a graphic or the background of an ink-coloured label, never text: gold-coloured text uses `#7a5810`. The logo's gold mark is a gradient from champagne `#DDBF7C` through `#BC9444` to `#88621F`; it is a graphic, not text, and the name itself is the Ink wordmark (14.24:1 on ivory, 15.52:1 on white).

**Known gap:** input, select and secondary-button borders (`#d9d4c6`) are 1.48:1 against white. They are visible but below the 3:1 that WCAG 1.4.11 asks of the boundary of a form control; the controls are also identifiable by their label and shape. Raising it was not done because it changes the look of every form. The ratios above are arithmetic on the token values; they are not a substitute for a screen-reader or Lighthouse/axe audit, which was not run (see [LIMITATIONS.md](LIMITATIONS.md)).

## Evaluation charts, matrices and tables (version 2.5.0)

The AI performance page (`/performance`) and the stock-movement card on Analytics follow the same rules as the other charts, plus these:

- **A chart is only drawn for a number that was measured.** A missing figure is a "Not measured" badge or a hatched "n/a" cell, never an estimate or a zero.
- **Every chart has a Table view**, and the two matrices (a heatmap of percentages and a confusion matrix of counts) are real HTML tables with captions, row and column headers, so a screen reader can walk them. Every cell prints its number, so colour is never the only carrier of meaning. They are plain HTML, not a chart-library component (`components/Heatmap.tsx`).
- **One gold ramp for magnitude** (the heat colour is the brand gold mixed into the surface, lighter to darker), and the series colours `--c1..--c4` for categories, in a fixed order. In the confusion matrix a right answer is gold, a harmless outcome (asked which pack, not recognised) is grey and a wrong answer is rose. Text never takes a series colour.
- **Restrained geometry:** thin bars, no 3-D, no dual axes, titles that say what the chart shows, axis titles with units, direct value labels where there is room, and a tooltip with the counts behind every cell.
- **Tables** (`components/GridTable.tsx`): search, an optional filter, click-to-sort column headings (`aria-sort`), pagination, an empty state that says what to do, and a CSV download of exactly what is shown after search and filter (a text cell starting with `=`, `+`, `-` or `@` is prefixed so a spreadsheet does not run it; UTF-8 with a byte-order mark). It is for tables whose rows are all in the browser; long lists (orders, inventory, catalogue) page on the server.
- **Status indicators** pair a colour with a word (Passed, Failed, Not run, Mocked, Live, Not measured); none is colour alone.
- **Generated demo data is labelled** wherever it appears, and the Demo data switch removes it from every view.

The chart colours are the ones validated above; the gold ramp is a single hue whose cells print their values, so the contrast note above (marks below 3:1 relieved by a table view and printed values) applies to it too. Nothing in this release was checked with a screen reader, axe or Lighthouse.

## Brand: SWARA AI

**Name** SWARA AI. **Tagline** "Every Voice. Smarter Commerce." **Short description** "Your intelligent voice-powered assistant for smarter grocery commerce." The full and brand descriptions are in `frontend/src/lib/brand.ts` (front end) and `backend/app/brand.py` (API), so the wording lives in one place per side.

**The mark.** An S made of three flowing gold ribbons. The centre line is two stacked ellipse arcs joined with a common tangent, so the S is smooth; each ribbon follows a true parallel offset of that line, tapers to a point at both ends and has its own length, which reads as a voice waveform bent into a letter. Below about 40 px (the sidebar, the tab icon) a bolder two-ribbon version is used, because three fine ribbons blur there.

**The wordmark.** Exactly "SWARA AI": Geist SemiBold capitals, one weight, one size and one colour (Ink `#242424`), converted to outlines so no SVG needs the font. The name is never split into a big word and a small one, and nothing else is written in the logo.

**Palette.** Ink `#242424` (the wordmark), Champagne Gold `#D6B574` (the mark, as a gradient `#DDBF7C`, `#BC9444`, `#88621F` on ivory and white), Ivory `#F7F5EF`. Nothing the product ships is a black surface: the app icons are white, ivory or gold tiles, the share card is ivory and the sidebar is ivory. There is no reversed logo for dark backgrounds, because the product has no dark surface; the logo is not to be placed on one.

**Files** (all generated from one geometry definition by `python scripts/brand/build_logo.py`, so they cannot drift apart): [`brand/`](../brand) holds the horizontal logo, symbol, compact symbol, square app icon (white, ivory, gold and one-colour), favicon and a 1200 by 630 share card, each as SVG and as transparent PNG where transparency makes sense (app icons are opaque rounded squares by design), in full colour and in one colour (Ink). There is no reversed or dark-surface set. [`brand/README.md`](../brand/README.md) has the usage rules. The React component is `components/Logo.tsx`; its geometry is the generated `components/logoPaths.ts`.

**Where it appears in the app.** Sidebar (full lockup, or the mark alone when the sidebar is collapsed or on a tablet), landing page header (full name on desktop and phone) and footer, the landing About section, the browser tab (SVG and ICO favicon on a transparent background, readable on light and dark tab strips), the Apple touch icon, the web manifest icons, the browser and API page titles, and the API docs. The sign-in, sign-up, password-reset and e-mail-confirmation screens (the shared frame in `components/AuthKit.tsx`), the Terms and Privacy pages and the not-found page carry the logo too.

**Honest limits.** The favicon is checked at 16, 32 and 48 px by eye on rendered PNGs; the logo was not tested on printed material or on every operating system's icon grid. There is no trademark search behind the name.

## Layout and responsiveness

- Sidebar (252 px) collapses to an icon rail on request and to a slide-in menu below 900 px. The top bar holds global search (Ctrl/⌘+K), the *Demo data* switch and the theme toggle.
- Four summary tiles are 4 across, 2 by 2 below 1240 px, and stacked below 520 px (never three plus one).
- Tables become labelled cards below 760 px (Orders, Customers, Inventory, Conversations). Because column headers disappear in that layout, Inventory gets a *Sort by* select on phones.
- Card headers wrap, so on a phone the chart controls drop below the title instead of squeezing it.
- Drawers (order, customer, catalogue item, product) are full width on a phone and 520 px on larger screens. Every drawer has a link-able URL (`?open=<id>`), so a row can be shared or reloaded.

## Components and states

Reusable pieces, each used by more than one page: `Card`, `Badge`, `Field`, `Seg` (segmented control), `Drawer`, `Dialog`/`ConfirmDialog`, `Combobox`, `CommandPalette`, `Pagination`, `SortTh`, `KpiCard` + `Delta`, `ChartCard` (chart with a table alternative), `TrendChart`, `HBars`, `ColumnBars`, `Sparkline`, `HealthBar`, `Toast`, `ErrorBoundary`.

Every data page has four explicit states: **loading** (skeleton rows or cards, not a spinner), **error** (what failed, in words, with *Try again*), **empty** (what to do next), and **loaded**. A render error anywhere is caught by the error boundary and shows a recovery message instead of a blank screen. Cancelling an order, the one action that cannot be undone from the UI, uses a confirm dialog that names the consequence (stock returns to the shelf).

## Accessibility

Checked by automated tests and by reading the markup; **not** checked with a screen reader on real hardware.

- Skip-to-content link; one `h1` per page; landmarks for navigation, main content and drawers.
- Every control is a real `button`, `a`, `input` or `select` with a visible label or `aria-label`. Visible focus ring on all of them.
- Segmented controls use `aria-pressed`; sortable headers use `aria-sort`; the pagination announces "Page x of y" politely.
- Overlays trap focus, restore it to the control that opened them, close on Escape and lock page scroll. Destructive confirms are `alertdialog` with the consequence as the description.
- Whole table rows open a drawer with Enter or Space (the key press is stopped from reaching the drawer's own Close button). A bug where Enter closed the drawer instantly was found and fixed this way.
- Toasts are a polite live region; error notes use `role="alert"`.
- Colour is never the only signal: badges carry text, bars carry values, every chart has a table view, partial periods are marked in words.
- `prefers-reduced-motion` turns off animation. Text is selectable; sizes are in `px` but the layout reflows at browser zoom.

## The public site and the sign-in screens

The landing page, Terms, Privacy and the account screens use the same tokens as the app (white page, champagne gold primary buttons with ink text, champagne gold for the
accent), in the one light theme. `styles/landing.css` holds the landing layout; the auth screens share one frame
(`components/AuthKit.tsx`: logo, title, form, the links beneath).

- **Landing structure** (redesigned in 2.4.0), top to bottom: a 72 px sticky bar (wordmark, Product, How it works, Languages, Technology, Security, Contact, Sign In, Get Started Free; a menu button
  on screens under 1080 px, and the Sign In button folds into that menu under 560 px); the hero (headline "Commerce that understands every voice.", the supporting
  paragraph, *Get Started Free* and *Explore the Platform*, a row of the eleven language names in their own scripts, then the real dashboard screenshot on an ivory band); one
  statement of what the product is; **Product**, five areas each with its own composition; **How it works**, a live demonstration; **Languages**; **Technology**;
  **Security and trust**; **Why SWARA AI**; the FAQ; a closing call to action beside the contact form; the footer.
- **The five product areas are not one card repeated.** Voice ordering is typeset: three sample sentences in Gujarati, Hindi and Hinglish, with the quantity and item the
  language engine picks out underlined in gold (the underlines were checked against the running parser). Product recognition is a ledger: four spellings of one item
  (*doodh*, *દૂધ*, *दूध*, *milk*) meeting at "Milk". Inventory is one large screenshot with three facts beside it. Order processing overlaps two screenshots (the Order desk
  and the Orders list). Analytics is one full-width screenshot with three plain notes under it. Every picture is a real screenshot of the running app, with a caption that
  says the shop and numbers are generated demo data.
- **The demonstration is labelled as one.** The four-step strip (Heard, Products found, Stock checked, Bill prepared) is filled in from the real `POST /api/text/parse`
  answer for the sentence typed in the box; before the first answer it says "Waiting for a sentence" rather than showing an invented result. The note under it says that it
  is typed text only, with no audio, that it runs on this server against generated demo stock, and that nothing is saved.
- **Languages** are a ledger of eleven rows in two groups (the four from the first release, the seven added in 2.3.0), each with its name in its own script, a sample
  sentence and a note. The paragraph above it says what has been checked (the text rules are unit-tested) and what has not (none of the eleven has been run against Gnani's live service
  in this release). The page does not say "verified", "fully supported" or "all languages work".
- **What is deliberately not on it:** testimonials, partner or customer logos, customer counts, revenue figures, performance claims, certifications and a GitHub link
  (there is no public repository to point to). The footer's *API reference* link goes to the backend's own `/docs` page, which exists unless the owner sets `API_DOCS=false`.
- **One memorable thing, the rest quiet.** The type is the memorable thing: a large, light serif headline on white. Colour is the stated palette only (white, ivory `#f7f5ef`,
  champagne gold `#d6b574` for the primary button, thin underlines and rules, ink and grey text, `#eae7df` borders). There is no dark section, no glass, no decorative gradient
  (the one gradient is the hard-edged white-to-ivory band behind the hero picture) and no emoji. The only motion is a short rise of the hero text on load and a gold underline
  that draws under a bar link on hover; both are off under `prefers-reduced-motion`. Anchors scroll below the sticky bar (`scroll-padding-top: 88px`).
- **Forms.** Every field has a visible label, errors are written beside the field and read out (`aria-invalid`, `aria-describedby`), the first invalid field takes focus,
  the password has a show/hide button and a strength guide that never replaces the server's rules, and a failed sign-in clears the password but keeps the e-mail.
- **Keyboard.** A skip link is the first stop on every page; the FAQ uses native `details`, and the mobile menu closes on Escape and returns focus to its button.
- **Responsive.** Checked in a real browser at 320, 360, 390, 768, 1024, 1280 and 1440 px on 6 public and 8 signed-in pages: no horizontal scrolling at any of them.
  That check found two real overflow bugs at 320 px (a page grid with a minimum width on the order desk, and a segmented control wider than its card on
  Analytics); both are fixed (`minmax(0, 1fr)` and letting nested flex rows shrink) and the check is in `scripts/e2e_browser.py`.
- **Not done:** an axe or Lighthouse run, a screen-reader pass, Safari and Firefox, real phones.

## UX review for 2.6.0

Every screen the release touched was opened in a real browser at desktop (1440), tablet (820) and phone (390) size, in the one light theme, and checked against the rules above. The screens that did not change (Orders, Customers, Inventory, Catalogue, Settings, Account, the public site) were only re-run through the width sweep and the button and link audit ([TESTING.md](TESTING.md)); they were not redesigned. What the review found:

| Finding | What was done |
|---|---|
| **Voice diagnostics scrolled sideways on a phone** (89 px too wide at 320, 49 at 360, 19 at 390). Two tables sat in their cards without the shared scroll wrapper, and a long settings value would not wrap. Found by the width sweep in the browser run, not by a unit test. | Tables now sit in the shared `table-wrap`, the settings table lets text wrap, and the three-column table's headings wrap so nothing needs an inner scroll down to 320 px. A unit test checks that every table on the page has the wrapper; the width sweep now includes `/diagnostics`. |
| **A shop on its first day saw ₹0 and 0 orders in the first three Analytics tiles** above charts that showed that day's orders. The tiles count complete periods only (the page says so), which is right for comparisons but reads as a contradiction. The new Demo data default makes this the first thing a new shop sees. | Each of the three tiles gets one quiet line, "Today so far: ₹300" (or "This week so far", "This month so far"), shown only when the unfinished period has orders. The totals and the comparisons are unchanged. |
| Four tiles on Voice diagnostics each say "Not measured yet" before any spoken order, and a note says the same. | Kept. Each tile names what it will show and what it needs, so none is a repeat of another, and a zero would be a claim the page cannot make. |
| On the Order desk the conversation box is a scroll area, so on a phone its first message can sit half-hidden above the latest. | Kept. It is a normal scrolled list with a visible edge; the latest message stays in view. |
| The Order desk, Voice diagnostics and Analytics use the same cards, tables, badges, spacing, type and colours as the other screens; no new colour, animation or decoration was added. | None needed. |

Not checked: Safari and Firefox, a screen reader, axe or Lighthouse, a real phone, and a real microphone. Chromium (headless) is the only browser used.

## Performance and robustness

- The API client de-duplicates identical in-flight `GET`s and keeps a short cache (8 to 60 seconds) for slow-changing reads: health, settings, category list, catalogue facets and source. Any write clears it.
- Live pages poll every few seconds and **pause while the tab is hidden**.
- Search boxes are debounced; filters live in the URL, so back/forward and reloads behave.
- Pagination, sorting and filtering happen on the server (`page`, `page_size`, `sort`, `q`), so the 5,325-row catalogue never loads at once.
- Pages are code-split; the chart library is a separate chunk loaded only by pages that draw charts.
- Analytics numbers are computed from API responses by small tested functions (`lib/stats.ts`): complete periods only, comparison only when the earlier window is full and at least half of its periods had orders.

## Testing the UI

- 513 Vitest + Testing Library tests across 50 files cover each page's data flow (mock `fetch`, assert on what a person sees), the comparison rules, overlays and focus handling, the API client's cache, and the keyboard paths. See [TESTING.md](TESTING.md).
- `scripts/take_screenshots.py` opens every page at desktop, tablet and phone size, in the one light theme, against the running backend and **fails on any console error, failed request or HTTP 4xx/5xx**. The last run's count is in [TESTING.md](TESTING.md).
- Not done: Safari and Firefox, a Lighthouse or axe pass, a screen-reader pass, and testing on real phones. Chromium (headless) is the only browser used.
- The type and layout rules of the landing page are checked against the real stylesheet by `backend/tests/test_landing_design.py` (10 tests), because the frontend runner does not load CSS. They check rules, not taste.


## Language selector

The Order desk's language control is a single button (current language in its own script, with its Gnani code) that opens a list of all eleven languages plus Auto-detect. Each row shows an honest status badge taken from the server: "Not verified live" (the default), "Live checked" (a real run passed both a voice and a speech check), "Live check failed", "Simulated only"; and "New in 2.3" for the seven languages whose understanding rules are unit-tested but not native-reviewed. A switched-off language is listed but cannot be chosen; Auto-detect is disabled with the reason when the server is on Prisma v2.5. The list works as a radio group (arrow keys, Escape closes and returns focus), every name carries the right `lang` attribute, and nothing is conveyed by colour alone. The status badges never use a "working" or "supported" word that a live check has not earned.
