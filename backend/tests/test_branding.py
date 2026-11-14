"""SWARA AI branding: one name everywhere, the official wording, and nothing of the old name left behind.

The repository scan is the regression guard behind docs/BRANDING_AUDIT.md: if the previous product name creeps back
into source, scripts or docs, this fails and names the file.
"""
from __future__ import annotations

import json
import re

from .helpers import AuthedClient

from app import brand
from app.config import REPO_ROOT, Settings, default_db_path

OLD = re.compile(r"dukaan[\s_\-]*mitra", re.IGNORECASE)          # note: the Hindi word "dukaan" (shop) alone is vocabulary, not the brand

# Where the old name may still appear, and why.
ALLOWED = {
    "backend/app/config.py": "falls back to a database file created before the rename",
    "backend/tests/test_branding.py": "this test",
    "frontend/src/lib/legacy.ts": "moves browser settings saved under the old name",
    "frontend/src/lib/legacy.test.ts": "tests that move",
    "docs/BRANDING_AUDIT.md": "the audit lists what was found",
}
SKIP_DIRS = {"node_modules", ".venv", "dist", "__pycache__", ".git", ".pytest_cache", "htmlcov", "tmp"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".docx", ".zip", ".db", ".woff", ".woff2", ".gz", ".pyc", ".sqlite", ".csv", ".lock"}


def _repo_files():
    for p in REPO_ROOT.rglob("*"):
        rel = p.relative_to(REPO_ROOT)
        if p.is_symlink() or not p.is_file() or set(rel.parts) & SKIP_DIRS or p.suffix.lower() in SKIP_SUFFIX:
            continue
        if rel.parts[:2] == ("backend", "data"):
            continue
        yield rel.as_posix(), p


def test_official_wording():
    assert brand.NAME == "SWARA AI"
    assert brand.TAGLINE == "Every Voice. Smarter Commerce."
    assert brand.SHORT == "Your intelligent voice-powered assistant for smarter grocery commerce."
    assert brand.DESCRIPTION.startswith("SWARA AI empowers Indian Kirana stores with multilingual voice ordering")
    assert brand.DESCRIPTION.endswith("actionable business insights.")


def test_api_identifies_itself_as_swara_ai(make_app):
    with AuthedClient(make_app()) as c:
        info = c.get("/openapi.json").json()["info"]
        assert info["title"] == "SWARA AI"
        assert info["summary"] == "Every Voice. Smarter Commerce."
        assert "SWARA AI empowers Indian Kirana stores" in info["description"]
        assert c.get("/api/health").json()["app"] == "SWARA AI"
        assert "SWARA AI" in c.get("/docs").text                    # the interactive API docs page title


def test_no_old_brand_left_in_the_repository():
    hits = []
    for rel, p in _repo_files():
        if rel in ALLOWED:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if OLD.search(line):
                hits.append(f"{rel}:{n}: {line.strip()[:100]}")
    assert not hits, "old product name found:\n" + "\n".join(hits)


def test_the_hindi_word_dukaan_is_still_in_the_language_engine():
    """A careless search-and-replace would have broken this: 'dukaan' (shop) is a Hinglish marker word."""
    assert "dukaan|" in (REPO_ROOT / "backend/app/nlu/vocab.py").read_text(encoding="utf-8")


def test_windows_scripts_use_the_new_name_and_keep_crlf_line_endings():
    for name in ("setup.bat", "start.bat", "dev.bat", "test.bat", "verify_gnani.bat"):
        raw = (REPO_ROOT / name).read_bytes()
        assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n"), f"{name} must keep CRLF (cmd.exe labels break on LF)"
        assert b"SWARA AI" in raw


def test_new_installs_use_swara_db_and_old_databases_are_still_found(tmp_path):
    assert default_db_path(tmp_path) == tmp_path / "swara.db"                       # nothing there yet
    (tmp_path / "dukaanmitra.db").write_bytes(b"")
    assert default_db_path(tmp_path) == tmp_path / "dukaanmitra.db"                 # an existing shop keeps its data
    (tmp_path / "swara.db").write_bytes(b"")
    assert default_db_path(tmp_path) == tmp_path / "swara.db"                       # once the new file exists it wins


def test_brand_assets_exist():
    for rel in ("brand/svg/swara-logo-horizontal-light.svg", "brand/svg/swara-symbol-light.svg",
                "brand/svg/swara-app-icon.svg", "brand/svg/swara-favicon.svg",
                "brand/svg/swara-symbol-mono.svg", "brand/png/swara-logo-horizontal-light@2000w.png",
                "brand/favicon.ico", "frontend/public/favicon.svg", "frontend/public/favicon.ico",
                "frontend/public/apple-touch-icon.png", "frontend/public/site.webmanifest"):
        assert (REPO_ROOT / rel).is_file(), rel


def test_logo_svgs_are_self_contained_and_name_the_product():
    for p in (REPO_ROOT / "brand/svg").glob("*.svg"):
        svg = p.read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "SWARA AI" in svg, p.name
        assert "<text" not in svg or p.name == "swara-social-card.svg", f"{p.name}: wordmark must be outlines, not font-dependent text"
        assert "http://" not in svg.replace("http://www.w3.org/2000/svg", ""), f"{p.name}: no external references"


SVG_DIR = REPO_ROOT / "brand/svg"


def test_the_only_name_in_any_logo_file_is_exactly_swara_ai():
    """Every logo and icon file is labelled with the exact product name; the card adds only the tagline."""
    labels = {"SWARA AI", "SWARA AI symbol", "SWARA AI. Every Voice. Smarter Commerce."}
    for p in SVG_DIR.glob("*.svg"):
        svg = p.read_text(encoding="utf-8")
        assert re.search(r'aria-label="([^"]*)"', svg).group(1) in labels, p.name
        assert re.search(r"<title>([^<]*)</title>", svg).group(1) in labels, p.name
        for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg):             # only the social card has live text
            assert "SWARA" not in t, f"{p.name}: the name is drawn as outlines, never typed as text"


def test_wordmark_is_two_words_in_one_colour():
    """'SWARA AI' is two outlined words in one weight, size and colour, after the mark; no third piece of text."""
    for mode, colour in (("light", "#242424"), ("mono", "#242424")):
        svg = (SVG_DIR / f"swara-logo-horizontal-{mode}.svg").read_text(encoding="utf-8")
        words = re.findall(r'<path d="[^"]+" fill="([^"]+)" transform="translate\(', svg)
        assert words == [colour, colour], (mode, words)                       # SWARA, AI: nothing else, same colour
        assert len(re.findall(r"<path ", svg)) == 3 + 2, mode                 # three ribbons of the mark + the two words


def _luminance(hex_colour: str) -> float:
    """WCAG relative luminance of #RRGGBB."""
    def lin(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def test_no_logo_file_is_made_for_a_dark_surface():
    """SWARA AI is light only, so the brand kit has no reversed / white-on-dark variants."""
    names = [p.name for p in (REPO_ROOT / "brand/svg").glob("*")] + [p.name for p in (REPO_ROOT / "brand/png").glob("*")]
    bad = [n for n in names if "-dark" in n or "mono-white" in n or "reversed" in n]
    assert not bad, f"logo files for dark surfaces are not part of a light-only product: {bad}"
    readme = (REPO_ROOT / "brand/README.md").read_text(encoding="utf-8")
    for stale in ("-dark", "mono-white", "mono-black", "reversed** set", "optional dark theme", "Luxury Black"):
        assert stale not in readme, f"brand/README.md still describes {stale!r}"


def test_nothing_the_product_ships_is_a_dark_surface():
    """Icon tiles and the share card are white, ivory or gold; the manifest and theme colour are white; the sidebar is a light token."""
    for name in ("swara-app-icon", "swara-app-icon-ivory", "swara-app-icon-gold", "swara-app-icon-mono", "swara-social-card"):
        svg = (SVG_DIR / f"{name}.svg").read_text(encoding="utf-8")
        tile = re.search(r'<rect [^>]*fill="(#[0-9A-Fa-f]{6})"', svg).group(1).upper()
        assert _luminance(tile) > 0.4, f"{name}: the tile {tile} is dark"
    manifest = json.loads((REPO_ROOT / "frontend/public/site.webmanifest").read_text(encoding="utf-8"))
    assert manifest["background_color"].upper() == "#FFFFFF" and manifest["theme_color"].upper() == "#FFFFFF"
    html = (REPO_ROOT / "frontend/index.html").read_text(encoding="utf-8")
    head = html.split("<script")[0]
    assert re.search(r'name="theme-color" content="#FFFFFF"', head, re.I), "index.html must ask for a white browser theme colour"
    css = (REPO_ROOT / "frontend/src/styles/app.css").read_text(encoding="utf-8")
    sidebar = re.search(r"\.sidebar \{[^}]*\}", css).group(0)
    assert "background: var(--surface-2)" in sidebar, "the sidebar must use the light ivory surface token"


def test_settings_default_database_name(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = Settings(_env_file=None).database_url
    assert url.endswith("/swara.db") or url.endswith("/dukaanmitra.db")           # the latter only if an old file is present


def test_order_numbers_use_the_sw_prefix_and_old_dm_numbers_still_resolve(client):
    first = client.get("/api/orders", params={"limit": 1}).json()["items"][0]
    assert re.fullmatch(r"SW-\d{6}-\d{4}", first["code"]), first["code"]
    legacy = "DM-" + first["code"][3:]                     # the number a shopkeeper may already have written down or printed
    for q in (first["code"], legacy):
        ids = [o["id"] for o in client.get("/api/orders", params={"q": q}).json()["items"]]
        assert first["id"] in ids, q
        hits = [o["id"] for o in client.get("/api/search", params={"q": q}).json()["orders"]]
        assert first["id"] in hits, q
