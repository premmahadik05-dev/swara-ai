"""The stored evaluation summary behind the AI performance page: internally consistent, and reproducible from the code and data in this repository."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "eval" / "results" / "evaluation_summary.json"


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SHIPPED.read_text(encoding="utf-8"))


def test_branded_verdicts_add_up_and_the_percentages_are_recomputed_from_them(summary):
    b = summary["branded"]
    v = b["verdicts"]
    assert sum(v.values()) == b["cases"]
    assert b["exact_pct"] == round(100 * v["exact"] / b["cases"], 1)
    assert b["wrong_product_pct"] == round(100 * v["wrong_product"] / b["cases"], 1)
    assert b["recognised_or_asked_pct"] == round(100 * (v["exact"] + v["ambiguous_contains_expected"]) / b["cases"], 1)
    for key in v:
        assert sum(row.get(key, 0) for row in b["by_language"].values()) == v[key], key


def test_end_to_end_counts_add_up(summary):
    e = summary["end_to_end"]
    assert sum(e["outcomes"].values()) == e["n_sentences"]
    assert e["n_scored"] == e["n_sentences"] - e["outcomes"].get("skipped_gold_not_convertible", 0)
    assert e["order_correct_pct"] == round(100 * e["outcomes"]["order_correct"] / e["n_scored"], 1)
    g = e["stock_guard"]
    assert g["empty_refused"] + g.get("empty_not_refused", 0) == g["empty_checked"]
    assert g["empty_negative_stock"] == 0 and g["half_negative_stock"] == 0
    assert g["half_asked_or_offered"] + g["half_refused"] <= g["half_checked"]


def test_dataset_sizes_match_the_files_they_name(summary):
    counts: dict[str, int] = {}
    for line in (ROOT / "eval" / "utterances.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            counts[row["set"]] = counts.get(row["set"], 0) + 1
    counts["authored"] = sum(1 for line in (ROOT / "eval" / "language_sentences.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    by_id = {d["id"]: d for d in summary["datasets"]}
    for dataset, n in counts.items():
        assert by_id[dataset]["n"] == n, dataset


def test_noise_levels_are_ordered_and_bounded(summary):
    levels = summary["noise"]["levels"]
    assert [l["cer"] for l in levels] == sorted(l["cer"] for l in levels) and levels[0]["cer"] == 0
    for l in levels:
        assert 0 <= l["utterance_exact_min"] <= l["utterance_exact"] <= l["utterance_exact_max"] <= 1
    assert levels[0]["utterance_exact"] == 1.0   # no damage -> the parser's own gold must be reproduced exactly


def test_no_speech_to_text_or_voice_figures_are_stored_without_a_live_call(summary):
    """No live Gnani call has been made, so no key may hold a word-error rate or an STT / TTS timing (the text may say they are absent)."""
    keys: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                keys.add(k.lower())
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(summary)
    assert not keys & {"wer", "word_error_rate", "stt_ms", "tts_ms", "stt_latency", "tts_latency", "stt_p50_ms", "tts_p50_ms"}
    assert not (ROOT / "eval" / "results" / "live_verification.json").exists()


def test_every_number_in_the_summary_reproduces_from_the_code_and_data(tmp_path, monkeypatch, summary):
    """Rebuild the summary into a temporary file and compare. Only the timestamp and the wall-clock parser timings may differ."""
    spec = importlib.util.spec_from_file_location("build_evaluation_summary", ROOT / "scripts" / "build_evaluation_summary.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "rebuilt.json"
    monkeypatch.setattr(mod, "OUT", out)
    mod.main()
    rebuilt = json.loads(out.read_text(encoding="utf-8"))
    for d in (summary, rebuilt):
        d.pop("generated_at", None)
        d.pop("parser_latency", None)
    assert rebuilt == summary, "eval/results/evaluation_summary.json is out of date: run python scripts/build_evaluation_summary.py"
