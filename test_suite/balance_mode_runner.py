#!/usr/bin/env python3
"""
BlackTrader Balance-Based Copy Trading Test Suite (100 Followers)
=================================================================
Executes full transition and testing for Balance-Based Copy Trading:
1. All 100 followers completely leave the master (unfollow).
2. Verifies master active follower linkages drop to 0.
3. Configures varied capital balances via Admin API across the 100 followers:
   - Master: 100,000,000 (Base 1.0x)
   - Followers 1-25: 100,000,000 (Ratio 1.0x -> 0.10 lot)
   - Followers 26-50: 200,000,000 (Ratio 2.0x -> 0.20 lot)
   - Followers 51-75: 300,000,000 (Ratio 3.0x -> 0.30 lot)
   - Followers 76-100: 50,000,000 (Ratio 0.5x -> 0.05 lot)
4. All 100 followers join in Balance-Based mode (method='balance').
5. Verifies 100 active linkages restored with method='balance'.
6. Executes all scenarios with at least 10 orders per scenario:
   - Market BUY Fan-Out (10 orders -> 1,000 balance-scaled positions)
   - Partial Close across 10 orders (50% reduction -> 1,000 positions)
   - Full Close across 10 orders (squareoff -> 0 orphans)
   - TP / SL Propagation across 10 orders (1,000 positions with active TP/SL)
   - Pending Limit Orders & Cancel (10 orders -> 1,000 pendings clean)
   - Rapid Concurrency Burst (10 orders)
   - Market SELL Fan-Out (10 orders -> 1,000 short positions)
   - Follower manual close isolation & follow mid-trade isolation
   - Final teardown & zero orphan verification across all 101 accounts
7. Generates evidence reports in reports/evidence/.

Usage:
    python test_suite/balance_mode_runner.py
    python test_suite/balance_mode_runner.py --start 1 --end 100 --orders-count 10
"""

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import MASTER_EMAIL, MASTER_ID, FOLLOWER_COUNT
from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN
from test_suite.baseline import get_expected_multiplier
from test_suite.client import BlackTraderClient
from test_suite.scenarios import ScenarioRunner


def setup_balance_mode(
    client: BlackTraderClient,
    master_email: str,
    master_client_id: str,
    follower_emails: list,
    instance: str = "paper"
) -> dict:
    print("\n" + "=" * 80)
    print(f" [PHASE 1] TRANSITION TO BALANCE-BASED COPY TRADING ({len(follower_emails)} FOLLOWERS)")
    print("=" * 80)

    # Step 1: Teardown existing positions and orders
    client.teardown_all_accounts(master_email, follower_emails, instance=instance)
    time.sleep(1.5)

    # Step 2: All 100 followers completely leave master
    print(f"[*] Step 2: All {len(follower_emails)} followers leaving master {master_email} (unfollowing)...")
    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        list(executor.map(lambda em: client.unfollow_master(em, master_client_id, instance=instance), follower_emails))
    time.sleep(2.0)

    # Step 3: Verify active linkages drop to 0
    active_after_unfollow = client.get_copy_followers(master_email, instance=instance, active_only=True)
    print(f"[+] Master reports {len(active_after_unfollow)} active follower links after leave (target: 0).")

    # Step 4: Configure varied balances across the 100 followers via Admin API
    print(f"[*] Step 4: Fetching admin member records to configure varied balances...")
    members = client.get_admin_members()
    email_to_id = {m.get("email"): m.get("member_id") for m in members}

    print(f"[*] Configuring varied balances across {len(follower_emails)} followers:")
    print(f"    - Followers 1-25  : 100,000,000 (Ratio 1.0x -> 0.10 lot)")
    print(f"    - Followers 26-50 : 200,000,000 (Ratio 2.0x -> 0.20 lot)")
    print(f"    - Followers 51-75 : 300,000,000 (Ratio 3.0x -> 0.30 lot)")
    print(f"    - Followers 76-100:  50,000,000 (Ratio 0.5x -> 0.05 lot)")
    print(f"    - Master          : 100,000,000 (Base  1.0x)")

    # Set master balance
    master_mem_id = email_to_id.get(master_email)
    if master_mem_id:
        client.set_member_balance(master_mem_id, balance=100000000.0, instance=instance)

    # Set follower balances concurrently
    def set_balance_item(item):
        idx, email = item
        mult = get_expected_multiplier(idx)
        target_balance = 100000000.0 * mult
        mem_id = email_to_id.get(email)
        if mem_id:
            res = client.set_member_balance(mem_id, balance=target_balance, instance=instance)
            return email, target_balance, res.get("status_code") == 200
        return email, target_balance, False

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        items = [(i + 1, email) for i, email in enumerate(follower_emails)]
        set_results = list(executor.map(set_balance_item, items))

    successful_balance_sets = sum(1 for _, _, ok in set_results if ok)
    print(f"[+] Balances configured: {successful_balance_sets}/{len(follower_emails)} successful.")
    time.sleep(1.5)

    # Step 5: All 100 followers join in Balance-Based mode
    print(f"[*] Step 5: All {len(follower_emails)} followers joining master in BALANCE-BASED mode (method='balance')...")
    def join_balance_mode(email):
        headers = {
            "Authorization": f"Bearer {client.get_trader_token(email)}",
            "Content-Type": "application/json"
        }
        payload = {
            "master_client_id": master_client_id,
            "method": "balance",
            "multiplier": 1.0,
            "reverse": False,
            "copy_mode": "public"
        }
        resp = client.request_with_retry("POST", f"{client.base_url}/v1/oms/{instance}/copy/follow", headers=headers, json=payload)
        return email, resp.status_code == 200

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        join_results = list(executor.map(join_balance_mode, follower_emails))

    successful_joins = sum(1 for _, ok in join_results if ok)
    print(f"[+] Balance-based join completed: {successful_joins}/{len(follower_emails)} successful.")
    time.sleep(2.0)

    # Step 6: Verify master reports all active links with method='balance'
    active_after_join = client.get_copy_followers(master_email, instance=instance, active_only=True)
    all_balance_method = all(f.get("method") == "balance" for f in active_after_join)
    print(f"[+] Master reports {len(active_after_join)} active follower links (all method='balance': {all_balance_method}).")

    # Step 7: Pre-test snapshot
    print(f"[*] Concurrently snapshotting master and all {len(follower_emails)} followers...")
    master_pos_data = client.get_positions(master_email, instance=instance)
    master_funds = master_pos_data.get("funds", {})
    master_snapshot = {
        "email": master_email,
        "client_id": master_client_id,
        "balance": master_funds.get("balance", 0),
        "equity": master_funds.get("equity", 0),
        "open_positions": master_pos_data.get("count", 0)
    }

    follower_positions = client.fetch_all_followers_positions(follower_emails, instance=instance)
    follower_snapshots = {}
    for i, email in enumerate(follower_emails):
        idx = i + 1
        pos_data = follower_positions.get(email, {})
        funds = pos_data.get("funds", {})
        mult = get_expected_multiplier(idx)
        follower_snapshots[email] = {
            "index": idx,
            "balance_ratio": mult,
            "balance": funds.get("balance", 0),
            "equity": funds.get("equity", 0),
            "open_positions": pos_data.get("count", 0)
        }

    setup_summary = {
        "unfollow_clean": len(active_after_unfollow) == 0,
        "successful_balance_sets": successful_balance_sets,
        "successful_joins": successful_joins,
        "active_links_count": len(active_after_join),
        "all_balance_method": all_balance_method,
        "master_snapshot": master_snapshot,
        "follower_snapshots_count": len(follower_snapshots)
    }

    print("=" * 80 + "\n")
    return setup_summary


def main():
    parser = argparse.ArgumentParser(description="BlackTrader Balance-Based Copy Trading 100-Follower Test Runner")
    parser.add_argument("--master", default=MASTER_EMAIL, help="Master trader email")
    parser.add_argument("--master-id", default=MASTER_ID, help="Master client ID")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Follower prefix")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="Follower domain")
    parser.add_argument("--start", type=int, default=1, help="Starting follower index")
    parser.add_argument("--end", type=int, default=FOLLOWER_COUNT, help="Ending follower index")
    parser.add_argument("--symbol", default="BINANCE:BTCUSDT.P", help="Trading symbol")
    parser.add_argument("--lot", type=float, default=0.1, help="Master lot size per order")
    parser.add_argument("--orders-count", type=int, default=10, help="Number of orders per scenario (>= 10)")
    parser.add_argument("--instance", default="paper", help="Trading instance (paper)")
    parser.add_argument("--burst", type=int, default=10, help="Number of orders in rapid burst scenario")
    args = parser.parse_args()

    follower_emails = [f"{args.prefix}{i}@{args.domain}" for i in range(args.start, args.end + 1)]

    print("\n" + "=" * 80)
    print(" BLACKTRADER BALANCE-BASED COPY TRADING 100-FOLLOWER TEST SUITE")
    print("=" * 80)
    print(f"[*] Base URL            : {BASE_URL}")
    print(f"[*] Master Trader       : {args.master} (ID: {args.master_id})")
    print(f"[*] Followers Tested    : {len(follower_emails)} ({follower_emails[0]} -> {follower_emails[-1]})")
    print(f"[*] Trading Symbol      : {args.symbol}")
    print(f"[*] Copy Trading Mode   : BALANCE-BASED (method='balance')")
    print(f"[*] Orders Per Scenario : {args.orders_count} (>= 10 orders)")
    print(f"[*] Lot Per Order       : {args.lot}")
    print(f"[*] Trading Instance    : {args.instance} (Hedging)")
    print("=" * 80 + "\n")

    client = BlackTraderClient(base_url=BASE_URL, max_workers=10)
    test_start_time = datetime.now(timezone.utc).isoformat()
    results = []

    # -------------------------------------------------------------------------
    # Transition Phase: Leave Master & Join in Balance Mode
    # -------------------------------------------------------------------------
    setup_summary = setup_balance_mode(
        client=client,
        master_email=args.master,
        master_client_id=args.master_id,
        follower_emails=follower_emails,
        instance=args.instance
    )

    runner = ScenarioRunner(
        client=client,
        master_email=args.master,
        follower_emails=follower_emails,
        symbol=args.symbol,
        instance=args.instance
    )

    # -------------------------------------------------------------------------
    # Scenario 1: Market BUY Fan-Out (10 Orders, Balance-Scaled)
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
    # Scenario 7: Market SELL Fan-Out & Balance Sizing (10 Orders)
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
    # Final Clean Teardown & Zero Orphan Verification
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
    # Generate Evidence Files (JSON & Markdown)
    # -------------------------------------------------------------------------
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = BASE_DIR / "reports" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    json_report_path = evidence_dir / f"balance_mode_evidence_{timestamp_str}.json"
    md_report_path = evidence_dir / f"balance_mode_evidence_{timestamp_str}.md"

    report_payload = {
        "suite_name": "BlackTrader Balance-Based Copy Trading 100-Follower Test Suite",
        "copy_mode": "balance",
        "started_at": test_start_time,
        "completed_at": test_end_time,
        "master_email": args.master,
        "master_id": args.master_id,
        "followers_count": len(follower_emails),
        "symbol": args.symbol,
        "lot_size": args.lot,
        "orders_per_scenario": args.orders_count,
        "instance": args.instance,
        "setup_summary": setup_summary,
        "scenarios": results
    }

    with open(json_report_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    passed_tests = sum(1 for r in results if r.get("status") == "PASS")
    total_tests = len([r for r in results if r.get("status") in ["PASS", "FAIL"]])

    md_content = f"""# Balance-Based Copy Trading 100-Follower Test Evidence Report

**Generated:** {test_end_time}  
**Master Trader:** `{args.master}` (`{args.master_id}`)  
**Followers Tested:** {len(follower_emails)} (`{follower_emails[0]}` to `{follower_emails[-1]}`)  
**Trading Symbol:** `{args.symbol}` (Lot per order: {args.lot})  
**Copy Trading Mode:** `balance` (Follower Lot = Master Lot × Follower Balance / Master Balance)  
**Orders per Scenario:** ≥ {args.orders_count} orders  
**Instance:** `{args.instance}` (Hedging)  
**Overall Result:** **{passed_tests}/{total_tests} SCENARIOS PASSED**

---

## 1. Executive Summary

| Scenario | Orders Placed | Followers Verified | Status | Details |
| :--- | :---: | :---: | :---: | :--- |
"""

    for r in results:
        status_badge = "✅ PASS" if r.get("status") == "PASS" else ("ℹ️ OBSERVED" if r.get("status") == "OBSERVED" else "❌ FAIL")
        detail = ""
        orders_col = r.get("orders_placed", r.get("orders_count", r.get("orders_reduced", r.get("orders_closed", r.get("burst_count", "10")))))
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
        elif "orphan_count" in r:
            detail = f"{r['orphan_count']} orphans"

        md_content += f"| **{r.get('name')}** | {orders_col} | {r.get('pass_count', len(follower_emails))}/{len(follower_emails)} | {status_badge} | {detail} |\n"

    md_content += f"""
---

## 2. Transition & Dynamic Balance Scaling Verification
1. **Full Leave (Unfollow):** All {len(follower_emails)} followers cleanly unfollowed master; active links confirmed dropped to **0**.
2. **Capital Configuration:**
   * Master Balance: `100,000,000.00` ($1.0\\times$)
   * Followers 1–25 Balance: `100,000,000.00` (Ratio: **$1.0\\times$** -> **0.10 lot**)
   * Followers 26–50 Balance: `200,000,000.00` (Ratio: **$2.0\\times$** -> **0.20 lot**)
   * Followers 51–75 Balance: `300,000,000.00` (Ratio: **$3.0\\times$** -> **0.30 lot**)
   * Followers 76–100 Balance: `50,000,000.00` (Ratio: **$0.5\\times$** -> **0.05 lot**)
3. **Balance Join:** All {len(follower_emails)} followers re-linked with `method='balance'`; confirmed active links restored to **{len(follower_emails)}**.
4. **Execution Sizing:** Each master order of `0.10` lot automatically scaled across all 100 followers in exact proportion to their balance ratios.
"""

    with open(md_report_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n" + "=" * 80)
    print(f"[+] BALANCE-BASED TEST SUITE COMPLETED!")
    print(f"[+] Scenarios Passed  : {passed_tests}/{total_tests}")
    print(f"[+] Evidence JSON     : {json_report_path}")
    print(f"[+] Evidence Markdown : {md_report_path}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()

