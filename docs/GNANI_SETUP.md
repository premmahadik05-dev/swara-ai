# Configuring and verifying your Gnani credentials

SWARA AI uses two speech models from **Gnani.ai** and nothing else from them:

| Model | Used for | Where in the app |
|---|---|---|
| **Prisma** v2.5 (default; v3.0 optional) | Speech to text: *Tap to talk*, *Live stream*, the Noise lab | Order desk |
| **Timbre** v2.5 | Text to speech: the spoken read-back of the bill | Order desk, *Speak replies* |

Gnani, Prisma and Timbre belong to Gnani.ai. SWARA AI is not affiliated with or endorsed by Gnani.ai. Your key, your usage and your audio are
governed by your agreement with Gnani. Audio leaves your server only when someone uses the microphone or *Speak replies*, and it goes to Gnani
under your key. SWARA AI has no analytics or tracking of its own. [MODEL_INTEGRATION.md](MODEL_INTEGRATION.md) lists exactly what is sent and how
failures are handled.

**Without a key the app still works.** Typed orders run through the same engine. The Order desk says **Typing only** and the microphone explains why
it is off. That is the "demo" state; a real-voice state exists only after a key is set and accepted by Gnani.

## 1. Get a key

Keys are issued by Gnani, not by SWARA AI. Gnani's quick-start page says to sign up on the Gnani API platform at https://app.gnani.ai/voice and generate a key there
(documentation: https://docs.gnani.ai). The exact screens and any free-credit terms are Gnani's and change; they were not checked when this guide was written.
Treat the key like a password: SWARA AI cannot create one for you and never will.

## 2. Put the key where the backend reads it

Choose one.

**A. In the `.env` file** (Windows):

```bat
setup.bat                  :: once; it creates .env from .env.example
notepad .env
```

Set the line `GNANI_API_KEY=` to your key (no quotes, no spaces), save, and **restart** `start.bat`. The other `GNANI_*` lines have working defaults:

| Setting | Default | Meaning |
|---|---|---|
| `GNANI_BASE_URL` | `https://api.vachana.ai` | Gnani's API host |
| `GNANI_STT_MODEL` | `prisma-v2.5` | or `prisma-v3.0` |
| `GNANI_STT_FORMAT` | `verbatim` | words as spoken; `transcribe` applies number formatting (Hindi and English India only, on v2.5) |
| `GNANI_STT_BIAS` | `false` | send shop item names to Prisma v2.5 as hints (experimental: measure before relying on it) |
| `GNANI_TTS_MODEL` | `timbre-v2.5` | |
| `TTS_VOICE_<KEY>` | per language, see [LANGUAGES.md](LANGUAGES.md): GU Falak, HI Nalini, EN Devika, HINGLISH Poorvi, MR Zahira, BN Kirra, TA Asmita, TE Lavanya, KN Saanvi, ML Reshma, PA Mehuli | the Timbre v2.5 voice for each of the eleven languages. A name that is not in Gnani's documented v2.5 list for that language is ignored and the default is used |
| `DISABLED_LANGUAGES` | empty | e.g. `mr,bn`: those languages are not offered for voice and the API refuses them. English cannot be switched off. The owner can also do this in Settings |
| `GNANI_MAX_CALLS_PER_HOUR` | `300` | a local safety limit so a bug or a loop cannot spend your credits |
| `GNANI_STT_TIMEOUT_S` | `20` | how long to wait for a speech-to-text answer (new in 2.6.0; optional) |
| `GNANI_TTS_TIMEOUT_S` | `15` | how long to wait for a spoken reply (new in 2.6.0; optional) |
| `GNANI_CONNECT_TIMEOUT_S` | `5` | how long to wait for a connection to open (new in 2.6.0; optional) |
| `GNANI_TIMEOUT_S` | `40` | a ceiling: none of the three limits above may exceed it. A call that was sent and got no answer in time is **not** repeated (see [MODEL_INTEGRATION.md](MODEL_INTEGRATION.md)) |

**B. On the Settings page** (owner only): paste the key into *Paste your Gnani API key* and choose **Save key**. It is written to `.env` on the
server, is never shown again, and is never sent to the browser; afterwards only the last four characters are shown as a hint. Staff cannot see or change it.

Never put the key in source files, screenshots, chat messages, an issue or a commit. `.env` is listed in `.gitignore`; keep it that way.

## 3. Verify it: three levels

| Level | What it proves | Cost |
|---|---|---|
| `/api/health` shows `"gnani_configured": true` | A key is present and is not the placeholder. **It does not prove Gnani accepts it** | none |
| Settings → **Test connection** (owner) | A real round trip: Timbre speaks "two kilo rice and one litre milk", Prisma transcribes that audio. Shows latency and the transcript | 2 calls |
| Settings → **Languages and voices → Test** (owner), one language | The same round trip for the language on that row (Timbre speaks that language's sample sentence, Prisma listens to it) | 2 calls per language |
| `verify_gnani.bat` | **Eleven languages, four independent checks each** (below). Prints a table, saves the full report, and writes the file the app reads to show each language's live status | about 33 calls for all 11 (3 per language) |

```bat
verify_gnani.bat                    :: all 11 languages x 3 calls = about 33 calls
verify_gnani.bat --langs ta mr      :: only some languages (3 calls each)
verify_gnani.bat --stream           :: also tests the realtime WebSocket (+1 call per language)
```

**What is checked, per language, and recorded separately** (a pass in one check is never used to stand in for another):

| Check | Calls | Passes when | Proves | Does not prove |
|---|---|---|---|---|
| `tts` | 1 | Timbre returns audio for the language's sample sentence with the configured voice | Gnani accepts the language value and the voice | That it sounds right to a native listener |
| `stt_code` | 1 | Prisma accepts the language code for an audio request. The audio is a generated tone, not speech | Gnani accepts the code | Anything about recognising speech |
| `stt_loopback` | 1 | Prisma transcribes the Timbre audio from `tts` and the parser finds the expected order. Skipped if `tts` failed | Speech to text to order works end to end for a synthetic voice | Real recognition: Timbre is a clean synthetic voice from the same vendor |
| `stt_human` | 1, only if you supply a recording | Prisma transcribes **your recording of a person**, `eval\samples\<key>.wav` (say the sentence the app shows for that language; put the exact words in `eval\samples\<key>.txt` if you said something else) | The only evidence about real recognition | More than one speaker and one sentence can show |

**Reading the result.** A table with one row per language and one column per check (passed, failed, skipped, with the latency or the error code), then the transcript and
parsed order for the speech checks. The exit code is `0` only if no call failed. The report is saved as `eval\results\gnani_live_<timestamp>.md` and `.json`, and the
app's status file as `eval\results\live_verification.json`. They contain measured values only, never the key. The app then shows **"Live checked"** next to a language only
when both its voice and a speech check passed against Gnani; a failed check shows as **"Live check failed"** with what failed; a language you have not run stays **"Not verified live"**.
The status file is written only by a run against real Gnani: a run that used a simulated transport never writes it.

**What this does not prove.** The test audio is Timbre's clean synthetic voice, not a person in a noisy shop, so `tts`, `stt_code` and `stt_loopback` show the connection and the
chain work, not how well Prisma hears real customers. Supply a `stt_human` recording for each language you intend to rely on, and use the **Noise lab** (add shop noise at a
chosen level and run Prisma on each version) or `backend\.venv\Scripts\python.exe scripts\evaluate_noise.py --langs ta mr`, and then judge with your own recordings. Latencies include your network.

## 4. What the automated tests do and do not cover

| Kind | Status |
|---|---|
| Request and response shapes for Prisma (REST and streaming) and Timbre, every documented error, retries and back-off | **Tested against a local simulator** built from Gnani's public documentation (`backend/tests/test_gnani_contract.py`, `test_api_voice.py`, `test_ws_proxy.py`). A simulator is not Gnani |
| Live calls to Gnani | **Never made by the test suite.** The numbers above come only from a script you run with your own key. Anything the repository says about live behaviour is a statement that it has **not** been verified until you have run it |
| Every one of the eleven languages | Tested through the same simulator only, one test group per language (voice turn, spoken reply, a full order, error cases). **None of the eleven has been run against live Gnani by the project author** |
| The key stays out of the browser | Tested: the settings response carries only a masked hint (the last four characters), and staff get none. The key is read by `gnani/client.py` and the streaming proxy only |

## 4b. What the code was checked against (documentation read on 11 November 2026)

The public Gnani documentation was read again for release 2.5.0 and the code was compared with it. This is a comparison with the **documentation**, not with a live server:

| Item | Documentation says | Code |
|---|---|---|
| Speech to text, default model | Prisma v2.5, `POST https://api.vachana.ai/stt/v3`, key in the `X-API-Key-ID` header, one `language_code` per request; `model=prisma-v3.0` is optional | Same (`gnani/client.py`; `test_gnani_contract.py`) |
| Text to speech, recommended model | Timbre v2.5, `POST /api/v1/tts/inference`; Timbre v2.0 is marked deprecated | Timbre v2.5 only; v2.0 is not used |
| Languages | Ten Indian languages plus English for Prisma v2.5 and Timbre v2.5 | The registry (`languages.py`) and a copy of the documented list inside `test_languages_registry.py` agree; Hinglish is this project's own label on top of the English and Hindi-English codes |
| Key handling | A secret to be kept off the client | The key lives in `.env` on the server only, is masked in the settings API and appears in no log, screenshot or document (tests assert it) |

No response from Gnani has ever been received by this project's build environment, so **nothing here says that a live call succeeds**. `verify_gnani.bat` is the check that can. The AI performance page shows live Prisma and Timbre timings only after live calls have been made on your installation (it reads the same call log as the Conversations screen); before that it says "Not measured".

## 5. If something fails

| What you see | Meaning | Do |
|---|---|---|
| `GNANI_API_KEY is not set` (script) / `NOT_CONFIGURED` (app) | No key, or the placeholder `your_…` is still in `.env` | Set the key (step 2) and restart |
| `INVALID_API_KEY` / *Gnani rejected the API key* | The key is wrong, revoked or for another product | Paste it again; check it with Gnani (your account or their support) |
| *insufficient credit* (402) | The key has no credit left | Add credit with Gnani, under your agreement with them |
| `RATE_LIMITED` | Gnani limited the key, or the local `GNANI_MAX_CALLS_PER_HOUR` was reached | Wait, or raise the local limit. Checking all 11 languages makes about 33 calls, well inside the default of 300 per hour |
| `BAD_LANGUAGE` / `LANGUAGE_DISABLED` / `AUTO_DETECT_NEEDS_V3` (HTTP 422) | The language is unknown, switched off, or Auto-detect was asked for on Prisma v2.5 | Pick a listed language; see [LANGUAGES.md](LANGUAGES.md) |
| A language fails the `tts` or `stt_code` check with a 400 | Gnani did not accept that language value, voice or code with your key or plan | Look at the error text in the report; check Gnani's current documentation, and switch the language off (`DISABLED_LANGUAGES`) until it is fixed |
| *Could not reach Gnani* | Offline, or a firewall or proxy blocks `api.vachana.ai` | Allow the host; check `GNANI_BASE_URL` |
| *The speech service took too long to answer* (`TIMEOUT`, HTTP 504) | The call was sent and got no answer within `GNANI_STT_TIMEOUT_S` or `GNANI_TTS_TIMEOUT_S`. It is **not** repeated, and the bill has not changed. The Order desk keeps the recording and offers **Try again** | Try again; if it keeps happening, look at **Voice diagnostics** (owner) for the slow stage, and raise the limit in `.env` only if your connection is genuinely slow (see [UPDATING.md](UPDATING.md)) |
| `MAX_AUDIO_DURATION_EXCEEDED` / `UNSUPPORTED_AUDIO_FORMAT` | The recording was too long (30 s or 8 MB limit per message) or unreadable | Record a shorter message |

**Seeing how fast your own voice path is.** After a few spoken orders, the owner's **Voice diagnostics** page (sidebar, Insights) shows, for your shop and your network: the time for each step of a spoken
order (audio check, speech to text, order processing, spoken reply), the Gnani calls (how many, how many failed and why, how many needed a retry, median and slowest 1 in 20 times), and what the
browser itself measured. These are measured values from real calls; the page says "Not measured yet" until there are some.

More: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## 6. If the key leaks

Revoke it with Gnani at once (their documentation says how), get a new one, and put the new one in `.env`. Remove any copy from places where it was pasted. SWARA AI
stores the key only in `.env` (plain text, as most local tools do) and never in the database or the build.
