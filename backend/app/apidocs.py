"""The API reference page at /docs.

FastAPI's built-in /docs and /redoc pages load Swagger UI and ReDoc from a public CDN and run an inline script. SWARA AI's content-security-policy
(no inline script, no third-party script) refuses both, so those pages render blank, and a page that quietly calls a third-party host would also
contradict the product's own "no third-party requests" statements. This page draws the same /openapi.json with one small local script instead.
Set API_DOCS=false to switch the page and /openapi.json off.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from . import brand

STATIC = Path(__file__).resolve().parent / "static"

PAGE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{brand.NAME} API reference</title><meta name="color-scheme" content="light"><meta name="robots" content="noindex">
<style>
:root{{color-scheme:light}} *{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:#242424;font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:960px;margin:0 auto;padding:28px 20px 60px}} h1{{font-size:28px;margin:0 0 4px}} h2{{font-size:18px;margin:28px 0 8px;text-transform:capitalize;border-bottom:1px solid #eae7df;padding-bottom:6px}}
h4{{margin:14px 0 4px;font-size:13px;color:#686868}} .muted{{color:#686868}} a{{color:#7a5810}}
.note{{background:#f7f5ef;border:1px solid #eae7df;border-radius:10px;padding:10px 14px;color:#242424}}
.tools{{display:flex;gap:14px;align-items:center;margin:16px 0;flex-wrap:wrap}} input[type=search]{{flex:1;min-width:220px;padding:9px 12px;border:1px solid #d9d4c6;border-radius:9px;font:inherit}}
input:focus-visible,summary:focus-visible,a:focus-visible{{outline:2px solid #8a6414;outline-offset:2px}}
details.op{{border:1px solid #eae7df;border-radius:10px;margin:6px 0;background:#fff}} summary{{cursor:pointer;padding:9px 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.verb{{min-width:62px;text-align:center;font-weight:700;font-size:12px;border-radius:6px;padding:2px 8px;background:#f7f5ef;color:#242424;border:1px solid #d9d4c6}}
.m-get .verb{{background:#eef6ee;color:#1d5a2a}} .m-post .verb{{background:#fbf3df;color:#7a5810}} .m-put .verb,.m-patch .verb{{background:#eaf1fb;color:#1f4f8a}} .m-delete .verb{{background:#fbecec;color:#9a1c1c}}
.path{{font:13px ui-monospace,Menlo,Consolas,monospace}} .sum{{color:#686868}} .body{{padding:2px 14px 12px}} .desc{{margin:8px 0;white-space:pre-wrap}}
.tbl{{border-collapse:collapse;width:100%;font-size:13px}} .tbl th,.tbl td{{border:1px solid #eae7df;padding:5px 8px;text-align:left;vertical-align:top}} .tbl th{{background:#f7f5ef}}
</style></head>
<body><main id="app" aria-busy="true">Loading the API description…</main><script src="/api-reference.js"></script></body></html>
"""

router = APIRouter(include_in_schema=False)


@router.get("/docs")
def docs() -> HTMLResponse:
    return HTMLResponse(PAGE)


@router.get("/redoc")
def redoc() -> RedirectResponse:
    return RedirectResponse("/docs", status_code=307)


@router.get("/api-reference.js")
def script() -> FileResponse:
    return FileResponse(STATIC / "api_reference.js", media_type="text/javascript")
