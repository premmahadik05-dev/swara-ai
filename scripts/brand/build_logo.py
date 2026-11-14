#!/usr/bin/env python3
"""Builds every SWARA AI logo asset (SVG + transparent PNG + favicon) from one geometry definition.

Why a script: the symbol is geometry, not a drawing, so every variant, size and file stays consistent and can be
regenerated. Nothing here calls a network service.

The mark: an "S" made of flowing sound-wave ribbons
    The centre line is an S made of two stacked ellipse arcs. Each strand is a ribbon that follows a true parallel
    offset of that line and tapers to a point at both ends; three strands of different length read as one
    voice waveform bent into a letter. A two-strand version is used below about 40 px.

The wordmark: exactly "SWARA AI" in Geist SemiBold capitals, one size, one weight, one colour, converted to
    outlines (so no SVG needs the font). Geist is SIL OFL 1.1, which allows this.

Palette: Ink #242424 (the wordmark, the same ink the app uses for text), Champagne Gold #D6B574 (the mark, as a
    gradient down to a deeper antique gold so it holds on ivory and white), Ivory #F7F5EF. SWARA AI is light only:
    no icon tile, card or panel is black, and no reversed or dark-surface variant of the logo is produced.

Run (from the repo root):
    python scripts/brand/build_logo.py
Needs: fonttools, brotli (to read the woff2), pillow and playwright (+ chromium) for the PNG/ICO files.
    pip install fonttools brotli pillow playwright && playwright install chromium
The font file is read from frontend/node_modules (run `npm install` in frontend/ first).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "brand"
SVG_DIR, PNG_DIR = BRAND / "svg", BRAND / "png"
FONT = ROOT / "frontend/node_modules/@fontsource-variable/geist/files/geist-latin-wght-normal.woff2"

# ---- brand palette (the official one) -----------------------------------------------------------
INK, GOLD, IVORY = "#242424", "#D6B574", "#F7F5EF"       # Ink (wordmark / text), Champagne Gold, Ivory
# The mark is a gold gradient. On the light surfaces the product uses, champagne gold alone is too pale to carry a
# shape, so the same three-stop gradient runs from champagne down to a deeper antique gold.
GRAD_LIGHT = ("#DDBF7C", "#BC9444", "#88621F")            # default: ivory / white backgrounds

# ---- the S ---------------------------------------------------------------------------------------
# The centre line is two stacked ellipse arcs joined at the origin with a common horizontal tangent (a clean S).
# Each strand is a ribbon that follows a true parallel offset of that line and tapers to a point at both ends, so
# the strands read as flowing sound waves of different length, not as concentric rings.
RX, RY = 112.0, 100.0                       # semi-axes of the two ellipses (wider than tall per bowl: S is 0.65 as wide as it is tall)
A_START, A_END = -40.0, 140.0               # where the centre line starts and ends (screen angles, y down)
TAPER = 0.30                                # fraction of a strand's length over which it grows to full width / shrinks to a point
STRANDS = [  # (offset from the centre line, maximum width, start, end), start/end as a fraction of the length
    (-25.0, 15.0, 0.10, 0.97),
    (0.0, 20.0, 0.00, 1.00),
    (25.0, 15.0, 0.03, 0.90),
]
COMPACT = [  # two bolder, more widely spaced strands for small sizes (sidebar mark, tab icon) where three would blur
    (-21.0, 20.0, 0.07, 0.97),
    (19.0, 30.0, 0.00, 1.00),
]


def _centreline(n: int = 900):
    """Sampled centre line: points, unit normals (one consistent side) and cumulative length."""
    raw = []
    for i in range(n + 1):                  # top ellipse, centre (0,-RY): angle falls from A_START to -270 (counter-clockwise)
        a = math.radians(A_START + (-270.0 - A_START) * i / n)
        raw.append((RX * math.cos(a), -RY + RY * math.sin(a), RX * math.sin(a), -RY * math.cos(a)))
    for i in range(1, n + 1):               # bottom ellipse, centre (0,RY): angle rises from -90 to A_END (clockwise)
        a = math.radians(-90.0 + (A_END + 90.0) * i / n)
        raw.append((RX * math.cos(a), RY + RY * math.sin(a), -RX * math.sin(a), RY * math.cos(a)))
    pts, nrm, cum = [], [], [0.0]
    for k, (x, y, dx, dy) in enumerate(raw):
        length = math.hypot(dx, dy)
        pts.append((x, y))
        nrm.append((-dy / length, dx / length))
        if k:
            cum.append(cum[-1] + math.hypot(x - raw[k - 1][0], y - raw[k - 1][1]))
    return pts, nrm, cum


_CL = _centreline()


def _at(u: float):
    pts, nrm, cum = _CL
    target = u * cum[-1]
    lo, hi = 0, len(cum) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if cum[mid] <= target else (lo, mid)
    t = 0.0 if cum[hi] == cum[lo] else (target - cum[lo]) / (cum[hi] - cum[lo])
    x = pts[lo][0] + (pts[hi][0] - pts[lo][0]) * t
    y = pts[lo][1] + (pts[hi][1] - pts[lo][1]) * t
    nx = nrm[lo][0] + (nrm[hi][0] - nrm[lo][0]) * t
    ny = nrm[lo][1] + (nrm[hi][1] - nrm[lo][1]) * t
    norm = math.hypot(nx, ny)
    return x, y, nx / norm, ny / norm


def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _spline(points: list[tuple[float, float]]) -> str:
    """Catmull-Rom through the points, as cubic Bezier segments (no leading M)."""
    out = []
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < n else points[i + 1]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return "".join(out)


def strand_outline(d: float, width: float, u0: float, u1: float, steps: int = 56) -> tuple[str, list[tuple[float, float]]]:
    """Closed outline of one tapered ribbon: (SVG path, its sampled points for the bounding box)."""
    left, right = [], []
    for i in range(steps + 1):
        t = 0.5 - 0.5 * math.cos(math.pi * i / steps)     # denser near the ends, where the width changes fastest
        x, y, nx, ny = _at(u0 + (u1 - u0) * t)
        w = width * min(_smooth(t / TAPER), _smooth((1 - t) / TAPER))
        left.append((x + (d + w / 2) * nx, y + (d + w / 2) * ny))
        right.append((x + (d - w / 2) * nx, y + (d - w / 2) * ny))
    back = right[::-1]
    path = (f"M{left[0][0]:.1f} {left[0][1]:.1f}" + _spline(left) + f"L{back[0][0]:.1f} {back[0][1]:.1f}" + _spline(back) + "Z")
    return path, left + right


def _build(strands) -> dict:
    paths, allpts = [], []
    for d, w, u0, u1 in strands:
        path, pts = strand_outline(d, w, u0, u1)
        paths.append(path)
        allpts += pts
    xs, ys = [q[0] for q in allpts], [q[1] for q in allpts]
    return dict(paths=paths, x0=min(xs), y0=min(ys), w=max(xs) - min(xs), h=max(ys) - min(ys))


FULL, SMALL = _build(STRANDS), _build(COMPACT)
X0, Y0, SYM_W, SYM_H = FULL["x0"], FULL["y0"], FULL["w"], FULL["h"]
CX0, CY0, CSYM_W, CSYM_H = SMALL["x0"], SMALL["y0"], SMALL["w"], SMALL["h"]


def symbol_group(fill: str, uid: str, gradient: tuple[str, str, str] | None, compact: bool = False) -> tuple[str, str]:
    """Returns (defs, group) for the S, translated so its bounding box starts at (0,0)."""
    geo = SMALL if compact else FULL
    defs, paint = "", fill
    if gradient:
        hi, mid, lo = gradient
        defs = (f'<linearGradient id="{uid}" gradientUnits="userSpaceOnUse" x1="{geo["x0"]:.1f}" y1="{geo["y0"]:.1f}" '
                f'x2="{geo["x0"] + geo["w"]:.1f}" y2="{geo["y0"] + geo["h"]:.1f}">'
                f'<stop offset="0" stop-color="{hi}"/><stop offset=".5" stop-color="{mid}"/><stop offset="1" stop-color="{lo}"/></linearGradient>')
        paint = f"url(#{uid})"
    paths = "".join(f'<path d="{d}"/>' for d in geo["paths"])
    return defs, f'<g transform="translate({-geo["x0"]:.2f} {-geo["y0"]:.2f})" fill="{paint}">{paths}</g>'


# ---- wordmark outlines ---------------------------------------------------------------------------
_font_cache: dict[int, object] = {}


def _font(weight: int):
    if weight in _font_cache:
        return _font_cache[weight]
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    f = TTFont(str(FONT))
    inst = instancer.instantiateVariableFont(f, {"wght": weight})
    _font_cache[weight] = inst
    return inst


def text_outline(text: str, weight: int, cap_height: float, tracking_em: float) -> tuple[str, float]:
    """Outlined text with baseline at y=0 (glyphs rise to negative y). Returns (path d, total advance)."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    f = _font(weight)
    gs, cmap = f.getGlyphSet(), f.getBestCmap()
    upm = f["head"].unitsPerEm
    cap = f["OS/2"].sCapHeight
    scale = cap_height / cap
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    x = 0.0
    for i, ch in enumerate(text):
        name = cmap[ord(ch)]
        tp = TransformPen(pen, (scale, 0, 0, -scale, x, 0))
        gs[name].draw(tp)
        x += gs[name].width * scale
        if i < len(text) - 1:
            x += tracking_em * upm * scale
    return pen.getCommands(), x


# ---- composed logos ------------------------------------------------------------------------------
def svg_wrap(w: float, h: float, inner: str, defs: str = "", title: str = "SWARA AI") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}" width="{w:.0f}" height="{h:.0f}" role="img" aria-label="{title}">'
            f'<title>{title}</title>' + (f"<defs>{defs}</defs>" if defs else "") + inner + "</svg>")


# mode -> (symbol gradient or None, solid colour for mono modes, wordmark colour)
MODES: dict[str, tuple[tuple[str, str, str] | None, str, str]] = {
    "light": (GRAD_LIGHT, "", INK),                   # the logo: ivory / white backgrounds
    "mono": (None, INK, INK),                         # one ink, for print, stamps and single-colour output
}


def _sym(mode: str, compact: bool = False, uid: str = "g") -> tuple[str, str]:
    grad, solid, _ = MODES[mode]
    return symbol_group(solid, uid, grad, compact)


def symbol_svg(mode: str) -> str:
    pad = 6
    defs, g = _sym(mode)
    return svg_wrap(SYM_W + 2 * pad, SYM_H + 2 * pad, f'<g transform="translate({pad} {pad})">{g}</g>', defs, "SWARA AI symbol")


def compact_symbol_svg(mode: str) -> str:
    """The two-strand S for small sizes (24-40 px)."""
    pad = 4
    defs, g = _sym(mode, compact=True)
    return svg_wrap(CSYM_W + 2 * pad, CSYM_H + 2 * pad, f'<g transform="translate({pad} {pad})">{g}</g>', defs, "SWARA AI symbol")


# ---- the wordmark: the single name "SWARA AI", one weight, one size, one colour -------------------
CAP = 52.0           # cap height of the wordmark in the horizontal lockup
WEIGHT = 600         # Geist SemiBold
TRACKING = 0.10      # em; modest, so the eye reads one name rather than separate letters
GAP = 0.62           # symbol to wordmark, in cap heights


def lockup_geometry(compact: bool = False) -> dict:
    """Numbers for the horizontal lockup (symbol + 'SWARA AI'). Used for the SVG files and the React component."""
    sh, sw_ = (CSYM_H, CSYM_W) if compact else (SYM_H, SYM_W)
    sc = (CAP * (2.1 if compact else 2.3)) / sh
    sym_h, sym_w = sh * sc, sw_ * sc
    pad = 8.0
    a, aw = text_outline("SWARA", WEIGHT, CAP, TRACKING)
    b, bw = text_outline("AI", WEIGHT, CAP, TRACKING)
    tx = pad + sym_w + CAP * GAP
    base = pad + sym_h / 2 + CAP / 2                         # caps centred on the symbol
    word_gap = CAP * 0.46                                    # the space between SWARA and AI
    bx = tx + aw + word_gap
    return dict(pad=pad, scale=sc, sym_w=sym_w, sym_h=sym_h, swara=a, ai=b, tx=tx, base=base, ai_x=bx,
                width=bx + bw + pad, height=sym_h + 2 * pad)


def horizontal_svg(mode: str) -> str:
    text = MODES[mode][2]
    L = lockup_geometry()
    defs, g = _sym(mode)
    inner = (
        f'<g transform="translate({L["pad"]} {L["pad"]}) scale({L["scale"]:.4f})">{g}</g>'
        f'<path d="{L["swara"]}" fill="{text}" transform="translate({L["tx"]:.2f} {L["base"]:.2f})"/>'
        f'<path d="{L["ai"]}" fill="{text}" transform="translate({L["ai_x"]:.2f} {L["base"]:.2f})"/>'
    )
    return svg_wrap(L["width"], L["height"], inner, defs, "SWARA AI")


def app_icon_svg(bg: str, size: int = 1024, mark: str = "light", radius: float = 0.225, border: str = "") -> str:
    """Square icon: rounded square (light surface) + centred symbol."""
    s = (size * 0.58) / SYM_H
    w, h = SYM_W * s, SYM_H * s
    defs, g = _sym(mark) if mark in MODES else symbol_group(mark, "g", None)
    rx = size * radius
    edge = f' stroke="{border}" stroke-width="{size * 0.006:.1f}"' if border else ""
    inner = (f'<rect x="{size * 0.003:.1f}" y="{size * 0.003:.1f}" width="{size * 0.994:.1f}" height="{size * 0.994:.1f}" rx="{rx:.1f}" fill="{bg}"{edge}/>'
             f'<g transform="translate({(size - w) / 2:.2f} {(size - h) / 2:.2f}) scale({s:.4f})">{g}</g>')
    return svg_wrap(size, size, inner, defs, "SWARA AI")


def favicon_svg() -> str:
    """Tab icon: the compact S in gold on a transparent background (a gold that reads on a light tab strip)."""
    size = 64.0
    s = (size * 0.92) / CSYM_H
    w, h = CSYM_W * s, CSYM_H * s
    defs, g = symbol_group("", "f", ("#D9B66A", "#C39A48", "#A67B2C"), compact=True)
    inner = f'<g transform="translate({(size - w) / 2:.2f} {(size - h) / 2:.2f}) scale({s:.4f})">{g}</g>'
    return svg_wrap(size, size, inner, defs, "SWARA AI")


def social_card_svg() -> str:
    """1200x630 share image: ivory field, horizontal logo, tagline."""
    import re
    w, h = 1200, 630
    hz = horizontal_svg("light")
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', hz)
    lw, lh = float(m.group(1)), float(m.group(2))
    sc = 700 / lw
    body = hz[hz.index(">") + 1: hz.rindex("</svg>")]
    body = re.sub(r"<title>.*?</title>", "", body)
    defs_m = re.search(r"<defs>.*?</defs>", body)
    defs = defs_m.group(0) if defs_m else ""
    body = body.replace(defs, "")
    top = 190
    inner = (f'<rect width="{w}" height="{h}" fill="{IVORY}"/>'
             f'<g transform="translate({(w - lw * sc) / 2:.1f} {top}) scale({sc:.4f})">{body}</g>'
             f'<rect x="{w / 2 - 40}" y="{top + lh * sc + 44}" width="80" height="2" fill="{GOLD}"/>'
             f'<text x="{w / 2}" y="{top + lh * sc + 108}" text-anchor="middle" font-family="Geist, Inter, Segoe UI, Arial, sans-serif" font-size="38" font-weight="500" letter-spacing="1" fill="{INK}">Every Voice. Smarter Commerce.</text>'
             f'<text x="{w / 2}" y="{top + lh * sc + 160}" text-anchor="middle" font-family="Geist, Inter, Segoe UI, Arial, sans-serif" font-size="24" fill="#5F5B50">Multilingual voice ordering for Indian Kirana stores</text>')
    return svg_wrap(w, h, inner, defs, "SWARA AI. Every Voice. Smarter Commerce.")


FILES: dict[str, str] = {}


def build_svgs() -> None:
    for v in MODES:
        FILES[f"swara-logo-horizontal-{v}.svg"] = horizontal_svg(v)
        FILES[f"swara-symbol-{v}.svg"] = symbol_svg(v)
        FILES[f"swara-symbol-compact-{v}.svg"] = compact_symbol_svg(v)
    FILES["swara-app-icon.svg"] = app_icon_svg("#FFFFFF", mark="light", border="#E4DCC8")   # primary: gold S on white
    FILES["swara-app-icon-ivory.svg"] = app_icon_svg(IVORY, mark="light", border="#E4DCC8")  # gold S on Ivory
    FILES["swara-app-icon-gold.svg"] = app_icon_svg(GOLD, mark=INK)                          # Ink S on Champagne Gold
    FILES["swara-app-icon-mono.svg"] = app_icon_svg("#FFFFFF", mark=INK, border="#D9D9D9")
    FILES["swara-favicon.svg"] = favicon_svg()
    FILES["swara-social-card.svg"] = social_card_svg()


def write_svgs() -> None:
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    for name, svg in FILES.items():
        (SVG_DIR / name).write_text(svg, encoding="utf-8")


def render_pngs() -> None:
    """Transparent PNGs via headless Chromium (omit_background keeps alpha). App icons are opaque rounded squares by design."""
    import base64
    import re

    from playwright.sync_api import sync_playwright
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[str, str, int | None, int | None]] = []   # (svg, png name, width, height)
    for v in MODES:
        jobs.append((f"swara-logo-horizontal-{v}.svg", f"swara-logo-horizontal-{v}@2000w.png", 2000, None))
        jobs.append((f"swara-logo-horizontal-{v}.svg", f"swara-logo-horizontal-{v}@800w.png", 800, None))
        jobs.append((f"swara-symbol-{v}.svg", f"swara-symbol-{v}@1024h.png", None, 1024))
        jobs.append((f"swara-symbol-{v}.svg", f"swara-symbol-{v}@256h.png", None, 256))
    jobs.append(("swara-symbol-compact-light.svg", "swara-symbol-compact-light@256h.png", None, 256))
    for name in ("swara-app-icon", "swara-app-icon-ivory", "swara-app-icon-gold", "swara-app-icon-mono"):
        for px in (1024, 512, 192):
            jobs.append((f"{name}.svg", f"{name}@{px}.png", px, px))
    for px in (16, 32, 48, 64, 180):
        jobs.append(("swara-favicon.svg", f"swara-favicon@{px}.png", px, px))
    jobs.append(("swara-social-card.svg", "swara-social-card@1200x630.png", 1200, 630))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for svg_name, png_name, w, h in jobs:
            svg = (SVG_DIR / svg_name).read_text(encoding="utf-8")
            m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
            vw, vh = float(m.group(1)), float(m.group(2))
            if w is None:
                w = round(h * vw / vh)
            if h is None:
                h = round(w * vh / vw)
            html = (f'<html><body style="margin:0;background:transparent">'
                    f'<img src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}" '
                    f'style="display:block;width:{w}px;height:{h}px"></body></html>')
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.set_content(html)
            page.wait_for_timeout(60)
            page.screenshot(path=str(PNG_DIR / png_name), omit_background=True, clip={"x": 0, "y": 0, "width": w, "height": h})
            page.close()
        browser.close()


def write_web_assets() -> None:
    """Geometry for the React <Logo> component + the files the web app serves (favicon, touch icons, manifest)."""
    import json
    import shutil

    def geo(g: dict):
        return dict(w=round(g["w"], 2), h=round(g["h"], 2), x0=round(g["x0"], 2), y0=round(g["y0"], 2), paths=g["paths"])

    data = dict(SYMBOL=geo(FULL), SYMBOL_COMPACT=geo(SMALL),
                LOCKUP={k: (round(v, 3) if isinstance(v, float) else v) for k, v in lockup_geometry(False).items()},
                LOCKUP_COMPACT={k: (round(v, 3) if isinstance(v, float) else v) for k, v in lockup_geometry(True).items()})
    out = ROOT / "frontend/src/components/logoPaths.ts"
    body = "// GENERATED by scripts/brand/build_logo.py. Do not edit by hand; change the script and re-run it.\n"
    body += "// Geometry of the SWARA AI mark and wordmark (outlined, so no font is needed).\n\n"
    for k, v in data.items():
        body += f"export const {k} = {json.dumps(v, separators=(',', ':'))} as const\n\n"
    out.write_text(body, encoding="utf-8")

    pub = ROOT / "frontend/public"
    pub.mkdir(exist_ok=True)
    shutil.copy(SVG_DIR / "swara-favicon.svg", pub / "favicon.svg")
    shutil.copy(BRAND / "favicon.ico", pub / "favicon.ico")
    shutil.copy(PNG_DIR / "swara-app-icon@192.png", pub / "apple-touch-icon.png")      # opaque tile, as iOS wants
    shutil.copy(PNG_DIR / "swara-app-icon@192.png", pub / "icon-192.png")
    shutil.copy(PNG_DIR / "swara-app-icon@512.png", pub / "icon-512.png")
    shutil.copy(PNG_DIR / "swara-social-card@1200x630.png", pub / "social-card.png")
    (pub / "site.webmanifest").write_text(json.dumps({
        "name": "SWARA AI", "short_name": "SWARA AI",
        "description": "Your intelligent voice-powered assistant for smarter grocery commerce.",
        "start_url": "/", "display": "standalone", "background_color": "#FFFFFF", "theme_color": "#FFFFFF",
        "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}],
    }, indent=2) + "\n", encoding="utf-8")


def build_ico() -> None:
    from PIL import Image
    sizes = [16, 32, 48]
    imgs = [Image.open(PNG_DIR / f"swara-favicon@{s}.png").convert("RGBA") for s in sizes]
    imgs[-1].save(BRAND / "favicon.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])


if __name__ == "__main__":
    if not FONT.exists():
        sys.exit(f"Font not found: {FONT}\nRun `npm install` in frontend/ first.")
    build_svgs()
    write_svgs()
    if "--svg-only" not in sys.argv:
        render_pngs()
        build_ico()
        write_web_assets()
    print(f"symbol {SYM_W:.1f} x {SYM_H:.1f} units; wrote {len(FILES)} SVG files to {SVG_DIR}")
