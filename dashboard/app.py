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
import stat
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from flask import Flask, Response, g, jsonify, make_response, render_template, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.doctor import run_checks, summarize as summarize_checks
from config.settings import (BASE_URL, DEFAULT_DOMAIN, DEFAULT_PREFIX, DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_TOKEN,
                             FOLLOWER_COUNT, MASTER_EMAIL, MASTER_ID)
from dashboard.suites import INSTANCES, SUITE_INDEX, build_command, effective_instance, is_real, needs_confirmation, public_registry
from test_suite.client import BlackTraderClient
from test_suite import symbol_coverage_runner as SC

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.errorhandler(Exception)
def _api_json_errors(e):
    """Any unhandled error on /api/* returns JSON (the UI parses JSON), never Flask's HTML 500 page."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"error": e.description}), e.code
        return e
    if request.path.startswith("/api/"):
        import requests as _rq
        unreachable = isinstance(e, (_rq.exceptions.ConnectionError, _rq.exceptions.Timeout))
        return jsonify({"error": ("Platform unreachable: " if unreachable else "Server error: ") + str(e)[:200]}), (502 if unreachable else 500)
    raise e

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


_LOG_LOCK = threading.Lock()
_LOG_SNAPSHOT = None


def _live_log_snapshot(path: Path) -> tuple:
    global _LOG_SNAPSHOT
    with _LOG_LOCK, path.open(encoding="utf-8", errors="replace") as log:
        st = os.fstat(log.fileno())
        fingerprint = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        if _LOG_SNAPSHOT is not None and _LOG_SNAPSHOT[0] == fingerprint:
            return _LOG_SNAPSHOT[1]

        tail = deque(maxlen=300)
        passed = failed = total = 0
        for line in log:
            tail.append(line)
            passed += line.count("[PASS]")
            failed += line.count("[FAIL]")
            total += 1

        snapshot = ("".join(tail), total, passed, failed)
        _LOG_SNAPSHOT = (fingerprint, snapshot)
        return snapshot


def count_log_results(path: Path) -> tuple:
    """Count [PASS] / [FAIL] markers using the shared live log snapshot."""
    try:
        _, _, passed, failed = _live_log_snapshot(path)
    except OSError:
        return 0, 0
    return passed, failed


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
    try:
        logs, total, _, _ = _live_log_snapshot(LATEST_LOG_FILE)
        return jsonify({"logs": logs, "total_lines": total})
    except FileNotFoundError:
        return jsonify({"logs": ""})
    except OSError as e:
        return jsonify({"logs": f"Error reading logs: {e}"})


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
                        "reason": ("Runs against the REAL instance." if is_real(effective_instance(suite, params))
                                   else "Closes positions and cancels orders.")}), 412
    with REGRESSION_LOCK:
        if REGRESSION.get("status") == "RUNNING":
            return jsonify({"error": "A regression is running - stop it first (Regression tab)."}), 409
    body, code = _launch(suite_key, suite, params)
    return jsonify(body), code


def _launch(suite_key: str, suite: dict, params: dict):
    """Start one suite as a subprocess (one at a time). Returns (json body, http code)."""
    global RUNNING_PROCESS
    cmd = build_command(suite, params, {"follower_count": FOLLOWER_COUNT})
    title = suite["name"]
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + suite_key

    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            return {"error": "A test suite is already running.", "current": CURRENT_TASK["name"]}, 409

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

    return {"message": f"Launched {title}", "pid": proc.pid, "suite": suite_key, "run_id": run_id}, 200


# -------------------------------------------------------------------------------------
# Regression: run several safe suites one after another, then one shareable report
# -------------------------------------------------------------------------------------
REGRESSION_LOCK = threading.Lock()
REGRESSION: dict = {"status": "IDLE"}
REGRESSION_DIR = BASE_DIR / "reports" / "regressions"
REGRESSION_DIR.mkdir(parents=True, exist_ok=True)
REGRESSION_PRESETS = {
    "smoke": ["e2e", "symbols_sample"],
    "standard": ["e2e", "symbols_sample", "copy_complex", "pending_trigger_race", "accounting", "security"],
    "full": ["e2e", "symbols_sample", "multiplier", "symmetry", "copy_complex", "breakpoint", "race", "extreme",
             "pending_trigger_race", "pending", "advanced", "state", "extended", "accounting", "security", "ui_journey"],
}


def _history_entry(run_id):
    with HISTORY_LOCK:
        return next((h for h in _load_history() if h.get("id") == run_id), {})


def _latest_evidence(prefix: str, since: str):
    """Newest evidence JSON whose name starts with prefix and was written during this regression."""
    cands = sorted(EVIDENCE_DIR.glob(prefix + "_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in cands:
        if datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds") >= since:
            return p
    return None


def _regression_worker(reg_id: str):
    while True:
        with REGRESSION_LOCK:
            if REGRESSION.get("id") != reg_id or REGRESSION["status"] != "RUNNING":
                return
            step = next((s for s in REGRESSION["steps"] if s["status"] == "QUEUED"), None)
            if step is None:
                REGRESSION.update(status="DONE", ended_at=datetime.now().isoformat(timespec="seconds"))
                _save_regression()
                return
            step["status"] = "RUNNING"
            params = dict(REGRESSION["params"])
        suite = SUITE_INDEX[step["suite"]]
        body, code = _launch(step["suite"], suite, params)
        if code != 200:
            with REGRESSION_LOCK:
                step.update(status="ERROR", error=body.get("error"))
            continue
        with REGRESSION_LOCK:
            step.update(run_id=body["run_id"], started_at=datetime.now().isoformat(timespec="seconds"))
        while True:                                     # wait for this suite to finish
            time.sleep(2)
            with PROCESS_LOCK:
                busy = RUNNING_PROCESS is not None and RUNNING_PROCESS.poll() is None and CURRENT_TASK.get("run_id") == body["run_id"]
            if not busy:
                break
        time.sleep(1.5)                                 # let monitor_process write the history entry
        h = _history_entry(body["run_id"])
        with REGRESSION_LOCK:
            step.update(status=h.get("status", "UNKNOWN"), passed=h.get("passed"), failed=h.get("failed"),
                        duration_sec=h.get("duration_sec"), exit_code=h.get("exit_code"))
            if step["status"] == "TERMINATED":
                REGRESSION["status"] = "STOPPED"
            _save_regression()


def _save_regression():
    try:
        (REGRESSION_DIR / f"{REGRESSION['id']}.json").write_text(json.dumps(REGRESSION, indent=1, default=str), encoding="utf-8")
    except Exception:
        pass


@app.route("/api/regression", methods=["GET"])
def regression_status():
    with REGRESSION_LOCK:
        cur = json.loads(json.dumps(REGRESSION, default=str))
    past = sorted((p.stem for p in REGRESSION_DIR.glob("reg_*.json")), reverse=True)[:20]
    if not cur.get("id") and past:                 # after a dashboard restart, show the last saved regression
        try:
            cur = json.loads((REGRESSION_DIR / f"{past[0]}.json").read_text(encoding="utf-8"))
            if cur.get("status") == "RUNNING":     # the server stopped while it ran
                cur["status"] = "INTERRUPTED"
        except Exception:
            cur = {"status": "IDLE"}
    safe = [{"key": s["key"], "name": s["name"], "minutes": s.get("minutes"), "category": s["category"]}
            for s in public_registry() if s["risk"] == "safe" and s["key"] not in ("symbols_all", "jmeter")]
    return jsonify({"current": cur, "past": past, "presets": REGRESSION_PRESETS, "suites": safe})


@app.route("/api/regression/start", methods=["POST"])
def regression_start():
    data = request.get_json(silent=True) or {}
    # an explicit list (even an empty one) is taken as-is; the preset only applies when no list is sent
    keys = data["suites"] if isinstance(data.get("suites"), list) else REGRESSION_PRESETS.get(data.get("preset"), [])
    keys = [k for k in dict.fromkeys(keys) if k in SUITE_INDEX]
    unsafe = [k for k in keys if SUITE_INDEX[k]["risk"] != "safe"]
    if unsafe:
        return jsonify({"error": f"regressions run non-destructive suites only; remove {unsafe}"}), 400
    if not keys:
        return jsonify({"error": "pick at least one suite"}), 400
    refused = _account_change_refused({"instance": "real", "confirm": data.get("confirm")})
    if refused:
        return refused
    p = data.get("params") or {}
    try:
        start, end = max(1, int(p.get("start", 1))), min(FOLLOWER_COUNT, int(p.get("end", 10)))
    except (TypeError, ValueError):
        return jsonify({"error": "bad follower range"}), 400
    params = {"instance": "real", "start": min(start, end), "end": max(start, end), "lot": p.get("lot", 0.1)}
    with REGRESSION_LOCK, PROCESS_LOCK:
        if REGRESSION.get("status") == "RUNNING":
            return jsonify({"error": "A regression is already running"}), 409
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            return jsonify({"error": "A suite is running - wait for it or stop it first"}), 409
        reg_id = "reg_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        REGRESSION.clear()
        REGRESSION.update(id=reg_id, status="RUNNING", started_at=datetime.now().isoformat(timespec="seconds"), params=params,
                          name=data.get("name") or "", steps=[{"suite": k, "name": SUITE_INDEX[k]["name"], "status": "QUEUED"} for k in keys])
    threading.Thread(target=_regression_worker, args=(reg_id,), daemon=True).start()
    return jsonify({"message": f"Regression started: {len(keys)} suites", "id": reg_id})


@app.route("/api/regression/stop", methods=["POST"])
def regression_stop():
    with REGRESSION_LOCK:
        if REGRESSION.get("status") != "RUNNING":
            return jsonify({"message": "No regression is running."})
        REGRESSION["status"] = "STOPPED"
        for s in REGRESSION["steps"]:
            if s["status"] == "QUEUED":
                s["status"] = "SKIPPED"
        _save_regression()
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            CURRENT_TASK["status"] = "TERMINATED"
            RUNNING_PROCESS.terminate()
    return jsonify({"message": "Regression stopped. Run Emergency Teardown if a suite was cut off mid-trade."})


@app.route("/api/regression/<reg_id>/report")
def regression_report(reg_id):
    """Self-contained HTML report of one regression, for attaching to a ticket or sending to the team."""
    if not re.fullmatch(r"reg_\d{8}_\d{6}", reg_id):
        return jsonify({"error": "bad id"}), 400
    p = REGRESSION_DIR / f"{reg_id}.json"
    with REGRESSION_LOCK:
        reg = json.loads(json.dumps(REGRESSION, default=str)) if REGRESSION.get("id") == reg_id else None
    if reg is None:
        if not p.exists():
            return jsonify({"error": "not found"}), 404
        reg = json.loads(p.read_text(encoding="utf-8"))
    from html import escape as h
    ok = lambda s: s.get("status") == "COMPLETED" and not s.get("failed")
    steps_html = "".join(
        f"<tr><td>{h(s['name'])}</td><td class='{'ok' if ok(s) else ('bad' if s.get('status') in ('FAILED', 'ERROR') or s.get('failed') else 'muted')}'>"
        f"{h(str(s.get('status')))}</td><td>{s.get('passed') if s.get('passed') is not None else ''}</td>"
        f"<td>{s.get('failed') if s.get('failed') is not None else ''}</td><td>{h(str(s.get('duration_sec') or ''))}s</td>"
        f"<td><code>{h(str(s.get('run_id') or ''))}</code></td></tr>" for s in reg.get("steps", []))
    extra = ""
    e2e = _latest_evidence("e2e_evidence", reg.get("started_at", ""))
    if e2e:
        d = json.loads(e2e.read_text(encoding="utf-8"))
        rows = "".join(f"<tr><td>{h(r['id'])}</td><td>{h(r['title'])}</td><td class='{'ok' if r['status'] == 'PASS' else 'bad' if r['status'] in ('FAIL', 'ERROR') else 'muted'}'>"
                       f"{h(r['status'])}</td><td>{'<br>'.join(h(f['severity'] + ': ' + f['message']) for f in r['findings'] if f['severity'] != 'INFO')}</td></tr>"
                       for r in d.get("results", []))
        extra += f"<h2>End-to-End steps ({h(d.get('verdict', ''))})</h2><table><tr><th>Step</th><th>Check</th><th>Result</th><th>Findings</th></tr>{rows}</table>"
    sym = _latest_evidence("symbols_evidence", reg.get("started_at", ""))
    if sym:
        d = json.loads(sym.read_text(encoding="utf-8"))
        rows = "".join(f"<tr><td>{h(g)}</td><td>{v['PASS']}</td><td>{v['FAIL']}</td><td>{v['WARN']}</td><td>{v['SKIP']}</td></tr>"
                       for g, v in d.get("groups", {}).items())
        extra += f"<h2>Market types ({h(d.get('verdict', ''))})</h2><table><tr><th>Market group</th><th>Pass</th><th>Fail</th><th>Warn</th><th>Closed</th></tr>{rows}</table>"
    total_f = sum(int(s.get("failed") or 0) for s in reg.get("steps", []))
    bad = [s for s in reg.get("steps", []) if s.get("status") in ("FAILED", "ERROR", "TERMINATED") or s.get("failed")]
    verdict = "FAIL" if bad else ("PASS" if reg.get("status") == "DONE" else str(reg.get("status")))
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Regression {h(reg_id)}</title><style>
:root{{--bg:#fff;--fg:#14161a;--mut:#666;--line:#ddd;--ok:#0a7a45;--bad:#b42318}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111316;--fg:#e8e8ea;--mut:#9a9aa2;--line:#2a2d33;--ok:#3ccf8e;--bad:#f87171}}}}
body{{font:14px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:1000px;margin:0 auto;padding:24px 16px}}
table{{border-collapse:collapse;width:100%;margin:8px 0 24px;display:block;overflow-x:auto}}th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:12px;color:var(--mut);text-transform:uppercase}}.ok{{color:var(--ok);font-weight:700}}.bad{{color:var(--bad);font-weight:700}}.muted{{color:var(--mut)}}
.v{{font-size:28px;font-weight:800}}code{{font-size:12px}}</style></head><body>
<div class="v {'ok' if verdict == 'PASS' else 'bad'}">{h(verdict)}</div>
<p>Regression <code>{h(reg_id)}</code> {h(reg.get('name') or '')}<br>Started {h(reg.get('started_at', ''))} · ended {h(str(reg.get('ended_at') or '-'))}<br>
Platform {h(BASE_URL)} · instance {h(reg.get('params', {}).get('instance', ''))} · followers {reg.get('params', {}).get('start')}-{reg.get('params', {}).get('end')}
 · master {h(MASTER_EMAIL)} · {total_f} failed checks in {len(bad)} suite(s)</p>
<h2>Suites</h2><table><tr><th>Suite</th><th>Status</th><th>Passed</th><th>Failed</th><th>Time</th><th>Run</th></tr>{steps_html}</table>{extra}
<p class="muted">Each suite's full log is in the Test Hub (History tab) under its run id; evidence files are in reports/evidence/.</p></body></html>"""
    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    if request.args.get("download"):
        resp.headers["Content-Disposition"] = f'attachment; filename="{reg_id}.html"'
    return resp


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



# --------------------------------------------------------------------------- platform overview (read-only)
_PLATFORM_CACHE: dict = {"at": 0.0, "data": None}


@app.route("/api/platform")
def platform_overview():
    """What the platform offers right now: instances (hedging/netting), copy/MAM/PAMM directories, plan modules, link counts."""
    if _PLATFORM_CACHE["data"] and time.time() - _PLATFORM_CACHE["at"] < 30 and request.args.get("refresh") != "true":
        return jsonify(_PLATFORM_CACHE["data"])
    c, master = dashboard_client, MASTER_EMAIL
    out: dict = {"success": True, "master": master, "instances": [], "directories": {}, "plans": {}, "links": {}, "errors": []}
    try:
        out["instances"] = [{k: i.get(k) for k in ("slug", "name", "mode", "netting", "real_money")} for i in c.get_instances(master)]
    except Exception as e:
        out["errors"].append(f"instances: {e}")
    for kind in c.SOCIAL_KINDS:
        try:
            ms = c.social_masters(master, kind, "real")
            out["directories"][kind] = {
                "count": len(ms), "kinds": sorted({m.get("kind") for m in ms if m.get("kind")}),
                "top": [{"name": m.get("name"), "rank": (m.get("stats") or {}).get("rank"), "growth": (m.get("stats") or {}).get("growth"),
                         "followers": (m.get("stats") or {}).get("followers"), "fund": (m.get("stats") or {}).get("fund"),
                         "drawdown": (m.get("stats") or {}).get("drawdown"), "share_percent": m.get("share_percent")} for m in ms[:5]]}
        except Exception as e:
            out["errors"].append(f"{kind}: {e}")
    try:
        cfg = c.admin_get("config")["data"].get("plan_modules", {})
        out["plans"] = {plan: sorted(set(mods) & {"copytrading", "mam", "pamm", "ib", "wallet", "alerts", "algo", "backtest"}) for plan, mods in cfg.items()}
    except Exception as e:
        out["errors"].append(f"plans: {e}")
    try:
        links = c.get_copy_followers(master, "real", active_only=False)
        by: dict = {}
        for l in links:
            key = f"{l.get('instance')}/{l.get('status')}"
            by[key] = by.get(key, 0) + 1
        out["links"] = by
        out["master_book"] = (c.get_member_books().get(master) or {}).get("book")
    except Exception as e:
        out["errors"].append(f"links: {e}")
    _PLATFORM_CACHE.update(at=time.time(), data=out)
    return jsonify(out)


@lru_cache(maxsize=256)
def _evidence_counts(path: Path, fingerprint: tuple) -> dict:
    counts = {"passed": 0, "failed": 0, "warned": 0}
    _count_statuses(json.loads(path.read_text(encoding="utf-8")), counts)
    return counts


@app.route("/api/summary")
def get_summary():
    families = {}
    for p in EVIDENCE_DIR.glob("*.json"):
        if p.stem in ("baseline_snapshot",) or p.stem.startswith(("jmeter_performance", "jmeter_load_test")):
            continue
        m = _FAMILY_RE.match(p.stem)
        fam = m.group("fam") if m else p.stem
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        if fam not in families or st.st_mtime_ns > families[fam][1].st_mtime_ns:
            families[fam] = (p, st)
    rows = []
    for fam, (p, st) in families.items():
        try:
            acc = _evidence_counts(p, (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
        except (OSError, ValueError, RecursionError):
            continue
        mt = st.st_mtime
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


_E2E_NAME = re.compile(r"^e2e_evidence_\d{8}_\d{6}\.json$")


@app.route("/api/e2e/latest")
def get_e2e_report():
    """Latest (or ?file=) End-to-End evidence, parsed, plus the list of earlier E2E runs for the picker."""
    files = sorted((p for p in EVIDENCE_DIR.glob("e2e_evidence_*.json") if _E2E_NAME.match(p.name)), key=lambda p: p.name, reverse=True)
    runs = []
    for p in files[:30]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            runs.append({"file": p.name, "verdict": d.get("verdict"), "started": d.get("started"), "instance": d.get("instance"),
                         "followers_range": d.get("followers_range"), "tally": d.get("tally")})
        except Exception:
            runs.append({"file": p.name, "verdict": "UNREADABLE"})
    wanted = request.args.get("file")
    if wanted and not _E2E_NAME.match(wanted):
        return jsonify({"error": "bad file name"}), 400
    target = (EVIDENCE_DIR / wanted) if wanted else (files[0] if files else None)
    if target is None or not target.exists():
        return jsonify({"report": None, "file": None, "runs": runs})
    try:
        report = json.loads(target.read_text(encoding="utf-8"))
    except Exception as e:
        return jsonify({"error": f"could not read {target.name}: {e}"}), 500
    md = target.with_suffix(".md")
    return jsonify({"report": report, "file": target.name, "markdown": md.name if md.exists() else None, "runs": runs})


_UNIVERSE_CACHE = {"t": 0.0, "symbols": None, "types": None}


def _universe():
    """Symbol list + market schedule from the platform's symbol_url, cached for an hour."""
    if _UNIVERSE_CACHE["symbols"] is None or time.time() - _UNIVERSE_CACHE["t"] > 3600:
        import requests as _rq
        data = _rq.get(SC.symbol_url(), timeout=60).json()["data"]
        SC._UNIVERSE = None                         # refresh the runner-side cache too
        _UNIVERSE_CACHE.update(t=time.time(), symbols=SC.load_symbols(), types=data.get("typeMap", {}))
    return _UNIVERSE_CACHE["symbols"], _UNIVERSE_CACHE["types"]


@app.route("/api/symbols/list")
def list_symbols():
    """Every tradable symbol with its market group and size rules (for the Dispatch symbol picker)."""
    try:
        syms, _ = _universe()
    except Exception as e:
        return jsonify({"error": f"symbol list unavailable: {e}", "symbols": []}), 502
    return jsonify({"symbols": [{"sym": s["sym"], "group": s["group"], "type": s["type"], "min": s["min_qty"], "step": s["step"],
                                 "max": s["max_qty"], "contract": s["csize"]} for s in syms]})


def market_open(sched: dict, now: datetime) -> bool:
    """Is a market type in session at `now` (UTC), per the platform's typeMap schedule."""
    days = sched.get("days") or []
    start, end = sched.get("session_start"), sched.get("session_end")
    day = now.strftime("%A")
    if not start or not end:                        # 24h on the listed days
        return day in days
    mins = now.hour * 60 + now.minute
    s = int(start[:2]) * 60 + int(start[3:5])
    e = int(end[:2]) * 60 + int(end[3:5])
    if s < e:                                       # same-day session
        return day in days and s <= mins < e
    # overnight session (e.g. FOREX 21:05 -> 21:00): open from `start` on a listed day until `end` the next day
    yesterday = (now - timedelta(days=1)).strftime("%A")
    return (day in days and mins >= s) or (yesterday in days and mins < e)


@app.route("/api/markets")
def markets_status():
    """Which market types are in session now (UTC, from the platform schedule) and how many symbols each has."""
    try:
        syms, types = _universe()
    except Exception as e:
        return jsonify({"error": f"symbol list unavailable: {e}"}), 502
    now = datetime.now(timezone.utc)
    counts: dict = {}
    for s in syms:
        counts[s["type"]] = counts.get(s["type"], 0) + 1
    rows = []
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        sch = types.get(t, {})
        rows.append({"type": t, "symbols": n, "open": market_open(sch, now) if sch else None,
                     "session_utc": f"{sch.get('session_start') or '00:00'}-{sch.get('session_end') or '24:00'}",
                     "days": [d[:3] for d in (sch.get("days") or [])], "data_feed": t in SC.DATA_FEED_TYPES})
    open_syms = sum(r["symbols"] for r in rows if r["open"])
    return jsonify({"now_utc": now.isoformat(timespec="minutes"), "markets": rows, "open_symbols": open_syms, "total_symbols": len(syms),
                    "note": "From the platform's published schedule (typeMap). Holidays are not included."})


_SYM_NAME = re.compile(r"^symbols_evidence_\d{8}_\d{6}\.json$")


@app.route("/api/symbols/latest")
def get_symbols_report():
    """Latest Symbol Coverage run: per market group tally + the problem symbols (not all ~3 600 rows)."""
    files = sorted((p for p in EVIDENCE_DIR.glob("symbols_evidence_*.json") if _SYM_NAME.match(p.name)), key=lambda p: p.name, reverse=True)
    if not files:
        return jsonify({"report": None})
    p = files[0]
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return jsonify({"error": f"could not read {p.name}: {e}"}), 500
    problems = [r for r in d.get("results", []) if r.get("status") in ("FAIL", "WARN")]
    keep = {k: d.get(k) for k in ("verdict", "started", "duration_sec", "instance", "mode", "universe", "tested",
                                   "followers_range", "followers_linked", "tally", "groups", "symbol_source")}
    md = p.with_suffix(".md")
    return jsonify({"report": {**keep, "problems": problems[:200], "problem_count": len(problems)}, "file": p.name,
                    "markdown": md.name if md.exists() else None})


@app.route("/api/reports")
def get_reports():
    reports = []
    seen_files = set()
    search_dirs = [BASE_DIR / "reports", BASE_DIR / "reports" / "evidence"]

    for d in search_dirs:
        candidates = []
        try:
            for f in d.iterdir():
                if f.suffix not in (".json", ".md", ".csv", ".jtl") or f.name.startswith("baseline") or f.name in seen_files:
                    continue
                try:
                    st = f.stat()
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(st.st_mode):
                    candidates.append((f, st))
        except FileNotFoundError:
            continue
        for f, st in sorted(candidates, key=lambda entry: entry[1].st_mtime_ns, reverse=True):
            seen_files.add(f.name)
            mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            category = "Other"
            if f.name.startswith("e2e"):
                category = "End-to-End"
            elif f.name.startswith("symbols"):
                category = "Symbol Coverage"
            elif "jmeter" in f.name:
                category = "JMeter Load Test"
            elif "real_money" in f.name:
                category = "Real Money Mode"
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
                "size_kb": round(st.st_size / 1024, 1),
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


def get_cached_active_links(instance: str = "real", force_refresh: bool = False) -> dict:
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
            if not fn or link.get("instance") != instance:   # the follows list covers EVERY instance
                continue
            prev = links_by_follower.get(fn)
            # a follower can have several records (ended + active); an ACTIVE one always wins,
            # otherwise keep the most recently created one
            if prev is None:
                links_by_follower[fn] = link
            else:
                p_act, l_act = prev.get("status") == "active", link.get("status") == "active"
                if (l_act and not p_act) or (l_act == p_act and (link.get("created_at") or "") > (prev.get("created_at") or "")):
                    links_by_follower[fn] = link
        ACTIVE_LINKS_CACHE["data"] = links_by_follower
        ACTIVE_LINKS_CACHE["timestamp"] = now
        ACTIVE_LINKS_CACHE["instance"] = instance
        return links_by_follower
    except Exception as e:
        print(f"Error fetching active links: {e}")
        return ACTIVE_LINKS_CACHE["data"] or {}


FOLLOWER_FUNDS_CACHE = {"data": {}, "timestamp": 0, "instance": None}


def get_cached_follower_funds(emails: list, instance: str, force_refresh: bool = False) -> dict:
    """Each follower's OWN funds ({email: {balance, equity}}), fetched concurrently and cached ~10s."""
    now = time.time()
    c = FOLLOWER_FUNDS_CACHE
    if not force_refresh and c["instance"] == instance and c["data"] and now - c["timestamp"] < 10:
        return c["data"]
    out = {}
    try:
        res = dashboard_client.fetch_all_followers_positions(emails, instance=instance)
        for e, r in res.items():
            f = (r or {}).get("funds") or {}
            if f:
                out[e] = f
    except Exception as e:
        print(f"Error fetching follower funds: {e}")
        return c["data"] if c["instance"] == instance else {}
    c.update({"data": out, "timestamp": now, "instance": instance})
    return out


def _fmt_money(v: float) -> str:
    return f"{v/1e6:,.2f}".rstrip("0").rstrip(".") + "M" if abs(v) >= 1e6 else f"{v:,.2f}"


@app.route("/api/followers")
def get_followers_list():
    from test_suite.baseline import get_expected_multiplier
    instance = request.args.get("instance", "real")
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

    all_emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(1, FOLLOWER_COUNT + 1)]
    funds_by_email = get_cached_follower_funds(all_emails, instance, force_refresh)

    followers = []
    for i in range(1, FOLLOWER_COUNT + 1):
        f_prefix = f"{DEFAULT_PREFIX}{i}"
        link = active_links.get(f_prefix, {})
        f_funds = funds_by_email.get(f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}")
        if f_funds:
            f_bal = float(f_funds.get("balance", 0) or 0)
            f_eq = float(f_funds.get("equity", f_bal) or f_bal)
            bal_txt, eq_txt = _fmt_money(f_bal), _fmt_money(f_eq)
        else:  # funds not available - say so instead of showing the master's numbers
            bal_txt = eq_txt = "--"

        if link and "multiplier" in link:
            mult = float(link.get("multiplier", 1.0))
            f_method = link.get("method", detected_mode)
            link_status = link.get("status", "ACTIVE").upper()
        else:
            mult = get_expected_multiplier(i)
            f_method = detected_mode
            link_status = "INACTIVE"

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
            "balance": bal_txt,
            "equity": eq_txt,
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
        instance = request.args.get("instance", "real")
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
        instance = request.args.get("instance", "real")
        res = dashboard_client.bulk_squareoff(email, instance=instance)
        return jsonify({"message": f"Positions closed for {email}", "data": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _account_change_refused(data: dict):
    """Account changes corrupt a running suite, and on REAL they touch real-money accounts: refuse unless safe."""
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            return jsonify({"error": "A test run is active - changing accounts now would corrupt its results. Wait or stop it."}), 409
    if is_real(data.get("instance")) and data.get("confirm") is not True:
        return jsonify({"error": "Changing REAL accounts needs confirmation.", "needs_confirmation": True}), 412
    return None


@app.route("/api/account/<email>/copy_settings", methods=["POST"])
def update_account_copy_settings(email):
    """Update copy trading settings (mode, multiplier) for a single follower."""
    data = request.json or {}
    refused = _account_change_refused(data)
    if refused:
        return refused
    mode = data.get("mode", "multiplier")
    instance = data.get("instance", "real")
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
    refused = _account_change_refused(data)
    if refused:
        return refused
    mode = data.get("mode", "multiplier")
    instance = data.get("instance", "real")
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
            # Re-submitting the follow updates the existing link in place. We do NOT unfollow first: a failed
            # follow after an unfollow would drop the follower for good .
            res = dashboard_client.follow_master(email, master_id, instance=instance, method=mode,
                                                 multiplier=mult, reverse=False, copy_mode="public")
            err = None if res.get("status_code") == 200 else f"HTTP {res.get('status_code')}: {str(res.get('data'))[:140]}"
            return {"email": email, "success": err is None, "multiplier": mult, "error": err}
        except Exception as e:
            return {"email": email, "success": False, "multiplier": mult, "error": str(e)}

    with ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(update_follower, follower_emails))

    global ACTIVE_LINKS_CACHE
    ACTIVE_LINKS_CACHE["data"] = None
    ACTIVE_LINKS_CACHE["timestamp"] = 0

    # verify by reading the links back - a 200 alone proves nothing
    try:
        live = get_cached_active_links(instance=instance, force_refresh=True)
    except Exception:
        live = {}
    for r in results:
        if not r["success"]:
            continue
        lk = live.get(r["email"].split("@")[0]) or {}
        if lk.get("status") != "active" or lk.get("method") != mode or abs(float(lk.get("multiplier", -1)) - r["multiplier"]) > 1e-9:
            r["success"] = False
            r["error"] = (f"platform accepted the request but the link reads {lk.get('method')} {lk.get('multiplier')}x "
                          f"({lk.get('status') or 'no link'}), expected {mode} {r['multiplier']}x")

    success_count = sum(1 for r in results if r["success"])
    total = len(follower_emails)
    if success_count:
        ACTIVE_LINKS_CACHE["forced_mode"] = mode
    failures = [r for r in results if not r["success"]]
    body = {
        "message": f"Updated {success_count} / {total} followers to {mode.upper()} mode ({custom_mult if not tier_based else 'Tier-Based'}x) on {instance.upper()}.",
        "mode": mode, "multiplier": custom_mult, "tier_based": tier_based,
        "success_count": success_count, "total": total, "instance": instance,
        "failures": [{"email": r["email"], "error": r["error"]} for r in failures[:10]],
    }
    if success_count == 0:
        body["error"] = f"No follower was updated on {instance.upper()}. " + (failures[0]["error"] if failures else "")
        return jsonify(body), 409
    return jsonify(body), (200 if not failures else 207)


@app.route("/api/accounts/sync_balance", methods=["POST"])
def sync_accounts_balance():
    """Set identical balance across Master and all 100 followers on selected instance."""
    from concurrent.futures import ThreadPoolExecutor
    data = request.json or {}
    refused = _account_change_refused(data)
    if refused:
        return refused
    instance = data.get("instance", "real")
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
        FOLLOWER_FUNDS_CACHE["timestamp"] = 0
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
        instance = request.args.get("instance", "real")
        res = dashboard_client.squareoff_position(email, market_order_id, instance=instance)
        return jsonify({"message": f"Position {market_order_id} closed for {email}", "data": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/live_activity")
def get_live_activity():
    try:
        instance = request.args.get("instance", "real")
        recent_events = []
        master_ords = dashboard_client.get_orders(MASTER_EMAIL, instance=instance).get("orders", [])
        for o in master_ords[:20]:
            raw_time = o.get("created_at", "")
            clean_time = raw_time
            if "T" in raw_time:
                clean_time = raw_time.split("T")[1].replace("Z", "")[:8]
            recent_events.append({
                "account": f"{MASTER_EMAIL.split('@')[0]} (Master Trader)",
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
        instance = request.args.get("instance", "real")
        tape = []
        
        # 1. Master orders
        master_ords = dashboard_client.get_orders(MASTER_EMAIL, instance=instance).get("orders", [])
        for o in master_ords[:15]:
            raw_time = o.get("created_at", "")
            clean_time = raw_time
            if "T" in raw_time:
                clean_time = raw_time.split("T")[1].replace("Z", "")[:8]
            tape.append({
                "account": f"Master ({MASTER_EMAIL.split('@')[0]})",
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

        # 2. Sample followers spread across the configured range (one per multiplier tier by default)
        picks = sorted({i for i in (1, FOLLOWER_COUNT // 4 + 1, FOLLOWER_COUNT // 2 + 1, 3 * FOLLOWER_COUNT // 4 + 1) if 1 <= i <= FOLLOWER_COUNT})
        sample_followers = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in picks]
        for f_email in sample_followers:
            f_ords = dashboard_client.get_orders(f_email, instance=instance).get("orders", [])
            f_name = f_email.split("@")[0]
            for o in f_ords[:5]:
                raw_time = o.get("created_at", "")
                clean_time = raw_time
                if "T" in raw_time:
                    clean_time = raw_time.split("T")[1].replace("Z", "")[:8]
                tape.append({
                    "account": f"Follower {f_name.replace(DEFAULT_PREFIX, '#')}",
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


@app.route("/api/order/dispatch_and_verify", methods=["POST"])
def dispatch_and_verify():
    """Place ONE master order and verify every linked follower copied it.

    MARKET: compares each follower's net position on the symbol before/after (expected change = qty x factor, factor
            from the follower's own copy link: multiplier / balance / equity ratio, negative when reverse).
    LIMIT / STOP: checks every follower received a pending copy that references the master order.
    Followers without an active copy link are listed as NOT LINKED and left out of the pass rate.
    """
    data = request.get_json(silent=True) or {}
    instance = data.get("instance") if data.get("instance") in INSTANCES else "real"
    symbol = str(data.get("symbol") or "BINANCE:BTCUSDT.P").strip()
    side = str(data.get("side", "BUY")).upper()
    order_type = str(data.get("type", "MARKET")).upper()
    if side not in ("BUY", "SELL") or order_type not in ("MARKET", "LIMIT", "STOP"):
        return jsonify({"success": False, "error": "side must be BUY/SELL and type MARKET/LIMIT/STOP"}), 400

    def num(k):
        try:
            v = data.get(k)
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
    qty, price, tp, sl = num("qty"), num("price"), num("tp"), num("sl")
    if not qty or qty <= 0:
        return jsonify({"success": False, "error": "quantity must be > 0"}), 400
    if order_type != "MARKET" and not price:
        return jsonify({"success": False, "error": f"{order_type} orders need a price"}), 400
    if is_real(instance) and data.get("confirm") is not True:
        return jsonify({"success": False, "needs_confirmation": True, "error": "Dispatch on REAL needs confirmation"}), 412
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            return jsonify({"success": False, "error": "A test run is active - a manual order would corrupt its results. Wait or stop it."}), 409

    emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(1, FOLLOWER_COUNT + 1)]
    linked, factor = SC.linked_followers(dashboard_client, MASTER_EMAIL, MASTER_ID, emails, instance)
    links = get_cached_active_links(instance=instance, force_refresh=True)
    linked_set = set(linked)

    def net(positions):
        return sum((1 if p.get("side") == "BUY" else -1) * float(p.get("net_qty") or 0) for p in positions if p.get("symbol") == symbol)
    before = {e: d.get("positions", []) for e, d in dashboard_client.fetch_all_followers_positions(linked, instance=instance).items()}
    before_ids = {e: {p.get("position_id") for p in ps} for e, ps in before.items()}

    t0 = time.time()
    res = dashboard_client.place_order(MASTER_EMAIL, symbol=symbol, side=side, order_type=order_type, qty=qty, price=price,
                                       tp=tp, sl=sl, instance=instance)
    body = res.get("data")
    if res.get("status_code") != 200 or not isinstance(body, dict):
        msg = body.get("error") if isinstance(body, dict) else str(body)
        return jsonify({"success": False, "error": f"Master order rejected (HTTP {res.get('status_code')}): {str(msg)[:300]}",
                        "master_response": res}), 400
    mo, mp = body.get("order") or {}, body.get("position") or {}
    master_ids = {i for i in (mo.get("order_id"), mo.get("market_order_id")) if i}
    master_price = mp.get("avg_entry_price") or mo.get("avg_fill_price") or price
    master_time = mo.get("created_at")
    sign = 1 if side == "BUY" else -1

    def ts(s):
        """Server timestamps carry up to 9 fractional digits ('...07.75168207Z'); trim to microseconds."""
        m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?", str(s or ""))
        if not m:
            return None
        return datetime.fromisoformat(m.group(1) + "." + (m.group(2) or "0")[:6].ljust(6, "0"))

    rows = {}
    if order_type == "MARKET":
        deadline = time.time() + 20
        while True:
            after = {e: d.get("positions", []) for e, d in dashboard_client.fetch_all_followers_positions(linked, instance=instance).items()}
            for e in linked:
                exp = qty * factor[e] * sign
                got = net(after[e]) - net(before[e])
                new = [p for p in after[e] if p.get("position_id") not in before_ids[e] and p.get("symbol") == symbol]
                ok = abs(got - exp) <= max(1e-6, 0.01 * abs(exp))
                lat = None
                if new and ts(new[0].get("opened_at")) and ts(master_time):
                    lat = (ts(new[0]["opened_at"]) - ts(master_time)).total_seconds()
                rows[e] = {"replicated": bool(new) or abs(got) > 1e-12, "actual_lots": round(abs(got), 8), "expected_lots": round(abs(exp), 8),
                           "lots_match": ok, "fill_price": new[0].get("avg_entry_price") if new else "--",
                           "order_id": new[0].get("market_order_id") if new else "--", "latency_s": lat,
                           "state": "FILLED" if ok else ("WRONG SIZE" if new else "MISSING"),
                           "side_ok": (not new) or new[0].get("side") == (side if factor[e] > 0 else ("SELL" if side == "BUY" else "BUY"))}
            if all(r["lots_match"] for r in rows.values()) or time.time() > deadline:
                break
            time.sleep(0.8)
    else:
        deadline = time.time() + 20
        while True:
            def check(e):
                for o in dashboard_client.get_orders(e, instance).get("orders", [])[:40]:
                    if str(o.get("copy_ref") or "").lstrip("-") in master_ids:
                        q = float(o.get("requested_qty") or 0)
                        exp = qty * abs(factor[e])
                        return e, {"replicated": True, "actual_lots": q, "expected_lots": round(exp, 8),
                                   "lots_match": abs(q - exp) <= max(1e-6, 0.01 * exp), "fill_price": o.get("price") or "--",
                                   "order_id": o.get("order_id"), "latency_s": None, "state": o.get("state") or "PENDING", "side_ok": True}
                return e, {"replicated": False, "actual_lots": 0.0, "expected_lots": round(qty * abs(factor[e]), 8),
                           "lots_match": False, "fill_price": "--", "order_id": "--", "latency_s": None, "state": "MISSING", "side_ok": True}
            with ThreadPoolExecutor(max_workers=16) as ex:
                rows = dict(ex.map(check, linked))
            if all(r["replicated"] for r in rows.values()) or time.time() > deadline:
                break
            time.sleep(2.0)

    comparison = []
    for i, e in enumerate(emails, 1):
        link = links.get(f"{DEFAULT_PREFIX}{i}", {})
        base = {"index": i, "email": e, "method": (link.get("method") or "-"), "multiplier": link.get("multiplier", "-"),
                "reverse": bool(link.get("reverse")), "master_lots": qty, "master_price": master_price}
        if e not in linked_set:
            comparison.append({**base, "linked": False, "replicated": False, "order_id": "--", "copy_ref": "--", "expected_lots": 0,
                               "actual_lots": 0, "lots_match": True, "fill_price": "--", "slippage": "--", "state": "NOT LINKED",
                               "latency": "--", "passed": None})
            continue
        r = rows.get(e, {})
        slip = "--"
        try:
            if r.get("fill_price") not in (None, "--") and master_price:
                slip = f"{float(r['fill_price']) - float(master_price):+.6g}"
        except (TypeError, ValueError):
            pass
        lat = r.get("latency_s")
        comparison.append({**base, "linked": True, "replicated": r.get("replicated", False), "order_id": r.get("order_id", "--"),
                           "copy_ref": ",".join(master_ids), "expected_lots": r.get("expected_lots"), "actual_lots": r.get("actual_lots"),
                           "lots_match": r.get("lots_match", False), "fill_price": r.get("fill_price", "--"), "slippage": slip,
                           "state": r.get("state", "MISSING") if r.get("side_ok", True) else "WRONG SIDE",
                           "latency": f"{lat:.2f}s" if isinstance(lat, (int, float)) else "--",
                           "passed": bool(r.get("lots_match")) and r.get("side_ok", True)})
    linked_rows = [c for c in comparison if c["linked"]]
    passed = sum(1 for c in linked_rows if c["passed"])
    lats = [float(c["latency"][:-1]) for c in linked_rows if c["latency"] not in ("--", None)]
    return jsonify({
        "success": True,
        "master_order": {"order_id": mo.get("order_id"), "symbol": symbol, "side": side, "type": order_type, "requested_qty": qty,
                         "filled_qty": mo.get("filled_qty"), "fill_price": master_price, "created_at": master_time,
                         "status": mo.get("state"), "tp": tp, "sl": sl},
        "summary": {"total_followers": len(linked_rows), "not_linked": len(comparison) - len(linked_rows),
                    "replicated_count": sum(1 for c in linked_rows if c["replicated"]), "perfect_match_count": passed,
                    "pass_rate_pct": round(100.0 * passed / len(linked_rows), 1) if linked_rows else 0.0,
                    "total_elapsed_seconds": round(time.time() - t0, 2),
                    "max_copy_latency_s": round(max(lats), 3) if lats else None, "instance": instance},
        "comparison": comparison,
    })


@app.route("/api/order/close_master", methods=["POST"])
def close_master_and_verify():
    """Cancel the master's pending orders and close its positions, then verify every linked follower is flat."""
    data = request.get_json(silent=True) or {}
    instance = data.get("instance") if data.get("instance") in INSTANCES else "real"
    if is_real(instance) and data.get("confirm") is not True:
        return jsonify({"error": "Closing on REAL needs confirmation", "needs_confirmation": True}), 412
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            return jsonify({"error": "A test run is active - stop it first."}), 409
    emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(1, FOLLOWER_COUNT + 1)]
    linked, _ = SC.linked_followers(dashboard_client, MASTER_EMAIL, MASTER_ID, emails, instance)
    t0 = time.time()

    def pending(e):
        return sum(1 for o in dashboard_client.get_orders(e, instance).get("orders", [])
                   if str(o.get("state") or "").upper() in ("PENDING", "OPEN", "NEW", "WORKING", "ACCEPTED") and o.get("type") in ("LIMIT", "STOP"))
    master_pending = pending(MASTER_EMAIL)
    dashboard_client.bulk_cancel(MASTER_EMAIL, instance)
    dashboard_client.bulk_squareoff(MASTER_EMAIL, instance)
    left, left_pending = {}, {}
    while time.time() - t0 < 20:
        d = dashboard_client.fetch_all_followers_positions(linked, instance=instance)
        left = {e: v.get("count", 0) for e, v in d.items() if v.get("count", 0)}
        if not left:
            break
        time.sleep(1.0)
    sample = []
    if master_pending:   # each read downloads a follower's WHOLE order history (no API filter): check a spread sample of 12
        n = len(linked)
        sample = linked if n <= 12 else [linked[round(i * (n - 1) / 11)] for i in range(12)]
        for _ in range(3):
            time.sleep(1.5)
            with ThreadPoolExecutor(max_workers=12) as ex:
                left_pending = {e: k for e, k in zip(sample, ex.map(pending, sample)) if k}
            if not left_pending:
                break
    master_left = dashboard_client.get_positions(MASTER_EMAIL, instance).get("count", 0)
    return jsonify({"master_open": master_left, "master_pending_cancelled": master_pending, "followers_checked": len(linked),
                    "followers_still_open": len(left), "still_open": [e.split("@")[0] for e in list(left)[:20]],
                    "followers_with_pending": len(left_pending), "still_pending": [e.split("@")[0] for e in list(left_pending)[:20]],
                    "pending_checked": len(sample),
                    "seconds": round(time.time() - t0, 1), "ok": master_left == 0 and not left and not left_pending,
                    "note": "Followers still holding positions/pending orders either did not copy the close/cancel or hold their own trades."})


# -------------------------------------------------------------------------------------
# A-book / B-book routing (per account)
#   A-book: the member's REAL orders are executed at the liquidity provider.
#   B-book: booked on the platform's own engine. 
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
        "note": "Book only affects REAL-instance routing. ",
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


REAL_MODES = {"real": "Real (hedging)", "real-net": "Real Net (netting)"}


ALL_BROKERS = {"paper": "Paper (hedging)", "paper-net": "Paper (netting)", **REAL_MODES}


def _follower_real_links(instances=REAL_MODES) -> dict:
    """email -> {instance: active copy-link} for the configured followers, for the given instances."""
    links = dashboard_client.get_copy_followers(MASTER_EMAIL, instance="real", active_only=True)
    by_name = {}
    for l in links:
        if l.get("instance") in instances and l.get("follower_name"):
            by_name.setdefault(l["follower_name"], {})[l["instance"]] = l
    return {f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}": by_name.get(f"{DEFAULT_PREFIX}{i}", {}) for i in range(1, FOLLOWER_COUNT + 1)}


@app.route("/api/copy/instances")
def copy_instances_summary():
    """How many followers currently copy on real hedging vs real netting."""
    per = _follower_real_links()
    counts = {"real": 0, "real-net": 0, "both": 0, "none": 0}
    for m in per.values():
        if len(m) == 2: counts["both"] += 1
        elif "real" in m: counts["real"] += 1
        elif "real-net" in m: counts["real-net"] += 1
        else: counts["none"] += 1
    per_all = _follower_real_links(ALL_BROKERS)
    per_instance = {k: sum(1 for m in per_all.values() if k in m) for k in ALL_BROKERS}
    per_instance["none"] = sum(1 for m in per_all.values() if not m)
    return jsonify({"counts": counts, "followers": len(per), "per_instance": per_instance})


@app.route("/api/copy/switch_instance", methods=["POST"])
def switch_copy_instance():
    """ONE call moves every follower's copy link between real (hedging) and real-net (netting),
    keeping each follower's method / multiplier / reverse / copy_mode. One follow on the target moves the single link."""
    data = request.get_json(silent=True) or {}
    target = str(data.get("to", ""))
    if target not in ALL_BROKERS:
        return jsonify({"error": "to must be paper | paper-net (simulated) or real | real-net (hedging | netting)"}), 400
    refused = _account_change_refused({"instance": target, "confirm": data.get("confirm")})
    if refused:
        return refused
    if data.get("confirm") is not True:
        return jsonify({"error": "Switching needs confirmation.", "needs_confirmation": True}), 412
    lo, hi = int(data.get("start") or 1), int(data.get("end") or FOLLOWER_COUNT)
    emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(max(1, lo), min(FOLLOWER_COUNT, hi) + 1)]
    before = _follower_real_links(ALL_BROKERS)
    results = {e: {"email": e, "ok": False, "error": None} for e in emails}

    def move(email):
        links = before.get(email, {})
        src = next((i for i in links if i != target), None)
        if target in links and src is None:
            results[email]["ok"] = True          # already on the target
            return
        if not links:
            results[email]["error"] = "no active copy link to move"
            return
        base = links.get(target) or links[src]
        if target not in links:
            r = dashboard_client.follow_master(email, MASTER_ID, instance=target, method=base.get("method", "multiplier"),
                                               multiplier=float(base.get("multiplier", 1.0)), reverse=bool(base.get("reverse", False)),
                                               copy_mode=base.get("copy_mode", "public"))
            if r.get("status_code") != 200:
                results[email]["error"] = f"follow on {target}: HTTP {r.get('status_code')} {str(r.get('data'))[:100]}"
                return
        # A follower has ONE link record per master: following on the target already MOVES it. Never unfollow the old
        # instance afterwards - that would end the moved link. The read-back below verifies the result.

    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(move, emails))

    ACTIVE_LINKS_CACHE["data"] = None
    ACTIVE_LINKS_CACHE["timestamp"] = 0
    after = _follower_real_links(ALL_BROKERS)           # verify by reading back, never trust the 200
    for e in emails:
        a = after.get(e, {})
        results[e]["ok"] = (set(a) == {target})
        if not results[e]["ok"] and not results[e]["error"]:
            results[e]["error"] = f"read-back shows links on {sorted(a) or 'none'}, expected only {target}"
    ok = sum(1 for r in results.values() if r["ok"])
    return jsonify({"to": target, "requested": len(emails), "switched_ok": ok, "failed": len(emails) - ok,
                    "results": [r for r in results.values() if not r["ok"]][:20]}), (200 if ok == len(emails) else 207)


# ---------------------------------------------------------------- real-only health check
def _all_emails():
    return [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(1, FOLLOWER_COUNT + 1)]


def _pos_count(res) -> int:
    return len((res or {}).get("positions") or [])


@app.route("/api/real_check", methods=["GET"])
def real_check():
    """Read-only: master + followers must be linked on REAL only, funded, and hold nothing on paper."""
    c = dashboard_client
    emails = _all_emails()
    problems = []
    try:
        links = c.get_copy_followers(MASTER_EMAIL, "real", active_only=False)
    except Exception as e:
        return jsonify({"ok": False, "error": f"could not read copy links: {e}"}), 502
    by_name = {l.get("follower_name"): l for l in links}
    not_real, not_active, missing = [], [], []
    for e in emails:
        l = by_name.get(e.split("@")[0])
        if not l:
            missing.append(e.split("@")[0])
        elif l.get("instance") != "real":
            not_real.append(e.split("@")[0])
        elif l.get("status") != "active":
            not_active.append(e.split("@")[0])

    def acct(e):
        try:
            r = c.get_positions(e, "real")
            p = c.get_positions(e, "paper")
            return e, float((r.get("funds") or {}).get("balance", 0) or 0), _pos_count(r), _pos_count(p)
        except Exception:
            return e, None, 0, 0
    with ThreadPoolExecutor(10) as ex:
        rows = list(ex.map(acct, [MASTER_EMAIL] + emails))
    unfunded = [e.split("@")[0] for e, bal, _, _ in rows if bal is None or bal <= 0]
    on_paper = [e.split("@")[0] for e, _, _, pp in rows if pp]
    open_real = [e.split("@")[0] for e, _, rp, _ in rows if rp]
    if missing: problems.append(f"{len(missing)} follower(s) have no copy link")
    if not_real: problems.append(f"{len(not_real)} follower(s) linked on a non-real instance")
    if not_active: problems.append(f"{len(not_active)} follower(s) with an inactive link")
    if unfunded: problems.append(f"{len(unfunded)} account(s) with no real balance")
    if on_paper: problems.append(f"{len(on_paper)} account(s) hold positions on paper")
    return jsonify({
        "ok": not problems, "problems": problems, "master": MASTER_EMAIL, "followers": len(emails),
        "linked_real_active": len(emails) - len(missing) - len(not_real) - len(not_active),
        "missing": missing[:20], "not_real": not_real[:20], "not_active": not_active[:20],
        "unfunded": unfunded[:20], "on_paper": on_paper[:20], "open_on_real": open_real[:20],
        "master_balance": rows[0][1],
    })


@app.route("/api/real_check/copy_test", methods=["POST"])
def real_check_copy_test():
    """Live: master BUYs 0.01 BTC on REAL, count followers that copy it, then flatten everything."""
    data = request.get_json(silent=True) or {}
    refused = _account_change_refused({"instance": "real", "confirm": data.get("confirm")})
    if refused:
        return refused
    c = dashboard_client
    emails = _all_emails()
    symbol = "BINANCE:BTCUSDT.P"
    try:
        r = c.place_order(MASTER_EMAIL, symbol, "BUY", "MARKET", 0.01, instance="real")
        if r.get("status_code") != 200:
            return jsonify({"ok": False, "error": f"master order rejected: HTTP {r.get('status_code')} {str(r.get('data'))[:200]}"}), 200
        time.sleep(6)
        pos = c.fetch_all_followers_positions(emails, "real")
        copied = [e for e, v in pos.items() if _pos_count(v)]
        master_pos = _pos_count(c.get_positions(MASTER_EMAIL, "real"))
    finally:
        try:
            c.teardown_all_accounts(MASTER_EMAIL, emails, "real")
        except Exception:
            pass
    missing = [e.split("@")[0] for e in emails if e not in copied]
    return jsonify({"ok": not missing and master_pos > 0, "symbol": symbol, "master_positions": master_pos,
                    "copied": len(copied), "followers": len(emails), "missing": missing[:20], "cleaned_up": True})


# ---------------------------------------------------------------- all members (read-only, like the lpadmin Members page)
@app.route("/api/members", methods=["GET"])
def all_members():
    """The master + configured followers from the admin API, with search / status / book filters and paging."""
    try:
        everyone = dashboard_client.get_admin_members()
    except Exception as e:
        return jsonify({"error": f"could not read members: {e}"}), 502
    mine = {MASTER_EMAIL.lower(), *(e.lower() for e in _all_emails())}      # only the master + follower1..N
    members = [m for m in everyone if str(m.get("email", "")).lower() in mine]
    members.sort(key=lambda m: (m.get("email") != MASTER_EMAIL, int(re.sub(r"\D", "", str(m.get("email", "")).split("@")[0]) or 0)))
    q = (request.args.get("q") or "").strip().lower()
    status, book = request.args.get("status") or "", request.args.get("book") or ""
    try:
        page, size = max(1, int(request.args.get("page", 1))), min(200, max(1, int(request.args.get("size", 50))))
    except ValueError:
        return jsonify({"error": "bad page/size"}), 400
    rows = [m for m in members
            if (not q or q in str(m.get("email", "")).lower() or q in str(m.get("name", "")).lower() or q in str(m.get("member_id", "")).lower())
            and (not status or m.get("status") == status) and (not book or m.get("book") == book)]
    keep = ("member_id", "email", "name", "status", "book", "account_type", "group_code", "plan", "created_at", "balances")
    return jsonify({"total": len(members), "matched": len(rows), "page": page, "size": size,
                    "members": [{k: m.get(k) for k in keep} for m in rows[(page - 1) * size: page * size]],
                    "statuses": sorted({m.get("status") for m in members if m.get("status")}),
                    "books": sorted({m.get("book") for m in members if m.get("book")})})


# ---------------------------------------------------------------- bulk Broker Settings (per instance, master + followers)
PAPER_MAX_BALANCE, BROKER_RESET_BALANCE = 10_000_000.0, 1_000_000.0


@app.route("/api/broker_accounts", methods=["GET"])
def broker_accounts():
    """Balance / equity / free margin / used margin of the master + every follower on ONE instance (read-only)."""
    inst = request.args.get("instance", "real")
    if inst not in ALL_BROKERS:
        return jsonify({"error": "instance must be paper | paper-net | real | real-net"}), 400
    emails = [MASTER_EMAIL] + _all_emails()

    def one(e):
        try:
            f = (dashboard_client.get_positions(e, inst).get("funds") or {})
            return {"email": e, "balance": f.get("balance"), "equity": f.get("equity"),
                    "free_margin": f.get("free_margin"), "used_margin": f.get("used_margin")}
        except Exception as ex:
            return {"email": e, "error": str(ex)[:80]}
    with ThreadPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(one, emails))
    ok = [r for r in rows if "error" not in r]
    return jsonify({"instance": inst, "label": ALL_BROKERS[inst], "real_money": is_real(inst), "accounts": rows,
                    "totals": {"balance": sum(r["balance"] or 0 for r in ok), "equity": sum(r["equity"] or 0 for r in ok),
                               "used_margin": sum(r["used_margin"] or 0 for r in ok)},
                    "paper_max": PAPER_MAX_BALANCE, "reset_to": BROKER_RESET_BALANCE})


@app.route("/api/broker_accounts/balance", methods=["POST"])
def broker_accounts_balance():
    """Set (or reset) the balance of the master + every follower on one instance, then read it back."""
    data = request.get_json(silent=True) or {}
    inst = str(data.get("instance", ""))
    if inst not in ALL_BROKERS:
        return jsonify({"error": "instance must be paper | paper-net | real | real-net"}), 400
    refused = _account_change_refused({"instance": inst, "confirm": data.get("confirm")})
    if refused:
        return refused
    if data.get("confirm") is not True:
        return jsonify({"error": "Setting balances needs confirmation.", "needs_confirmation": True}), 412
    try:
        target = BROKER_RESET_BALANCE if data.get("reset") else float(data.get("balance"))
    except (TypeError, ValueError):
        return jsonify({"error": "balance must be a number"}), 400
    if target < 0 or (target == 0 and is_real(inst)):
        return jsonify({"error": "balance must be greater than 0 on real instances (0 is allowed on paper to lock it)"}), 400
    if not is_real(inst) and target > PAPER_MAX_BALANCE:
        return jsonify({"error": f"practice funds are capped at {PAPER_MAX_BALANCE:,.0f} on {ALL_BROKERS[inst]}"}), 400
    ids = {m["email"].lower(): m["member_id"] for m in dashboard_client.get_admin_members() if m.get("email") and m.get("member_id")}
    emails = [MASTER_EMAIL] + _all_emails()
    results = {e: {"email": e, "ok": False, "error": None} for e in emails}

    def setb(e):
        mid = ids.get(e.lower())
        if not mid:
            results[e]["error"] = "member not found"
            return
        r = dashboard_client.set_member_balance(mid, target, instance=inst)
        if r.get("status_code") != 200:
            results[e]["error"] = f"HTTP {r.get('status_code')} {str(r.get('data'))[:80]}"
    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(setb, emails))
    for e in emails:                                            # verify by reading back, never trust the 200
        if not results[e]["error"]:
            bal = (dashboard_client.get_positions(e, inst).get("funds") or {}).get("balance")
            results[e]["ok"] = bal is not None and abs(float(bal) - target) < max(1.0, target * 1e-6)
            if not results[e]["ok"]:
                results[e]["error"] = f"read-back balance {bal}, expected {target}"
    okn = sum(1 for r in results.values() if r["ok"])
    return jsonify({"instance": inst, "balance": target, "requested": len(emails), "ok": okn, "failed": len(emails) - okn,
                    "results": [r for r in results.values() if not r["ok"]][:20]}), (200 if okn == len(emails) else 207)


DEFAULT_FUNDS = {"paper": 1_000_000.0, "paper-net": 1_000_000.0, "real": 100_000_000.0, "real-net": 1_000_000.0}


@app.route("/api/broker_accounts/exclusive", methods=["POST"])
def broker_accounts_exclusive():
    """Fund ONE instance on the master + every follower and set the other three wallets to 0, then read all four back."""
    data = request.get_json(silent=True) or {}
    inst = str(data.get("instance", ""))
    if inst not in ALL_BROKERS:
        return jsonify({"error": "instance must be paper | paper-net | real | real-net"}), 400
    refused = _account_change_refused({"instance": "real", "confirm": data.get("confirm")})   # always touches real wallets
    if refused:
        return refused
    if data.get("confirm") is not True:
        return jsonify({"error": "Needs confirmation.", "needs_confirmation": True}), 412
    try:
        amount = float(data["balance"]) if data.get("balance") not in (None, "") else DEFAULT_FUNDS[inst]
    except (TypeError, ValueError):
        return jsonify({"error": "balance must be a number"}), 400
    if not (amount > 0):
        return jsonify({"error": "balance for the chosen instance must be greater than 0"}), 400
    if not is_real(inst) and amount > PAPER_MAX_BALANCE:
        return jsonify({"error": f"practice funds are capped at {PAPER_MAX_BALANCE:,.0f}"}), 400
    emails = [MASTER_EMAIL] + _all_emails()
    ids = {m["email"].lower(): m["member_id"] for m in dashboard_client.get_admin_members() if m.get("email") and m.get("member_id")}
    wanted = {k: (amount if k == inst else 0.0) for k in ALL_BROKERS}
    errors = {e: [] for e in emails}

    def fund(e):
        mid = ids.get(e.lower())
        if not mid:
            errors[e].append("member not found")
            return
        for k, v in wanted.items():
            r = dashboard_client.set_member_balance(mid, v, instance=k)
            if r.get("status_code") != 200:
                errors[e].append(f"{k}: HTTP {r.get('status_code')} {str(r.get('data'))[:60]}")
    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(fund, emails))
    after = {m["email"].lower(): (m.get("balances") or {}) for m in dashboard_client.get_admin_members()}
    bad = []
    for e in emails:
        b = after.get(e.lower(), {})
        for k, v in wanted.items():                                     # verify all four wallets, never trust the 200
            got = b.get(k)
            if got is None or abs(float(got) - v) > max(1.0, v * 1e-6):
                errors[e].append(f"{k}: read-back {got}, expected {v:g}")
        if errors[e]:
            bad.append({"email": e, "error": "; ".join(errors[e])[:200]})
    return jsonify({"instance": inst, "funded": amount, "others_zeroed": [k for k in wanted if k != inst],
                    "requested": len(emails), "ok": len(emails) - len(bad), "failed": len(bad), "results": bad[:20]}), (200 if not bad else 207)


@app.route("/api/copy/instance_link", methods=["POST"])
def copy_instance_link():
    """Mass ENABLE / DISABLE copy trading on one instance for the followers.
    A follower has ONE link record per master, so: enable = follow on that instance (an existing link on another
    instance is converted, keeping its method/multiplier); disable = end the link if it is on that instance."""
    data = request.get_json(silent=True) or {}
    inst, action = str(data.get("instance", "")), str(data.get("action", ""))
    if inst not in ALL_BROKERS or action not in ("enable", "disable"):
        return jsonify({"error": "instance must be paper|paper-net|real|real-net and action enable|disable"}), 400
    if action == "enable" and not is_real(inst):
        return jsonify({"error": f"Cannot enable copy trading on {ALL_BROKERS[inst]}: the platform no longer creates paper copy links "
                                 "(Copy trading, MAM and PAMM run on real-money accounts). Nothing was changed."}), 409
    refused = _account_change_refused({"instance": inst, "confirm": data.get("confirm")})
    if refused:
        return refused
    if action == "disable" and not is_real(inst) and not os.environ.get("BT_ALLOW_PAPER_UNFOLLOW") == "1":
        return jsonify({"error": "Disabling a PAPER link is blocked: an unfollowed paper follower can never be re-linked. "
                                 "Set BT_ALLOW_PAPER_UNFOLLOW=1 in .env to override. Nothing was changed."}), 409
    lo, hi = int(data.get("start") or 1), int(data.get("end") or FOLLOWER_COUNT)
    emails = [f"{DEFAULT_PREFIX}{i}@{DEFAULT_DOMAIN}" for i in range(max(1, lo), min(FOLLOWER_COUNT, hi) + 1)]
    before = _follower_real_links(ALL_BROKERS)
    results = {e: {"email": e, "ok": False, "error": None} for e in emails}

    def apply(email):
        links = before.get(email, {})
        other = next((i for i in links if i != inst), None)
        if action == "enable":
            if inst in links and other is None:
                return                                            # already enabled
            base = links.get(inst) or (links.get(other) if other else {}) or {}
            r = dashboard_client.follow_master(email, MASTER_ID, instance=inst, method=base.get("method", "multiplier"),
                                               multiplier=float(base.get("multiplier", 1.0)), reverse=bool(base.get("reverse", False)),
                                               copy_mode=base.get("copy_mode", "public"))
            if r.get("status_code") != 200:
                results[email]["error"] = f"HTTP {r.get('status_code')}: {str(r.get('data'))[:110]}"
        else:
            if inst not in links:
                return                                            # nothing to disable
            u = dashboard_client.unfollow_master(email, MASTER_ID, instance=inst)
            if u.get("status_code") != 200:
                results[email]["error"] = f"HTTP {u.get('status_code')}: {str(u.get('data'))[:110]}"

    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(apply, emails))

    ACTIVE_LINKS_CACHE["data"] = None
    ACTIVE_LINKS_CACHE["timestamp"] = 0
    after = _follower_real_links(ALL_BROKERS)                     # verify by reading back
    for e in emails:
        on = inst in after.get(e, {})
        results[e]["ok"] = on if action == "enable" else not on
        if not results[e]["ok"] and not results[e]["error"]:
            results[e]["error"] = f"read-back: link {'not on' if action == 'enable' else 'still on'} {inst}"
    ok = sum(1 for r in results.values() if r["ok"])
    failed = [r for r in results.values() if not r["ok"]]
    return jsonify({"instance": inst, "action": action, "requested": len(emails), "ok": ok, "failed": len(failed),
                    "results": failed[:10]}), (200 if not failed else 207)


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
