"""
Offline smoke tests - no network, no credentials, no trades.
Run:  python -m pytest -q
They protect the parts a new contributor is most likely to break:
the suite registry, command building, real-money guards, dashboard access control.
"""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard import suites as S  # noqa: E402

LOCAL = {"Host": "localhost"}
DEFAULTS = {"follower_count": 100}


@pytest.fixture()
def client():
    from dashboard.app import app
    app.config["TESTING"] = True
    return app.test_client()


# ---------------------------------------------------------------- registry
def test_registry_is_consistent():
    keys = [s["key"] for s in S.SUITES]
    assert len(keys) == len(set(keys)), "duplicate suite keys"
    for s in S.SUITES:
        assert s["risk"] in ("safe", "real", "destructive"), s["key"]
        assert set(s["flags"]) <= {"start", "end", "instance", "lot", "orders_count", "burst", "ramp", "profile", "only"}, s["key"]
        if s["script"]:
            assert (ROOT / s["script"]).exists(), f"{s['key']}: missing {s['script']}"


def test_every_runner_accepts_the_flags_the_registry_passes():
    """Catches a registry flag that the runner's argparse would reject."""
    flag_map = {"start": "--start", "end": "--end", "instance": "--instance", "lot": "--lot",
                "orders_count": "--orders-count", "burst": "--burst", "ramp": "--ramp", "profile": "--profile", "only": "--only"}
    for s in S.SUITES:
        if not s["script"]:
            continue
        text = (ROOT / s["script"]).read_text(encoding="utf-8")
        for f in s["flags"]:
            assert f'"{flag_map[f]}"' in text, f"{s['key']}: {s['script']} has no {flag_map[f]}"


@pytest.mark.parametrize("name", sorted(p.stem for p in (ROOT / "test_suite").glob("*.py") if p.stem != "__init__"))
def test_runner_modules_import(name):
    importlib.import_module(f"test_suite.{name}")


# ---------------------------------------------------------------- command building
def test_build_command_basic_and_clamped():
    s = S.SUITE_INDEX["race"]
    cmd = S.build_command(s, {"start": 5, "end": 2, "instance": "real"}, DEFAULTS)   # swapped on purpose
    assert cmd[cmd.index("--start") + 1] == "2" and cmd[cmd.index("--end") + 1] == "5"
    assert cmd[cmd.index("--instance") + 1] == "real"


def test_build_command_rejects_injection_and_junk():
    s = S.SUITE_INDEX["breakpoint"]
    cmd = S.build_command(s, {"start": "1; rm -rf /", "end": "x", "ramp": "10,abc,$(id)", "instance": "../../etc"}, DEFAULTS)
    assert all(";" not in c and "$" not in c for c in cmd)
    assert cmd[cmd.index("--instance") + 1] == "paper"


def test_e2e_only_flag_is_validated():
    s = S.SUITE_INDEX["e2e"]
    cmd = S.build_command(s, {"only": "e06, E07,E08;rm -rf /,X1,$(id)"}, DEFAULTS)
    assert cmd[cmd.index("--only") + 1] == "E06,E07"            # junk chunks are dropped, never passed through
    assert "--only" not in S.build_command(s, {"only": "junk"}, DEFAULTS)
    assert "--only" not in S.build_command(s, {}, DEFAULTS)


def test_e2e_steps_are_well_formed():
    from test_suite.e2e_runner import STEPS
    ids = [sid for sid, *_ in STEPS]
    assert ids == [f"E{i:02d}" for i in range(1, len(ids) + 1)]
    assert STEPS[-1][0] == "E16" and STEPS[-1][3] is True        # final audit always runs


def test_symbol_pnl_rules():
    from test_suite import symbol_coverage_runner as SC
    row = {"side": "BUY", "qty": 2, "entry_price": 3872.22, "exit_price": 3872.0, "realized_pnl": -44.0}
    gold = {"csize": 100.0, "ckind": "type1", "converted": False}
    assert abs(SC.expected_pnl(row, gold) - (-44.0)) < 1e-6                 # XAUUSD: 100 oz per lot
    assert SC.expected_pnl(row, {"csize": 1000.0, "ckind": "type2", "converted": True}) is None
    ok = [("m", {"side": "BUY", "qty": 2, "entry_price": 1.0, "exit_price": 0.9, "realized_pnl": -1.0}),
          ("f", {"side": "BUY", "qty": 4, "entry_price": 1.0, "exit_price": 0.9, "realized_pnl": -2.0})]
    assert SC.converted_pnl_issues(ok) == []
    bad = ok + [("g", {"side": "BUY", "qty": 2, "entry_price": 1.0, "exit_price": 0.9, "realized_pnl": +1.0})]
    assert SC.converted_pnl_issues(bad)                                       # wrong sign and wrong per-unit PnL


def test_symbol_order_qty_is_two_steps():
    from test_suite.symbol_coverage_runner import order_qty
    assert order_qty({"step": 0.01, "min_qty": 0.01, "lot": 1}) == 0.02
    assert order_qty({"step": 20, "min_qty": 20, "lot": 20}) == 40
    assert order_qty({"step": 0.1, "min_qty": 1, "lot": 1}) == 2          # US30cash-1: 0.5x copy must stay >= min


def test_e2e_report_endpoint_without_evidence(client, tmp_path, monkeypatch):
    import dashboard.app as a
    monkeypatch.setattr(a, "EVIDENCE_DIR", tmp_path)
    d = client.get("/api/e2e/latest", headers=LOCAL).get_json()
    assert d["report"] is None and d["runs"] == []
    (tmp_path / "e2e_evidence_20260101_000000.json").write_text('{"verdict": "PASS", "results": []}', encoding="utf-8")
    d = client.get("/api/e2e/latest", headers=LOCAL).get_json()
    assert d["report"]["verdict"] == "PASS" and d["file"] == "e2e_evidence_20260101_000000.json"
    assert client.get("/api/e2e/latest?file=../../.env", headers=LOCAL).status_code == 400


def test_market_open_schedule():
    from datetime import datetime
    from dashboard.app import market_open
    india = {"days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "session_start": "03:45", "session_end": "10:00"}
    assert market_open(india, datetime(2026, 11, 12, 5, 0)) and not market_open(india, datetime(2026, 11, 12, 17, 0))
    assert not market_open(india, datetime(2026, 11, 14, 5, 0))                       # Saturday
    fx = {"days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "session_start": "21:05", "session_end": "21:00"}
    assert market_open(fx, datetime(2026, 11, 12, 17, 0))                             # overnight session, mid-day
    assert not market_open(fx, datetime(2026, 11, 12, 21, 2))                         # daily break
    assert market_open({"days": ["Saturday"], "session_start": None, "session_end": None}, datetime(2026, 11, 14, 3, 0))


@pytest.mark.parametrize("payload", [{"qty": 0}, {"qty": 1, "type": "BOGUS"}, {"qty": 1, "type": "LIMIT"}, {"qty": 1, "side": "HOLD"}])
def test_dispatch_validates_before_touching_the_platform(client, payload):
    assert client.post("/api/order/dispatch_and_verify", json=payload, headers=LOCAL).status_code == 400


def test_dispatch_on_real_needs_confirmation(client):
    r = client.post("/api/order/dispatch_and_verify", json={"qty": 1, "instance": "real"}, headers=LOCAL)
    assert r.status_code == 412 and r.get_json()["needs_confirmation"]
    assert client.post("/api/order/close_master", json={"instance": "real"}, headers=LOCAL).status_code == 412


def test_regression_guards(client, monkeypatch):
    import dashboard.app as a
    launched = []
    monkeypatch.setattr(a, "_launch", lambda *args, **kw: (launched.append(args) or ({"error": "test"}, 500)))  # never start a suite
    assert client.post("/api/regression/start", json={"suites": ["real_money"]}, headers=LOCAL).status_code == 400
    assert client.post("/api/regression/start", json={"suites": ["teardown"]}, headers=LOCAL).status_code == 400
    assert client.post("/api/regression/start", json={"suites": []}, headers=LOCAL).status_code == 400
    assert client.post("/api/regression/start", json={}, headers=LOCAL).status_code == 400             # no list, no preset
    assert launched == []
    assert client.get("/api/regression/..%2F..%2Fsecret/report", headers=LOCAL).status_code in (400, 404)
    d = client.get("/api/regression", headers=LOCAL).get_json()
    assert set(d["presets"]) == {"smoke", "standard", "full"}
    assert all(k in {s["key"] for s in d["suites"]} for k in d["presets"]["full"])     # presets only use offered safe suites


def test_fixed_instance_cannot_be_overridden():
    assert S.effective_instance(S.SUITE_INDEX["paper_2x"], {"instance": "real"}) == "paper"
    assert S.effective_instance(S.SUITE_INDEX["real_money"], {"instance": "paper"}) == "real"


def test_confirmation_rules():
    assert S.needs_confirmation(S.SUITE_INDEX["real_money"], {})
    assert S.needs_confirmation(S.SUITE_INDEX["teardown"], {"instance": "paper"})
    assert S.needs_confirmation(S.SUITE_INDEX["race"], {"instance": "real"})
    assert not S.needs_confirmation(S.SUITE_INDEX["race"], {"instance": "paper"})


# ---------------------------------------------------------------- dashboard API
def test_config_endpoint_never_leaks_secrets(client):
    from config import settings
    body = client.get("/api/config", headers=LOCAL).get_data(as_text=True)
    for secret in (settings.ADMIN_PASSWORD, settings.MEMBER_PASSWORD):
        if secret:
            assert secret not in body
    assert "password" not in body.lower()


def test_suites_endpoint(client):
    d = client.get("/api/suites", headers=LOCAL).get_json()
    assert len(d["suites"]) == len(S.SUITES) and "follower_count" in d["defaults"]


@pytest.mark.parametrize("payload,code", [
    ({"suite": "nope"}, 400),
    ({"suite": "real_money"}, 412),
    ({"suite": "teardown", "params": {"instance": "paper"}}, 412),
    ({"suite": "race", "params": {"instance": "real"}}, 412),
])
def test_run_guards(client, payload, code):
    assert client.post("/api/run", json=payload, headers=LOCAL).status_code == code


def test_non_localhost_is_blocked_without_token(client):
    assert client.get("/api/config", headers={"Host": "evil.example.com"}).status_code == 403


def test_token_protection(client, monkeypatch):
    import dashboard.app as app_mod
    monkeypatch.setattr(app_mod, "DASHBOARD_TOKEN", "s3cret")
    assert client.get("/api/config", headers={"Host": "10.0.0.5"}).status_code == 401
    assert client.get("/api/config?token=wrong", headers={"Host": "10.0.0.5"}).status_code == 401
    ok = client.get("/api/config?token=s3cret", headers={"Host": "10.0.0.5"})
    assert ok.status_code == 200 and "bt_dash" in ok.headers.get("Set-Cookie", "")


def test_history_log_endpoint_rejects_path_traversal(client):
    assert client.get("/api/history/..%2F..%2Fetc%2Fpasswd/log", headers=LOCAL).status_code in (400, 404)


# ---------------------------------------------------------------- doctor
def test_doctor_flags_placeholder_credentials(monkeypatch):
    from config import doctor, settings
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "your_admin_password")
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "")
    res = {r["id"]: r for r in doctor.check_credentials()}
    assert res["var_ADMIN_PASSWORD"]["status"] == "fail" and res["var_ADMIN_EMAIL"]["status"] == "fail"
    assert "your_admin_password" not in str(res)           # never echo secrets


def test_doctor_offline_runs_without_network():
    from config import doctor
    ids = {r["id"] for r in doctor.run_checks(offline=True)}
    assert {"python", "env_file", "writable"} <= ids


# ---------------------------------------------------------------- race-hunter helpers
def test_parallel_releases_all_calls_and_survives_exceptions():
    from test_suite.breakpoint_race_runner import parallel

    def fn(i):
        if i == 3:
            raise RuntimeError("boom")
        return {"status_code": 200}

    res = parallel(fn, 8)
    assert len(res) == 8 and sum(r["status_code"] == 599 for r in res) == 1


def test_findings_status_logic():
    from test_suite.breakpoint_race_runner import Findings
    f = Findings("x"); f.add("INFO", "m"); assert f.result()["status"] == "PASS"
    f.add("MED", "m"); assert f.result()["status"] == "WARN"
    f.add("HIGH", "m"); assert f.result()["status"] == "FAIL"


# ---------------------------------------------------------------- A-book / B-book switch
class FakeBookClient:
    """Stands in for BlackTraderClient so book tests never touch the platform."""
    def __init__(self, emails, fail_for=()):
        self.m = {e: {"member_id": f"mem_{i}", "book": "a", "account_type": "live", "status": "active"} for i, e in enumerate(emails)}
        self.m["customer@real.com"] = {"member_id": "mem_cust", "book": "a", "account_type": "live", "status": "active"}
        self.fail_for, self.calls = set(fail_for), []

    def get_member_books(self):
        return {e: dict(v) for e, v in self.m.items()}

    def set_member_book(self, member_id, book):
        self.calls.append((member_id, book))
        if member_id in self.fail_for:
            return {"status_code": 500, "data": "boom"}
        for v in self.m.values():
            if v["member_id"] == member_id:
                v["book"] = book
        return {"status_code": 200, "data": {"success": True}}


@pytest.fixture()
def books(client, monkeypatch):
    import dashboard.app as a
    fake = FakeBookClient(a._topology_emails())
    monkeypatch.setattr(a, "dashboard_client", fake)
    return fake


def test_book_switch_validation_and_guards(client, books):
    P = lambda **kw: client.post("/api/books/switch", json=kw, headers=LOCAL)
    assert P(book="x", scope="master").status_code == 400                       # invalid book
    assert P(book="b", scope="emails", emails=["customer@real.com"]).status_code == 400   # real customer is off limits
    assert P(book="b", scope="master").status_code == 412                       # needs confirmation
    assert books.calls == []                                                    # nothing changed without confirm


def test_book_switch_refused_while_run_active(client, books, monkeypatch):
    import dashboard.app as a

    class Running:
        def poll(self):
            return None
    monkeypatch.setattr(a, "RUNNING_PROCESS", Running())
    r = client.post("/api/books/switch", json={"book": "b", "scope": "master", "confirm": True}, headers=LOCAL)
    assert r.status_code == 409 and books.calls == []


def test_book_switch_success_is_verified_by_read_back(client, books):
    r = client.post("/api/books/switch", json={"book": "b", "scope": "followers", "start": 1, "end": 3, "confirm": True}, headers=LOCAL)
    d = r.get_json()
    assert r.status_code == 200 and d["requested"] == 3 and d["switched_ok"] == 3 and d["failed"] == 0
    assert books.m["customer@real.com"]["book"] == "a"                          # untouched
    summary = client.get("/api/books", headers=LOCAL).get_json()
    assert summary["followers"]["b"] == 3 and summary["master"]["book"] == "a"


def test_book_switch_reports_failures_instead_of_trusting_200(client, books):
    books.fail_for = {books.m[f"{__import__('config.settings', fromlist=['x']).DEFAULT_PREFIX}2@{__import__('config.settings', fromlist=['x']).DEFAULT_DOMAIN}"]["member_id"]}
    r = client.post("/api/books/switch", json={"book": "b", "scope": "followers", "start": 1, "end": 3, "confirm": True}, headers=LOCAL)
    d = r.get_json()
    assert r.status_code == 207 and d["failed"] == 1 and d["switched_ok"] == 2


def test_client_rejects_bad_book_value():
    from test_suite.client import BlackTraderClient
    with pytest.raises(ValueError):
        BlackTraderClient().set_member_book("mem_x", "c")


# ---------------------------------------------------------------- paper-link safety guard
def test_unfollow_on_paper_is_blocked_by_default(monkeypatch):
    """The platform no longer lets paper copy links be re-created, so an unfollow would be permanent."""
    from test_suite import client as cl
    monkeypatch.delenv("BT_ALLOW_PAPER_UNFOLLOW", raising=False)
    assert cl.paper_unfollow_blocked("paper") and not cl.paper_unfollow_blocked("real")
    c = cl.BlackTraderClient("http://127.0.0.1:9")            # unreachable: proves no request is made
    res = c.unfollow_master("a@b.c", "mem_x", "paper")
    assert res["status_code"] == 0 and res.get("blocked")
    monkeypatch.setenv("BT_ALLOW_PAPER_UNFOLLOW", "1")
    assert not cl.paper_unfollow_blocked("paper")
