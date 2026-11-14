# Recordings for the live language check (optional)

`verify_gnani.bat` / `python scripts/verify_gnani.py` can also test Prisma on **a real person's voice**. This is the only check that says anything about
how Prisma hears a shopkeeper, as opposed to Timbre's own synthetic speech. It is the `stt_human` check, and it is skipped for a language that has no file here.

Put one recording per language in this folder, named after the language key:

| Key | Language | Key | Language |
|---|---|---|---|
| `gu.wav` | Gujarati | `ta.wav` | Tamil |
| `hi.wav` | Hindi | `te.wav` | Telugu |
| `en.wav` | English (India) | `kn.wav` | Kannada |
| `hinglish.wav` | Hinglish | `ml.wav` | Malayalam |
| `mr.wav` | Marathi | `pa.wav` | Punjabi |
| `bn.wav` | Bengali | | |

- **Say the sample sentence the Order desk shows for that language** ("Customer speaks" → the language → the sample), or write what you said in
  `<key>.txt` next to the recording (one line, in the language's script) and that is what the transcript is compared with.
- The file must be a readable **PCM WAV** and no larger than the server's upload limit. Anything else is skipped with the reason shown in the result.
- Recordings stay on your machine and are sent only to Gnani when you run the check. Do not commit recordings of other people's voices.
- Without a file here the language still gets its other three checks (`tts`, `stt_code`, `stt_loopback`); the missing one is shown as "skipped", never as a pass.
