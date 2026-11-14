"""What has actually been checked against the live Gnani service, per language.

``scripts/verify_gnani.py`` is the only writer of ``eval/results/live_verification.json`` (see its docstring for the schema). This
module only *reads* it, and never turns a missing or simulated result into a pass: a language shows "not run" until a real run
with a real key said otherwise, and a file whose ``mode`` is not ``live`` is reported as simulated.

Four independent checks exist per language:

* ``tts``          Timbre synthesised the language's sample sentence with the configured voice.
* ``stt_code``     Prisma accepted the language code for an audio request (a generated silent clip, so this proves the code is
                   accepted and says nothing about recognition quality).
* ``stt_loopback`` Prisma transcribed the Timbre audio from ``tts``. A loopback (synthetic speech, same vendor) - it is a weak signal.
* ``stt_human``    Prisma transcribed a person's recording placed in ``eval/samples/<language>.wav``. The only recognition evidence.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..languages import ORDER

CHECKS = ("tts", "stt_code", "stt_loopback", "stt_human")
STATUSES = {"passed", "failed", "skipped"}
MAX_FILE_BYTES = 2_000_000


def _entry(raw: Any, live: bool) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("status") not in STATUSES:
        return {"status": "not_run"}
    status = raw["status"] if live else "simulated"
    out: dict[str, Any] = {"status": status}
    for k in ("latency_ms", "audio_bytes"):
        v = raw.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = round(float(v), 1)
    for k, limit in (("detail", 240), ("voice", 40), ("transcript", 240), ("expected", 240), ("error_code", 60)):
        v = raw.get(k)
        if isinstance(v, str) and v:
            out[k] = v[:limit]
    if isinstance(raw.get("matched"), bool):
        out["matched"] = raw["matched"]
    return out


def load(settings: Settings) -> dict[str, Any]:
    """The verification file, reduced to what the UI may show. Never raises: an unreadable file reads as "nothing verified"."""
    path: Path = settings.verification_file
    empty = {"mode": "none", "generated_at": None, "stt_model": None, "tts_model": None,
             "languages": {k: {c: {"status": "not_run"} for c in CHECKS} for k in ORDER}}
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return empty
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and isinstance(data.get("checks"), dict)
    except (OSError, ValueError, AssertionError):
        return empty
    mode = data.get("mode") if data.get("mode") in ("live", "simulated") else "simulated"
    live = mode == "live"
    generated = data.get("generated_at")
    if isinstance(generated, str):
        try:
            datetime.fromisoformat(generated.replace("Z", "+00:00"))
        except ValueError:
            generated = None
    else:
        generated = None
    langs = {}
    for k in ORDER:
        row = data["checks"].get(k) if isinstance(data["checks"].get(k), dict) else {}
        langs[k] = {c: _entry(row.get(c), live) for c in CHECKS}
    return {
        "mode": mode, "generated_at": generated,
        "stt_model": data.get("stt_model") if isinstance(data.get("stt_model"), str) else None,
        "tts_model": data.get("tts_model") if isinstance(data.get("tts_model"), str) else None,
        "languages": langs,
    }
