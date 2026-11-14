"""Voice diagnostics for the owner: where the time goes between the end of speech and the reply, from what this server recorded.

Everything here is read from rows the app wrote while taking orders:
  * the server's stage times for each spoken turn (stored with the reply in ``turns.detail.timing``, since 2.6.0),
  * what the browser reported about how long the person waited (``turns.detail.client``; browser-reported, kept apart),
  * one row per outbound Gnani call (``api_calls``: status, latency, number of tries).
Nothing is estimated. A figure with no rows behind it is None and the page says "Not measured yet".
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import ApiCall, Turn, utcnow

MAX_TURNS = 5000
STAGES = ("validate_ms", "stt_ms", "nlu_ms", "db_ms", "process_ms", "tts_ms", "server_ms")


def percentile(values: list[float], p: float) -> Optional[float]:
    """Linear-interpolated percentile (the same convention as numpy's default); None for no data."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def summary(values: list[float]) -> dict[str, Any]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return {"n": 0, "p50": None, "p95": None, "max": None, "mean": None}
    return {"n": len(vals), "p50": percentile(vals, 50), "p95": percentile(vals, 95), "max": round(max(vals), 1), "mean": round(sum(vals) / len(vals), 1)}


def _calls(db: Session, since, provider: str) -> dict[str, Any]:
    rows = list(db.scalars(select(ApiCall).where(ApiCall.created_at >= since, ApiCall.provider == provider)))
    ok = [r for r in rows if r.ok]
    errs = Counter((r.error_type or "unknown") for r in rows if not r.ok)
    out = summary([r.latency_ms for r in ok])
    out.update({
        "calls": len(rows), "ok": len(ok), "errors": len(rows) - len(ok),
        "retried": sum(1 for r in rows if (r.attempts or 1) > 1),
        "error_types": [{"type": k, "count": v} for k, v in errs.most_common(6)],
    })
    return out


def voice_diagnostics(db: Session, settings: Settings, gnani_budget_used: int, hours: int = 168) -> dict[str, Any]:
    now = utcnow()
    since = now - timedelta(hours=hours)
    turns = list(db.scalars(select(Turn).where(Turn.role == "assistant", Turn.created_at >= since).order_by(Turn.id.desc()).limit(MAX_TURNS)))
    timed = [(t, (t.detail or {}).get("timing") or {}) for t in turns]
    timed = [(t, tm) for t, tm in timed if tm]
    spoken = [(t, tm) for t, tm in timed if tm.get("mode") in ("voice", "stream")]
    typed = [(t, tm) for t, tm in timed if tm.get("mode") == "text"]

    stages = {k: summary([tm[k] for _, tm in spoken if tm.get(k) is not None]) for k in STAGES}
    spoken_tts = [tm for _, tm in spoken if "tts_ms" in tm]
    cached = sum(1 for tm in spoken_tts if tm.get("tts_cached"))

    client = [((t.detail or {}).get("client") or {}) for t, _ in spoken]
    client = [c for c in client if c]
    endpoints = Counter(c.get("endpoint") for c in client if c.get("endpoint"))

    slowest = sorted(spoken, key=lambda x: -(x[1].get("server_ms") or 0))[:10]
    # The share of the median server time each stage takes. Only stages that really are separate steps (not the sub-parts of process_ms).
    parts = {k: stages[k]["p50"] for k in ("validate_ms", "stt_ms", "process_ms", "tts_ms")}
    total = sum(v for v in parts.values() if v is not None)

    return {
        "window_hours": hours,
        "generated_at": now.isoformat(timespec="seconds") + "Z",
        "voice": {
            "turns": len(spoken),
            "by_mode": {"voice": sum(1 for _, tm in spoken if tm["mode"] == "voice"), "stream": sum(1 for _, tm in spoken if tm["mode"] == "stream")},
            "stages": stages,
            "stage_share_of_median": {k: (round(v / total, 4) if (v is not None and total) else None) for k, v in parts.items()},
            "tts_cached_share": round(cached / len(spoken_tts), 4) if spoken_tts else None,
            "retried_speech_calls": sum(1 for _, tm in spoken if (tm.get("stt_attempts") or 1) > 1),
        },
        "browser_reported": {
            "turns": len(client),
            "end_to_reply_ms": summary([c["end_to_reply_ms"] for c in client if "end_to_reply_ms" in c]),
            "end_to_audio_ms": summary([c["end_to_audio_ms"] for c in client if "end_to_audio_ms" in c]),
            "capture_ms": summary([c["capture_ms"] for c in client if "capture_ms" in c]),
            "endpoints": [{"kind": k, "turns": v} for k, v in endpoints.most_common()],
        },
        "typed": {"turns": len(typed), "process_ms": summary([tm["process_ms"] for _, tm in typed if tm.get("process_ms") is not None])},
        "gnani": {"stt": _calls(db, since, "gnani-stt"), "tts": _calls(db, since, "gnani-tts")},
        "budget": {"calls_last_hour": gnani_budget_used, "max_per_hour": settings.gnani_max_calls_per_hour},
        "config": {
            "stt_model": settings.gnani_stt_model, "tts_model": settings.gnani_tts_model,
            "stt_timeout_s": min(settings.gnani_stt_timeout_s, settings.gnani_timeout_s), "tts_timeout_s": min(settings.gnani_tts_timeout_s, settings.gnani_timeout_s),
            "connect_timeout_s": min(settings.gnani_connect_timeout_s, settings.gnani_timeout_s),
            "tts_sample_rate": settings.tts_sample_rate, "tts_speed": settings.tts_speed,
            "gnani_configured": settings.gnani_configured,
        },
        "slowest": [{
            "turn_id": t.id, "at": t.created_at.isoformat(timespec="seconds") + "Z", "mode": tm.get("mode"), "language": t.language,
            "server_ms": tm.get("server_ms"), "validate_ms": tm.get("validate_ms"), "stt_ms": tm.get("stt_ms"), "process_ms": tm.get("process_ms"),
            "tts_ms": tm.get("tts_ms"), "tts_cached": tm.get("tts_cached"), "stt_attempts": tm.get("stt_attempts"),
            "end_to_reply_ms": ((t.detail or {}).get("client") or {}).get("end_to_reply_ms"),
        } for t, tm in slowest],
    }
