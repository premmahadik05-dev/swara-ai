"""Render brand/preview.png (contact sheet of the generated logo assets, on the light surfaces the product uses).

Run from the repository root after scripts/brand/build_logo.py:
    python scripts/brand/render_preview.py
"""
import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

S = Path("brand/svg")


def img(name, h=None, w=None):
    b = base64.b64encode((S / name).read_bytes()).decode()
    st = (f"height:{h}px;" if h else "") + (f"width:{w}px;" if w else "")
    return f'<img src="data:image/svg+xml;base64,{b}" style="{st}display:block">'


html = f'''<html><body style="margin:0;font-family:sans-serif;color:#242424">
<div style="width:1400px;background:#F7F5EF">
 <div style="padding:56px 64px 40px;display:flex;align-items:center;justify-content:center;background:#FFFFFF">{img('swara-logo-horizontal-light.svg', w=760)}</div>
 <div style="display:grid;grid-template-columns:1fr 1fr;gap:0">
  <div style="padding:36px 64px;display:flex;gap:44px;align-items:center;background:#F7F5EF;border-top:1px solid #E4DCC8">
    {img('swara-logo-horizontal-light.svg', w=300)}{img('swara-logo-horizontal-light.svg', w=180)}</div>
  <div style="padding:36px 64px;display:flex;gap:30px;align-items:flex-end;background:#F7F5EF;border-top:1px solid #E4DCC8">
    {img('swara-symbol-light.svg', h=150)}{img('swara-symbol-light.svg', h=64)}{img('swara-symbol-compact-light.svg', h=64)}{img('swara-symbol-compact-light.svg', h=36)}{img('swara-symbol-compact-light.svg', h=24)}
    {img('swara-favicon.svg', h=32)}{img('swara-favicon.svg', h=16)}</div>
  <div style="padding:30px 64px;display:flex;gap:24px;align-items:center;background:#FFFFFF;border-top:1px solid #E4DCC8">
    {img('swara-app-icon.svg', h=96)}{img('swara-app-icon-ivory.svg', h=96)}{img('swara-app-icon-gold.svg', h=96)}{img('swara-app-icon-mono.svg', h=96)}</div>
  <div style="padding:30px 64px;display:flex;gap:40px;align-items:center;background:#FFFFFF;border-top:1px solid #E4DCC8">
    {img('swara-logo-horizontal-mono.svg', w=250)}{img('swara-symbol-mono.svg', h=84)}</div>
 </div>
 <div style="display:flex;font:13px/1.35 sans-serif">
   <div style="flex:1;background:#F7F5EF;color:#242424;padding:18px 24px;border:1px solid #E4DCC8"><b>Ink</b><br>#242424 (wordmark, text)</div>
   <div style="flex:1;background:#D6B574;padding:18px 24px"><b>Champagne Gold</b><br>#D6B574 (mark, gradient)</div>
   <div style="flex:1;background:#F7F5EF;padding:18px 24px;border:1px solid #E4DCC8"><b>Ivory</b><br>#F7F5EF (surface)</div>
 </div>
</div></body></html>'''
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 400})
    pg.set_content(html)
    pg.wait_for_timeout(200)
    pg.screenshot(path="brand/preview.png", full_page=True)
    b.close()
