# Gnani model integration

Implemented from the public Gnani documentation (https://docs.gnani.ai), read on 10 Nov 2026. Everything below is what the code in `backend/app/gnani/` and `backend/app/routers/ws.py` does.

> **Verification status.** The build environment had no network route to Gnani and no API key. The client is tested against a **simulator written from the documentation** (`httpx.MockTransport` for REST, a local `websockets` server for streaming). Those tests prove request shape, error parsing and retry behaviour. They do **not** prove Gnani's live behaviour. `verify_gnani.bat` (about 33 real calls for all eleven languages, 3 per language) does; run it first. **No language has been run against live Gnani by the project author.**

## Where the key lives

`GNANI_API_KEY` is read by the backend from `.env` or from the Settings page (which writes `.env`). It is sent only as the `X-API-Key-ID` header (REST) or `x-api-key-id` header (WebSocket) from server to Gnani. The browser receives only a mask (last four characters) and a boolean `configured`. A test asserts the key appears in no GET response.

## Models

| Model | Role | Endpoint | Notes |
|---|---|---|---|
| Prisma v2.5 | Speech to text, default | `POST https://api.vachana.ai/stt/v3` (multipart) | One language code per request, no auto-detect. The ten documented codes: `bn-IN en-IN gu-IN hi-IN kn-IN ml-IN mr-IN pa-IN ta-IN te-IN`; all ten are wired (see [LANGUAGES.md](LANGUAGES.md)). English-Hindi mix is handled through `en-IN` and returns Latin script |
| Prisma v3.0 | Speech to text, optional | same endpoint with `model=prisma-v3.0` | Auto language (`indic-auto`), comma-separated language lists, `format=codemix` |
| Prisma streaming | Live ordering | `wss://api.vachana.ai/stt/v3/stream` | Headers `x-api-key-id`, **both** `lang_code` and `language_code` (Gnani's pages name the header both ways, so both are sent), `x-sample-rate: 16000`; binary PCM16 frames of 1024 bytes; JSON `commit` to finalise |
| Timbre v2.5 | Spoken replies | `POST https://api.vachana.ai/api/v1/tts/inference` (JSON) | Returns WAV bytes. `language` values `en-IN hi-IN hi-en ta-IN te-IN kn-IN ml-IN mr-IN bn-IN gu-IN pa-IN`. The 42 voices of the Timbre v2.5 catalogue, as documented: `en-IN` Kaveri, Trupti, Devika, Pranav, Shlok, Girish; `hi-IN` 13 voices (default Nalini); `hi-en` Poorvi; `ta-IN` 5; `te-IN` 5; `kn-IN` 2; `ml-IN` 2; `mr-IN` 2; `bn-IN` 2; `gu-IN` Falak, Veera; `pa-IN` Mehuli, Zayan. Voices of Timbre v3.0 are a different list and are not offered |
| Evon v3.3 | Reasoning | **not available** | see [EVON.md](EVON.md) |

## Connection, time limits and retries (changed in 2.6.0)

| Topic | What the code does | File |
|---|---|---|
| Connection | **One pooled HTTP client** per server process, kept warm (60 s idle), instead of a new connection for every call. It is rebuilt if the event loop, the base URL or the transport changes, and closed when the server stops | `gnani/client.py: _client, aclose` |
| Time limits | Speech to text `GNANI_STT_TIMEOUT_S` (default 20 s), text to speech `GNANI_TTS_TIMEOUT_S` (15 s), opening a connection `GNANI_CONNECT_TIMEOUT_S` (5 s). `GNANI_TIMEOUT_S` (40 s) is a ceiling none of them may exceed | `config.py: _timeout` |
| A call that was **sent** and got no answer in time | **Not retried.** It ends as `TIMEOUT` (HTTP 504): "The speech service took too long to answer. Your bill has not changed. Try again." Repeating a call that may already have been accepted would make the person wait twice and could be charged twice | `_send` |
| A failure **before** the request was accepted (connection refused, reset, stale pooled connection) | Retried on a fresh connection, up to 3 attempts, waits of 0.25 s then 0.5 s | `RETRY_ON` |
| `429`, `500`, `502`, `503`, `504` | Up to 3 attempts, same waits (Gnani's retry guidance). Other `4xx` are not retried | `RETRYABLE_STATUS` |
| What is recorded | Each call writes one `api_calls` row: provider, model, ok, status, error type (for a timeout, the exception name, for example `ReadTimeout`), latency and **number of attempts** | `services/apilog.py` |
| Local safety valve | `CallBudget` refuses further calls once `GNANI_MAX_CALLS_PER_HOUR` is reached | `gnani/client.py` |

Worst case for a service that never answers: before 2.6.0, 3 attempts of the single time limit (121.5 s at the defaults, counting the waits); from 2.6.0, one speech-to-text
limit (20 s). Measured on a stand-in with a 1 s limit: 4529 ms before, 1020 ms after ([PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md)).

## Reply first, voice after (2.6.0)

Gnani's REST endpoints give a finished transcript and a finished audio file: there is **no streaming** of either on these endpoints, and the two calls cannot overlap (the reply
text, which is what gets spoken, does not exist until the transcript has been understood). What 2.6.0 changes is **when the screen is allowed to update**.

1. The browser sends the recording with `speak_reply=false`. The server calls Prisma, runs the same `process_turn`, stores the reply as an assistant turn and answers with the
   transcript, reply, bill and `assistant_turn_id`. **No Timbre call has happened yet.**
2. The browser draws the reply and the bill at once, then calls `POST /api/turns/{assistant_turn_id}/speak`.
3. The server reads the text it **stored** for that turn, makes (or finds in the cache) the audio, and returns the audio URL, the time taken and whether it came from the cache.
   Nothing the caller sends is spoken: the endpoint takes no text, so it cannot be used to have arbitrary text read out on the shop's Gnani credits. It refuses a customer turn
   and an unknown turn (404) and a reply more than an hour old (410).
4. The browser plays the audio and reports what it measured (`POST /api/turns/{id}/client-timing`: time from end of speech to reply on screen, and to the voice starting).

The live stream (`/ws/voice?defer_audio=true`) does the same in one connection: the `turn` message (reply and bill) is sent first and an `audio` message follows. A voice that
fails leaves the written reply on screen and says why. The old behaviour (`speak_reply=true`, or `speak: true` on a typed turn) still works for other callers.

**Time to the voice is not shortened by this**; the person sees the bill earlier (about 0.7 s on the stand-in) and the voice about when it came before.

## Speech to text, request by request

| Step | What the code does | File |
|---|---|---|
| Input check | Magic-byte sniffing against Gnani's documented formats (WAV, MP3, OGG, FLAC, AAC, M4A). **WebM**, which is what a browser's `MediaRecorder` produces by default, is rejected with an actionable message; the app records WAV itself instead. Size ≤ 8 MB, duration ≤ 30 s | `services/audio.py`, `routers/voice.py` |
| Language | UI choice → exactly one `language_code` from the central table `languages.py` (Gujarati `gu-IN`, Hindi `hi-IN`, English and Hinglish `en-IN`, Marathi `mr-IN`, Bengali `bn-IN`, Tamil `ta-IN`, Telugu `te-IN`, Kannada `kn-IN`, Malayalam `ml-IN`, Punjabi `pa-IN`). `auto`/`mixed` only on v3.0; on v2.5 they are refused with `AUTO_DETECT_NEEDS_V3` (before 2.3.0 they silently meant Gujarati). A switched-off or unknown language is refused too, never replaced by another | `gnani/voices.py: stt_params`, `languages.py: choose` |
| Request | `audio_file`, `language_code`; `model` only when v3.0; `format` only if not `verbatim`; `bias_list` (≤100 single letters-only words, taken from the shop's product names **in the script of the chosen language**) and `bias_score` only on v2.5 and only if you turn *Send shop item names as hints* on and a single language was chosen | `gnani/client.py: transcribe` |
| Response | Reads `transcript`, `request_id`, `processing_time`, `end_to_end_latency`, `detected_language_code`, `output.literal` | `STTResult` |
| Empty speech | If the transcript is empty the assistant replies that it heard nothing (stored as a normal reply, so it can be spoken like any other) and the cart is unchanged. The response carries the open bill, so the screen can draw it without special cases (before 2.6.0 it did not, and the order desk could blank the bill) | `routers/voice.py`, `pipeline.no_speech_turn` |

Prisma's own `bias_list` feature is **experimental and off by default**: it is the only place item names reach Gnani, and I have not measured whether it helps. Measure with the Noise lab before relying on it.

## Streaming proxy (`/ws/voice`)

The browser connects to our WebSocket, not to Gnani (so the key stays on the server).

1. Origin check, key present, `language` and `session_id` validated.
2. Server opens `wss://…/stt/v3/stream` with the Gnani headers.
3. Incoming browser audio is **re-chunked to exactly 1024 bytes** (odd-sized chunks are buffered; the last frame is zero-padded).
4. Only Gnani messages of type `transcript` with non-empty text become turns. They run through the same `pipeline.process_turn` as typed text and are spoken back with Timbre if *Speak replies* is on.
5. The browser receives `ready`, `speech_start`, `processing`, `turn`, `error`, `closed`.
6. While a spoken reply is playing the browser stops sending microphone frames, so the assistant does not hear itself.

Tested against a local fake Gnani stream server for the frame size, headers, commit handling, origin rejection and upstream failure. **Not** tested against the real endpoint.

## Text to speech

- Request: `{text, voice, model, language, speed, audio_config{sample_rate 24000, mono, 16-bit, linear_pcm, container wav}}`.
- Voice and `language` per reply language, from the same table: each of the eleven languages has a default voice (see [LANGUAGES.md](LANGUAGES.md)); Hinglish uses the documented `hi-en` value with the voice Poorvi. The voice is configurable per language in Settings, but only names in Gnani's documented v2.5 list for that language are accepted (anything else falls back to the default instead of reaching Gnani as a 400). Speed 0.85–1.15.
- A language that is switched off is not spoken: the reply comes back as text with `audio.error` saying so.
- Replies are cached on disk by a hash of (model, voice, language, speed, sample rate, text), newest 300 files kept, so repeated phrases ("Aur kuch chahiye?") do not spend credits again.
- If TTS fails, the turn still succeeds: the reply text is shown and `audio.error` says why. Typed ordering is never blocked by a speech failure.

## Failure handling

| Condition | Behaviour |
|---|---|
| No key | Voice endpoints return `NOT_CONFIGURED` (503) with the exact fix; the UI disables the mic and explains why; typing works |
| 401 / invalid key | `INVALID_API_KEY` mapped to "Gnani rejected the API key. Check GNANI_API_KEY in .env." |
| 402 | "insufficient credit for this key" |
| 429, 500, 502, 503, 504, connection errors | up to 3 attempts, short exponential back-off (0.25 s, 0.5 s; was 0.5 s, 1 s before 2.6.0) as Gnani's retry guidance describes; other 4xx are not retried |
| No answer within the time limit | `TIMEOUT` (HTTP 504), **not retried**, with a plain message; the browser keeps the recording and offers **Try again**, and the bill is untouched |
| Documented error envelopes | `{success:false, error:{type,message}}`, `{detail:{error_code,message}}`, 422 validation lists, 504 gateway shape are all parsed (`_parse_error`) |
| Audio too long / unreadable | `MAX_AUDIO_DURATION_EXCEEDED`, `UNSUPPORTED_AUDIO_FORMAT`, `EMPTY_AUDIO` turned into plain sentences |
| Runaway loop | `CallBudget`: refuses further calls locally once `GNANI_MAX_CALLS_PER_HOUR` (default 300) is reached |
| Observability | every call is logged to `api_calls` (provider, model, ok, status, error type, latency, units, attempts); the Live screen and the owner's **Voice diagnostics** page show medians and 95th percentiles from that table, and every spoken turn stores its stage times |

## What is *not* measured here

Prisma accuracy on real shop speech in **any** of the eleven languages, Timbre quality in any of them, end-to-end latency over your network, behaviour under packet loss, and `bias_list` benefit. The scripts to measure them are in `scripts/` and write only measured values:

| Script | Calls | Measures |
|---|---|---|
| `scripts/verify_gnani.py [--langs ...] [--stream]` | 3 per language, 33 for all eleven (+1 per language with `--stream`) | Per language, four separate checks: `tts`, `stt_code` (a generated tone), `stt_loopback` (Timbre audio into Prisma, then the parser) and, if you supply a recording, `stt_human`. Writes `eval/results/live_verification.json`, which the app reads. See [LANGUAGES.md](LANGUAGES.md) |
| `scripts/evaluate_noise.py [--quick]` | many (it prints the count first) | STT word error rate vs SNR and noise type on Timbre-spoken phrases |
| Noise lab screen | conditions + 1 | the same for one clip you record |
