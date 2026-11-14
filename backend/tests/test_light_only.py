"""SWARA AI has one theme, and it is light.

These tests read the real front-end source and the design tokens, so a dark mode (or a black fill) cannot come back by accident.
They check colours by computing WCAG relative luminance and contrast from the values in `frontend/src/styles/tokens.css`.
"""
from __future__ import annotations

import re

from app.config import REPO_ROOT

FRONTEND = REPO_ROOT / "frontend"
TOKENS = (FRONTEND / "src" / "styles" / "tokens.css").read_text(encoding="utf-8")
SKIP = {"node_modules", "dist"}


def token(name: str) -> str:
    m = re.search(rf"--{re.escape(name)}:\s*([^;]+);", TOKENS)
    assert m, f"token --{name} is missing"
    return m.group(1).strip()


def rgb(value: str) -> tuple[int, int, int]:
    h = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
    if h:
        return tuple(int(h.group(1)[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    f = re.match(r"rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)", value)
    assert f, f"cannot read colour {value}"
    return int(f.group(1)), int(f.group(2)), int(f.group(3))


def lum(value: str) -> float:
    def lin(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def front_end_files():
    for root in (FRONTEND / "src", FRONTEND / "public"):
        for p in root.rglob("*"):
            if p.is_file() and not (SKIP & set(p.parts)) and p.suffix in {".ts", ".tsx", ".css", ".js", ".html", ".webmanifest"}:
                yield p
    yield FRONTEND / "index.html"


def test_no_dark_theme_anywhere_in_the_front_end_source():
    pattern = re.compile(r"data-theme|prefers-color-scheme|color-scheme:\s*(dark|light dark)|content=\"[^\"]*\bdark\b", re.IGNORECASE)
    files = list(front_end_files())
    assert len(files) > 60, "the scan did not find the source tree"
    offenders = [str(p.relative_to(REPO_ROOT)) for p in files if pattern.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert offenders == []


def test_there_is_no_theme_code_left():
    assert not (FRONTEND / "src" / "lib" / "theme.tsx").exists()
    assert not (FRONTEND / "public" / "theme-init.js").exists()
    text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (FRONTEND / "src").rglob("*.tsx") if ".test." not in p.name)
    assert not re.search(r"ThemeProvider|useTheme|Switch to dark", text)


def test_the_page_is_declared_light_so_a_browser_cannot_recolour_it():
    assert re.search(r"color-scheme:\s*light;", TOKENS)
    assert re.search(r'<meta name="color-scheme" content="light only"', (FRONTEND / "index.html").read_text(encoding="utf-8"))
    manifest = (FRONTEND / "public" / "site.webmanifest").read_text(encoding="utf-8")
    assert lum(re.search(r'"background_color":\s*"([^"]+)"', manifest).group(1)) > 0.8
    assert lum(re.search(r'"theme_color":\s*"([^"]+)"', manifest).group(1)) > 0.8


def test_the_palette_is_the_requested_one():
    assert token("bg").lower() == "#ffffff"
    assert token("surface-2").lower() == "#f7f5ef"
    assert token("gold").lower() == "#d6b574"
    assert token("text").lower() == "#242424"
    assert token("text-3").lower() == "#686868"
    assert token("line").lower() == "#eae7df"


def test_every_surface_is_light_and_the_primary_action_is_gold_not_black():
    for name in ("bg", "surface", "surface-2", "surface-3", "overlay", "chart-surface", "gold-soft", "ok-bg", "warn-bg", "bad-bg", "info-bg"):
        assert lum(token(name)) > 0.8, f"--{name} is not a light colour"
    assert lum(token("brand")) > 0.4 and lum(token("gold")) > 0.4


def test_no_stylesheet_paints_a_dark_background_with_a_literal_colour():
    """Components use tokens; a literal near-black background in a stylesheet would bypass them."""
    bad = []
    for p in (FRONTEND / "src" / "styles").glob("*.css"):
        if p.name == "tokens.css":
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"background(?:-color)?:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}|black)\b", line):
                v = m.group(1)
                if v == "black" or (len(v) == 7 and lum(v) < 0.35) or (len(v) == 4 and lum("#" + "".join(c * 2 for c in v[1:])) < 0.35):
                    bad.append(f"{p.name}:{n}: {v}")
    assert bad == []


def test_text_is_readable_on_every_surface_it_sits_on():
    surfaces = [token(n) for n in ("bg", "surface", "surface-2", "surface-3")]
    for t in ("text", "text-2", "text-3", "link", "gold-strong"):
        for s in surfaces:
            assert contrast(token(t), s) >= 4.5, f"--{t} on {s} is {contrast(token(t), s):.2f}:1"
    assert contrast(token("brand-text"), token("brand")) >= 4.5
    assert contrast(token("brand-text"), token("brand-hover")) >= 4.5
    for fg, bg in (("ok", "ok-bg"), ("warn", "warn-bg"), ("bad", "bad-bg"), ("info", "info-bg")):
        assert contrast(token(fg), token(bg)) >= 4.5, f"--{fg} on --{bg}"


def test_the_keyboard_focus_ring_shows_on_white_and_ivory():
    for s in ("bg", "surface-2"):
        assert contrast(token("focus"), token(s)) >= 3
