# Evaluation

Everything here is either **MEASURED** (a script in this repository produced it, and the output file is saved) or **PROPOSED** (an engineering target I chose; nothing has been measured against it). The two are never mixed in one cell.

> **The most important caveat.** No result below involves Gnani Prisma or Timbre. The build environment could not reach Gnani. Language-understanding numbers are on **transcripts I wrote**, not on transcripts Prisma produced from real speech. Speech accuracy, speech latency and acoustic-noise robustness are **not measured**. The scripts to measure them on your machine are provided and listed in section 6.

## 1. Summary: measured vs proposed

| Metric | Proposed target | Measured here | Status |
|---|---|---|---|
| Line accuracy (product + quantity + unit exactly right), authored gold set, 114 order sentences | ≥ 95% | **100%** after fixes (94.0% on the first run) | Measured, **tuned on the same set**, so optimistic; not a held-out result |
| Product recognition alone (right product, any quantity), authored set | ≥ 98% | **100%** (also 100% on the first run) | Measured, same caveat |
| Ambiguous requests are asked about, never guessed | 100% | **4/4** (0/4 on the first run, see 3.2) | Measured, 4 cases only |
| Non-order sentences (price questions, greetings) add nothing to the bill | 100% | **10/10** | Measured, 10 cases only |
| Language detected correctly when the detector is confident | ≥ 95% | **100%** (confident on 93.8% of sentences; the rest fall back to the session language) | Measured |
| Templated regression set (160 sentences from catalogue names) | 100% | **100%** | Regression check only; says nothing about generalisation |
| Order logic and money (stock never oversold, exact paise) | 0 defects | 0 failing tests of 1,103 backend + 513 frontend; stock race, double confirm and two simultaneous confirms covered by tests (`test_order_integrity.py`) | Measured (tests) |
| **Branded product recognition, held-out** (300 templated sentences, 527 products the matcher was not tuned on) | ≥ 90% exact | **81.3% exact** (244/300); **6.3% wrong product** (19); 5.3% asked which pack (16); 7.0% not recognised (21) | Measured on 2.5.0, text only, optimistic (section 3.4). 2.3.0 and 2.4.0 reported 84.0% exact / 8.3% wrong / 2 asked, before a pack-family alias fix |
| **Typed orders end to end** (sentence, "that's all", "confirm" through the real dialogue, 344 sentences, 11 languages) | 100% | **340 of 340** scored sentences gave the exact gold order; 4 sentences have gold lines that cannot be written as an order and are not scored | Measured; gold written by the parser's author (a ceiling), 7 languages without native review |
| **Stock guard** (the same orders against an empty shelf and a half-stocked shelf) | 0 oversold | **84 of 84** empty-shelf orders refused, 0 negative stock; half stock: 82 offered the remaining stock, 2 refused, 0 over-stock | Measured |
| **Language label** with no hint (648 sentences, 11 languages) | ≥ 95% | **100%** for every language except Hinglish 99.5% (195 of 196) and Marathi **71.4%** (5 of 7; Hindi and Marathi share a script) | Measured; Marathi's sample is 7 sentences |
| Parser latency | p95 < 5 ms | **p50 0.134 ms, p95 0.213 ms** (1,440 calls) | Measured |
| Local HTTP latency, typed turn | p95 < 100 ms | **p50 7.10 ms, p95 9.73 ms** | Measured on one Linux machine, signed in, 2.6.0 (2.5.0 on the same machine and database size, run just before: p50 7.32 ms, p95 10.49 ms) |
| Local HTTP latency, confirm order (stock update and ledger rows) | p95 < 100 ms | **p50 12.62 ms, p95 17.07 ms** | Measured, 2.6.0 |
| Local HTTP latency, analytics overview (30 days, 3,101 orders in the database) | p95 < 300 ms | **p50 40.02 ms, p95 100.28 ms** | Measured, 2.6.0 |
| Local HTTP latency, sales series (61 days / 25 months) | p95 < 300 ms | **p50 6.07 ms / 8.19 ms, p95 8.06 ms / 11.66 ms** | Measured |
| Line accuracy on **real Prisma transcripts of real shop speech** | ≥ 90% | not measured | **Not measured** |
| Speech-to-text word error rate, clean speech, per language | ≤ 15% | not measured | **Not measured** (needs your key: `verify_gnani`) |
| Word error rate at 10 dB and 5 dB SNR | ≤ 30% / ≤ 45% | not measured | **Not measured** (`evaluate_noise`, Noise lab) |
| End-to-end voice turn (record → reply audio), p95 | < 3 s | not measured | **Not measured**; Live screen records it as you use the app |
| Streaming time to first transcript | < 1.5 s | not measured | **Not measured** (`verify_gnani --stream`) |

The "proposed" column is my own engineering goal, not derived from data or from any Gnani statement.

## 2. Method and honesty notes

**The gold set** (`eval/utterances.jsonl`, 288 lines, built by `eval/build_dataset.py`):

| Set | Size | What it is | What it can and cannot show |
|---|---:|---|---|
| `handwritten` | 128 (Gujarati 37, Hindi 30, Hinglish 36, English 25) | Sentences I wrote in a customer's voice, including number idioms (*dedh, dhai, sava*), code-mixing, units, 4 ambiguous requests, 10 non-orders | **Not independent**: the same person wrote the parser and the test. Results are optimistic against a blind third-party set |
| `templated` | 160 (40 per language) | Generated from catalogue names with fixed templates | A **regression** check. It uses the catalogue's own names, so 100% here is expected |

A line is correct only if SKU, quantity **and** unit all match as *spoken* (a unit the customer did not say stays empty and the dialogue asks). Reported: precision, recall and F1 per line, utterance exact match, whether ambiguity was asked rather than guessed, whether a non-order added anything, and language accuracy overall and when the detector was confident.

**Two runs are kept, never merged:**

- `nlu_eval_first_run.json`: 284 sentences, before I looked at any failure.
- `nlu_eval_final.json` (identical to `nlu_eval_after_fixes.json`): 288 sentences, after the fixes below. I re-ran it on the final code to confirm it reproduces.

## 3. Language understanding (MEASURED, authored transcripts)

### 3.1 Results per language, final run

| Set / language | Sentences | Order sentences | Line F1 | Utterance exact | Ambiguity asked | Non-order, no false add | Language correct (all) |
|---|---:|---:|---:|---:|:---:|:---:|---:|
| handwritten Gujarati | 37 | 34 | 100% | 100% | 1/1 | 2/2 | 100% |
| handwritten Hindi | 30 | 27 | 100% | 100% | 1/1 | 2/2 | 100% |
| handwritten Hinglish | 36 | 32 | 100% | 100% | 1/1 | 3/3 | 97.2% |
| handwritten English | 25 | 21 | 100% | 100% | 1/1 | 3/3 | 100% |
| **handwritten total** | **128** | **114** | **100%** | **100%** | **4/4** | **10/10** | **99.2%** |
| templated (all four) | 160 | 160 | 100% | 100% | n/a | n/a | 100% |

The one language error is `paneer 250 gram`, which I labelled Hinglish but which carries no Hinglish cue at all (the detector says English, and not confidently). When the detector says it is confident (93.8% of authored sentences) it was right every time; otherwise the session's language is kept, so a wrong guess does not flip the conversation language.

### 3.2 First run, before any fix

| Set / language | Line F1 | Utterance exact | Ambiguity asked | Language correct (all) |
|---|---:|---:|:---:|---:|
| handwritten Gujarati | 95.1% | 93.9% | 0/1 | 100% |
| handwritten Hindi | 90.3% | 88.5% | 0/1 | 100% |
| handwritten Hinglish | 94.7% | 93.5% | 0/1 | **80.0%** |
| handwritten English | 95.8% | 95.0% | 0/1 | 100% |
| **handwritten total (124 sentences)** | **94.0%** | **92.7%** | **0/4** | **94.4%** |
| templated | 100% | 100% | n/a | 100% |

### 3.3 The 12 first-run failures, honestly classified

| Count | Case | Kind | What I did |
|---:|---|---|---|
| 6 | *adrak sau gram / અદરક સો ગ્રામ / अदरक सौ ग्राम* and *badam…*: bare "sau" read as 1 | **parser bug** | bare *sau / સો / सौ* now means 100 (and *hazaar* 1000) |
| 1 | *मूंग की दाल एक किलो*: split at the genitive "की" | **parser bug** | genitive particles dropped inside product phrases |
| 1 | *half a kilo tea*: unit lost between the fraction and "kilo" | **parser bug** | article and filler words skipped between a fraction and its unit |
| 4 | *"two packets of biscuits"* in four languages, labelled "ambiguous" | **gold-label change** | The shop has a single biscuit product, so the correct behaviour is to add it. I **relabelled the four cases as normal** after seeing the failure. This is an honest change to the answer key, not a parser fix, and it is why the first run scores 0/4 on ambiguity |

Fixes found outside the 12 (from language-detection errors in the first run and from re-reading output): English sentences tagged Hinglish because *kilo* was a Hinglish cue; romanised Gujarati (*mane … joie*) answered in Hindi; code-mixed Gujarati+English counted as English because script was counted per character rather than per token; Latin diacritics (*dūdh*) unmatched. Four new "dal" ambiguity cases were added to the gold set because *dal* genuinely matches several pulses (this is why the final set has 4 ambiguity cases and 288 sentences instead of 284).

**Reading the 100%:** the final run is 100% because I fixed exactly the failures this set exposed. It is a regression guard, not an estimate of accuracy on sentences I have not seen.

### 3.4 Branded products, held-out (MEASURED, templated text)

The 65-product staples set above says nothing about a shop that imports real branded packs. The Catalogue screen lets a shopkeeper import products from the Open Food Facts India extract (5,325 products, see [DATA.md](DATA.md)), so I measured that separately, on products I never tuned the matcher on.

- **Test set:** `data/test/branded_utterances.jsonl`, 300 sentences built by `scripts/data/make_test_set.py` from the catalogue's deterministic 10% `test` split (527 products). Matching rules were only looked at on the `train` 90%.
- **Run:** `python scripts/evaluate_branded.py` imports the 527 held-out products into a throw-away database and feeds each sentence to the same parser. Output: `data/test/branded_results.json`.

| Result | Count | Share |
|---|---:|---:|
| Exact: the expected product, nothing else | 244 | **81.3%** |
| Wrong product added | 19 | 6.3% |
| Not recognised (nothing added; the app would ask) | 21 | 7.0% |
| Ambiguous, and the expected product was among the choices (the app asks which pack) | 16 | 5.3% |

| Language | Cases | Exact | Wrong | Not recognised | Asked which pack |
|---|---:|---:|---:|---:|---:|
| English | 60 | 49 | 0 | 6 | 5 |
| Gujarati | 60 | 47 | 4 | 7 | 2 |
| Hindi | 60 | 50 | 3 | 4 | 3 |
| Hinglish | 120 | 98 | 12 | 4 | 6 |

**What the misses look like** (full sample in the results file): the shop already had a similar product and the generic word won ("3 Roses Natural Care Tea" matched "Tea Leaves"; "Everest Rajma Masala" matched "Rajma" and "Garam Masala"); two sizes of the same brand ("Amul Ghee 1ltr" matched the 500 g pack); names that are mostly marketing copy ("The Only Cinnamon Powder you need"). The 6.3% wrong-product rate is the figure to watch: those are the cases where a wrong item reaches the bill without a question. I have not made it zero and I do not claim to have.

**2.4.0 → 2.5.0, a defect fixed:** a brand's pack-less alias ("amul butter") belonged only to the pack imported first, so a sentence quietly became that pack whatever else the shop stocked. Packs of the same brand now share the alias, so the parser sees several candidates and the dialogue asks which pack. After the fix the same 300 sentences give 244 exact, 19 wrong product, 21 not recognised and 16 asked which pack (before: 252 / 25 / 21 / 2). Fewer sentences are "exact" because the app now asks which pack where the family has several, which is the intended behaviour. The full list of the 19 wrong products is on the AI performance page and in `eval/results/evaluation_summary.json` (`branded.confusion.wrong_pairs`); by the author's reading about half are a generic or larger pack of the same item.

**2.2.0 → 2.3.0, what changed and why** (compared sentence by sentence against the 2.2.0 build, the same 300 sentences): 251 → 252 exact, wrong product 23 → 25, not recognised 24 → 21. Three sentences changed, all about the brand "Parle-G": the 2.3.0 parser no longer reads the "g" in "Parle-G" as grams, so the shop's own *Parle-G 100 g* is now found (one sentence became exact); but the held-out set holds three pack sizes whose templated names are all just "Parle g", so two sentences aimed at another pack size now get the 100 g pack (counted as wrong product). Before the final fix there were four more wrong-product sentences (9.7%): the new language packs let short Latin brand words sound like a staple's native-script name ("Nero" → water, "Raw" → semolina, "Day" → curd, "pohe" → poha). A Latin word now reaches a native-script name that exists only in a 2.3.0 pack by sound alone only when the sound-alike skeleton is 5+ letters (`Lexicon.PACK_SOUND_MIN_SKEL`; test `test_short_latin_brand_words_are_not_pulled_onto_a_native_script_staple_by_sound` fails without it). Gujarati, Hindi and English behaviour is unchanged by that gate.

**Caveats, all of which make the real number lower than 81.3%:** the sentences are generated from each product's own name, so they are cleaner than anything a customer says; there is no speech recognition in the loop (Prisma may mis-hear brand names); train and test come from one crowdsourced catalogue so brand and naming patterns are shared; and only the 527 held-out products were imported for the run, so there were fewer look-alike competitors than in a full shop.

**What importing does to the staples results:** with the *whole* catalogue imported, none of the 288 gold utterances in section 3.1 changes result. `backend/tests/test_branded_nlu.py` checks this on every test run, because generic words ("tea", "oil", "dal") must not be taken over by branded items.

## 4. Noise robustness

### 4.1 Simulated transcript noise (MEASURED, but a proxy)

`scripts/evaluate_nlu.py` corrupts the **letters** of each handwritten sentence (digits untouched; delete, substitute or duplicate characters), 5 random seeds per rate, mean over seeds. This imitates spelling damage a speech model might introduce. **It is not acoustic noise** and it does not model how Prisma actually errs.

| Character corruption rate | Utterance exact (mean, min–max of 5 seeds) | Line F1 (mean) |
|---:|---:|---:|
| 0% | 100% | 100% |
| 3% | 78.6% (73.7–81.6) | 83.7% |
| 6% | 63.3% (61.4–67.5) | 71.2% |
| 10% | 46.0% (42.1–50.0) | 53.7% |
| 15% | 32.5% (26.3–35.1) | 40.7% |

What this says: the matcher is sensitive to spelling damage in short utterances. The design answer is to ask rather than add when a match is weak (so errors become questions, not wrong bills), but this table counts those as misses. Prisma's real error patterns are different and will likely be gentler than random character damage on clean words; that is a hypothesis, not a result.

### 4.2 Acoustic noise (NOT MEASURED here; tooling provided)

The Noise lab and `scripts/evaluate_noise.py` do the real test once you have a key:

1. Take clean speech (your recording, or Timbre-spoken phrases).
2. Add noise at a chosen SNR: hiss (white), rumble (pink), crowd (speech-shaped babble, synthetic), 50 Hz mains hum, and an optional 300–3400 Hz phone-line filter. The measured SNR is reported next to the requested one (tested to match).
3. Send each version to Prisma and compute word and character error rates against the reference text, plus what the shop system then understood.

Caveats that apply to any result you get: noise is generated by code, babble is not a recording of a real crowd, Timbre speech is cleaner than a human voice, and a handful of phrases is a smoke test, not a benchmark.

## 5. Performance (MEASURED on one machine, no Gnani)

`scripts/benchmark_api.py` against a local server (Linux 6.18.44-fc-v378 Python 3.13.18), loopback HTTP, a signed-in session, a throw-away database, rate limit raised (`RATE_LIMIT_PER_MINUTE=100000`) so it does not interfere. It places real orders, so it must only be pointed at a throw-away database. Saved to `eval/results/api_latency.json`. **All rows were re-measured for 2.6.0 on 11 November 2026**, with the 2.5.0 tree measured on the same machine just before, against the same kind of database, for the comparison in [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md). The parser-only row and the language rows are text-only measurements from the 2.5.0 summary build; the parser did not change.

| Operation | n | p50 | p95 | max |
|---|---:|---:|---:|---:|
| Parser only (in process, 2.5.0 vocabulary) | 1,440 | 0.134 ms | 0.213 ms | 0.663 ms |
| `POST /api/text/parse` | 200 | 5.11 ms | 6.45 ms | 10.15 ms |
| `POST /api/text/turn` (dialogue, DB write) | 100 | 7.10 ms | 9.73 ms | 64.65 ms |
| `POST /api/sessions/{id}/confirm` (atomic stock update, ledger rows, order insert) | 50 | 12.62 ms | 17.07 ms | 20.70 ms |
| `GET /api/products` (65 curated products plus imports) | 50 | 8.72 ms | 9.89 ms | 15.76 ms |
| `GET /api/analytics/overview?days=30` (aggregated in Python) | 50 | 40.02 ms | 100.28 ms | 106.05 ms |
| `GET /api/analytics/sales` daily, 61 periods | 50 | 7.54 ms | 9.12 ms | 9.33 ms |
| `GET /api/analytics/sales` monthly, 25 periods | 50 | 9.11 ms | 13.64 ms | 13.92 ms |
| `GET /api/analytics/demand?days=30` | 50 | 9.55 ms | 13.74 ms | 17.45 ms |
| `GET /api/analytics/inventory` (valuation summary) | 50 | 5.31 ms | 6.36 ms | 6.65 ms |
| `GET /api/analytics/stock-movement?days=30` | 50 | 4.97 ms | 5.73 ms | 6.08 ms |
| `GET /api/orders?limit=20` | 50 | 6.1 ms | 6.85 ms | 8.09 ms |
| `GET /api/orders?q=...` (search) | 50 | 7.94 ms | 10.68 ms | 11.46 ms |
| `GET /api/catalog?q=...` (5,325-row catalogue search) | 50 | 8.98 ms | 11.23 ms | 20.93 ms |
| `GET /api/search?q=...` (global search) | 50 | 8.58 ms | 11.16 ms | 13.35 ms |
| `GET /api/evaluation` (the stored summary) | 50 | 3.70 ms | 4.73 ms | 12.71 ms |

These ran against a database holding **3,101 orders** (the 120-day demo history plus the orders the benchmark itself created; the side-by-side 2.5.0 run had 3,101 as well). Timings move by a few milliseconds from run to run on a shared machine; read them as orders of magnitude, not as precise values. The "Not measured" speech rows are unchanged: no Gnani call was made.

Meaning: everything this project computes is a few milliseconds. A voice turn will be dominated by Prisma and Timbre round trips and your network, which are **not measured here**. The Live screen records them as you use the app (p50/p95 from the `api_calls` table), so the number you quote should come from your own run.

## 6. How to reproduce, and how to get the missing numbers

| What | Command | Needs |
|---|---|---|
| Language evaluation | `python scripts/evaluate_nlu.py --tag mine --failures` | nothing |
| Branded-product evaluation | `python scripts/evaluate_branded.py` | nothing |
| API latency | start a server, then `python scripts/benchmark_api.py --base http://localhost:8000` (raise `RATE_LIMIT_PER_MINUTE` first) | nothing |
| **Real STT/TTS round trip, each of the 11 languages** (voice, language code, loopback and, with a recording, a person) | `verify_gnani.bat` (`--stream` for the WebSocket) | Gnani key |
| **WER vs noise type and SNR** | `backend\.venv\Scripts\python scripts\evaluate_noise.py --quick` (drop `--quick` for the full grid; it prints the call count first) | Gnani key |
| One clip, your own voice, any noise | **Noise lab** screen | Gnani key, microphone |

After running the two Gnani scripts, replace the "Not measured" rows in section 1 with the saved values from `eval/results/gnani_live_*.md` and `eval/results/noise_live_*.md`, and keep this file's rule: a number appears only if a script produced it.

## 7. Threats to validity

- **Same-author test set.** The strongest limitation. A fair check needs sentences written by other people and, better, recorded by them.
- **Transcripts, not audio.** Real Prisma output contains errors this set does not.
- **Small N.** 128 authored sentences, 4 ambiguity cases, 10 non-orders; percentages move about 1% per sentence here (0.33% per case in the 300-case branded set).
- **One synthetic shop.** 65 curated staples plus whatever is imported; a different catalogue changes ambiguity (*dal*, *oil*, *tea*) and accuracy.
- **Templated brand sentences.** Section 3.4 is generated from product names; real customers abbreviate, mispronounce and mix brands.
- **Fixes tuned on the evaluation set.** Disclosed above; the 288-sentence final run is not held-out. The branded set (3.4) is the only held-out number here.
- **Analytics are not an accuracy claim.** The dashboard figures are exact sums over the database rows (tests check this), but the orders in the demo database are synthetic, so the figures say nothing about any real shop.
- **Latency on one Linux machine**, loopback, no TLS, no Gnani.
