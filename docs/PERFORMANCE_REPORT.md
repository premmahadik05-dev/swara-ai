# Performance report: voice response, 2.5.0 compared with 2.6.0

This report says what was measured, how, and what the numbers do and do not show. Read the first section before the tables.

## What these numbers are, and are not

- **The speech service was not called.** The build environment has no Gnani key and no route to Gnani. Every speech figure below comes from a **local stand-in** that answers
  like the documented endpoints after a **fixed delay that the benchmark sets** (speech to text 600 ms, text to speech 500 ms, 100 ms to open a new connection). Those delays are
  the benchmark's own assumptions, not Gnani's real speed. The differences between the two versions are real (the same stand-in measured both); the absolute milliseconds are not
  a prediction for your shop.
- **Nothing here is streaming.** Gnani's REST endpoints return a finished transcript and a finished audio file. The 2.6.0 changes do not make speech recognition or synthesis
  faster, and they do not overlap the two (the spoken reply cannot be made before the reply text exists). They remove waiting that was not needed and make the remaining waiting
  visible. The live-stream mode (`/ws/voice`) already existed; each finished speech segment it returns is a complete segment, not a partial one.
- **Your own numbers come from the app.** Every speech call and every spoken turn is timed as it happens, and the owner's **Voice diagnostics** page (`/diagnostics`) shows them. Use
  that page, on your network and with your Gnani account, as the source of truth for your shop.

## What changed in the path from "end of speech" to "reply"

| Step | 2.5.0 | 2.6.0 |
|---|---|---|
| End of speech | The person taps again | The person taps, **or stops talking** (a short silence ends the recording; "Send when I stop talking", on by default, can be switched off). Silence at both ends is cut before upload |
| Upload and speech to text | A new connection to Gnani for every call | One pooled connection kept warm between calls (60 s idle) |
| A slow or hung speech service | Waited up to the single timeout **three times** (40 s each by default, 121.5 s in the worst case) | Speech to text gets 20 s, text to speech 15 s, **once**: a call that was sent and got no answer is reported ("took too long, your bill has not changed, try again") and is not sent a second time |
| Connection failures, 429 and 5xx | Up to 3 tries, waits of 0.5 s and 1 s | Up to 3 tries, waits of 0.25 s and 0.5 s |
| Understanding the sentence and updating the bill | Same | Same (about 7 to 11 ms) |
| Reply and bill on screen | After the **spoken reply was also made** | **As soon as processing ends**; the spoken reply is requested separately and plays when ready |
| What the person sees meanwhile | One spinner | Listening, Understanding, Preparing the voice, Replying; a recording that could not be sent is kept with **Try again** |
| After a network failure or a reload | The open bill could be lost from the screen | The bill is on the server; the tab remembers its id and puts it back |

## Results on the stand-in

Reproduce with `python scripts/bench_voice_path.py --label X --out X.json` (it starts its own stand-in and a throw-away database; add `--backend-dir` to run it against another
copy of the project). Both versions below were run on the same machine, one after the other, with the same script.

| Measurement | 2.5.0 | 2.6.0 | What it shows |
|---|---|---|---|
| Connections opened for 20 speech calls | **20** | **1** | The pool works: only the first call pays for opening a connection |
| Median time per speech-to-text call (stand-in: 600 ms + 100 ms per new connection) | 716.1 ms | 644.1 ms | The stand-in charges 100 ms for every new connection, so the pool saves most of that on each call (72 ms observed). The real saving depends on your network and was not measured against Gnani |
| Reply **with its voice**, in one request (median, 15 runs) | 1350.7 ms | 1208.3 ms | Two connection set-ups saved |
| Reply and bill **on screen** (median, 15 runs) | 1350.7 ms (the reply waited for the voice) | **659.6 ms** | The screen no longer waits for the voice: the bill appears after speech to text and processing only |
| Voice **ready** (median, 15 runs) | 1350.7 ms | 1214.4 ms | Unchanged apart from the saved connections: the voice still needs speech to text, then text to speech, one after the other |
| Server's own total for the reply (median) | not recorded | 649.0 ms | Cross-check: the server's stage timer agrees with the outside measurement (659.6 ms) within the HTTP overhead |
| A service that never answers (timeout set to 1 s for the test) | blocked **4529 ms**, 3 attempts, reported as a network error | blocked **1020 ms**, 1 attempt, reported as `TIMEOUT` | The wait for an unresponsive service is one timeout, not three |
| The same, at the default settings (calculated, not run: it would take two minutes) | up to 121.5 s | up to 20 s | 3 x 40 s + 1.5 s of waiting, against one 20 s limit |

Reading the table honestly:

- **Faster bill, same voice.** On the stand-in the person sees the order about 0.7 s sooner, because the bill no longer waits for the voice (the stand-in's 500 ms of speech synthesis
  plus a connection charge). With Gnani the gain is however long Timbre takes to answer on your network. The moment the voice *starts* is about 140 ms earlier on the stand-in, from the
  pooled connection; nobody should expect the voice itself to start much sooner than before.
- **The big change is in the bad case.** A hung speech service used to hold the counter for two minutes; it now holds it for at most 20 s, with a message and the recording kept.
- **Silence trimming and automatic end-of-speech** shorten what the person has to do (no second tap) and what is uploaded. Their effect on real speech was **not measured**: the
  test recordings are synthetic tones, and the real Gnani response time for shorter audio is unknown.

## Where the time goes inside the app

On a local run the application's own work per turn is small compared with the speech calls:

- Understanding a sentence and updating the bill: about 7 to 11 ms (typed turns; see the table below).
- Everything else in a spoken turn is the two Gnani calls and the network between the browser, this server and Gnani.

The Voice diagnostics page splits each turn into: audio check, speech to text, order processing (of which understanding and database work are shown separately in the table
view), spoken reply (zero when the reply came from the cache), the server total, and what the browser itself measured from the end of speech to the reply on screen and to the
voice starting. Figures are medians and "slowest 1 in 20" (95th percentile), over 24 hours, 7 days or 30 days, and read "Not measured yet" when there is nothing behind them.

## Typed orders, local server

Typing skips speech, so this is the time the server takes for the order logic and the database, with no Gnani call. It was measured with `scripts/benchmark_api.py` (200 parses and 100 typed turns, 50 of each other request) against a **throw-away database of 3,101 orders** (the 120-day generated demo history plus the orders the benchmark places), over loopback HTTP, signed in, with `RATE_LIMIT_PER_MINUTE` raised so the app's own limit did not interfere. The 2.5.0 tree and the 2.6.0 tree were run **back to back on the same machine** (Linux, 2 CPU cores, Python 3.13.18) with the same script, so the two columns are comparable with each other. They are not comparable with the figures in the 2.5.0 release notes, which were measured at another time on the same machine (typed turn 6.91 ms).

| Request | 2.5.0 p50 | 2.5.0 p95 | 2.6.0 p50 | 2.6.0 p95 |
|---|---:|---:|---:|---:|
| Parse a sentence, no order (`POST /api/text/parse`) | 5.34 ms | 7.04 ms | 5.11 ms | 6.45 ms |
| One typed turn (`POST /api/text/turn`) | 7.32 ms | 10.49 ms | 7.10 ms | 9.73 ms |
| Confirm an order, stock updated (`POST .../confirm`) | 12.50 ms | 16.96 ms | 12.62 ms | 17.07 ms |
| Analytics overview, 30 days | 38.07 ms | 78.84 ms | 40.02 ms | 100.28 ms |
| Inventory list | 7.95 ms | 11.83 ms | 8.72 ms | 9.89 ms |
| Orders page, 20 rows | 6.24 ms | 9.19 ms | 6.55 ms | 8.13 ms |

What to read from it: **the stage timing added in 2.6.0 costs nothing measurable on a typed turn** (7.32 to 7.10 ms at the median, inside the run-to-run spread). The analytics overview's 95th percentile moved from 78.84 to 100.28 ms in this pair of runs; that request is 50 samples with a long tail, no code on its path changed in 2.6.0, and the median moved by 2 ms, so this is read as noise, not as a regression, but it was not investigated further. Every row is on a shared machine and moves by a few milliseconds between runs. All 15 requests are in `eval/results/api_latency.json` (the 2.6.0 run). Nothing here says anything about speech.

## What was not measured

- Gnani's real speech-to-text and text-to-speech latency, on any network, for any of the eleven languages.
- The effect of silence trimming and automatic end-of-speech on real recordings.
- Behaviour under packet loss or a mobile connection.
- Many shops or many counters at once (the app is built for one shop and one server process).

To measure the first of these on your own shop: add the Gnani key in Settings, take a few spoken orders on the Order desk, open **Voice diagnostics**. For a scripted run, use
`scripts/verify_gnani.py` (about 33 calls for all eleven languages).
