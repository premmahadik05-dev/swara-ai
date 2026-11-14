"""SWARA AI is presented as an independent product.

No file of the project (source, scripts, documents, metadata, the built front end) may carry wording that ties it to a one-off programme
(a one-off programme, a challenge, a competition, a submission). Genuine technical credit to Gnani.ai for Prisma and Timbre is kept and is checked for here too: removing the
event wording must not remove the attribution, and the attribution must not claim an affiliation.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".pytest_cache", "data", "test-results", "htmlcov", ".git"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".html", ".md", ".txt", ".json", ".bat", ".svg", ".webmanifest", ".example", ".toml", ".ini", ".yml", ".yaml", ".cfg"}
ME = Path(__file__).resolve()

# The wording being kept out. "challenge" alone is not listed: it has plain engineering meanings (an authentication challenge). The phrases below are the event itself.
FORBIDDEN = re.compile(
    r"intern" r"ship|great\s*indian\s*ai|greatindianai|challenge[- ]submission|submission (pack|form|deadline)|hackathon|"
    r"(coding|ai|design|startup)\s+competition|for the (gnani|challenge)|participant\s+(id|name|number)|judging (panel|criteria)|\bjudges?\b\s+(will|can|may)",
    re.I,
)


def _files():
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.resolve() == ME:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.suffix.lower() in TEXT_SUFFIXES or p.name in {".env.example", ".gitignore"}:
            yield p


def test_the_guard_recognises_the_wording_it_looks_for():
    """A guard that matches nothing would pass forever; check it fires on each kind of phrase."""
    for sample in ("Built for the Great Indian AI Intern" "ship Challenge", "a hack" "athon entry", "Submission deadline", "participant ID: 12", "for the Gnani team"):
        assert FORBIDDEN.search(sample), sample
    for fine in ("Speech recognition by Gnani.ai Prisma", "an authentication challenge", "internal links"):
        assert not FORBIDDEN.search(fine), fine


def test_no_programme_specific_wording_anywhere():
    hits = []
    for p in _files():
        if p.name in {"package-lock.json"}:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in FORBIDDEN.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{p.relative_to(ROOT)}:{line}: {m.group(0)}")
    assert not hits, "programme-specific wording found:\n" + "\n".join(hits[:20])


def test_built_front_end_has_none_either():
    dist = ROOT / "frontend" / "dist"
    if not dist.exists():
        return
    hits = [str(p.relative_to(ROOT)) for p in dist.rglob("*") if p.is_file() and p.suffix in {".js", ".html", ".css", ".webmanifest", ".txt"} and FORBIDDEN.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert not hits, f"programme-specific wording in the built front end: {hits}"


def test_gnani_attribution_is_kept_and_claims_no_affiliation():
    landing = (ROOT / "frontend" / "src" / "pages" / "Landing.tsx").read_text(encoding="utf-8")
    assert "Gnani.ai Prisma" in landing and "Gnani.ai Timbre" in landing
    assert "not affiliated with or endorsed by Gnani.ai" in landing
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(r"products of Gnani\.ai", readme) and "not affiliated with or endorsed by Gnani.ai" in readme


def test_pdf_and_docx_report_have_none(tmp_path):
    """The Word and PDF copies of the report are binary files the text scan cannot see."""
    import shutil
    import subprocess
    import zipfile
    docx = ROOT / "docs" / "PROJECT_REPORT.docx"
    if docx.exists():
        xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8", "ignore")
        assert not FORBIDDEN.search(re.sub(r"<[^>]+>", "", xml)), "programme-specific wording in PROJECT_REPORT.docx"
    pdf = ROOT / "docs" / "PROJECT_REPORT.pdf"
    if pdf.exists() and shutil.which("pdftotext"):  # poppler is not installed everywhere; the DOCX check above always runs
        text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
        assert not FORBIDDEN.search(text), "programme-specific wording in PROJECT_REPORT.pdf"
