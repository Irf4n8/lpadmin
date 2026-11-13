#!/usr/bin/env python3
"""
BlackTrader Copy Trading Test Runner (100 Followers)
===================================================
Executes the comprehensive test suite for Copy Trading under master ctmaster.
Generates evidence reports in reports/evidence/ (JSON and Markdown).

Usage:
    python test_suite/runner.py
    python test_suite/runner.py --lot 1.0 --burst 5
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import MASTER_EMAIL, MASTER_ID, FOLLOWER_COUNT
from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN
from test_suite.baseline import run_setup_and_baseline
from test_suite.client import BlackTraderClient
from test_suite.scenarios import ScenarioRunner


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Copy Trading 100-Follower Test Runner")
    parser.add_argument("--master", default=MASTER_EMAIL, help="Master trader email")
    parser.add_argument("--master-id", default=MASTER_ID, help="Master client ID")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Follower prefix")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Follower domain")
    parser.add_argument("--start", type=int, default=1, help="Starting follower index")
    parser.add_argument("--end", type=int, default=FOLLOWER_COUNT, help="Ending follower index")
    parser.add_argument("--symbol", default="BINANCE:BTCUSDT.P", help="Trading symbol")
    parser.add_argument("--lot", type=float, default=0.1, help="Master lot size per order")
    parser.add_argument("--orders-count", type=int, default=10, help="Number of orders per scenario (at least 10)")
    parser.add_argument("--instance", default="paper", help="Trading instance (paper)")
    parser.add_argument("--burst", type=int, default=10, help="Number of orders in rapid burst scenario")
    args = parser.parse_args()

    follower_emails = [f"{args.prefix}{i}@{args.domain}" for i in range(args.start, args.end + 1)]

    print("\n" + "=" * 80)
    print(" BLACKTRADER COPY TRADING 100-FOLLOWER MULTI-ORDER TEST SUITE")
    print("=" * 80)
    print(f"[*] Base URL            : {BASE_URL}")
    print(f"[*] Master Trader       : {args.master} (ID: {args.master_id})")
    print(f"[*] Followers Count     : {len(follower_emails)} ({follower_emails[0]} -> {follower_emails[-1]})")
    print(f"[*] Trading Symbol      : {args.symbol}")
    print(f"[*] Orders Per Scenario : {args.orders_count} (>= 10 orders)")
    print(f"[*] Lot Per Order       : {args.lot}")
    print(f"[*] Trading Instance    : {args.instance} (Hedging)")
    print("=" * 80 + "\n")

    client = BlackTraderClient(base_url=BASE_URL, max_workers=10)
    runner = ScenarioRunner(
        client=client,
        master_email=args.master,
        follower_emails=follower_emails,
        symbol=args.symbol,
        instance=args.instance
    )

    test_start_time = datetime.now(timezone.utc).isoformat()
    results = []

    # -------------------------------------------------------------------------
    # PHASE A: Setup and Baseline
    # -------------------------------------------------------------------------
    baseline_data = run_setup_and_baseline(
        client=client,
        master_email=args.master,
        master_client_id=args.master_id,
        follower_emails=follower_emails,
        instance=args.instance
    )

    # -------------------------------------------------------------------------
    # PHASE B & D: Market BUY Fan-Out & Lot Sizing (10 Orders)
    # -------------------------------------------------------------------------
    res_buy = runner.test_market_buy_fanout(master_lot=args.lot, count=args.orders_count)
    results.append(res_buy)
    master_mkt_ids = res_buy.get("master_mkt_ids", [])

    # Scenario 2: Partial Close across 10 orders
    if master_mkt_ids:
        res_part = runner.test_partial_close(master_mkt_ids=master_mkt_ids, initial_master_lot=args.lot, reduce_qty=0.5 * args.lot)
        results.append(res_part)

        # Scenario 3: Full Close across 10 orders
        res_close = runner.test_full_close(master_mkt_ids=master_mkt_ids)
        results.append(res_close)
    else:
        results.append({"name": "Partial Close", "status": "SKIPPED", "error": "No open master orders"})
        results.append({"name": "Full Close", "status": "SKIPPED", "error": "No open master orders"})

    # -------------------------------------------------------------------------
    # Scenario 4: Take Profit / Stop Loss Propagation (10 Orders)
    # -------------------------------------------------------------------------
    res_tpsl = runner.test_tp_sl_propagation(master_lot=args.lot, count=args.orders_count)
    results.append(res_tpsl)

    # -------------------------------------------------------------------------
    # Scenario 5: Pending Order Fan-Out & Cancel (10 Orders)
    # -------------------------------------------------------------------------
    res_pending = runner.test_pending_order_and_cancel(count=args.orders_count)
    results.append(res_pending)

    # -------------------------------------------------------------------------
    # Scenario 6: Concurrency / Rapid Burst (10 Orders)
    # -------------------------------------------------------------------------
    res_burst = runner.test_rapid_burst(burst_count=max(args.burst, args.orders_count))
    results.append(res_burst)

    # -------------------------------------------------------------------------
    # Scenario 7: Market SELL Fan-Out & Multiplier Sizing (10 Orders)
    # -------------------------------------------------------------------------
    res_sell = runner.test_market_sell_fanout(master_lot=args.lot, count=args.orders_count)
    results.append(res_sell)

    # -------------------------------------------------------------------------
    # Scenario 8: Follower Manual Close Isolation
    # -------------------------------------------------------------------------
    probe_manual_follower = follower_emails[min(2, len(follower_emails) - 1)]
    res_manual = runner.test_follower_manual_close_isolation(probe_follower=probe_manual_follower)
    results.append(res_manual)

    # -------------------------------------------------------------------------
    # Scenario 9: Follow Mid-Trade Isolation (No Retroactive Copying)
    # -------------------------------------------------------------------------
    probe_follow_mid = follower_emails[min(9, len(follower_emails) - 1)]
    res_follow_mid = runner.test_follow_mid_trade_isolation(probe_follower=probe_follow_mid)
    results.append(res_follow_mid)

    # -------------------------------------------------------------------------
    # Scenario 10: Unfollow Mid-Trade Behavior Probe (Scenario 20)
    # -------------------------------------------------------------------------
    probe_unfollow = follower_emails[min(4, len(follower_emails) - 1)]
    res_unfollow = runner.test_unfollow_mid_trade_probe(probe_follower=probe_unfollow)
    results.append(res_unfollow)

    # -------------------------------------------------------------------------
    # FINAL TEARDOWN & RECONCILIATION
    # -------------------------------------------------------------------------
    print("\n[*] Performing final clean teardown and checking for leftover positions...")
    client.teardown_all_accounts(args.master, follower_emails, instance=args.instance)
    time.sleep(1.5)

    final_positions = client.fetch_all_followers_positions(follower_emails, instance=args.instance)
    total_orphans = sum(p.get("count", 0) for p in final_positions.values())
    no_orphans_pass = total_orphans == 0

    results.append({
        "name": "Final Teardown & Zero Orphan Verification",
        "status": "PASS" if no_orphans_pass else "FAIL",
        "orphan_count": total_orphans
    })

    test_end_time = datetime.now(timezone.utc).isoformat()

    # -------------------------------------------------------------------------
    # GENERATE EVIDENCE REPORT (JSON & MARKDOWN)
    # -------------------------------------------------------------------------
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = BASE_DIR / "reports" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    json_report_path = evidence_dir / f"evidence_{timestamp_str}.json"
    md_report_path = evidence_dir / f"evidence_{timestamp_str}.md"

    report_payload = {
        "suite_name": "BlackTrader Copy Trading 100-Follower Test Suite",
        "started_at": test_start_time,
        "completed_at": test_end_time,
        "master_email": args.master,
        "master_id": args.master_id,
        "followers_count": len(follower_emails),
        "symbol": args.symbol,
        "lot_size": args.lot,
        "instance": args.instance,
        "baseline_summary": {
            "master_balance": baseline_data.get("master", {}).get("balance"),
            "followers_count": baseline_data.get("followers_count"),
            "multiplier_distribution": baseline_data.get("multiplier_distribution")
        },
        "scenarios": results
    }

    with open(json_report_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    # Generate Markdown Report
    passed_tests = sum(1 for r in results if r.get("status") == "PASS")
    total_tests = len([r for r in results if r.get("status") in ["PASS", "FAIL"]])

    md_content = f"""# Copy Trading 100-Follower Test Suite Evidence Report

**Generated:** {test_end_time}  
**Master Trader:** `{args.master}` (`{args.master_id}`)  
**Followers Tested:** {len(follower_emails)} (`{follower_emails[0]}` to `{follower_emails[-1]}`)  
**Trading Symbol:** `{args.symbol}` (Lot: {args.lot})  
**Instance:** `{args.instance}` (Hedging)  
**Overall Result:** **{passed_tests}/{total_tests} SCENARIOS PASSED**

---

## 1. Executive Summary

| Scenario | Focus | Status | Details |
| :--- | :--- | :---: | :--- |
"""

    for r in results:
        status_badge = "✅ PASS" if r.get("status") == "PASS" else ("ℹ️ OBSERVED" if r.get("status") == "OBSERVED" else "❌ FAIL")
        detail = ""
        if "orders_placed" in r:
            detail = f"{r.get('orders_placed')} orders placed, {r['pass_count']}/{r.get('total_followers', 100)} followers verified"
        elif "orders_count" in r:
            detail = f"{r.get('orders_count')} orders verified across {r['pass_count']}/{r.get('total_followers', 100)} followers"
        elif "orders_reduced" in r:
            detail = f"{r.get('orders_reduced')} orders reduced across {r['pass_count']}/{r.get('total_followers', 100)} followers"
        elif "orders_closed" in r:
            detail = f"{r.get('orders_closed')} orders closed across {r['pass_count']}/{r.get('total_followers', 100)} followers"
        elif "pass_count" in r:
            detail = f"{r['pass_count']}/{r.get('total_followers', 100)} passed"
        elif "behavior_summary" in r:
            detail = r["behavior_summary"]
        elif "summary" in r:
            detail = r["summary"]
        elif "probe_closed" in r:
            detail = f"Probe closed: {r.get('probe_closed')}, Master intact: {r.get('master_still_open')}"
        elif "orphan_count" in r:
            detail = f"{r['orphan_count']} orphans"
        elif "burst_count" in r:
            detail = f"{r['placed_count']} orders placed in {r.get('burst_duration_sec', '')}s"

        md_content += f"| **{r.get('name')}** | {r.get('name')} | {status_badge} | {detail} |\n"

    # Latency section if present
    lat = res_buy.get("latencies", {})
    if lat:
        md_content += f"""
---

## 2. Latency Metrics (Market BUY Fan-Out)

* **Minimum Fill Delay:** `{lat.get('min_ms')} ms`
* **Average Fill Delay:** `{lat.get('avg_ms')} ms`
* **P95 Fill Delay:** `{lat.get('p95_ms')} ms`
* **Maximum Fill Delay:** `{lat.get('max_ms')} ms`

---

## 3. Varied Multiplier Distribution (100 Followers)
* **1.0x:** Followers 1–25
* **2.0x:** Followers 26–50
* **3.0x:** Followers 51–75
* **0.5x:** Followers 76–100

---

## 4. Platform Behavior Observation (Scenario 20)
* **Scenario:** Unfollow mid-trade with an active copied position.
* **Observation:** `{res_unfollow.get('behavior_summary', 'N/A')}`
* **Note:** Per developer requirements, documented as informative observation without asserting premature failure.
"""

    with open(md_report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n" + "=" * 80)
    print(f"[+] TEST SUITE COMPLETED!")
    print(f"[+] Scenarios Passed  : {passed_tests}/{total_tests}")
    print(f"[+] Evidence JSON     : {json_report_path}")
    print(f"[+] Evidence Markdown : {md_report_path}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
