"""Small, dependency-free audio helpers (WAV only needs the stdlib)."""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass


@dataclass
class WavInfo:
    sample_rate: int
    channels: int
    sample_width: int
    frames: int

    @property
    def duration(self) -> float:
        return self.frames / float(self.sample_rate) if self.sample_rate else 0.0


def sniff_audio(data: bytes) -> str | None:
    """Identify the container from magic bytes (never trust the client's Content-Type)."""
    if len(data) < 12:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:3] == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0 and (data[1] & 0x06) != 0):
        # 0xFFF1/0xFFF9 is ADTS AAC; others are MPEG audio (MP3)
        return "aac" if data[1] in (0xF1, 0xF9) else "mp3"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"fLaC":
        return "flac"
    if data[4:8] == b"ftyp":
        return "m4a"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    return None


CONTENT_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg", "flac": "audio/flac", "m4a": "audio/mp4", "aac": "audio/aac"}


def inspect_wav(data: bytes) -> WavInfo:
    with wave.open(io.BytesIO(data), "rb") as w:
        return WavInfo(w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes())


def pcm16_to_wav(pcm: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()
