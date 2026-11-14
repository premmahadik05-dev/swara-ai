# Languages

SWARA AI offers eleven language choices on the Order desk. This page says what each one is wired to, what has been tested, and, just as important, what has **not**.

> **Read this before you tell anyone "all the languages work".** In the environment this release was built in there was no Gnani API key and no network route to Gnani. **No live Prisma (speech-to-text) or Timbre (text-to-speech) call was made for any language, old or new.** Every Gnani response in the automated tests is simulated. What is true is that the code, the language codes, the voice names and the text-understanding rules are all in place and unit-tested, and that a one-command check (`verify_gnani.bat`) will measure the real thing on your machine. Until you have run it, the app itself says **"Not verified live"** next to each language. Nothing in this repository claims otherwise.

## The eleven choices

| Key | Language | Prisma v2.5 `language_code` | Timbre v2.5 `language` | Default voice | Text understanding | Live check on Gnani |
|---|---|---|---|---|---|---|
| `gu` | Gujarati | `gu-IN` | `gu-IN` | Falak | In use and tested since the first release | **Not run here** |
| `hi` | Hindi | `hi-IN` | `hi-IN` | Nalini | In use and tested since the first release | **Not run here** |
| `en` | English (India) | `en-IN` | `en-IN` | Devika | In use and tested since the first release | **Not run here** |
| `hinglish` | Hinglish (Hindi in Roman letters) | `en-IN` | `hi-en` | Poorvi | In use and tested since the first release | **Not run here** |
| `mr` | Marathi | `mr-IN` | `mr-IN` | Zahira | **New in 2.3.0**: unit-tested, not reviewed by a native speaker | **Not run here** |
| `bn` | Bengali | `bn-IN` | `bn-IN` | Kirra | **New in 2.3.0**: same | **Not run here** |
| `ta` | Tamil | `ta-IN` | `ta-IN` | Asmita | **New in 2.3.0**: same | **Not run here** |
| `te` | Telugu | `te-IN` | `te-IN` | Lavanya | **New in 2.3.0**: same | **Not run here** |
| `kn` | Kannada | `kn-IN` | `kn-IN` | Saanvi | **New in 2.3.0**: same | **Not run here** |
| `ml` | Malayalam | `ml-IN` | `ml-IN` | Reshma | **New in 2.3.0**: same | **Not run here** |
| `pa` | Punjabi | `pa-IN` | `pa-IN` | Mehuli | **New in 2.3.0**: same | **Not run here** |

The last column is the state of this repository as delivered. After you run `verify_gnani.bat`, the same information appears **inside the app** (Order desk language list and Settings → Languages and voices), taken from the file the script writes, not from this page.

Gnani lists ten languages for Prisma v2.5 and Timbre v2.5: Hindi, Indian English, Gujarati, Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam and Punjabi. Hinglish is not an eleventh Prisma language: it is Indian English (`en-IN`) for listening, which Gnani documents as handling English-Hindi mixed speech, and the documented `hi-en` value (voice Poorvi) for speaking.

## What was checked against Gnani's documentation

On 10 November 2026 the following were read from Gnani's public documentation, and the registry was built from them (the pages are linked at the end):

- the ten Prisma language codes and the rule that Prisma v2.5 takes **one** language per request with **no** automatic language detection;
- the Timbre `language` values (`en-IN hi-IN hi-en ta-IN te-IN kn-IN ml-IN mr-IN bn-IN gu-IN pa-IN`, plus `auto`);
- the **42** Timbre v2.5 voice names and which language each one is for (a voice from the separate v3.0 list is rejected by `timbre-v2.5`, so the app only ever offers v2.5 names);
- that automatic inverse text normalisation (`transcribe` mode) exists only for Hindi and English.

A test (`backend/tests/test_languages_registry.py`) compares the registry with a copy of these facts, so a typo in a code or a voice fails the build. That test shows the code matches **what I read in the documentation**. It cannot show that the documentation matches Gnani's live service.

Where Gnani's documentation disagreed with itself, the app does not guess: the realtime socket documentation names its language header both `lang_code` and `language_code`, so the app sends both.

## How a language choice flows through the app

1. **Selector.** The Order desk's language button opens a list of every language the server offers. The list comes from `GET /api/languages`, so a language you switch off disappears from the choices (it stays visible but unselectable, labelled "Switched off") and a language that cannot work on this server says why.
2. **Speech to text.** For a recording, the chosen key becomes exactly one Prisma `language_code`. The shop's product words, **in the script of the chosen language**, are sent as Prisma's `bias_list` so that brand and item names are more likely to be heard correctly.
3. **Understanding.** The deterministic text engine reads the transcript. Each language has its own pack of number words, unit words, filler words, corrections and product names (`backend/app/nlu/langpacks/`). The chosen language is passed only as a *hint*, used when two languages share a script (Hindi and Marathi are both written in Devanagari). The engine also reads what was typed, so a sentence typed in another language than the selector is still understood.
4. **Quantity, unit and product.** Spoken numbers ("do", "ek", "dhai", the Tamil, Bengali and other number words), fractions ("sava", "derh", "adhi"), units and dozen/pack words become numbers, units and products in the shop's own price list. The parser never invents stock or prices.
5. **Confirmation.** The bill is read back in the chosen language, with the product's name in that language where the product has one, and otherwise in English.
6. **Voice reply.** The reply is spoken with Timbre using the language's `language` value and the voice chosen in Settings.

At no step does the app switch to another language, another speech provider or a canned recording when a language cannot be served. It stops and tells the person why (next section).

## When a language cannot be served

| Situation | What the API returns | What the person sees |
|---|---|---|
| A language key that does not exist | HTTP 422, `BAD_LANGUAGE` | The message, and the language list is refreshed |
| A language you switched off with `DISABLED_LANGUAGES` or in Settings | HTTP 422, `LANGUAGE_DISABLED` | "Marathi is switched off on this server" and the list is refreshed. Typing still works (see below) |
| Auto-detect or mixed-language mode while the server uses Prisma v2.5 | HTTP 422, `AUTO_DETECT_NEEDS_V3` | The Auto-detect row is shown as unavailable, with the reason. **Before 2.3.0 these choices were silently treated as Gujarati. They no longer are.** |
| Gnani refuses a language code or a voice, or fails (HTTP 400, 401, 403, 429, 5xx) | The Gnani error. Known kinds (bad key, no credit, rate limit, audio too long) become a plain sentence; any other error shows Gnani's own message | The message. No fallback provider and no fake audio |
| No Gnani key | `NOT_CONFIGURED` | The microphone is disabled and says so; typed orders keep working |
| A TTS failure after a successful transcript | The order is still processed; the reply text is returned with no audio and an `audio.error` message | The reply is shown as text and a notice carries the error |

A **disabled** language means "not offered for voice". The text engine still reads a typed sentence in that language if someone types one, because it works out the language from the characters; that is deliberate and is documented in [LIMITATIONS.md](LIMITATIONS.md). English cannot be switched off.

## Hinglish and mixed speech

- **Hinglish** is treated as a language of its own (`hinglish`): listening with `en-IN`, which Gnani documents for English-Hindi mixed speech, the transcript in Latin letters, and a spoken reply with the documented `hi-en` voice.
- **Mixed sentences in the text engine** ("2 kilo chawal and ek litre doodh") are handled by the parser for typed text and for whatever Prisma returns, because every language pack is consulted for every word.
- **True per-recording auto-detection and code-mix** (`indic-auto`, `format=codemix`) are Prisma **v3.0** features. They are available as a setting (`GNANI_STT_MODEL=prisma-v3.0`) and are offered in the selector only when the server is on v3.0. They have not been run against Gnani.

## What the text evaluation says, per language (2.5.0)

Text only: no speech and no Gnani call is behind any figure below. The table is generated from `eval/results/evaluation_summary.json` (built 2026-11-11) and is also shown, with sorting, search and CSV download, on the **AI performance** page and as the language table in Section 9 of [PROJECT_REPORT.md](PROJECT_REPORT.md).

| Language | Sentences (non-brand sets) | Exact order match | Held-out brands exact | Language label correct | Typed order correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gujarati | 78 | 100.0% | 47 of 60 (78.3%) | 139 of 139 (100.0%) | 77 of 77 |
| Hindi | 71 | 100.0% | 50 of 60 (83.3%) | 132 of 132 (100.0%) | 70 of 70 |
| English (India) | 64 | 100.0% | 49 of 60 (81.7%) | 125 of 125 (100.0%) | 63 of 63 |
| Hinglish | 75 | 100.0% | 98 of 120 (81.7%) | 195 of 196 (99.5%) | 74 of 74 |
| Marathi | 7 | 100.0% | not in set | 5 of 7 (71.4%) | 7 of 7 |
| Bengali | 9 | 100.0% | not in set | 9 of 9 (100.0%) | 9 of 9 |
| Tamil | 8 | 100.0% | not in set | 8 of 8 (100.0%) | 8 of 8 |
| Telugu | 8 | 100.0% | not in set | 8 of 8 (100.0%) | 8 of 8 |
| Kannada | 8 | 100.0% | not in set | 8 of 8 (100.0%) | 8 of 8 |
| Malayalam | 8 | 100.0% | not in set | 8 of 8 (100.0%) | 8 of 8 |
| Punjabi | 8 | 100.0% | not in set | 8 of 8 (100.0%) | 8 of 8 |

How to read it. "Exact order match" counts the sentences of the handwritten, templated and authored sets for which every parsed line (product, quantity, unit) equals the gold lines. "Held-out brands exact" is the share of held-out branded-product sentences resolved to exactly the right product; it exists for the four original languages only, and the shortfall from 100% is mostly sentences that asked which pack or were not recognised (see [EVALUATION.md](EVALUATION.md)). "Language label correct" is how often the parser's own language label was right with no selector hint. "Typed order correct" is the typed sentence taken through the real dialogue to a saved order whose lines equal the gold lines.

Two cautions. The gold sentences of the four original languages were written by the parser's author, so their 100% is a ceiling. The seven added languages have 7 to 9 sentences per check, written without native-speaker review, so one sentence moves a percentage by 11 to 14 points: their figures show the parser agrees with its author, not that a native speaker would be understood. Marathi's lower language-label figure is real: Hindi and Marathi share a script, and the app relies on marker words and the language selector to tell them apart.

## Checking it for real

```bat
verify_gnani.bat                      :: all 11 languages, 3 calls each (about 33 calls)
verify_gnani.bat --langs ta mr        :: only some
verify_gnani.bat --stream             :: also the realtime WebSocket (+1 call per language)
```

Four independent checks are recorded **per language**, so a pass in one never hides or stands in for another:

| Check | What it proves | What it does **not** prove |
|---|---|---|
| `tts` | Timbre accepted the language and the voice and returned audio | That the audio sounds natural or is the right language to a native ear |
| `stt_code` | Prisma accepted the language code for an audio request (the audio is a generated tone, not speech) | Anything about recognising speech |
| `stt_loopback` | Prisma transcribed the Timbre audio and the parser found the expected order | Weak evidence: a synthetic voice from the same vendor reading a sentence this project wrote |
| `stt_human` | Prisma transcribed **a recording of a person** you supplied and the parser found the order | Only as much as one speaker, one room and one sentence can show |

To run `stt_human`, put a recording at `eval/samples/<key>.wav` (for example `eval/samples/ta.wav`), saying the sample sentence the app shows for that language, or put the exact words you said in `eval/samples/<key>.txt`. That is the only check that says anything about real recognition, and it is the one that has never been run.

The script writes `eval/results/live_verification.json`. The app reads that file and shows a language as "Live checked" only if both its voice and a speech check **passed against Gnani**. A file produced by a simulated run is labelled "Simulated only" and is never shown as a pass. Re-running the script for some languages keeps the earlier results of the others, but only if they came from the same Gnani host and models.

The Settings page also has a **Test** button per language. It makes two Gnani calls (Timbre speaks the sample sentence, Prisma listens to it). It is the same loopback as above and is labelled as such.

## What is tested without Gnani (and what that means)

| Kind of test | What it covers | Real Gnani involved? |
|---|---|---|
| Registry tests | Codes, 42 voices, switching languages off, ITN rules, voice fallbacks | No |
| Text-understanding tests (`test_languages_nlu.py`) | For every language: sample sentences with and without the language hint, quantities, units, intents, every product name and alias, case endings, unknown words, scripts, Hindi versus Marathi, reply templates, read-back | No |
| API tests with a **mocked** Gnani (`test_languages_api.py`) | Per language: a voice turn, a TTS reply, a full order from first word to confirmation, the disabled-language, auto-detect and bad-language errors, a Gnani 400 on STT and TTS, no key, the realtime socket's headers | **No: a fake transport answers every request** |
| `test_scripts.py` | The verification script itself: four checks per language, failure isolation, the results file, its merge rules, and that the file the script writes is the file the app reads | **No: a simulator** |
| Frontend tests | The selector, the Settings card, the Order desk flow, the landing page wording, the API client | No |

Because the Gnani side is simulated, **these tests cannot tell you whether Prisma recognises Tamil in a noisy shop.** They tell you that if Gnani behaves as its documentation says, the app does the right thing with the answer.

## Known limits specific to the new languages

- The rules for Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam and Punjabi (number words, unit words, product names) were **written for this release by the project author, not by native speakers**, and are covered by unit tests the same author wrote. They are most likely to miss colloquial and regional forms, and to mis-hear brand names. They have **not** been compared with real Prisma output in any of these languages.
- Several Indian scripts are matched to the product list through a Devanagari phonetic spelling (the same method used for Gujarati), and by stripping case endings. Words that sound alike after that mapping can be confused; the engine asks which product was meant when two fit, and never guesses.
- Product names in the new scripts exist only where the project author supplied them (the curated staples). Imported catalogue products have English names and are read back in English.
- Hindi and Marathi share a script. When a sentence has no marker word that tells them apart, the language selected in the selector decides. With no selection, a sentence made only of shared words is read as Hindi.
- Gnani's documentation says text normalisation is deepest for Hindi, Marathi, Tamil and English and "supported" for the other six; spoken numbers and units in Bengali, Telugu, Kannada, Malayalam, Punjabi and Gujarati may therefore be pronounced less naturally.
- A word typed or transcribed in **Latin letters** reaches a product name that exists only in a new language's own script by sound only when the sound-alike match is at least five letters long (`Lexicon.PACK_SOUND_MIN_SKEL`). Without that rule short brand words such as "Nero" or "Raw" became water or semolina (found by the held-out branded-product check, [EVALUATION.md](EVALUATION.md) section 3.4). The cost: a short romanised spelling of a Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam or Punjabi staple name (for example a two-syllable word) is not matched by sound alone; the native-script spelling, the English name and the existing Hinglish aliases still match, longer romanised spellings still match by sound, and the packs hold no Latin-letter aliases of their own. A word that does not match is reported as unknown and the app asks.
- Automatic inverse text normalisation (turning spoken numbers into digits) is documented only for Hindi and English; for the others, the app relies on its own number-word rules.

## Adding or removing a language

Everything language-specific that the server needs lives in **one table**: `backend/app/languages.py`.

- **Switch a language off** without touching code: `DISABLED_LANGUAGES=mr,bn` in `.env`, or the switch in Settings → Languages and voices (the owner only). English cannot be switched off.
- **Change a voice**: Settings → Languages and voices, or `TTS_VOICE_<KEY>=Name` in `.env`. Only voices in the documented Timbre v2.5 list for that language are accepted; a stale name falls back to the default rather than reaching Gnani as a 400.
- **Add a language** that Gnani documents: add one `Language(...)` entry to the registry (key, names, script, Prisma code, Timbre language, default voice, a sample sentence), add its voices to `TIMBRE_V25_VOICES`, add a pack in `backend/app/nlu/langpacks/` (copy the smallest existing one), and add the key to `frontend/src/lib/languages.ts`. The selector, the Settings card, the API validation, the verification script and the tests that loop over every language pick it up from the table. A test fails if the pack is missing or a code is not on the documented list.

## Sources

Read on 10 November 2026:

- Prisma speech-to-text: <https://docs.gnani.ai/api/STT/prisma-v2.5.md>
- Timbre voices and languages: <https://docs.gnani.ai/api/TTS/available-voices.md>
- Timbre text normalisation: <https://docs.gnani.ai/api/TTS/text-normalization.md>

This project is not affiliated with or endorsed by Gnani.ai.
