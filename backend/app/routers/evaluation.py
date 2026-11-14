"""Serves the stored evaluation summary (eval/results/evaluation_summary.json) to the AI performance page.

The file is written by ``scripts/build_evaluation_summary.py`` from the project's own datasets and code; it holds TEXT-only results.
This route adds nothing to it and invents nothing: if the file is missing the page says how to create it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

RESULTS_DIR = Path(__file__).resolve().parents[3] / "eval" / "results"
SUMMARY_PATH = RESULTS_DIR / "evaluation_summary.json"
VERIFICATION_PATH = RESULTS_DIR / "verification_summary.json"   # scripts/build_verification_summary.py, counted from saved test logs
API_LATENCY_PATH = RESULTS_DIR / "api_latency.json"             # scripts/benchmark_api.py, local HTTP timings, no Gnani calls
HOW_TO = "python scripts/build_evaluation_summary.py"


def _optional(path: Path) -> Any:
    """A side file the page can show when it exists. A missing or unreadable file is simply absent, never an error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.get("")
def evaluation() -> dict[str, Any]:
    try:
        raw = SUMMARY_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return {"available": False, "summary": None, "how_to_create": HOW_TO}
    modified = datetime.fromtimestamp(SUMMARY_PATH.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return {
        "available": True, "summary": data, "file_modified": modified, "how_to_create": HOW_TO,
        "verification": _optional(VERIFICATION_PATH), "api_latency": _optional(API_LATENCY_PATH),
    }
