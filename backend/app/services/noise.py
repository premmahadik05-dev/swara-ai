"""Acoustic degradation for the Noisy Audio Testing Mode + WER/CER scoring.

Everything is synthetic and deterministic (seeded).  "babble" is *speech-shaped synthetic
noise* built from amplitude-modulated band-limited noise streams - it is **not** a recording of
real crowds, and results obtained with it should not be presented as real-market performance.

SNR is computed against the RMS of the *active* speech frames (frames within 20 dB of the loudest)
so that silence in the clip does not make the noise louder than the requested level.
"""
from __future__ import annotations

import io
import re
import wave
from dataclasses import dataclass

import numpy as np

NOISE_KINDS = ("white", "pink", "babble", "hum")
TARGET_SR = 16000


class AudioFormatError(ValueError):
    pass


# ------------------------------------------------------------------ WAV I/O
def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError) as exc:
        raise AudioFormatError("Not a readable PCM WAV file. Convert to 16-bit PCM WAV (the app's recorder produces this).") from exc
    if sw == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise AudioFormatError(f"Unsupported WAV sample width: {sw * 8}-bit")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def write_wav(x: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


# ------------------------------------------------------------------ DSP helpers
def _fft_filter(x: np.ndarray, sr: int, lo: float | None, hi: float | None) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    mask = np.ones_like(freqs, dtype=bool)
    if lo is not None:
        mask &= freqs >= lo
    if hi is not None:
        mask &= freqs <= hi
    return np.fft.irfft(spec * mask, n=len(x)).astype(np.float32)


def resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to or len(x) == 0:
        return x
    if sr_to < sr_from:
        x = _fft_filter(x, sr_from, None, 0.45 * sr_to)  # anti-alias
    n_out = int(round(len(x) * sr_to / sr_from))
    t_out = np.linspace(0, len(x) - 1, n_out)
    return np.interp(t_out, np.arange(len(x)), x).astype(np.float32)


def mulaw_roundtrip(x: np.ndarray, mu: int = 255) -> np.ndarray:
    y = np.sign(x) * np.log1p(mu * np.abs(np.clip(x, -1, 1))) / np.log1p(mu)
    q = np.round((y + 1) / 2 * mu) / mu * 2 - 1  # 8-bit quantisation
    return (np.sign(q) * (1 / mu) * ((1 + mu) ** np.abs(q) - 1)).astype(np.float32)


def telephony(x: np.ndarray, sr: int) -> np.ndarray:
    """8 kHz narrowband channel: 300-3400 Hz band-pass + mu-law quantisation (G.711-style)."""
    y = _fft_filter(x, sr, 300.0, 3400.0)
    y = resample(y, sr, 8000)
    y = mulaw_roundtrip(y)
    return resample(y, 8000, sr)


def active_rms(x: np.ndarray, sr: int) -> float:
    frame = max(1, int(0.02 * sr))
    n = len(x) // frame
    if n == 0:
        return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
    frames = x[: n * frame].reshape(n, frame)
    rms = np.sqrt((frames**2).mean(axis=1))
    keep = rms >= rms.max() * 0.1  # within 20 dB of the loudest frame
    if not keep.any():
        return float(rms.max())
    return float(np.sqrt((frames[keep] ** 2).mean()))


# ------------------------------------------------------------------ noise generators
def gen_noise(kind: str, n: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    if kind == "white":
        return rng.standard_normal(n).astype(np.float32)
    if kind == "pink":
        w = rng.standard_normal(n)
        spec = np.fft.rfft(w)
        f = np.fft.rfftfreq(n, 1.0 / sr)
        f[0] = f[1] if len(f) > 1 else 1.0
        return np.fft.irfft(spec / np.sqrt(f), n=n).astype(np.float32)
    if kind == "hum":  # mains hum + harmonics + low-level pink (fan / shop equipment)
        t = np.arange(n) / sr
        hum = sum(np.sin(2 * np.pi * 50 * k * t + rng.uniform(0, 6.28)) / k for k in range(1, 6))
        return (hum + 0.3 * gen_noise("pink", n, sr, rng)).astype(np.float32)
    if kind == "babble":  # speech-shaped, syllabically modulated noise, 6 "talkers"
        out = np.zeros(n, dtype=np.float32)
        t = np.arange(n) / sr
        for _ in range(6):
            carrier = _fft_filter(rng.standard_normal(n).astype(np.float32), sr, 200.0, 3500.0)
            rate = rng.uniform(2.5, 6.0)
            env = 0.5 * (1 + np.sin(2 * np.pi * rate * t + rng.uniform(0, 6.28)))
            env *= 0.5 * (1 + np.sin(2 * np.pi * rng.uniform(0.2, 0.8) * t + rng.uniform(0, 6.28)))
            out += (carrier * env).astype(np.float32)
        return out
    raise ValueError(f"unknown noise kind: {kind}")


def mix_at_snr(signal: np.ndarray, noise: np.ndarray, snr_db: float, sr: int) -> np.ndarray:
    ps = active_rms(signal, sr) ** 2
    pn = float(np.mean(noise**2)) + 1e-12
    scale = np.sqrt(ps / (pn * 10 ** (snr_db / 10.0)))
    return (signal + noise * scale).astype(np.float32)


@dataclass
class Degraded:
    wav: bytes
    label: str
    measured_snr_db: float | None


def degrade(data: bytes, *, kind: str | None, snr_db: float | None, use_telephony: bool = False, seed: int = 7) -> Degraded:
    """Return a 16 kHz mono WAV with optional noise at ``snr_db`` and optional 8 kHz telephony channel."""
    x, sr = read_wav(data)
    x = resample(x, sr, TARGET_SR) if sr != TARGET_SR else x
    sr = TARGET_SR
    if len(x) < sr // 10:
        raise AudioFormatError("Audio is too short (< 0.1 s).")
    peak = float(np.max(np.abs(x))) or 1.0
    x = x / peak * 0.8  # normalise so clipping does not hide differences
    rng = np.random.default_rng(seed)
    measured = None
    label = "clean"
    if kind:
        if kind not in NOISE_KINDS:
            raise ValueError(f"noise kind must be one of {NOISE_KINDS}")
        if snr_db is None:
            raise ValueError("snr_db is required with a noise kind")
        noise = gen_noise(kind, len(x), sr, rng)
        mixed = mix_at_snr(x, noise, snr_db, sr)
        resid = mixed - x
        measured = float(10 * np.log10((active_rms(x, sr) ** 2) / (np.mean(resid**2) + 1e-12)))
        x = mixed
        label = f"{kind}@{snr_db:g}dB"
    if use_telephony:
        x = telephony(x, sr)
        label = f"{label}+tel" if label != "clean" else "telephony"
    return Degraded(write_wav(x, sr), label, measured)


# ------------------------------------------------------------------ metrics
def _norm_for_wer(s: str) -> list[str]:
    from ..nlu.normalize import normalize_text
    return normalize_text(s).split()


def _edit_distance(a: list, b: list) -> int:
    if not a:
        return len(b)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = _norm_for_wer(reference), _norm_for_wer(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    ref = re.sub(r"\s+", "", " ".join(_norm_for_wer(reference)))
    hyp = re.sub(r"\s+", "", " ".join(_norm_for_wer(hypothesis)))
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(list(ref), list(hyp)) / len(ref)
