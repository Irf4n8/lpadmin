"""
Test-operations service for the MAM terminal (dashboard_server.py).

Framework-free port of the test-runner features of the Flask test dashboard (dashboard/app.py):
suite launcher, live log, run history, evidence summary, report browser and the setup health check.
Every public function returns ``(payload_dict, http_status)``.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, FOLLOWER_COUNT, FOLLOWER_PREFIX, DEFAULT_DOMAIN, MASTER_EMAIL, MASTER_ID, DASHBOARD_TOKEN  # noqa: E402
from dashboard.suites import SUITE_INDEX, build_command, effective_instance, needs_confirmation, public_registry  # noqa: E402

REPORTS_DIR = BASE_DIR / "reports"
EVIDENCE_DIR = REPORTS_DIR / "evidence"
LOGS_DIR = REPORTS_DIR / "logs"
RUNS_DIR = LOGS_DIR / "runs"
LATEST_LOG_FILE = LOGS_DIR / "live_execution.log"
HISTORY_FILE = LOGS_DIR / "run_history.json"
for _d in (EVIDENCE_DIR, LOGS_DIR, RUNS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

PROCESS_LOCK = threading.Lock()
HISTORY_LOCK = threading.Lock()
RUNNING_PROCESS: Optional[subprocess.Popen] = None
CURRENT_TASK: Dict[str, Any] = {"suite": None, "name": None, "status": "IDLE", "started_at": None, "pid": None,
                                "exit_code": None, "ended_at": None, "run_id": None, "params": {}, "risk": None}


# ---------------------------------------------------------------- history
def _load_history() -> list:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_history(items: list) -> None:
    HISTORY_FILE.write_text(json.dumps(items[-100:], indent=1), encoding="utf-8")


def _history_add(entry: dict) -> None:
    with HISTORY_LOCK:
        items = _load_history()
        items.append(entry)
        _save_history(items)


def _history_update(run_id: str, **fields) -> None:
    with HISTORY_LOCK:
        items = _load_history()
        for it in items:
            if it.get("id") == run_id:
                it.update(fields)
        _save_history(items)


def _count_log_results(path: Path) -> Tuple[int, int]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0
    return text.count("[PASS]"), text.count("[FAIL]")


def _monitor(proc: subprocess.Popen, run_id: str, log_handle) -> None:
    global RUNNING_PROCESS
    proc.wait()
    try:
        log_handle.close()
    except Exception:
        pass
    passed, failed = _count_log_results(LATEST_LOG_FILE)
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
    _history_update(run_id, status=status, exit_code=proc.returncode, ended_at=datetime.now().isoformat(timespec="seconds"),
                    duration_sec=round(time.time() - started, 1), passed=passed, failed=failed)


# ---------------------------------------------------------------- config / suites / health
def get_config() -> Tuple[dict, int]:
    return {"base_url": BASE_URL, "master_email": MASTER_EMAIL, "master_id": MASTER_ID, "follower_prefix": FOLLOWER_PREFIX,
            "follower_domain": DEFAULT_DOMAIN, "follower_count": FOLLOWER_COUNT, "token_protected": bool(DASHBOARD_TOKEN),
            "env_file_present": (BASE_DIR / ".env").exists()}, 200


def get_suites() -> Tuple[dict, int]:
    return {"suites": public_registry(),
            "defaults": {"follower_count": FOLLOWER_COUNT, "lot": 0.1, "orders_count": 10, "ramp": "10,25,50,100"}}, 200


_HEALTH_CACHE: Dict[str, Any] = {"t": 0.0, "data": None}


def get_health(offline: bool = False, refresh: bool = False) -> Tuple[dict, int]:
    from config.doctor import run_checks, summarize
    if not offline and not refresh and _HEALTH_CACHE["data"] and time.time() - _HEALTH_CACHE["t"] < 20:
        return _HEALTH_CACHE["data"], 200
    results = run_checks(offline=offline)
    data = {"overall": summarize(results), "checks": results, "checked_at": datetime.now().isoformat(timespec="seconds")}
    if not offline:
        _HEALTH_CACHE.update(t=time.time(), data=data)
    return data, 200


# ---------------------------------------------------------------- run control
def get_status() -> Tuple[dict, int]:
    with PROCESS_LOCK:
        task = dict(CURRENT_TASK)
    elapsed = 0
    if task["started_at"]:
        end = time.time() if task["status"] == "RUNNING" else (task.get("ended_at") or task["started_at"])
        elapsed = round(end - task["started_at"], 1)
    passed, failed = _count_log_results(LATEST_LOG_FILE) if task["suite"] else (0, 0)
    return {**task, "elapsed_seconds": elapsed, "is_running": task["status"] == "RUNNING",
            "pass_count": passed, "fail_count": failed}, 200


def get_logs() -> Tuple[dict, int]:
    if not LATEST_LOG_FILE.exists():
        return {"logs": ""}, 200
    try:
        lines = LATEST_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        return {"logs": "".join(lines[-300:]), "total_lines": len(lines)}, 200
    except Exception as e:
        return {"logs": f"Error reading logs: {e}"}, 200


def run_suite(data: dict) -> Tuple[dict, int]:
    global RUNNING_PROCESS
    suite_key = data.get("suite")
    suite = SUITE_INDEX.get(suite_key)
    if not suite:
        return {"error": f"Unknown suite '{suite_key}'"}, 400
    params = data.get("params") or {}
    if needs_confirmation(suite, params) and data.get("confirm") is not True:
        return {"error": "This action needs explicit confirmation.", "needs_confirmation": True,
                "reason": ("Runs against the REAL instance." if effective_instance(suite, params) in ("real", "both")
                           else "Closes positions and cancels orders.")}, 412

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
            f.write(f"Command  : {shown}\nInstance : {effective_instance(suite, params)}\n")
            f.write(f"Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        log_out = open(LATEST_LOG_FILE, "a", encoding="utf-8")
        proc = subprocess.Popen(cmd, stdout=log_out, stderr=subprocess.STDOUT, cwd=str(BASE_DIR), text=True, env=env)
        RUNNING_PROCESS = proc
        CURRENT_TASK.update(suite=suite_key, name=title, status="RUNNING", started_at=time.time(), ended_at=None,
                            pid=proc.pid, exit_code=None, run_id=run_id,
                            params={**params, "instance": effective_instance(suite, params)}, risk=suite["risk"])
        _history_add({"id": run_id, "suite": suite_key, "name": title, "status": "RUNNING",
                      "started_at": datetime.now().isoformat(timespec="seconds"), "params": CURRENT_TASK["params"]})
        threading.Thread(target=_monitor, args=(proc, run_id, log_out), daemon=True).start()
    return {"message": f"Launched {title}", "pid": proc.pid, "suite": suite_key, "run_id": run_id}, 200


def stop_suite() -> Tuple[dict, int]:
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            CURRENT_TASK["status"] = "TERMINATED"
            RUNNING_PROCESS.terminate()
            return {"message": "Run stopped. Positions may still be open - use Emergency Teardown to clean up."}, 200
    return {"message": "Nothing is running."}, 200


def get_history() -> Tuple[dict, int]:
    with HISTORY_LOCK:
        items = _load_history()
    return {"runs": list(reversed(items))}, 200


def get_history_log(run_id: str) -> Tuple[dict, int]:
    if not run_id.replace("_", "").replace("-", "").isalnum():
        return {"error": "bad id"}, 400
    p = RUNS_DIR / f"{run_id}.log"
    if not p.exists():
        return {"error": "log not archived"}, 404
    return {"logs": p.read_text(encoding="utf-8", errors="replace")[-200000:]}, 200


# ---------------------------------------------------------------- evidence summary / reports
_FAMILY_RE = re.compile(r"^(?P<fam>.+?)_(?P<ts>\d{8}_\d{6})$")


def _count_statuses(obj, acc) -> None:
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


def get_summary() -> Tuple[dict, int]:
    families: Dict[str, tuple] = {}
    for p in EVIDENCE_DIR.glob("*.json"):
        if p.stem == "baseline_snapshot" or p.stem.startswith(("jmeter_performance", "jmeter_load_test")):
            continue
        m = _FAMILY_RE.match(p.stem)
        fam = m.group("fam") if m else p.stem
        mt = p.stat().st_mtime
        if fam not in families or mt > families[fam][1]:
            families[fam] = (p, mt)
    rows = []
    for fam, (p, mt) in families.items():
        acc = {"passed": 0, "failed": 0, "warned": 0}
        try:
            _count_statuses(json.loads(p.read_text(encoding="utf-8")), acc)
        except Exception:
            pass
        if acc["passed"] + acc["failed"] + acc["warned"] == 0:
            continue
        rows.append({"family": fam, "label": fam.replace("_", " ").replace(" evidence", "").title(), "file": p.name,
                     "modified": datetime.fromtimestamp(mt).isoformat(timespec="seconds"), **acc,
                     "status": "FAIL" if acc["failed"] else ("WARN" if acc["warned"] else "PASS")})
    rows.sort(key=lambda r: r["modified"], reverse=True)
    with HISTORY_LOCK:
        hist = _load_history()
    return {"families": rows,
            "totals": {"suites": len(rows), "suites_green": sum(1 for r in rows if r["status"] == "PASS"),
                       "passed": sum(r["passed"] for r in rows), "failed": sum(r["failed"] for r in rows)},
            "last_run": hist[-1] if hist else None, "runs_recorded": len(hist)}, 200


def get_reports() -> Tuple[dict, int]:
    reports, seen = [], set()
    for d in (REPORTS_DIR, EVIDENCE_DIR):
        if not d.exists():
            continue
        for f in sorted(d.iterdir(), key=os.path.getmtime, reverse=True):
            if f.is_file() and f.suffix in (".json", ".md", ".csv", ".jtl") and not f.name.startswith("baseline") and f.name not in seen:
                seen.add(f.name)
                reports.append({"filename": f.name, "type": f.suffix[1:].upper(), "size_kb": round(f.stat().st_size / 1024, 1),
                                "modified_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
    return {"reports": reports}, 200


def get_report_content(filename: str) -> Tuple[dict, int]:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return {"error": "bad filename"}, 400
    path = next((p for p in (EVIDENCE_DIR / filename, REPORTS_DIR / filename) if p.is_file()), None)
    if not path:
        return {"error": "Report file not found"}, 404
    try:
        return {"filename": filename, "is_json": filename.endswith(".json"), "content": path.read_text(encoding="utf-8", errors="replace")}, 200
    except Exception as e:
        return {"error": str(e)}, 500
