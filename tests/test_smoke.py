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
        assert set(s["flags"]) <= {"start", "end", "instance", "lot", "orders_count", "burst", "ramp", "profile"}, s["key"]
        if s["script"]:
            assert (ROOT / s["script"]).exists(), f"{s['key']}: missing {s['script']}"


def test_every_runner_accepts_the_flags_the_registry_passes():
    """Catches a registry flag that the runner's argparse would reject."""
    flag_map = {"start": "--start", "end": "--end", "instance": "--instance", "lot": "--lot",
                "orders_count": "--orders-count", "burst": "--burst", "ramp": "--ramp", "profile": "--profile"}
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
