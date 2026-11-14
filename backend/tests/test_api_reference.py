"""The API reference page (/docs).

FastAPI's own Swagger UI page needs a CDN and an inline script, so under SWARA AI's content-security-policy it showed a blank page. The page that
replaces it must work under that policy: one local script, no third-party host, no innerHTML, light only, and switchable off with API_DOCS=false.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

JS = Path(__file__).resolve().parents[1] / "app" / "static" / "api_reference.js"


def test_docs_page_is_served_and_names_the_product(make_app):
    with TestClient(make_app()) as c:
        r = c.get("/docs")
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "SWARA AI API reference" in r.text
        assert 'name="color-scheme" content="light"' in r.text


def test_page_uses_only_the_local_script_and_no_other_host(make_app):
    with TestClient(make_app()) as c:
        r = c.get("/docs")
        html = r.text
        assert re.findall(r"<script[^>]*>", html) == ['<script src="/api-reference.js">']
        assert "http://" not in html and "https://" not in html
        assert not re.search(r"<script[^>]*>[^<]+</script>", html), "no inline script: the content-security-policy forbids it"
        csp = r.headers["content-security-policy"]
        assert "script-src 'self'" in csp and "cdn" not in csp


def test_script_is_served_javascript_without_innerhtml_or_eval(make_app):
    with TestClient(make_app()) as c:
        r = c.get("/api-reference.js")
        assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    src = JS.read_text(encoding="utf-8")
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "http://", "https://"):
        assert bad not in src, bad


def test_redoc_goes_to_the_same_page(make_app):
    with TestClient(make_app()) as c:
        r = c.get("/redoc", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "/docs"


def test_openapi_schema_is_served_and_matches_the_committed_copy(make_app):
    import json
    with TestClient(make_app()) as c:
        live = c.get("/openapi.json").json()
    saved = json.loads((Path(__file__).resolve().parents[2] / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert live["info"]["version"] == saved["info"]["version"]
    assert set(live["paths"]) == set(saved["paths"]), "docs/openapi.json is out of date: regenerate it"


def test_api_docs_false_switches_everything_off(make_app):
    with TestClient(make_app(api_docs=False)) as c:
        assert c.get("/openapi.json").status_code == 404
        assert c.get("/api-reference.js").status_code == 404
        assert "API reference" not in c.get("/docs").text
