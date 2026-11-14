"""Stock movement report, order-status mix and the stored evaluation summary behind the AI performance page."""
from __future__ import annotations

import json

from app.routers import evaluation as evaluation_router


def _place(client, text="2 kilo chawal"):
    r = client.post("/api/text/turn", json={"text": text}).json()
    sid = r["session_id"]
    client.post("/api/text/turn", json={"text": "bas itna hi", "session_id": sid})
    return client.post("/api/text/turn", json={"text": "haan", "session_id": sid}).json()["order"]


def test_stock_movement_is_empty_and_honest_on_a_fresh_shop(client):
    d = client.get("/api/analytics/stock-movement").json()
    assert d["movements"] == 0 and d["rows"] == [] and d["products_moved"] == 0
    assert len(d["series"]) == 30 and all(s["in_paise"] == 0 and s["out_paise"] == 0 for s in d["series"])
    assert "demo orders never touched the shelf" in d["method"]


def test_stock_movement_follows_sales_restocks_and_cancellations(client):
    order = _place(client)
    pid = order["items"][0]["product_id"]
    qty = order["items"][0]["qty"]
    client.post(f"/api/products/{pid}/restock", json={"qty": 5})
    d = client.get("/api/analytics/stock-movement").json()
    row = next(r for r in d["rows"] if r["product_id"] == pid)
    assert row["sold"] == qty and row["added"] == 5 and row["returned"] == 0
    # opening + added + returned - sold - written_off == current, by construction of the report
    assert abs(row["opening"] + row["added"] + row["returned"] - row["sold"] - row["written_off"] - row["current"]) < 1e-6
    stock_now = next(i for i in client.get("/api/inventory", params={"page_size": 100, "q": row["name"]}).json()["items"] if i["id"] == pid)["stock"]
    assert abs(row["current"] - float(stock_now)) < 1e-6
    assert d["totals"]["out_paise"] > 0 and d["totals"]["in_paise"] > 0
    assert d["totals"]["out_paise"] == sum(s["out_paise"] for s in d["series"])
    # cancelling puts the stock back, and the ledger shows it as returned (not as a restock)
    assert client.post(f"/api/orders/{order['id']}/status", json={"status": "cancelled"}).status_code == 200
    d2 = client.get("/api/analytics/stock-movement").json()
    row2 = next(r for r in d2["rows"] if r["product_id"] == pid)
    assert row2["returned"] == qty and row2["sold"] == qty and row2["added"] == 5


def test_stock_movement_window_is_clamped_and_needs_sign_in(client, anon):
    assert len(client.get("/api/analytics/stock-movement", params={"days": 5000}).json()["series"]) == 365
    assert len(client.get("/api/analytics/stock-movement", params={"days": 0}).json()["series"]) == 1
    assert anon.get("/api/analytics/stock-movement").status_code == 401


def test_overview_reports_the_order_status_mix(client):
    ov = client.get("/api/analytics/overview", params={"days": 30}).json()
    mix = {r["status"]: r["orders"] for r in ov["orders_by_status"]}
    assert list(mix) == ["confirmed", "fulfilled", "cancelled"]   # all three, even when one is zero, so the chart is complete
    assert sum(mix.values()) == ov["kpis"]["orders"] + ov["kpis"]["cancelled"]


def test_evaluation_route_serves_the_stored_summary(client, anon, monkeypatch, tmp_path):
    f = tmp_path / "evaluation_summary.json"
    f.write_text(json.dumps({"schema": 1, "languages": ["en"]}), encoding="utf-8")
    monkeypatch.setattr(evaluation_router, "SUMMARY_PATH", f)
    d = client.get("/api/evaluation").json()
    assert d["available"] is True and d["summary"]["languages"] == ["en"] and d["file_modified"]
    assert anon.get("/api/evaluation").status_code == 401


def test_evaluation_route_says_how_to_create_a_missing_or_broken_file(client, monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation_router, "SUMMARY_PATH", tmp_path / "nope.json")
    d = client.get("/api/evaluation").json()
    assert d == {"available": False, "summary": None, "how_to_create": "python scripts/build_evaluation_summary.py"}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(evaluation_router, "SUMMARY_PATH", bad)
    assert client.get("/api/evaluation").json()["available"] is False


def test_the_shipped_summary_is_valid_and_carries_its_caveats(client):
    d = client.get("/api/evaluation").json()
    assert d["available"] is True
    s = d["summary"]
    for key in ("schema", "scope", "languages", "branded", "noise", "end_to_end", "parser_latency", "limitations"):
        assert key in s
    assert s["limitations"], "the caveats must travel with the numbers"


def test_evaluation_route_adds_the_test_record_and_http_timings_only_when_their_files_exist(client, monkeypatch, tmp_path):
    f = tmp_path / "evaluation_summary.json"
    f.write_text(json.dumps({"app_version": "x", "limitations": []}), encoding="utf-8")
    monkeypatch.setattr(evaluation_router, "SUMMARY_PATH", f)
    monkeypatch.setattr(evaluation_router, "VERIFICATION_PATH", tmp_path / "none.json")
    monkeypatch.setattr(evaluation_router, "API_LATENCY_PATH", tmp_path / "none2.json")
    d = client.get("/api/evaluation").json()
    assert d["available"] is True and d["verification"] is None and d["api_latency"] is None
    v, a = tmp_path / "v.json", tmp_path / "a.json"
    v.write_text(json.dumps({"generated_at": "t", "rows": [{"category": "c", "status": "Passed"}]}), encoding="utf-8")
    a.write_text("{not json", encoding="utf-8")   # unreadable side file -> absent, not an error
    monkeypatch.setattr(evaluation_router, "VERIFICATION_PATH", v)
    monkeypatch.setattr(evaluation_router, "API_LATENCY_PATH", a)
    d = client.get("/api/evaluation").json()
    assert d["verification"]["rows"][0]["category"] == "c" and d["api_latency"] is None


def test_verification_rows_are_counted_from_logs_and_a_missing_log_is_not_run(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("bvs", Path(__file__).resolve().parents[2] / "scripts" / "build_verification_summary.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "LOGS", tmp_path)
    xml = (
        '<testsuites><testsuite>'
        '<testcase classname="backend.tests.test_auth" name="a"/>'
        '<testcase classname="backend.tests.test_auth" name="b"><failure message="x"/></testcase>'
        '<testcase classname="backend.tests.test_security" name="c"><skipped/></testcase>'
        '<testcase classname="backend.tests.test_brand_new_file" name="d"/>'
        '</testsuite></testsuites>'
    )
    (tmp_path / "backend_pytest.xml").write_text(xml, encoding="utf-8")
    rows = {r["category"]: r for r in mod.backend_rows()}
    acct = rows["Accounts, sessions and security"]
    assert (acct["total"], acct["passed"], acct["failed"], acct["skipped"], acct["status"]) == (3, 1, 1, 1, "Failed")
    assert rows["Other backend tests"]["total"] == 1                       # an unlisted test file is still counted
    assert rows["Gnani client (mocked HTTP, not live)"]["total"] == 0
    assert mod.vitest_row()["status"] == "Not run" and mod.build_row()["status"] == "Not run"   # no logs in the temporary folder
    (tmp_path / "frontend_vitest.txt").write_text("      Tests  2 failed | 5 passed | 1 skipped (8)\n", encoding="utf-8")
    v = mod.vitest_row()
    assert (v["total"], v["passed"], v["failed"], v["skipped"]) == (8, 5, 2, 1) and v["status"] == "Failed"
    assert mod.live_row()["status"] in ("Not run", "Recorded") and mod.windows_row()["status"] == "Not run"
