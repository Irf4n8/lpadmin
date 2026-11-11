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

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_from_directory, make_response

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN
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
    "status": "IDLE",  # IDLE, RUNNING, COMPLETED, FAILED
    "started_at": None,
    "pid": None,
    "exit_code": None
}
PROCESS_LOCK = threading.Lock()


SUITE_COMMANDS = {
    "multiplier": ["python", "test_suite/runner.py", "--start", "1", "--end", "100", "--orders-count", "10", "--lot", "0.1", "--burst", "10"],
    "balance": ["python", "test_suite/balance_mode_runner.py", "--start", "1", "--end", "100", "--orders-count", "10", "--lot", "0.1", "--burst", "10"],
    "equity": ["python", "test_suite/equity_mode_runner.py", "--start", "1", "--end", "100", "--orders-count", "10", "--lot", "0.1", "--burst", "10"],
    "race": ["python", "test_suite/race_conditions_runner.py", "--start", "1", "--end", "100"],
    "pending": ["python", "test_suite/pending_live_execution_runner.py", "--start", "1", "--end", "100", "--lot", "0.1"],
    "symmetry": ["python", "test_suite/buy_sell_symmetric_runner.py", "--start", "1", "--end", "100", "--orders-count", "10", "--lot", "0.1"],
    "state": ["python", "test_suite/state_changes_and_hedging_runner.py", "--start", "1", "--end", "100"],
    "extended": ["python", "test_suite/extended_runner.py", "--start", "1", "--end", "100"],
    "accounting": ["python", "test_suite/accounting_reconciliation_runner.py", "--start", "1", "--end", "100", "--lot", "0.1"],
    "extreme": ["python", "test_suite/extreme_scenarios_and_race_runner.py", "--start", "1", "--end", "100"],
    "pending_trigger_race": ["python", "test_suite/pending_trigger_race_runner.py", "--start", "1", "--end", "100"],
    "teardown": ["python", "-c", "from test_suite.client import BlackTraderClient; from config.settings import BASE_URL; c = BlackTraderClient(BASE_URL); c.teardown_all_accounts('ctmaster@mailinator.com', [f'follower{i}@mailinator.com' for i in range(1, 101)]); print('All 101 accounts cleanly torn down!')"]
}

SUITE_NAMES = {
    "multiplier": "Multiplier Mode 100-Follower Suite (>=10 Orders)",
    "balance": "Balance-Based Mode 100-Follower Suite (>=10 Orders)",
    "equity": "Equity-Based Mode 100-Follower Suite (>=10 Orders)",
    "race": "Race Conditions & Concurrency Stress Suite (6/6)",
    "pending": "Pending Orders Live Trigger & Execution (No Cancel)",
    "symmetry": "Buy/Sell Parity & STOP Orders Suite (Market, Limit, Stop)",
    "state": "Account State Changes & Hedging Isolation Suite",
    "extended": "Extended Edge Cases (Odd Multipliers, Rounding, Security)",
    "accounting": "Financial Accounting Audit (162.5x Multiplier Verification)",
    "extreme": "Extreme Scenarios & Concurrency Race Suite (7 Scenarios)",
    "pending_trigger_race": "Pending Order Trigger vs Modify/Cancel Race Suite",
    "teardown": "Emergency Teardown & Clean All 101 Accounts"
}


def monitor_process(proc, suite_key):
    global RUNNING_PROCESS, CURRENT_TASK
    proc.wait()
    with PROCESS_LOCK:
        CURRENT_TASK["status"] = "COMPLETED" if proc.returncode == 0 else "FAILED"
        CURRENT_TASK["exit_code"] = proc.returncode
        RUNNING_PROCESS = None


@app.route("/")
def index():
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/status")
def get_status():
    with PROCESS_LOCK:
        elapsed = 0
        if CURRENT_TASK["started_at"] and CURRENT_TASK["status"] == "RUNNING":
            elapsed = round(time.time() - CURRENT_TASK["started_at"], 1)
        return jsonify({
            **CURRENT_TASK,
            "elapsed_seconds": elapsed,
            "is_running": CURRENT_TASK["status"] == "RUNNING"
        })


@app.route("/api/logs")
def get_logs():
    if not LATEST_LOG_FILE.exists():
        return jsonify({"logs": "No logs recorded yet."})
    try:
        with open(LATEST_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            recent = "".join(lines[-150:])
            return jsonify({"logs": recent})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {str(e)}"})


@app.route("/api/run", methods=["POST"])
def run_suite():
    global RUNNING_PROCESS, CURRENT_TASK
    data = request.json or {}
    suite_key = data.get("suite")

    if not suite_key or suite_key not in SUITE_COMMANDS:
        return jsonify({"error": f"Invalid suite key '{suite_key}'"}), 400

    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            return jsonify({"error": "A test suite is already running!", "current": CURRENT_TASK["name"]}), 409

        cmd = SUITE_COMMANDS[suite_key]
        suite_title = SUITE_NAMES.get(suite_key, suite_key)

        # Clear/initialize live log
        with open(LATEST_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"=== LAUNCHING: {suite_title} ===\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        log_out = open(LATEST_LOG_FILE, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            stdout=log_out,
            stderr=subprocess.STDOUT,
            cwd=str(BASE_DIR),
            text=True
        )

        RUNNING_PROCESS = proc
        CURRENT_TASK["suite"] = suite_key
        CURRENT_TASK["name"] = suite_title
        CURRENT_TASK["status"] = "RUNNING"
        CURRENT_TASK["started_at"] = time.time()
        CURRENT_TASK["pid"] = proc.pid
        CURRENT_TASK["exit_code"] = None

        # Start background monitor thread
        t = threading.Thread(target=monitor_process, args=(proc, suite_key), daemon=True)
        t.start()

    return jsonify({
        "message": f"Successfully launched {suite_title}",
        "pid": proc.pid,
        "suite": suite_key
    })


@app.route("/api/stop", methods=["POST"])
def stop_suite():
    global RUNNING_PROCESS, CURRENT_TASK
    with PROCESS_LOCK:
        if RUNNING_PROCESS and RUNNING_PROCESS.poll() is None:
            RUNNING_PROCESS.terminate()
            CURRENT_TASK["status"] = "TERMINATED"
            RUNNING_PROCESS = None
            return jsonify({"message": "Running test suite terminated."})
        return jsonify({"message": "No test suite currently running."})


@app.route("/api/reports")
def get_reports():
    reports = []
    if not EVIDENCE_DIR.exists():
        return jsonify({"reports": []})

    for f in sorted(EVIDENCE_DIR.iterdir(), key=os.path.getmtime, reverse=True):
        if f.suffix in [".json", ".md"] and not f.name.startswith("baseline"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            category = "Other"
            if "balance" in f.name:
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
    file_path = EVIDENCE_DIR / filename
    if not file_path.exists() or not file_path.is_file():
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


ACTIVE_LINKS_CACHE = {"data": None, "timestamp": 0}


def get_cached_active_links(instance: str = "paper") -> dict:
    global ACTIVE_LINKS_CACHE
    now = time.time()
    if ACTIVE_LINKS_CACHE["data"] is not None and (now - ACTIVE_LINKS_CACHE["timestamp"] < 15):
        return ACTIVE_LINKS_CACHE["data"]
    try:
        raw_links = dashboard_client.get_copy_followers("ctmaster@mailinator.com", instance=instance, active_only=True)
        links_by_follower = {}
        for link in raw_links:
            fn = link.get("follower_name")
            if fn:
                links_by_follower[fn] = link
        ACTIVE_LINKS_CACHE["data"] = links_by_follower
        ACTIVE_LINKS_CACHE["timestamp"] = now
        return links_by_follower
    except Exception as e:
        print(f"Error fetching active links: {e}")
        return ACTIVE_LINKS_CACHE["data"] or {}


@app.route("/api/followers")
def get_followers_list():
    from test_suite.baseline import get_expected_multiplier
    instance = request.args.get("instance", "paper")
    active_links = get_cached_active_links(instance=instance)

    # Determine dominant mode across active links, or from current running task
    current_suite = CURRENT_TASK.get("suite")
    detected_mode = "multiplier"

    if current_suite in ["balance", "equity", "multiplier"]:
        detected_mode = current_suite
    elif active_links:
        methods_count = {}
        for l in active_links.values():
            m = l.get("method", "multiplier")
            methods_count[m] = methods_count.get(m, 0) + 1
        if methods_count:
            detected_mode = max(methods_count, key=methods_count.get)

    followers = []
    for i in range(1, 101):
        mult = get_expected_multiplier(i)
        tier = 1 if mult == 1.0 else (2 if mult == 2.0 else (3 if mult == 3.0 else 4))
        f_prefix = f"follower{i}"
        link = active_links.get(f_prefix, {})
        f_method = link.get("method", detected_mode)
        
        cap_val = int(100 * mult)
        display_label = f"{mult}x"
        if detected_mode == "balance":
            display_label = f"{cap_val}M"
        elif detected_mode == "equity":
            display_label = f"{cap_val}M Eq"

        followers.append({
            "index": i,
            "email": f"follower{i}@mailinator.com",
            "multiplier": mult,
            "method": f_method,
            "tier": tier,
            "balance": f"{cap_val}M",
            "equity": f"{cap_val}M",
            "display_label": display_label,
            "ratio_label": f"{mult}x",
            "status": link.get("status", "ACTIVE").upper()
        })

    return jsonify({
        "current_mode": detected_mode,
        "master": {"email": "ctmaster@mailinator.com", "id": "mem_aac4ca423a6925dca7", "balance": "100M", "equity": "100M"},
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
                expected_mult = get_expected_multiplier(follower_index)
                expected_cap = f"{int(100 * expected_mult):,}.00"
                tier = 1 if expected_mult == 1.0 else (2 if expected_mult == 2.0 else (3 if expected_mult == 3.0 else 4))
            except Exception:
                pass

            active_links_map = get_cached_active_links(instance=instance)
            # Exact match on follower name
            follow_info = active_links_map.get(f_prefix)

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
        master_ords = dashboard_client.get_orders("ctmaster@mailinator.com", instance=instance).get("orders", [])
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
        master_ords = dashboard_client.get_orders("ctmaster@mailinator.com", instance=instance).get("orders", [])
        for o in master_ords[:15]:
            raw_time = o.get("created_at", "")
            clean_time = raw_time
            if "T" in raw_time:
                clean_time = raw_time.split("T")[1].replace("Z", "")[:8]
            tape.append({
                "account": "Master (ctmaster)",
                "email": "ctmaster@mailinator.com",
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n" + "=" * 80)
    print(f" [*] BLACKTRADER TEST DASHBOARD SERVER STARTED")
    print(f" [*] Access live dashboard at: http://localhost:{port}")
    print("=" * 80 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)

