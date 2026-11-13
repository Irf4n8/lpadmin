"""
Setup health checks ("doctor")
==============================
Used by `python scripts/doctor.py` and by the dashboard's Getting Started panel.
Every check returns {id, label, status: ok|warn|fail|skip, detail, fix}.
Secrets are never included in the output.
"""

import importlib
import re
import sys
from typing import Dict, List

from config import settings as S

PLACEHOLDER = re.compile(r"^(your_|changeme|example|<)", re.I)


def _r(id_, label, status, detail="", fix=""):
    return {"id": id_, "label": label, "status": status, "detail": detail, "fix": fix}


def check_python():
    v = sys.version_info
    ok = v >= (3, 9)
    return _r("python", "Python 3.9+", "ok" if ok else "fail", f"{v.major}.{v.minor}.{v.micro}",
              "" if ok else "Install Python 3.9 or newer from python.org")


def check_deps():
    out = []
    for mod, pip, required in (("requests", "requests", True), ("dotenv", "python-dotenv", True),
                               ("flask", "flask", True), ("playwright", "playwright", False)):
        try:
            importlib.import_module(mod)
            out.append(_r(f"dep_{mod}", f"Package `{pip}`", "ok"))
        except ImportError:
            out.append(_r(f"dep_{mod}", f"Package `{pip}`", "fail" if required else "warn",
                          "not installed" + ("" if required else " (only needed for browser/UI suites)"),
                          "pip install -r requirements.txt" + ("" if required else " && playwright install chromium")))
    return out


def check_env_file():
    p = S.BASE_DIR / ".env"
    return _r("env_file", ".env file present", "ok" if p.exists() else "fail",
              "found" if p.exists() else "missing",
              "" if p.exists() else "Copy .env.example to .env and fill in your credentials")


def check_credentials():
    out = []
    for name, val in (("ADMIN_EMAIL", S.ADMIN_EMAIL), ("ADMIN_PASSWORD", S.ADMIN_PASSWORD),
                      ("MEMBER_PASSWORD", S.MEMBER_PASSWORD)):
        bad = (not val) or bool(PLACEHOLDER.match(val))
        out.append(_r(f"var_{name}", f"{name} configured", "fail" if bad else "ok",
                      "empty or still a placeholder" if bad else "set",
                      f"Set {name} in .env" if bad else ""))
    mid = S.MASTER_ID or ""
    bad = (not mid) or bool(re.fullmatch(r"mem_x+", mid))
    out.append(_r("var_MASTER_ID", "MASTER_ID configured", "fail" if bad else "ok",
                  "empty or still the template value" if bad else "set",
                  "Set MASTER_ID (mem_...) in .env - see the master's page in the admin panel" if bad else ""))
    return out


def check_reachable():
    import requests
    try:
        r = requests.get(S.BASE_URL, timeout=8)
        return _r("reach", f"Platform reachable ({S.BASE_URL})", "ok", f"HTTP {r.status_code}")
    except Exception as e:
        return _r("reach", f"Platform reachable ({S.BASE_URL})", "fail", type(e).__name__,
                  "Check BASE_URL in .env and your network / VPN")


def _client():
    from test_suite.client import BlackTraderClient
    return BlackTraderClient(base_url=S.BASE_URL, max_workers=4, timeout=10)


def check_admin(client):
    try:
        client.get_admin_token()
        return _r("admin", "Admin login", "ok")
    except Exception as e:
        return _r("admin", "Admin login", "fail", str(e)[:120], "Verify ADMIN_EMAIL / ADMIN_PASSWORD in .env")


def check_master(client):
    label = f"Master login ({S.MASTER_EMAIL})"
    try:
        client.get_trader_token(S.MASTER_EMAIL)
        return _r("master", label, "ok")
    except Exception as e:
        return _r("master", label, "fail", str(e)[:120],
                  "Create the master account on the platform, then set MASTER_EMAIL / MASTER_ID / MEMBER_PASSWORD in .env")


def check_followers(client):
    pat = re.compile(rf"^{re.escape(S.FOLLOWER_PREFIX)}(\d+)@{re.escape(S.DEFAULT_DOMAIN)}$", re.I)
    try:
        found = sum(1 for m in client.get_admin_members() if pat.match(m.get("email", "")))
    except Exception as e:
        return _r("followers", "Follower accounts exist", "fail", str(e)[:120])
    label = f"Follower accounts exist ({found}/{S.FOLLOWER_COUNT})"
    if found >= S.FOLLOWER_COUNT:
        return _r("followers", label, "ok")
    return _r("followers", label, "warn" if found else "fail", "some follower accounts are missing",
              f"python main.py create --start 1 --end {S.FOLLOWER_COUNT}   (or lower FOLLOWER_COUNT in .env)")


def check_links(client):
    try:
        n = len(client.get_copy_followers(S.MASTER_EMAIL, "paper", active_only=True))
    except Exception:
        n = 0
    ok = n >= S.FOLLOWER_COUNT
    return _r("links", f"Followers linked to master on paper ({n}/{S.FOLLOWER_COUNT})", "ok" if ok else "warn",
              "" if ok else "informational - suites re-link followers themselves",
              "" if ok else f"python main.py follow --master ctmaster --start 1 --end {S.FOLLOWER_COUNT}")


def check_writable():
    d = S.BASE_DIR / "reports"
    try:
        d.mkdir(parents=True, exist_ok=True)
        t = d / ".write_test"
        t.write_text("x")
        t.unlink()
        return _r("writable", "reports/ is writable", "ok")
    except Exception as e:
        return _r("writable", "reports/ is writable", "fail", str(e)[:120])


def check_jmeter():
    try:
        from test_suite.jmeter_real_runner import find_jmeter, find_java_bin
        ok = bool(find_jmeter() and find_java_bin())
    except Exception:
        ok = False
    return _r("jmeter", "Apache JMeter + Java (load tests)", "ok" if ok else "warn",
              "found" if ok else "not installed (only needed for the load-test suite)",
              "" if ok else "python scripts/install_jmeter.py")


def run_checks(offline: bool = False) -> List[Dict]:
    results: List[Dict] = [check_python()]
    results.extend(check_deps())
    results.append(check_env_file())
    results.extend(check_credentials())
    results.append(check_writable())
    results.append(check_jmeter())
    creds_ok = all(r["status"] == "ok" for r in results if r["id"].startswith("var_"))
    if offline:
        return results
    reach = check_reachable()
    results.append(reach)
    if reach["status"] != "ok" or not creds_ok:
        for id_, label in (("admin", "Admin login"), ("master", "Master login"), ("followers", "Follower accounts exist")):
            results.append(_r(id_, label, "skip", "blocked by an earlier failure"))
        return results
    client = _client()
    results.append(check_admin(client))
    results.append(check_master(client))
    results.append(check_followers(client))
    results.append(check_links(client))
    return results


def summarize(results: List[Dict]) -> str:
    if any(r["status"] == "fail" for r in results):
        return "fail"
    return "warn" if any(r["status"] == "warn" for r in results) else "ok"
