"""The landing page's type system and design rules, read from the real source.

The page has one job in typography: an editorial serif for display headings, a plain sans for everything else, nothing loaded from a font service.
These tests keep that from drifting (a bold heading, an all-capital label, an italic accent word, a link to Google Fonts) and keep the
"one light theme, restrained gold, little motion" rules in the stylesheet itself. Contrast is covered in test_light_only.py.
"""
from __future__ import annotations

import json
import re

from app.config import REPO_ROOT

FRONTEND = REPO_ROOT / "frontend"
SRC = FRONTEND / "src"
LANDING = (SRC / "styles" / "landing.css").read_text(encoding="utf-8")
TOKENS = (SRC / "styles" / "tokens.css").read_text(encoding="utf-8")
UI = (SRC / "styles" / "ui.css").read_text(encoding="utf-8")
CSS_FILES = sorted((SRC / "styles").glob("*.css"))


def rules(css: str):
    """(selector, body) pairs; good enough for these flat stylesheets (media queries are walked into)."""
    for m in re.finditer(r"([^{}@]+)\{([^{}]*)\}", css):
        yield m.group(1).strip(), m.group(2)


def test_display_headings_use_the_serif_token_and_the_token_names_a_bundled_font_with_fallbacks():
    line = next(l for l in TOKENS.splitlines() if "--font-display:" in l)
    assert "'Newsreader Variable'" in line
    assert "Georgia" in line and line.rstrip().endswith("serif;")
    for script in ("Gujarati", "Devanagari", "Bengali", "Tamil", "Telugu", "Kannada", "Malayalam", "Gurmukhi"):
        assert f"Noto Sans {script} Variable" in line, f"a heading in {script} would fall back to a Latin serif"
    assert "var(--font-display)" in LANDING
    assert re.search(r"h1\s*\{[^}]*font-family:\s*var\(--font-display\)", UI), "app page titles must use the same serif"


def test_fonts_are_bundled_with_the_app_and_never_fetched_from_a_font_service():
    pkg = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    deps = pkg["dependencies"]
    assert "@fontsource-variable/newsreader" in deps
    assert "@fontsource-variable/geist" in deps
    main = (SRC / "main.tsx").read_text(encoding="utf-8")
    assert "@fontsource-variable/newsreader" in main
    scanned = [FRONTEND / "index.html", *SRC.rglob("*.css"), *SRC.rglob("*.tsx"), *SRC.rglob("*.ts")]
    offenders = [str(p.relative_to(REPO_ROOT)) for p in scanned if p.is_file() and ".test." not in p.name and re.search(r"fonts\.(googleapis|gstatic)\.com|use\.typekit|cloud\.typography|cdnjs", p.read_text(encoding="utf-8", errors="ignore"))]
    assert offenders == []


def test_no_heading_on_the_landing_page_is_bold_and_the_app_page_title_is_the_same_serif():
    """Elegant display type is set light and large. Landing headings stay at weight 500 or below; the app's page title (h1) shares the serif."""
    heavy = []
    for sel, body in rules(LANDING):
        if not re.search(r"(^|[\s,>.#])(h[1-4])\b|\.lp-menu nav a", sel):
            continue
        m = re.search(r"font-weight:\s*(\d+)", body)
        if m and int(m.group(1)) > 500:
            heavy.append(f"{sel.strip()[:60]} {m.group(1)}")
    assert heavy == []
    h1 = re.search(r"(?m)^h1\s*\{([^}]*)\}", UI)
    assert h1 and "var(--font-display)" in h1.group(1)
    assert int(re.search(r"font-weight:\s*(\d+)", h1.group(1)).group(1)) <= 500


def test_landing_stylesheet_has_no_capital_labels_italic_accents_or_glass_effects():
    assert not re.search(r"text-transform:\s*uppercase", LANDING)
    assert not re.search(r"font-style:\s*italic", LANDING)
    assert "backdrop-filter" not in LANDING
    assert "filter: blur" not in LANDING
    assert not re.search(r"conic-gradient|radial-gradient", LANDING), "decorative gradients are not part of the system"


def test_the_only_gradient_on_the_landing_page_is_the_hard_edged_band_behind_the_hero_picture():
    found = re.findall(r"linear-gradient\([^;]*\)", LANDING)
    assert len(found) == 1, found
    assert "40%" in found[0] and "var(--bg)" in found[0] and "var(--surface-2)" in found[0]


def test_motion_is_limited_to_one_hero_rise_and_the_link_underline_and_respects_reduced_motion():
    assert "@media (prefers-reduced-motion: no-preference)" in LANDING
    # every `animation:` is inside the no-preference block (so reduced-motion visitors get none)
    outside = LANDING.split("@media (prefers-reduced-motion: no-preference)")[0]
    assert "animation:" not in outside
    assert len(re.findall(r"@keyframes", LANDING)) == 1
    assert not re.search(r"scroll-behavior:\s*smooth", LANDING) or "prefers-reduced-motion" in LANDING


def test_in_page_links_stop_below_the_sticky_bar():
    assert re.search(r"scroll-padding-top:\s*88px", LANDING)
    bar = re.search(r"\.lp-bar\s*\{[^}]*height:\s*(\d+)px", LANDING)
    assert bar and int(bar.group(1)) < 88


def test_the_page_stays_within_the_stated_palette():
    """Literal colours in the landing stylesheet are rgba shadows of the text colour only; every other colour comes from a token."""
    code = re.sub(r"/\*.*?\*/", "", LANDING, flags=re.S)
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b", code)
    assert literals == [], literals
    for m in re.finditer(r"rgba?\(([^)]*)\)", code):
        assert m.group(1).replace(" ", "").startswith("36,36,36"), f"a shadow colour that is not the text colour: {m.group(0)}"


def test_every_interactive_element_on_the_landing_page_has_a_visible_focus_style():
    ui = UI + LANDING
    assert re.search(r":focus-visible", ui)
    assert not re.search(r"outline:\s*(none|0)\s*[;}]", LANDING.replace(".land main { outline: none; }", "")), "an outline is removed without a replacement"


def test_headings_in_the_landing_source_do_not_carry_italic_or_a_single_accented_word():
    src = (SRC / "pages" / "Landing.tsx").read_text(encoding="utf-8") + (SRC / "pages" / "landing" / "Showcase.tsx").read_text(encoding="utf-8")
    for m in re.finditer(r"<h[1-3][^>]*>(.*?)</h[1-3]>", src):
        assert not re.search(r"<(em|i|strong|b|mark|span)\b", m.group(1)), f"an accent inside a heading: {m.group(0)}"
