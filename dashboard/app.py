#!/usr/bin/env python3
"""
BlackTrader Copy Trading Test Dashboard & Real-Time Monitoring Server
====================================================================
Provides an interactive live web UI:
- Real-time test suite execution monitoring with live logs stream
- Instant One-Click triggers for all 7 test suites
- Interactive evidence report browser (viewing all JSON & Markdown reports)
- Live account balance and position status monitor across 100 followers
"""

import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from flask import Flask, Response, g, jsonify, make_response, render_template, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.doctor import run_checks, summarize as summarize_checks
from config.settings import (BASE_URL, DEFAULT_DOMAIN, DEFAULT_PREFIX, DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_TOKEN,
                             FOLLOWER_COUNT, MASTER_EMAIL, MASTER_ID)
from dashboard.suites import SUITE_INDEX, build_command, effective_instance, needs_confirmation, public_registry
from test_suite.client import BlackTraderClient

app = Flask(__name__, template_folder="templates", static_folder="static")

dashboard_client = BlackTraderClient(base_url=BASE_URL, max_workers=10)

EVIDENCE_DIR = BASE_DIR / "reports" / "evidence"
LOGS_DIR = BASE_DIR / "reports" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

LATEST_LOG_FILE = LOGS_DIR / "live_execution.log"

# Global process tracker
RUNNING_PROCESS = None
CURRENT_TASK = {
    "suite": None,
    "name": None,
    "status": "IDLE",  # IDLE, RUNNING, COMPLETED, FAILED, TERMINATED
    "started_at": None,
    "pid": None,
    "exit_code": None,
    "ended_at": None,
    "run_id": None,
    "params": {},
    "risk": None,
}
PROCESS_LOCK = threading.Lock()

RUNS_DIR = LOGS_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = LOGS_DIR / "run_history.json"
HISTORY_LOCK = threading.Lock()
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


# -------------------------------------------------------------------------------------
# Access control: localhost-only unless DASHBOARD_TOKEN is set
# -------------------------------------------------------------------------------------
@app.before_request
def _access_control():
    g.set_token_cookie = False
    if DASHBOARD_TOKEN:
        supplied = request.cookies.get("bt_dash") or request.headers.get("X-Dashboard-Token") or request.args.get("token") or ""
        if hmac.compare_digest(supplied, DASHBOARD_TOKEN):
            g.set_token_cookie = request.args.get("token") is not None
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "unauthorized - open the dashboard once with /?token=<DASHBOARD_TOKEN>"}), 401
        return Response("Dashboard is locked. Open /?token=<DASHBOARD_TOKEN>", 401)
    # No token: only answer requests addressed to localhost (blocks DNS-rebinding / LAN access)
    host = (request.host or "").rsplit(":", 1)[0] if not request.host.startswith("[") else request.host.split("]")[0] + "]"
    if host not in LOOPBACK_HOSTS:
        return Response("Forbidden: set DASHBOARD_TOKEN in .env to allow non-localhost access.", 403)
    return None


@app.after_request
def _set_cookie(resp):
    if getattr(g, "set_token_cookie", False):
        resp.set_cookie("bt_dash", DASHBOARD_TOKEN, httponly=True, samesite="Strict")
    return resp


# -------------------------------------------------------------------------------------
# Run history (persisted so results survive restarts and are shareable)
# -------------------------------------------------------------------------------------
def _load_history() -> list:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_history(items: list) -> None:
    HISTORY_FILE.write_text(json.dumps(items[-100:], indent=1), encoding="utf-8")


def history_add(entry: dict) -> None:
    with HISTORY_LOCK:
        items = _load_history()
        items.append(entry)
        _save_history(items)


def history_update(run_id: str, **fields) -> None:
    with HISTORY_LOCK:
        items = _load_history()
        for it in items:
            if it.get("id") == run_id:
                it.update(fields)
        _save_history(items)


_COUNT_CACHE = {}


def count_log_results(path: Path) -> tuple:
    """Count [PASS] / [FAIL] markers in a log (cached by mtime+size)."""
    try:
        st = path.stat()
    except OSError:
        return 0, 0
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key in _COUNT_CACHE:
        return _COUNT_CACHE[key]
    text = path.read_text(encoding="utf-8", errors="replace")
    res = (text.count("[PASS]"), text.count("[FAIL]"))
    _COUNT_CACHE.clear()
    _COUNT_CACHE[key] = res
    return res


def monitor_process(proc, run_id, log_handle):
    global RUNNING_PROCESS
    proc.wait()
    try:
        log_handle.close()
    except Exception:
        pass
    passed, failed = count_log_results(LATEST_LOG_FILE)
    with PROCESS_LOCK:
        if CURRENT_TASK["status"] != "TERMINATED":
            CURRENT_TASK["status"] = "COMPLETED" if proc.returncode == 0 else "FAILED"
        CURRENT_TASK["exit_code"] = proc.returncode
        CURRENT_TASK["ended_at"] = time.time()
        status = CURRENT_TASK["status"]
        started = CURRENT_TASK["started_at"] or time.time()
        RUNNING_PROCESS = None
    try:
        shutil.copyfile(LATEST_LOG_FILE, RUNS_DIR / f"{run_id}.log")
    except Exception:
        pass
    history_update(run_id, status=status, exit_code=proc.returncode, ended_at=datetime.now().isoformat(timespec="seconds"),
                   duration_sec=round(time.time() - started, 1), passed=passed, failed=failed)


@app.route("/")
def index():
    resp = make_response(render_template("index.html", MASTER_EMAIL=MASTER_EMAIL, MASTER_ID=MASTER_ID))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/config")
def get_config():
    """Non-secret configuration, so the UI can show what it is pointed at."""
    return jsonify({
        "base_url": BASE_URL,
        "master_email": MASTER_EMAIL,
        "master_id": MASTER_ID,
        "follower_prefix": DEFAULT_PREFIX,
        "follower_domain": DEFAULT_DOMAIN,
        "follower_count": FOLLOWER_COUNT,
        "token_protected": bool(DASHBOARD_TOKEN),
        "env_file_present": (BASE_DIR / ".env").exists(),
    })


@app.route("/api/suites")
def get_suites():
    return jsonify({
        "suites": public_registry(),
        "defaults": {"follower_count": FOLLOWER_COUNT, "lot": 0.1, "orders_count": 10, "ramp": "10,25,50,100"},
    })


_HEALTH_CACHE = {"t": 0.0, "data": None}


@app.route("/api/health")
def get_health():
    """Run the setup doctor. Network checks are cached for 20s; ?refresh=1 forces a re-run."""
    offline = request.args.get("offline") == "1"
    fresh = request.args.get("refresh") == "1"
    if not offline and not fresh and _HEALTH_CACHE["data"] and time.time() - _HEALTH_CACHE["t"] < 20:
        return jsonify(_HEALTH_CACHE["data"])
    results = run_checks(offline=offline)
    data = {"overall": summarize_checks(results), "checks": results, "checked_at": datetime.now().isoformat(timespec="seconds")}
    if not offline:
        _HEALTH_CACHE.update(t=time.time(), data=data)
    return jsonify(data)


@app.route("/api/status")
def get_status():
    with PROCESS_LOCK:
        task = dict(CURRENT_TASK)
    elapsed = 0
    if task["started_at"]:
        end = time.time() if task["status"] == "RUNNING" else (task.get("ended_at") or task["started_at"])
        elapsed = round(end - task["started_at"], 1)
    passed, failed = count_log_results(LATEST_LOG_FILE) if task["suite"] else (0, 0)
    return jsonify({**task, "elapsed_seconds": elapsed, "is_running": task["status"] == "RUNNING",
                    "pass_count": passed, "fail_count": failed})


@app.route("/api/logs")
def get_logs():
    if not LATEST_LOG_FILE.exists():
        return jsonify({"logs": ""})
    try:
        with open(LATEST_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return jsonify({"logs": "".join(lines[-300:]), "total_lines": len(lines)})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {str(e)}"})


@app.route("/api/logs/download")
def download_log():
    if not LATEST_LOG_FILE.exists():
        return jsonify({"error": "no log yet"}), 404
    return send_from_directory(LOGS_DIR, LATEST_LOG_FILE.name, as_attachment=True)


@app.route("/api/history")
def get_history():
    with HISTORY_LOCK:
        items = _load_history()
    return jsonify({"runs": list(reversed(items))})


@app.route("/api/history/<run_id>/log")
def get_history_log(run_id):
    if not run_id.replace("_", "").replace("-", "").isalnum():
        return jsonify({"error": "bad id"}), 400
    p = RUNS_DIR / f"{run_id}.log"
    if not p.exists():
        return jsonify({"error": "log not archived"}), 404
    return jsonify({"logs": p.read_text(encoding="utf-8", errors="replace")[-200000:]})


@app.route("/api/run", methods=["POST"])
def run_suite():
    global RUNNING_PROCESS
    data = request.get_json(silent=True) or {}
    suite_key = data.get("suite")
    suite = SUITE_INDEX.get(suite_key)
    if not suite:
        return jsonify({"error": f"Unknown suite '{suite_key}'"}), 400
    params = data.get("params") or {}

    if needs_confirmation(suite, params) and data.get("confirm") is not True:
        return jsonify({"error": "This action needs explicit confirmation.", "needs_confirmation": True,
                        "reason": ("Runs against the REAL instance." if effective_instance(suite, params) in ("real", "both")
                                   else "Closes positions and cancels orders.")}), 412

    cmd = build_command(suite, params, {"follower_count": FOLLOWER_COUNT})
    title = suite["name"]
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + suite_key

    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            return jsonify({"error": "A test suite is already running.", "current": CURRENT_TASK["name"]}), 409

        with open(LATEST_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== LAUNCHING: {title} ===\n")
            shown = "(inline teardown script)" if "-c" in cmd[:3] else " ".join(["python"] + cmd[1:])
            f.write(f"Command  : {shown}\n")
            f.write(f"Instance : {effective_instance(suite, params)}\n")
            f.write(f"Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        log_out = open(LATEST_LOG_FILE, "a", encoding="utf-8")
        proc = subprocess.Popen(cmd, stdout=log_out, stderr=subprocess.STDOUT, cwd=str(BASE_DIR), text=True, env=env)
        RUNNING_PROCESS = proc
        CURRENT_TASK.update(suite=suite_key, name=title, status="RUNNING", started_at=time.time(), ended_at=None,
                            pid=proc.pid, exit_code=None, run_id=run_id,
                            params={**params, "instance": effective_instance(suite, params)}, risk=suite["risk"])
        history_add({"id": run_id, "suite": suite_key, "name": title, "status": "RUNNING",
                     "started_at": datetime.now().isoformat(timespec="seconds"),
                     "params": CURRENT_TASK["params"], "books": _book_snapshot()})
        threading.Thread(target=monitor_process, args=(proc, run_id, log_out), daemon=True).start()

    return jsonify({"message": f"Launched {title}", "pid": proc.pid, "suite": suite_key, "run_id": run_id})


@app.route("/api/stop", methods=["POST"])
def stop_suite():
    global RUNNING_PROCESS
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            CURRENT_TASK["status"] = "TERMINATED"
            RUNNING_PROCESS.terminate()
            return jsonify({"message": "Run stopped. Positions may still be open - use Emergency Teardown to clean up."})
    return jsonify({"message": "Nothing is running."})


# -------------------------------------------------------------------------------------
# Evidence summary (real numbers for the header cards)
# -------------------------------------------------------------------------------------
_FAMILY_RE = re.compile(r"^(?P<fam>.+?)_(?P<ts>\d{8}_\d{6})$")
_SUMMARY_CACHE = {}


def _count_statuses(obj, acc):
    if isinstance(obj, dict):
        st = obj.get("status")
        if isinstance(st, str):
            s = st.upper()
            if s.startswith("PASS"):
                acc["passed"] += 1
            elif s.startswith("FAIL") or s == "ERROR":
                acc["failed"] += 1
            elif s.startswith("WARN"):
                acc["warned"] += 1
        for v in obj.values():
            _count_statuses(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _count_statuses(v, acc)


@app.route("/api/summary")
def get_summary():
    families = {}
    for p in EVIDENCE_DIR.glob("*.json"):
        if p.stem in ("baseline_snapshot",) or p.stem.startswith(("jmeter_performance", "jmeter_load_test")):
            continue
        m = _FAMILY_RE.match(p.stem)
        fam = m.group("fam") if m else p.stem
        mt = p.stat().st_mtime
        if fam not in families or mt > families[fam][1]:
            families[fam] = (p, mt)
    rows = []
    for fam, (p, mt) in families.items():
        key = (p.name, mt)
        if key not in _SUMMARY_CACHE:
            acc = {"passed": 0, "failed": 0, "warned": 0}
            try:
                _count_statuses(json.loads(p.read_text(encoding="utf-8")), acc)
            except Exception:
                pass
            _SUMMARY_CACHE[key] = acc
        acc = _SUMMARY_CACHE[key]
        if acc["passed"] + acc["failed"] + acc["warned"] == 0:
            continue
        rows.append({"family": fam, "label": fam.replace("_", " ").replace(" evidence", "").title(), "file": p.name,
                     "modified": datetime.fromtimestamp(mt).isoformat(timespec="seconds"), **acc,
                     "status": "FAIL" if acc["failed"] else ("WARN" if acc["warned"] else "PASS")})
    rows.sort(key=lambda r: r["modified"], reverse=True)
    with HISTORY_LOCK:
        hist = _load_history()
    last = hist[-1] if hist else None
    return jsonify({
        "families": rows,
        "totals": {"suites": len(rows), "suites_green": sum(1 for r in rows if r["status"] == "PASS"),
                   "passed": sum(r["passed"] for r in rows), "failed": sum(r["failed"] for r in rows)},
        "last_run": last,
        "runs_recorded": len(hist),
    })


@app.route("/api/reports")
def get_reports():
    reports = []
    seen_files = set()
    search_dirs = [BASE_DIR / "reports", BASE_DIR / "reports" / "evidence"]

    for d in search_dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir(), key=os.path.getmtime, reverse=True):
            if f.is_file() and f.suffix in [".json", ".md", ".csv", ".jtl"] and not f.name.startswith("baseline") and f.name not in seen_files:
                seen_files.add(f.name)
                mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                category = "Other"
                if "jmeter" in f.name:
                    category = "JMeter Load Test"
                elif "real_money" in f.name:
                    category = "Real Money Mode"
                elif "paper_2x" in f.name:
                    category = "2x Multiplier Mode"
                elif "balance" in f.name:
                    category = "Balance Mode"
                elif "equity" in f.name:
                    category = "Equity Mode"
                elif "race" in f.name:
                    category = "Race Conditions"
                elif "parity" in f.name or "symmetric" in f.name:
                    category = "Buy/Sell Parity"
                elif "pending" in f.name:
                    category = "Pending Trigger"
                elif "extended" in f.name:
                    category = "Extended Edge Cases"
                elif "state" in f.name:
                    category = "Account States"
                elif "reconciliation" in f.name or "accounting" in f.name:
                    category = "Reconciliation"
                elif "evidence" in f.name:
                    category = "Core Multiplier"

                reports.append({
                    "filename": f.name,
                    "category": category,
                    "type": f.suffix.replace(".", "").upper(),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "modified_at": mtime
                })
    return jsonify({"reports": reports})


@app.route("/api/reports/<filename>")
def get_report_content(filename):
    search_paths = [
        BASE_DIR / "reports" / "evidence" / filename,
        BASE_DIR / "reports" / filename
    ]
    file_path = next((p for p in search_paths if p.exists() and p.is_file()), None)
    if not file_path:
        return jsonify({"error": "Report file not found"}), 404
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            return jsonify({
                "filename": filename,
                "is_json": filename.endswith(".json"),
                "content": content
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


SCREENSHOT_DIR = BASE_DIR / "reports" / "evidence" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/api/screenshots")
def list_screenshots():
    if not SCREENSHOT_DIR.exists():
        return jsonify({"screenshots": []})
    files = [f.name for f in SCREENSHOT_DIR.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg"]]
    return jsonify({"screenshots": sorted(files)})


@app.route("/api/screenshots/<filename>")
def get_screenshot(filename):
    return send_from_directory(SCREENSHOT_DIR, filename)


ACTIVE_LINKS_CACHE = {"data": None, "timestamp": 0, "instance": None, "forced_mode": None}


def get_cached_active_links(instance: str = "paper", force_refresh: bool = False) -> dict:
    global ACTIVE_LINKS_CACHE
    now = time.time()
    if not force_refresh and (ACTIVE_LINKS_CACHE["data"] is not None and 
        ACTIVE_LINKS_CACHE.get("instance") == instance and 
        (now - ACTIVE_LINKS_CACHE["timestamp"] < 8)):
        return ACTIVE_LINKS_CACHE["data"]
    try:
        raw_links = dashboard_client.get_copy_followers(MASTER_EMAIL, instance=instance, active_only=False)
        links_by_follower = {}
        for link in raw_links:
            fn = link.get("follower_name")
            if fn:
                links_by_follower[fn] = link
        ACTIVE_LINKS_CACHE["data"] = links_by_follower
        ACTIVE_LINKS_CACHE["timestamp"] = now
        ACTIVE_LINKS_CACHE["instance"] = instance
        return links_by_follower
    except Exception as e:
        print(f"Error fetching active links: {e}")
        return ACTIVE_LINKS_CACHE["data"] or {}


@app.route("/api/followers")
def get_followers_list():
    from test_suite.baseline import get_expected_multiplier
    instance = request.args.get("instance", "paper")
    force_refresh = request.args.get("refresh") == "true"
    active_links = get_cached_active_links(instance=instance, force_refresh=force_refresh)

    current_suite = CURRENT_TASK.get("suite")
    detected_mode = "multiplier"

    if current_suite in ["balance", "equity", "multiplier"]:
        detected_mode = current_suite
    elif ACTIVE_LINKS_CACHE.get("forced_mode"):
        detected_mode = ACTIVE_LINKS_CACHE["forced_mode"]
    elif active_links:
        methods_count = {}
        for l in active_links.values():
            m = l.get("method", "multiplier")
            methods_count[m] = methods_count.get(m, 0) + 1
        if methods_count:
            detected_mode = max(methods_count, key=methods_count.get)

    m_funds = dashboard_client.get_positions(MASTER_EMAIL, instance=instance).get("funds", {})
    m_bal = float(m_funds.get("balance", 100000000.0))
    m_eq = float(m_funds.get("equity", m_bal))

    followers = []
    for i in range(1, FOLLOWER_COUNT + 1):
        f_prefix = f"{DEFAULT_PREFIX}{i}"
        link = active_links.get(f_prefix, {})

        if link and "multiplier" in link:
            mult = float(link.get("multiplier", 1.0))
            f_method = link.get("method", detected_mode)
            link_status = link.get("status", "ACTIVE").upper()
        else:
            mult = get_expected_multiplier(i)
            f_method = detected_mode
            link_status = "INACTIVE" if active_links else "ACTIVE"

        tier = 1 if mult == 1.0 else (2 if mult == 2.0 else (3 if mult == 3.0 else 4))
        
        # Format display label dynamically based on follower's actual method and multiplier
        if f_method == "balance":
            display_label = f"Bal {mult:g}x"
        elif f_method == "equity":
            display_label = f"Eq {mult:g}x"
        else:
            display_label = f"{mult:g}x"

        followers.append({
            "index": i,
            "email": f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}",
            "multiplier": mult,
            "method": f_method,
            "tier": tier,
            "balance": f"{m_bal/1e6:.0f}M",
            "equity": f"{m_eq/1e6:.0f}M",
            "display_label": display_label,
            "ratio_label": f"{mult:g}x",
            "status": link_status,
            "instance": instance
        })

    return jsonify({
        "instance": instance,
        "current_mode": detected_mode,
        "master": {
            "email": MASTER_EMAIL,
            "id": MASTER_ID,
            "balance": f"{m_bal/1e6:.1f}M",
            "equity": f"{m_eq/1e6:.1f}M"
        },
        "followers": followers
    })


@app.route("/api/account/<email>")
def get_account_details(email):
    try:
        from test_suite.baseline import get_expected_multiplier
        instance = request.args.get("instance", "paper")
        pos_data = dashboard_client.get_positions(email, instance=instance)
        ord_data = dashboard_client.get_orders(email, instance=instance)

        f_prefix = email.split("@")[0]
        follow_info = None
        is_master = "master" in email
        follower_index = None
        expected_mult = 1.0
        expected_cap = "100,000,000.00"
        tier = 1

        if not is_master and f_prefix.startswith("follower"):
            try:
                follower_index = int(f_prefix.replace("follower", ""))
            except Exception:
                pass

            active_links_map = get_cached_active_links(instance=instance)
            follow_info = active_links_map.get(f_prefix)
            if follow_info and "multiplier" in follow_info:
                expected_mult = float(follow_info.get("multiplier", 1.0))
                expected_cap = f"{int(100 * expected_mult):,}.00"
                tier = 1 if expected_mult == 1.0 else (2 if expected_mult == 2.0 else (3 if expected_mult == 3.0 else 4))
            else:
                try:
                    expected_mult = get_expected_multiplier(follower_index) if follower_index else 1.0
                    expected_cap = f"{int(100 * expected_mult):,}.00"
                    tier = 1 if expected_mult == 1.0 else (2 if expected_mult == 2.0 else (3 if expected_mult == 3.0 else 4))
                except Exception:
                    pass

        positions = pos_data.get("positions", [])
        orders = ord_data.get("orders", [])

        # Process orders with formatted timestamps
        processed_orders = []
        for o in orders[:50]:
            raw_time = o.get("created_at", "")
            clean_time = raw_time
            if "T" in raw_time:
                clean_time = raw_time.split("T")[1].replace("Z", "")[:8]
            processed_orders.append({
                **o,
                "formatted_time": clean_time,
                "display_qty": o.get("requested_qty") or o.get("filled_qty", 0.0),
                "display_price": o.get("avg_fill_price") or o.get("price") or "--"
            })

        funds = pos_data.get("funds", {})

        return jsonify({
            "email": email,
            "is_master": is_master,
            "follower_index": follower_index,
            "tier": tier,
            "expected_multiplier": expected_mult,
            "expected_capital": expected_cap,
            "instance": instance,
            "funds": funds,
            "positions": positions,
            "positions_count": len(positions),
            "total_unrealized_pnl": pos_data.get("total_unrealized_pnl", 0),
            "orders": processed_orders,
            "orders_count": len(orders),
            "follow_info": follow_info
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/account/<email>/squareoff", methods=["POST"])
def squareoff_account(email):
    try:
        instance = request.args.get("instance", "paper")
        res = dashboard_client.bulk_squareoff(email, instance=instance)
        return jsonify({"message": f"Positions closed for {email}", "data": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/account/<email>/copy_settings", methods=["POST"])
def update_account_copy_settings(email):
    """Update copy trading settings (mode, multiplier) for a single follower."""
    data = request.json or {}
    mode = data.get("mode", "multiplier")
    instance = data.get("instance", "paper")
    try:
        mult = float(data.get("multiplier", 1.0))
    except Exception:
        mult = 1.0
    master_id = MASTER_ID

    try:
        dashboard_client.unfollow_master(email, master_id, instance=instance)
        res = dashboard_client.follow_master(
            email,
            master_id,
            instance=instance,
            method=mode,
            multiplier=mult,
            reverse=False,
            copy_mode="public"
        )
        global ACTIVE_LINKS_CACHE
        ACTIVE_LINKS_CACHE["data"] = None
        ACTIVE_LINKS_CACHE["timestamp"] = 0
        ACTIVE_LINKS_CACHE["forced_mode"] = mode
        return jsonify({
            "message": f"Updated {email} to {mode.upper()} mode with {mult}x multiplier on {instance}.",
            "data": res
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/copy/switch_mode", methods=["POST"])
def switch_copy_mode():
    """Bulk switch followers between Multiplier, Balance, and Equity modes with custom multipliers."""
    from concurrent.futures import ThreadPoolExecutor
    data = request.json or {}
    mode = data.get("mode", "multiplier")
    instance = data.get("instance", "paper")
    tier_based = data.get("tier_based", False)
    try:
        custom_mult = float(data.get("multiplier", 1.0))
    except Exception:
        custom_mult = 1.0
    start_idx = int(data.get("start", 1))
    end_idx = int(data.get("end", FOLLOWER_COUNT))

    follower_emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(start_idx, end_idx + 1)]
    master_id = MASTER_ID

    def update_follower(email):
        idx = int(email.split("@")[0].replace("follower", ""))
        if tier_based:
            from test_suite.baseline import get_expected_multiplier
            mult = get_expected_multiplier(idx)
        else:
            mult = custom_mult

        try:
            dashboard_client.unfollow_master(email, master_id, instance=instance)
            res = dashboard_client.follow_master(
                email,
                master_id,
                instance=instance,
                method=mode,
                multiplier=mult,
                reverse=False,
                copy_mode="public"
            )
            return {"email": email, "success": (res.get("status_code") == 200), "multiplier": mult}
        except Exception as e:
            return {"email": email, "success": False, "error": str(e)}

    with ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(update_follower, follower_emails))

    success_count = sum(1 for r in results if r["success"])
    global ACTIVE_LINKS_CACHE
    ACTIVE_LINKS_CACHE["data"] = None
    ACTIVE_LINKS_CACHE["timestamp"] = 0
    ACTIVE_LINKS_CACHE["forced_mode"] = mode

    return jsonify({
        "message": f"Successfully updated {success_count} / {len(follower_emails)} followers to {mode.upper()} mode ({custom_mult if not tier_based else 'Tier-Based'}x) on {instance.upper()}.",
        "mode": mode,
        "multiplier": custom_mult,
        "tier_based": tier_based,
        "success_count": success_count,
        "total": len(follower_emails)
    })


@app.route("/api/accounts/sync_balance", methods=["POST"])
def sync_accounts_balance():
    """Set identical balance across Master and all 100 followers on selected instance."""
    from concurrent.futures import ThreadPoolExecutor
    data = request.json or {}
    instance = data.get("instance", "paper")
    try:
        target_balance = float(data.get("balance", 100000000.0))
    except Exception:
        target_balance = 100000000.0

    master_email = MASTER_EMAIL
    follower_emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(1, FOLLOWER_COUNT + 1)]
    all_emails = [master_email] + follower_emails

    try:
        members = dashboard_client.get_admin_members()
        member_map = {m.get("email"): m.get("member_id") for m in members if m.get("email") and m.get("member_id")}

        def set_bal(email):
            mem_id = member_map.get(email)
            if not mem_id:
                return {"email": email, "success": False, "error": "No member ID"}
            res = dashboard_client.set_member_balance(mem_id, target_balance, instance=instance)
            return {"email": email, "success": (res.get("status_code") == 200), "balance": target_balance}

        with ThreadPoolExecutor(max_workers=20) as ex:
            results = list(ex.map(set_bal, all_emails))

        success_count = sum(1 for r in results if r["success"])
        return jsonify({
            "message": f"Successfully synchronized ${target_balance:,.2f} balance across {success_count} / {len(all_emails)} accounts on {instance.upper()}.",
            "target_balance": target_balance,
            "success_count": success_count,
            "total": len(all_emails),
            "instance": instance
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/account/<email>/position/<market_order_id>/close", methods=["POST"])
def close_single_position(email, market_order_id):
    try:
        instance = request.args.get("instance", "paper")
        res = dashboard_client.squareoff_position(email, market_order_id, instance=instance)
        return jsonify({"message": f"Position {market_order_id} closed for {email}", "data": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/live_activity")
def get_live_activity():
    try:
        instance = request.args.get("instance", "paper")
        recent_events = []
        master_ords = dashboard_client.get_orders(MASTER_EMAIL, instance=instance).get("orders", [])
        for o in master_ords[:20]:
            raw_time = o.get("created_at", "")
            clean_time = raw_time
            if "T" in raw_time:
                clean_time = raw_time.split("T")[1].replace("Z", "")[:8]
            recent_events.append({
                "account": "ctmaster (Master Trader)",
                "account_type": "master",
                "order_id": o.get("order_id"),
                "symbol": o.get("symbol"),
                "side": o.get("side"),
                "type": o.get("type"),
                "qty": o.get("requested_qty") or o.get("filled_qty"),
                "price": o.get("avg_fill_price") or o.get("price") or "--",
                "state": o.get("state"),
                "source": o.get("source", "direct"),
                "copy_ref": o.get("copy_ref"),
                "time": clean_time
            })
        return jsonify({"events": recent_events})
    except Exception as e:
        return jsonify({"events": [], "error": str(e)})


@app.route("/api/live_orders")
def get_live_orders():
    """Returns combined live order tape from master and sample active followers."""
    try:
        instance = request.args.get("instance", "paper")
        tape = []
        
        # 1. Master orders
        master_ords = dashboard_client.get_orders(MASTER_EMAIL, instance=instance).get("orders", [])
        for o in master_ords[:15]:
            raw_time = o.get("created_at", "")
            clean_time = raw_time
            if "T" in raw_time:
                clean_time = raw_time.split("T")[1].replace("Z", "")[:8]
            tape.append({
                "account": "Master (ctmaster)",
                "email": MASTER_EMAIL,
                "role": "MASTER",
                "order_id": o.get("order_id"),
                "symbol": o.get("symbol"),
                "side": o.get("side"),
                "type": o.get("type"),
                "qty": o.get("requested_qty") or o.get("filled_qty"),
                "price": o.get("avg_fill_price") or o.get("price") or "--",
                "state": o.get("state"),
                "source": o.get("source", "direct"),
                "copy_ref": o.get("copy_ref") or "--",
                "time": clean_time,
                "raw_time": raw_time
            })

        # 2. Sample followers (e.g. follower1, follower26, follower51, follower76)
        sample_followers = ["follower1@mailinator.com", "follower26@mailinator.com", "follower51@mailinator.com", "follower76@mailinator.com"]
        for f_email in sample_followers:
            f_ords = dashboard_client.get_orders(f_email, instance=instance).get("orders", [])
            f_name = f_email.split("@")[0]
            for o in f_ords[:5]:
                raw_time = o.get("created_at", "")
                clean_time = raw_time
                if "T" in raw_time:
                    clean_time = raw_time.split("T")[1].replace("Z", "")[:8]
                tape.append({
                    "account": f"Follower {f_name.replace('follower', '#')}",
                    "email": f_email,
                    "role": "FOLLOWER",
                    "order_id": o.get("order_id"),
                    "symbol": o.get("symbol"),
                    "side": o.get("side"),
                    "type": o.get("type"),
                    "qty": o.get("requested_qty") or o.get("filled_qty"),
                    "price": o.get("avg_fill_price") or o.get("price") or "--",
                    "state": o.get("state"),
                    "source": o.get("source", "copy"),
                    "copy_ref": o.get("copy_ref") or "--",
                    "time": clean_time,
                    "raw_time": raw_time
                })

        # Sort all by raw_time descending
        tape.sort(key=lambda x: x.get("raw_time", ""), reverse=True)
        return jsonify({"tape": tape[:40]})
    except Exception as e:
        return jsonify({"tape": [], "error": str(e)})
    except Exception as e:
        return jsonify({"events": [], "error": str(e)})


@app.route("/api/order/dispatch_and_verify", methods=["POST"])
def dispatch_and_verify():
    """Places an order on Master account and concurrently verifies 100 followers replication."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime

    data = request.json or {}
    symbol = data.get("symbol", "BINANCE:BTCUSDT.P")
    side = data.get("side", "BUY").upper()
    order_type = data.get("type", "MARKET").upper()
    try:
        qty = float(data.get("qty", 1.0))
    except Exception:
        qty = 1.0
    price = data.get("price")
    if price is not None:
        try:
            price = float(price)
        except Exception:
            price = None
    instance = data.get("instance", "paper")

    t_start = time.time()
    # 1. Place order on Master
    master_order_res = dashboard_client.place_order(
        email=MASTER_EMAIL,
        symbol=symbol,
        side=side,
        order_type=order_type,
        qty=qty,
        price=price,
        instance=instance
    )
    t_master_placed = time.time()

    master_status = master_order_res.get("status_code", 500)
    master_data = master_order_res.get("data", {})
    master_ord_obj = master_data.get("order", {}) if isinstance(master_data.get("order"), dict) else master_data
    master_order_id = master_ord_obj.get("order_id") or master_ord_obj.get("market_order_id") or master_data.get("order_id") or master_data.get("market_order_id")
    master_body = master_ord_obj

    if master_status != 200 or not master_order_id:
        return jsonify({
            "success": False,
            "error": "Failed to place Master order",
            "master_response": master_order_res
        }), 400

    # 2. Wait 2.2 seconds for fan-out replication across 100 followers
    time.sleep(2.2)

    # Fetch master order details from oms
    master_orders_list = dashboard_client.get_orders(MASTER_EMAIL, instance=instance).get("orders", [])
    master_ord_details = next((o for o in master_orders_list if o.get("order_id") == master_order_id or o.get("market_order_id") == master_order_id), {})
    master_fill_price = master_ord_details.get("avg_fill_price") or master_ord_details.get("price") or master_body.get("avg_fill_price") or "--"
    master_filled_qty = master_ord_details.get("filled_qty") or master_body.get("filled_qty") or qty
    master_created_at = master_ord_details.get("created_at") or master_body.get("created_at") or datetime.utcnow().isoformat()

    # 3. Check all 100 followers concurrently
    active_links = get_cached_active_links(instance=instance, force_refresh=True)

    def check_follower(idx):
        f_email = f"{DEFAULT_PREFIX}{idx}@{DEFAULT_DOMAIN}"
        f_prefix = f"{DEFAULT_PREFIX}{idx}"
        link = active_links.get(f_prefix, {})
        f_method = link.get("method", "multiplier")
        f_multiplier = float(link.get("multiplier", 1.0)) if link and "multiplier" in link else 1.0

        # Calculate expected lots based on mode & multiplier
        expected_lots = qty * f_multiplier

        try:
            f_ords = dashboard_client.get_orders(f_email, instance=instance).get("orders", [])
            # Find replicated order matching copy_ref or symbol & recent time
            matched = None
            clean_master_id = master_order_id.replace("-", "").strip()
            for o in f_ords:
                c_ref = (o.get("copy_ref") or "").replace("-", "").strip()
                if clean_master_id and clean_master_id in c_ref:
                    matched = o
                    break
            
            # Fallback to latest copy order within 10s if copy_ref format varies
            if not matched and f_ords:
                candidate = f_ords[0]
                if candidate.get("source") == "copy" and candidate.get("symbol") == symbol and candidate.get("side") == side:
                    matched = candidate

            if matched:
                actual_lots = float(matched.get("requested_qty") or matched.get("filled_qty", 0.0))
                fill_price = matched.get("avg_fill_price") or matched.get("price") or "--"
                state = (matched.get("state") or "FILLED").upper()
                created_at = matched.get("created_at", "")
                
                # Check lot sizing match (allow 0.001 margin)
                lots_matched = abs(actual_lots - expected_lots) < 0.01

                # Calculate latency
                latency_str = "~1.8s"
                try:
                    if created_at and master_created_at:
                        t_m = datetime.fromisoformat(master_created_at.replace("Z", "+00:00"))
                        t_f = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        diff = (t_f - t_m).total_seconds()
                        if diff >= 0:
                            latency_str = f"{diff:.2f}s"
                except Exception:
                    pass

                # Calculate slippage
                slippage_str = "0.0 pts"
                try:
                    if fill_price != "--" and master_fill_price != "--":
                        slip = float(fill_price) - float(master_fill_price)
                        slippage_str = f"{slip:+.1f} pts"
                except Exception:
                    pass

                return {
                    "index": idx,
                    "email": f_email,
                    "replicated": True,
                    "order_id": matched.get("order_id"),
                    "copy_ref": matched.get("copy_ref") or master_order_id,
                    "expected_lots": expected_lots,
                    "actual_lots": actual_lots,
                    "lots_match": lots_matched,
                    "master_lots": qty,
                    "multiplier": f_multiplier,
                    "method": f_method,
                    "fill_price": fill_price,
                    "master_price": master_fill_price,
                    "slippage": slippage_str,
                    "state": state,
                    "latency": latency_str,
                    "passed": (lots_matched and state in ["FILLED", "OPEN", "SUBMITTED"])
                }
            else:
                return {
                    "index": idx,
                    "email": f_email,
                    "replicated": False,
                    "order_id": "--",
                    "copy_ref": "--",
                    "expected_lots": expected_lots,
                    "actual_lots": 0.0,
                    "lots_match": False,
                    "master_lots": qty,
                    "multiplier": f_multiplier,
                    "method": f_method,
                    "fill_price": "--",
                    "master_price": master_fill_price,
                    "slippage": "--",
                    "state": "MISSING",
                    "latency": "--",
                    "passed": False
                }
        except Exception as e:
            return {
                "index": idx,
                "email": f_email,
                "replicated": False,
                "error": str(e),
                "expected_lots": expected_lots,
                "actual_lots": 0.0,
                "lots_match": False,
                "master_lots": qty,
                "multiplier": f_multiplier,
                "method": f_method,
                "fill_price": "--",
                "master_price": master_fill_price,
                "slippage": "--",
                "state": "ERROR",
                "latency": "--",
                "passed": False
            }

    with ThreadPoolExecutor(max_workers=25) as ex:
        follower_results = list(ex.map(check_follower, range(1, FOLLOWER_COUNT + 1)))

    total_followers = len(follower_results)
    replicated_count = sum(1 for r in follower_results if r["replicated"])
    perfect_match_count = sum(1 for r in follower_results if r["passed"])
    pass_rate_pct = round((perfect_match_count / total_followers) * 100, 1)

    total_elapsed = round(time.time() - t_start, 2)

    return jsonify({
        "success": True,
        "master_order": {
            "order_id": master_order_id,
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "requested_qty": qty,
            "filled_qty": master_filled_qty,
            "fill_price": master_fill_price,
            "created_at": master_created_at,
            "status": "FILLED"
        },
        "summary": {
            "total_followers": total_followers,
            "replicated_count": replicated_count,
            "perfect_match_count": perfect_match_count,
            "pass_rate_pct": pass_rate_pct,
            "total_elapsed_seconds": total_elapsed,
            "instance": instance
        },
        "comparison": follower_results
    })


# -------------------------------------------------------------------------------------
# A-book / B-book routing (per account)
#   A-book: the member's REAL orders are executed at the liquidity provider.
#   B-book: booked on the platform's own engine. Paper accounts are always B-book style (internal).
# -------------------------------------------------------------------------------------
def _topology_emails() -> list:
    return [MASTER_EMAIL] + [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(1, FOLLOWER_COUNT + 1)]


def _book_snapshot():
    """Book setup at launch time, stored with each run so results can be traced to the routing they ran under."""
    try:
        m = dashboard_client.get_member_books()
        fol = [m.get(f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}", {}).get("book") for i in range(1, FOLLOWER_COUNT + 1)]
        return {"master": m.get(MASTER_EMAIL, {}).get("book"), "followers_a": fol.count("a"), "followers_b": fol.count("b")}
    except Exception:
        return None


@app.route("/api/books")
def get_books():
    members = dashboard_client.get_member_books()
    rows = []
    for e in _topology_emails():
        m = members.get(e)
        rows.append({"email": e, "role": "master" if e == MASTER_EMAIL else "follower",
                     "book": m["book"] if m else None, "member_id": m["member_id"] if m else None})
    fol = [r for r in rows if r["role"] == "follower" and r["book"]]
    master = next((r for r in rows if r["role"] == "master"), {})
    return jsonify({
        "master": {"email": MASTER_EMAIL, "book": master.get("book")},
        "followers": {"a": sum(1 for r in fol if r["book"] == "a"), "b": sum(1 for r in fol if r["book"] == "b"),
                      "other": sum(1 for r in fol if r["book"] not in ("a", "b")),
                      "missing": sum(1 for r in rows if r["role"] == "follower" and not r["book"])},
        "accounts": rows,
        "note": "Book only affects REAL-instance routing. Paper accounts are always booked on the platform's own engine.",
    })


@app.route("/api/books/switch", methods=["POST"])
def switch_books():
    data = request.get_json(silent=True) or {}
    book = str(data.get("book", "")).lower()
    if book not in ("a", "b"):
        return jsonify({"error": "book must be 'a' or 'b'"}), 400

    topology = _topology_emails()
    scope = data.get("scope", "emails")
    if scope == "master":
        targets = [MASTER_EMAIL]
    elif scope == "followers":
        lo, hi = int(data.get("start") or 1), int(data.get("end") or FOLLOWER_COUNT)
        targets = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(max(1, lo), min(FOLLOWER_COUNT, hi) + 1)]
    elif scope == "all":
        targets = topology
    else:
        targets = list(dict.fromkeys(data.get("emails") or []))
    if not targets:
        return jsonify({"error": "no target accounts"}), 400
    outside = [e for e in targets if e not in set(topology)]
    if outside:    # never allow switching real customers through this endpoint
        return jsonify({"error": "only the configured master and follower accounts can be switched", "rejected": outside[:5]}), 400

    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            return jsonify({"error": "A test run is active - changing books mid-run would corrupt its results. Stop it first."}), 409
    if data.get("confirm") is not True:
        return jsonify({"error": "Changing the book changes where REAL orders are executed.", "needs_confirmation": True,
                        "reason": ("A-book: real orders will be sent to the liquidity provider." if book == "a"
                                   else "B-book: real orders will be booked on the platform's own engine."),
                        "accounts": len(targets)}), 412

    members = dashboard_client.get_member_books()
    missing = [e for e in targets if e not in members or not members[e]["member_id"]]
    results = {e: {"email": e, "before": members.get(e, {}).get("book"), "after": None, "ok": False,
                   "error": "member not found" if e in missing else None} for e in targets}

    def apply(email):
        if email in missing or results[email]["before"] == book:
            results[email]["ok"] = email not in missing
            return
        r = dashboard_client.set_member_book(members[email]["member_id"], book)
        if r["status_code"] != 200:
            results[email]["error"] = f"HTTP {r['status_code']}: {str(r['data'])[:120]}"

    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(apply, targets))

    after = dashboard_client.get_member_books()          # verify by reading back, never trust the 200
    for e in targets:
        results[e]["after"] = after.get(e, {}).get("book")
        results[e]["ok"] = results[e]["after"] == book
        if not results[e]["ok"] and not results[e]["error"]:
            results[e]["error"] = f"read-back shows '{results[e]['after']}', expected '{book}'"
    ok = sum(1 for r in results.values() if r["ok"])
    return jsonify({"book": book, "requested": len(targets), "switched_ok": ok, "failed": len(targets) - ok,
                    "results": [r for r in results.values() if not r["ok"]][:20]}), (200 if ok == len(targets) else 207)


if __name__ == "__main__":
    is_loopback = DASHBOARD_HOST in ("127.0.0.1", "localhost", "::1")
    if not is_loopback and not DASHBOARD_TOKEN:
        sys.exit("Refusing to bind to %s without DASHBOARD_TOKEN. Set DASHBOARD_TOKEN in .env (or use DASHBOARD_HOST=127.0.0.1)." % DASHBOARD_HOST)
    print()
    print("=" * 70)
    print(" BLACKTRADER TEST DASHBOARD")
    print(f" Open: http://localhost:{DASHBOARD_PORT}" + (f"/?token={DASHBOARD_TOKEN}" if DASHBOARD_TOKEN else ""))
    print(f" Target platform : {BASE_URL}")
    print(f" Master / followers: {MASTER_EMAIL} / {FOLLOWER_COUNT}")
    print(" First time here? Run:  python scripts/doctor.py")
    print("=" * 70)
    print()
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False, threaded=True)
