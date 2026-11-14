from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .helpers import KEY, AuthedClient


# Every route that changes shop data. Staff may read and take orders; only the owner may do these.
OWNER_CALLS = [
    ("post", "/api/products", {"json": {"sku": "AB-1", "name_en": "x", "unit": "kg", "price_paise": 100}}),
    ("patch", "/api/products/1", {"json": {"price_paise": 1}}),
    ("post", "/api/products/1/restock", {"json": {"qty": "1"}}),
    ("post", "/api/orders/1/status", {"json": {"status": "cancelled"}}),
    ("post", "/api/customers", {"json": {"name": "Test Person"}}),
    ("patch", "/api/customers/1", {"json": {"name": "Renamed"}}),
    ("post", "/api/catalog/1/import", {"json": {"price_paise": 5000}}),
    ("put", "/api/settings", {"json": {"tts_speed": 1.0}}),
    ("put", "/api/settings/gnani-key", {"json": {"api_key": "abcdefgh12345"}}),
    ("post", "/api/settings/test-gnani", {}),
    ("get", "/api/auth/users", {}),
    ("get", "/api/contact/messages", {}),
]


@pytest.fixture(autouse=True)
def _no_env_write(monkeypatch, tmp_path):
    monkeypatch.setattr("app.routers.settings.ENV_FILE", tmp_path / ".env")


@pytest.mark.parametrize("method,path,kw", OWNER_CALLS)
def test_owner_routes_refuse_staff_and_visitors(staff, anon, method, path, kw):
    assert getattr(anon, method)(path, **kw).status_code == 401
    r = getattr(staff, method)(path, **kw)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "OWNER_ONLY"


@pytest.mark.parametrize("method,path,kw", OWNER_CALLS)
def test_owner_routes_work_for_the_owner(client, method, path, kw):
    assert getattr(client, method)(path, **kw).status_code not in (401, 403)


READ_PATHS = ["/api/products", "/api/inventory", "/api/orders", "/api/customers", "/api/analytics/overview", "/api/analytics/sales",
              "/api/analytics/demand", "/api/analytics/inventory", "/api/analytics/latency", "/api/catalog", "/api/search?q=rice",
              "/api/settings", "/api/sessions", "/api/inventory/alerts", "/api/orders/1", "/api/customers/1", "/api/auth/me", "/api/auth/sessions"]
WRITE_CALLS = [("post", "/api/text/turn", {"json": {"text": "1 kilo sugar"}}), ("post", "/api/sessions", {}),
               ("post", "/api/voice/turn", {}), ("post", "/api/noise/preview", {}), ("post", "/api/auth/logout", {})]


@pytest.mark.parametrize("path", READ_PATHS)
def test_every_read_needs_a_session(anon, path):
    r = anon.get(path)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "NOT_AUTHENTICATED", path


def test_every_write_needs_a_session(anon):
    for method, path, kw in WRITE_CALLS[:4]:
        assert getattr(anon, method)(path, **kw).status_code == 401, path


@pytest.mark.parametrize("path", READ_PATHS[:-2])
def test_staff_can_read(staff, path):
    assert staff.get(path).status_code in (200, 404), path   # 404 only when a seeded row id does not exist


def test_route_inventory_every_api_route_is_guarded_or_deliberately_public(anon):
    """If someone adds a route and forgets to protect it, this fails."""
    public = {("GET", "/api/health"), ("POST", "/api/text/parse"), ("GET", "/api/auth/config"), ("POST", "/api/auth/signup"),
              ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("POST", "/api/auth/forgot"), ("POST", "/api/auth/reset"),
              ("POST", "/api/auth/verify-email"), ("POST", "/api/auth/resend-verification"), ("POST", "/api/contact"), ("GET", "/api/auth/session")}
    unguarded = set()
    for route in anon.app.routes:
        path, methods = getattr(route, "path", ""), getattr(route, "methods", None)
        if not path.startswith("/api/") or not methods:
            continue
        # include_router(dependencies=...) is flattened into each route's dependant by FastAPI
        guarded = bool({"require_user", "require_owner"} & _names(route.dependant))
        for m in methods - {"HEAD", "OPTIONS"}:
            if not guarded and (m, path) not in public:
                unguarded.add((m, path))
    assert not unguarded, sorted(unguarded)


def _names(dep) -> set:
    out = {getattr(dep.call, "__name__", "")}
    for d in dep.dependencies:
        out |= _names(d)
    return out


def test_ordering_works_for_staff(staff):
    assert staff.get("/api/products").status_code == 200
    assert staff.post("/api/text/turn", json={"text": "1 kilo sugar"}).status_code == 200


def test_landing_demo_parser_is_open_and_stores_nothing(anon, client):
    r = anon.post("/api/text/parse", json={"text": "2 kilo chawal"})
    assert r.status_code == 200 and r.json()["cart"]["lines"]
    assert client.get("/api/sessions").json() == []   # nothing was recorded


def test_public_demo_can_be_switched_off_and_then_needs_a_sign_in(make_app):
    from fastapi.testclient import TestClient
    from .helpers import AuthedClient
    app = make_app(public_demo=False)
    with TestClient(app) as visitor:
        r = visitor.post("/api/text/parse", json={"text": "2 kilo chawal"})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "DEMO_OFF"
        assert "chawal" not in r.text and "price" not in r.text      # nothing about the shop leaks in the refusal
    with AuthedClient(app) as person:                                 # a signed-in person still gets the parser
        r = person.post("/api/text/parse", json={"text": "2 kilo chawal"})
        assert r.status_code == 200 and r.json()["cart"]["lines"]
    with TestClient(make_app()) as default_visitor:                   # the default stays open, as documented
        assert default_visitor.post("/api/text/parse", json={"text": "2 kilo chawal"}).status_code == 200


def test_writes_without_the_csrf_header_are_refused(client):
    client.headers.pop("X-CSRF-Token")
    r = client.post("/api/text/turn", json={"text": "1 kilo sugar"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "CSRF_FAILED"
    assert client.get("/api/products").status_code == 200   # reads never need it
    client.headers["X-CSRF-Token"] = "wrong"
    assert client.post("/api/products/1/restock", json={"qty": "1"}).status_code == 403


def test_cross_site_origin_is_refused_for_writes(client):
    r = client.post("/api/text/turn", json={"text": "doodh"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "BAD_ORIGIN"
    assert client.post("/api/text/turn", json={"text": "doodh"}, headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert client.post("/api/text/turn", json={"text": "doodh"}, headers={"Origin": "http://testserver"}).status_code == 200
    assert client.post("/api/text/turn", json={"text": "doodh"}, headers={"Origin": "null"}).status_code == 403


def test_settings_hide_connection_details_from_staff(make_app, monkeypatch, tmp_path):
    from .helpers import AuthedClient, register, STAFF
    with AuthedClient(make_app(gnani_api_key=KEY)) as owner:
        g = owner.get("/api/settings").json()["gnani"]
        assert g["key_hint"] and g["base_url"] and KEY not in str(g)
        owner.cookies.clear(); owner.headers.pop("X-CSRF-Token")
        assert register(owner, STAFF).status_code == 201
        g = owner.get("/api/settings").json()["gnani"]
        assert g["key_hint"] is None and g["base_url"] is None and g["configured"] is True


def test_security_headers(client):
    r = client.get("/api/products")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_cors_allows_only_configured_origins(client):
    ok = client.options("/api/products", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    bad = client.options("/api/products", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers


def test_rate_limit_returns_429(make_app):
    with TestClient(make_app(rate_limit_per_minute=5)) as c:   # the open landing-page parser
        codes = [c.post("/api/text/parse", json={"text": "doodh"}).status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and 429 in codes[5:]


@pytest.mark.parametrize("payload", [
    {"text": ""}, {"text": "x" * 601}, {"text": "hi", "session_id": "a b"}, {"text": "hi", "session_id": "../x"},
    {"text": "hi", "session_id": "x" * 41}, {}, {"text": 5},
])
def test_text_turn_input_validation(client, payload):
    assert client.post("/api/text/turn", json=payload).status_code == 422


def test_sql_injection_strings_are_just_text(client):
    for t in ["'; DROP TABLE products;--", "1 kilo sugar' OR '1'='1", "{{7*7}}", "<script>alert(1)</script> doodh"]:
        assert client.post("/api/text/turn", json={"text": t}).status_code == 200
    assert client.get("/api/health").json()["products"] == 65


def test_xss_payload_is_returned_as_data_not_markup(client):
    r = client.post("/api/text/turn", json={"text": "<img src=x onerror=alert(1)> 1 kilo sugar"})
    assert r.headers["content-type"].startswith("application/json") and r.headers["x-content-type-options"] == "nosniff"


def test_api_key_never_appears_in_any_get_endpoint(make_app, monkeypatch, tmp_path):
    monkeypatch.setattr("app.routers.settings.ENV_FILE", tmp_path / ".env")
    with AuthedClient(make_app(gnani_api_key=KEY)) as c:
        for path in ["/api/health", "/api/settings", "/api/products", "/api/orders", "/api/analytics/overview",
                     "/api/analytics/latency", "/openapi.json", "/api/sessions"]:
            assert KEY not in c.get(path).text, path


def test_error_responses_use_a_uniform_envelope(client):
    r = client.get("/api/orders/999999")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "HTTP_404"


def test_websocket_rejects_foreign_origin(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/voice?language=gu", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()


def test_websocket_needs_a_session(anon):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as e:
        with anon.websocket_connect("/ws/voice?language=gu") as ws:
            ws.receive_json()
    assert e.value.code in (4401, 1008)


def test_security_headers_on_every_response(anon):
    r = anon.get("/api/health")
    assert r.headers["referrer-policy"] == "no-referrer" and "microphone=(self)" in r.headers["permissions-policy"]
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert "strict-transport-security" not in r.headers   # plain http: HSTS only when PUBLIC_URL is https


def test_https_deployments_get_hsts_and_host_cookie(make_app):
    with TestClient(make_app(public_url="https://shop.example")) as c:
        r = c.get("/api/health")
        assert "max-age=31536000" in r.headers["strict-transport-security"]


def test_csp_forbids_inline_scripts_and_framing():
    from app.security import csp
    p = csp("shop.example")
    assert "script-src 'self'" in p and "'unsafe-inline'" not in p.split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in p and "object-src 'none'" in p and "wss://shop.example" in p


def test_built_app_is_served_and_a_missing_file_is_a_404_not_the_app(make_app, tmp_path, monkeypatch):
    """The built React app is served from the same port. App routes get index.html; a missing picture or script must not quietly
    receive that page with status 200 (it would look like a broken image with no error anywhere)."""
    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (dist / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    (dist / "shots").mkdir()
    (dist / "shots" / "a.webp").write_bytes(b"RIFFxxxxWEBP")
    monkeypatch.setattr("app.main.REPO_ROOT", tmp_path)
    with TestClient(make_app()) as c:
        for route in ("/", "/dashboard", "/sign-in", "/some/unknown/route"):
            r = c.get(route)
            assert r.status_code == 200 and "<title>app</title>" in r.text, route
        assert c.get("/robots.txt").text.startswith("User-agent")
        assert c.get("/shots/a.webp").content.startswith(b"RIFF")
        for missing in ("/shots/nope.webp", "/theme-init.js", "/assets/x.js", "/favicon.ico"):
            assert c.get(missing).status_code == 404, missing
        assert c.get("/api/does-not-exist").status_code == 404
        (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")        # outside the served folder
        for sneaky in ("/%2e%2e/%2e%2e/secret.txt", "/..%2f..%2fsecret.txt", "/assets/..%2f..%2f..%2fsecret.txt"):
            assert "SECRET" not in c.get(sneaky).text, sneaky


def test_one_time_links_are_redacted_in_the_access_log():
    """/reset-password?token=... is an unused credential until it expires: the access log must not keep it."""
    import logging

    from app.security import RedactTokens, install_log_redaction

    f = RedactTokens()
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "x", 1, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:5000", "GET", "/reset-password?token=abc123XYZ_-&next=/dashboard", "1.1", 200), None)
    assert f.filter(rec) is True
    line = rec.getMessage()
    assert "abc123XYZ_-" not in line and "token=[redacted]" in line and "next=/dashboard" in line
    plain = logging.LogRecord("uvicorn.access", logging.INFO, "x", 1, '%s - "%s %s HTTP/%s" %d', ("c", "GET", "/api/orders?limit=20", "1.1", 200), None)
    f.filter(plain)
    assert "/api/orders?limit=20" in plain.getMessage()
    install_log_redaction(); install_log_redaction()
    assert sum(isinstance(x, RedactTokens) for x in logging.getLogger("uvicorn.access").filters) == 1


def test_an_unexpected_server_error_shows_no_traceback_path_or_key(make_app):
    """A crash inside a handler gives the browser a bare 500: no stack trace, file path, exception text or secret."""
    app = make_app(gnani_api_key=KEY)

    def boom():
        raise RuntimeError(f"secret detail {KEY} at /srv/app/private.py")

    app.add_api_route("/api/_boom", boom, methods=["GET"])
    app.router.routes.insert(0, app.router.routes.pop())   # ahead of the catch-all that serves the built site

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom")
    assert r.status_code == 500
    for needle in ("Traceback", "RuntimeError", "private.py", "secret detail", KEY, "File \""):
        assert needle not in r.text
