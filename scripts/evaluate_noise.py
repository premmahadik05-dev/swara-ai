"""Noise-robustness of the REAL speech chain (Prisma STT + SWARA AI parser), measured with your key.

Method: Timbre speaks each test order (3 phrases per language; the original 4 languages by default, all 11 with --langs) -> we degrade that audio with synthetic noise at
chosen SNRs and an 8 kHz telephone channel -> Prisma transcribes each variant -> WER/CER vs the spoken text and
whether the parser still extracts the right order.

Limits you must keep when quoting results (the script writes them into the report too):
  * Source speech is TTS, not real shop recordings; real voices vary far more.
  * Noise is synthetic (white/pink/hum/babble-like), mixed at a computed SNR - not a recording of a real shop.
  * 3 phrases per language is a small sample; treat differences of a few points as noise.

    python scripts/evaluate_noise.py                      # default: 4 langs x 3 phrases x 7 conditions ~ 96 STT calls
    python scripts/evaluate_noise.py --langs gu --phrases 1 --quick
    python scripts/evaluate_noise.py --langs ta mr bn     # any of the 11 languages in the registry (the default stays the original four)
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from collections import defaultdict
from dataclasses import asdict

from _live import PHRASES, Row, make_env, pct, save_report, synth, transcribe_row

from app.gnani.client import GnaniError  # noqa: E402
from app.services import noise as nz  # noqa: E402

CONDITIONS = [(None, None, False), ("white", 20, False), ("babble", 10, False), ("babble", 0, False),
              ("hum", 10, False), ("pink", 5, False), (None, None, True)]
QUICK = [(None, None, False), ("babble", 10, False), (None, None, True)]


async def run(env, langs, n_phrases, conditions):
    rows: list[Row] = []
    for lang in langs:
        for phrase, expected in PHRASES[lang][:n_phrases]:
            try:
                tts, voice = await synth(env, lang, phrase)
            except GnaniError as exc:
                rows.append(Row(lang, phrase, "tts", error=f"{exc.error_type}: {exc.user_message}"))
                if exc.error_type in ("NOT_CONFIGURED", "INVALID_API_KEY", "MISSING_API_KEY", "LOCAL_BUDGET_EXCEEDED"):
                    return rows
                continue
            for kind, snr, tel in conditions:
                d = nz.degrade(tts.audio, kind=kind, snr_db=snr, use_telephony=tel)
                row = Row(lang, phrase, d.label, tts_ms=tts.meta.latency_ms, voice=voice)
                await transcribe_row(env, row, d.wav, expected, phrase)
                rows.append(row)
                if row.error and "LOCAL_BUDGET" in row.error:
                    return rows
    return rows


def render(rows, env) -> str:
    s = env.settings
    by = defaultdict(list)
    for r in rows:
        if r.error is None:
            by[r.condition].append(r)
    L = ["# Noise-robustness (measured with Gnani Prisma)", "",
         f"* STT model `{s.gnani_stt_model}`, format `{s.gnani_stt_format}` | TTS source voice(s) from `{s.gnani_tts_model}`",
         "* Source audio: Timbre TTS output. Noise: synthetic, mixed at the stated SNR. Small sample - indicative only.", "",
         "| Condition | n | mean WER | mean CER | order parsed correctly | STT p50 ms |", "|---|---|---|---|---|---|"]
    for cond, rs in by.items():
        L.append(f"| {cond} | {len(rs)} | {statistics.mean(r.wer for r in rs):.3f} | {statistics.mean(r.cer for r in rs):.3f} | "
                 f"{sum(1 for r in rs if r.chain_ok)}/{len(rs)} | {pct([r.stt_ms for r in rs], 50)} |")
    langs = sorted({r.lang for r in rows})
    L += ["", "## By language (all conditions)", "", "| Lang | n | mean WER | order parsed correctly |", "|---|---|---|---|"]
    for lg in langs:
        rs = [r for r in rows if r.lang == lg and r.error is None]
        if rs:
            L.append(f"| {lg} | {len(rs)} | {statistics.mean(r.wer for r in rs):.3f} | {sum(1 for r in rs if r.chain_ok)}/{len(rs)} |")
    errs = [r for r in rows if r.error]
    if errs:
        L += ["", f"## Errors ({len(errs)})"] + [f"* {r.lang}/{r.condition}: {r.error}" for r in errs[:10]]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="*", default=["gu", "hi", "en", "hinglish"], choices=list(PHRASES))
    ap.add_argument("--phrases", type=int, default=3)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    env = make_env()
    if not env.settings.gnani_configured:
        print("GNANI_API_KEY is not set. Copy .env.example to .env, paste your key, run again.", file=sys.stderr)
        return 2
    conds = QUICK if a.quick else CONDITIONS
    calls = len(a.langs) * a.phrases * (1 + len(conds))
    print(f"This will make about {calls} Gnani API calls (limit {env.settings.gnani_max_calls_per_hour}/hour). Starting...")
    rows = asyncio.run(run(env, a.langs, a.phrases, conds))
    md = render(rows, env)
    print(md)
    print("saved:", save_report("noise_live", {"rows": [asdict(r) for r in rows], "stt_model": env.settings.gnani_stt_model}, md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
