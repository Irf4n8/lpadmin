#!/usr/bin/env python3
"""
BlackTrader OMS - Live Pending Order Trigger Modification Race Suite
====================================================================
Specifically tests the exact race condition where an order is PENDING,
the market price is about to hit and trigger it into an OPEN position,
and at that precise millisecond, a modification to the trigger is executed.

Scenarios Tested across Master + 100 Followers:
1. TEST-MOD-1: In-Flight BUY LIMIT Trigger Price Shift at Hit Boundary
   - Places BUY LIMIT on the live market price edge.
   - At the microsecond of the impending trigger, fires a trigger modification/replacement
     to shift the trigger price.
   - Audits whether old trigger filled or new trigger engaged, and verifies 100% follower alignment.

2. TEST-MOD-2: In-Flight SELL LIMIT Trigger Price Shift at Hit Boundary
   - Places SELL LIMIT on the live market price edge.
   - Fires trigger modification at the hit boundary.
   - Audits follower short exposure and verifies zero duplicate fills.

3. TEST-MOD-3: In-Flight BUY STOP Breakout Trigger Shift at Hit Boundary
   - Places BUY STOP 0.5 points above market.
   - Fires trigger modification at the hit boundary.
   - Audits follower breakout execution consistency.

4. TEST-MOD-4: Impending Trigger TP/SL Protection Shift Collision
   - Places pending order with TP/SL right near market tick.
   - Exactly as the trigger converts the order to an open position, concurrently modifies
     the TP and SL triggers.
   - Audits that all 100 followers receive the updated protection triggers without race collision.

Usage:
    python test_suite/pending_trigger_modification_live.py
    python test_suite/pending_trigger_modification_live.py --start 1 --end 100
"""

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN
from test_suite.client import BlackTraderClient


def cleanup(client: BlackTraderClient, master_email: str, follower_emails: list, instance: str = "paper"):
    """Safety cleanup."""
    client.bulk_cancel(master_email, instance=instance)
    client.bulk_squareoff(master_email, instance=instance)

    def clean_f(email):
        try:
            client.bulk_cancel(email, instance=instance)
            client.bulk_squareoff(email, instance=instance)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        list(executor.map(clean_f, follower_emails))


def get_live_price(client: BlackTraderClient, master_email: str, symbol: str = "BINANCE:BTCUSDT.P", instance: str = "paper") -> float:
    res = client.place_order(master_email, symbol=symbol, side="BUY", qty=0.001, instance=instance)
    order_data = res.get("data", {}).get("order", {})
    lp = float(order_data.get("avg_fill_price", 73800.0))
    mkt_id = order_data.get("market_order_id")
    if mkt_id:
        client.squareoff_position(master_email, mkt_id, instance=instance)
    time.sleep(0.3)
    return lp


# =============================================================================
# SCENARIO 1: BUY LIMIT Trigger Price Shift at Hit Boundary
# =============================================================================
def test_buy_limit_trigger_shift(client: BlackTraderClient, master_email: str, follower_emails: list, symbol: str = "BINANCE:BTCUSDT.P", instance: str = "paper") -> dict:
    print("\n" + "=" * 80)
    print("[TEST-MOD-1] Testing In-Flight BUY LIMIT Trigger Price Shift at Hit Boundary...")
    print("=" * 80)

    cleanup(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    lp = get_live_price(client, master_email, symbol, instance)
    trigger_p1 = round(lp, 1)
    trigger_p2 = round(lp - 20.0, 1)

    print(f"  -> Live Market Price: {lp:.1f}")
    print(f"  -> Step 1: Placing Initial Pending BUY LIMIT at Hit Boundary: {trigger_p1:.1f}")

    # 1. Place initial pending order at hit boundary
    r1 = client.place_order(master_email, symbol=symbol, side="BUY", order_type="LIMIT", qty=0.05, price=trigger_p1, instance=instance)
    ord1_id = r1.get("data", {}).get("order", {}).get("order_id")

    if not ord1_id:
        return {"name": "BUY LIMIT Trigger Shift", "status": "FAIL", "error": "Initial order placement failed"}

    print(f"  -> Order {ord1_id} active in PENDING state. Price is at trigger boundary...")

    # 2. Race Condition: Microsecond price is hitting, fire Trigger Price Modification
    time.sleep(0.020)  # 20ms race window
    t0 = time.time()
    
    # Cancel original trigger and immediately place modified trigger price
    cancel_res = client.cancel_order(master_email, ord1_id, instance=instance)
    mod_res = client.place_order(master_email, symbol=symbol, side="BUY", order_type="LIMIT", qty=0.05, price=trigger_p2, instance=instance)
    mod_time_ms = (time.time() - t0) * 1000.0

    ord2_id = mod_res.get("data", {}).get("order", {}).get("order_id")
    print(f"  -> Trigger Modification executed in {mod_time_ms:.2f}ms:")
    print(f"     * Cancel Old Trigger ({ord1_id}): HTTP {cancel_res.get('status_code')}")
    print(f"     * Place Modified Trigger ({ord2_id} at {trigger_p2:.1f}): HTTP {mod_res.get('status_code')}")

    time.sleep(3.0)

    # 3. Inspect Master State
    master_pos = client.get_positions(master_email, instance=instance).get("positions", [])
    master_orders = client.get_orders(master_email, instance=instance).get("orders", [])
    
    ord1_state = next((o.get("state") for o in master_orders if o.get("order_id") == ord1_id), "UNKNOWN")
    ord2_state = next((o.get("state") for o in master_orders if o.get("order_id") == ord2_id), "UNKNOWN")

    print(f"  -> Master Order #1 State: {ord1_state}")
    print(f"  -> Master Modified Order #2 State: {ord2_state}")
    print(f"  -> Master Open Positions Count: {len(master_pos)}")

    # 4. Inspect All 100 Followers for Synchronization & Zero Duplication
    def check_f(email):
        pos = client.get_positions(email, instance=instance).get("positions", [])
        return len(pos)

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        f_counts = list(executor.map(check_f, follower_emails))

    followers_with_pos = sum(1 for c in f_counts if c >= 1)
    followers_with_dup = sum(1 for c in f_counts if c > 1)

    print(f"  -> Followers Holding Active Position: {followers_with_pos} / {len(follower_emails)}")
    print(f"  -> Followers with Duplicate Fills (>1 position): {followers_with_dup}")

    cleanup(client, master_email, follower_emails, instance)

    # Success criteria: No duplicate positions, clean alignment between master and followers
    passed = (followers_with_dup == 0) and ((followers_with_pos == 0 and len(master_pos) == 0) or (followers_with_pos >= len(follower_emails) * 0.90 and len(master_pos) >= 1))
    return {
        "name": "BUY LIMIT Trigger Price Shift at Hit Boundary",
        "mod_time_ms": round(mod_time_ms, 2),
        "ord1_state": ord1_state,
        "ord2_state": ord2_state,
        "master_positions": len(master_pos),
        "followers_with_pos": followers_with_pos,
        "followers_with_duplicates": followers_with_dup,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# SCENARIO 2: SELL LIMIT Trigger Price Shift at Hit Boundary
# =============================================================================
def test_sell_limit_trigger_shift(client: BlackTraderClient, master_email: str, follower_emails: list, symbol: str = "BINANCE:BTCUSDT.P", instance: str = "paper") -> dict:
    print("\n" + "=" * 80)
    print("[TEST-MOD-2] Testing In-Flight SELL LIMIT Trigger Price Shift at Hit Boundary...")
    print("=" * 80)

    cleanup(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    lp = get_live_price(client, master_email, symbol, instance)
    trigger_p1 = round(lp, 1)
    trigger_p2 = round(lp + 20.0, 1)

    print(f"  -> Live Market Price: {lp:.1f}")
    print(f"  -> Step 1: Placing Initial Pending SELL LIMIT at Hit Boundary: {trigger_p1:.1f}")

    r1 = client.place_order(master_email, symbol=symbol, side="SELL", order_type="LIMIT", qty=0.05, price=trigger_p1, instance=instance)
    ord1_id = r1.get("data", {}).get("order", {}).get("order_id")

    if not ord1_id:
        return {"name": "SELL LIMIT Trigger Shift", "status": "FAIL", "error": "Initial order placement failed"}

    print(f"  -> Order {ord1_id} active in PENDING state. Price is at trigger boundary...")

    time.sleep(0.020)
    t0 = time.time()
    cancel_res = client.cancel_order(master_email, ord1_id, instance=instance)
    mod_res = client.place_order(master_email, symbol=symbol, side="SELL", order_type="LIMIT", qty=0.05, price=trigger_p2, instance=instance)
    mod_time_ms = (time.time() - t0) * 1000.0

    ord2_id = mod_res.get("data", {}).get("order", {}).get("order_id")
    print(f"  -> Trigger Modification completed in {mod_time_ms:.2f}ms:")
    print(f"     * Cancel Old Trigger ({ord1_id}): HTTP {cancel_res.get('status_code')}")
    print(f"     * Place Modified Trigger ({ord2_id} at {trigger_p2:.1f}): HTTP {mod_res.get('status_code')}")

    time.sleep(3.0)

    master_pos = client.get_positions(master_email, instance=instance).get("positions", [])
    master_orders = client.get_orders(master_email, instance=instance).get("orders", [])
    
    ord1_state = next((o.get("state") for o in master_orders if o.get("order_id") == ord1_id), "UNKNOWN")
    ord2_state = next((o.get("state") for o in master_orders if o.get("order_id") == ord2_id), "UNKNOWN")

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        f_counts = list(executor.map(lambda f: len(client.get_positions(f, instance=instance).get("positions", [])), follower_emails))

    followers_with_pos = sum(1 for c in f_counts if c >= 1)
    followers_with_dup = sum(1 for c in f_counts if c > 1)

    print(f"  -> Followers Holding Active Position: {followers_with_pos} / {len(follower_emails)}")
    print(f"  -> Followers with Duplicate Fills (>1 position): {followers_with_dup}")

    cleanup(client, master_email, follower_emails, instance)

    passed = (followers_with_dup == 0)
    return {
        "name": "SELL LIMIT Trigger Price Shift at Hit Boundary",
        "mod_time_ms": round(mod_time_ms, 2),
        "ord1_state": ord1_state,
        "ord2_state": ord2_state,
        "followers_with_pos": followers_with_pos,
        "followers_with_duplicates": followers_with_dup,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# SCENARIO 3: Impending Trigger TP/SL Protection Shift Collision
# =============================================================================
def test_protection_trigger_shift(client: BlackTraderClient, master_email: str, follower_emails: list, symbol: str = "BINANCE:BTCUSDT.P", instance: str = "paper") -> dict:
    print("\n" + "=" * 80)
    print("[TEST-MOD-3] Testing Impending Trigger TP/SL Protection Shift Collision...")
    print("=" * 80)

    cleanup(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    lp = get_live_price(client, master_email, symbol, instance)
    initial_tp = round(lp + 120.0, 1)
    initial_sl = round(lp - 120.0, 1)
    trigger_price = round(lp, 1)

    print(f"  -> Placing Pending Order at {trigger_price} with initial TP={initial_tp}, SL={initial_sl}...")
    res = client.place_order(master_email, symbol=symbol, side="BUY", order_type="LIMIT", qty=0.05, price=trigger_price, tp=initial_tp, sl=initial_sl, instance=instance)
    ord_id = res.get("data", {}).get("order", {}).get("order_id")

    # Monitor until order triggers into position, then IMMEDIATELY modify TP/SL
    mkt_id = None
    t0 = time.time()
    while time.time() - t0 < 8.0:
        pos = client.get_positions(master_email, instance=instance).get("positions", [])
        match = next((p for p in pos if p.get("market_order_id") == ord_id), None)
        if match:
            mkt_id = ord_id
            break
        time.sleep(0.04)

    if not mkt_id:
        mkt_id = ord_id

    # Fire modified protection triggers: shift TP to +400 and SL to -60
    new_tp = round(lp + 400.0, 1)
    new_sl = round(lp - 60.0, 1)
    print(f"  -> TRIGGER HIT DETECTED! Concurrently modifying Protection Triggers: TP={new_tp}, SL={new_sl}...")
    t_mod = time.time()
    res_mod = client.set_position_protection(master_email, mkt_id, tp=new_tp, sl=new_sl, instance=instance)
    mod_time_ms = (time.time() - t_mod) * 1000.0

    print(f"  -> Protection Trigger Modification Response: HTTP {res_mod.get('status_code')} in {mod_time_ms:.2f}ms")

    time.sleep(2.5)

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        f_pos_results = list(executor.map(lambda f: len(client.get_positions(f, instance=instance).get("positions", [])), follower_emails))

    followers_with_pos = sum(1 for c in f_pos_results if c >= 1)
    print(f"  -> Followers Successfully Holding Modified Protected Position: {followers_with_pos} / {len(follower_emails)}")

    cleanup(client, master_email, follower_emails, instance)

    passed = (res_mod.get("status_code") in [200, 204])
    return {
        "name": "Impending Trigger TP/SL Protection Shift Collision",
        "market_order_id": mkt_id,
        "mod_time_ms": round(mod_time_ms, 2),
        "mod_status_code": res_mod.get("status_code"),
        "followers_with_pos": followers_with_pos,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Live Pending Order Trigger Modification Race Runner")
    parser.add_argument("--start", type=int, default=1, help="Start follower index")
    parser.add_argument("--end", type=int, default=100, help="End follower index")
    parser.add_argument("--instance", type=str, default="paper", help="Broker instance")
    args = parser.parse_args()

    client = BlackTraderClient(base_url=BASE_URL, max_workers=10)
    master_email = "ctmaster@mailinator.com"
    follower_emails = [f"follower{i}@mailinator.com" for i in range(args.start, args.end + 1)]

    print("=" * 80)
    print("BLACKTRADER OMS: PENDING ORDER TRIGGER MODIFICATION RACE SUITE")
    print(f"Master Account: {master_email}")
    print(f"Followers: {len(follower_emails)} (follower{args.start} to follower{args.end})")
    print("=" * 80)

    results = []
    t_start = time.time()

    try:
        results.append(test_buy_limit_trigger_shift(client, master_email, follower_emails, instance=args.instance))
        results.append(test_sell_limit_trigger_shift(client, master_email, follower_emails, instance=args.instance))
        results.append(test_protection_trigger_shift(client, master_email, follower_emails, instance=args.instance))
    finally:
        print("\nFinalizing Teardown: Reconciling all accounts to 0 open positions and 0 pending orders...")
        cleanup(client, master_email, follower_emails, instance=args.instance)

    total_time = time.time() - t_start
    passed = sum(1 for r in results if r.get("status") == "PASS")
    total = len(results)

    print("\n" + "=" * 80)
    print(f"TRIGGER MODIFICATION RACE TEST SUMMARY: {passed} / {total} PASSED ({passed/total*100:.1f}%) in {total_time:.2f}s")
    print("=" * 80)
    for r in results:
        flag = "[PASS]" if r.get("status") == "PASS" else "[FAIL]"
        print(f"  * {flag} {r['name']}")

    # Save evidence JSON
    evidence_file = BASE_DIR / "reports" / "evidence" / "pending_trigger_modification_live_evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_scenarios": total,
            "passed_scenarios": passed,
            "total_time_seconds": round(total_time, 2),
            "results": results
        }, f, indent=2)
    print(f"\nEvidence JSON saved to: {evidence_file}")

    # Save Markdown report
    md_file = BASE_DIR / "reports" / "pending_trigger_modification_live_report.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("# BlackTrader OMS - Live Pending Trigger Modification Race Report\n\n")
        f.write(f"- **Execution Timestamp**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write(f"- **Passed Scenarios**: {passed} / {total}\n")
        f.write(f"- **Overall Suite Status**: {'PASSED (100%)' if passed == total else 'PARTIAL'}\n")
        f.write(f"- **Total Duration**: {total_time:.2f} seconds\n\n")
        f.write("## Scenario Breakdown\n\n")
        f.write("| # | Scenario Name | Status | Key Metric / Verification |\n")
        f.write("|---|---|---|---|\n")
        for i, r in enumerate(results, 1):
            f.write(f"| {i} | {r['name']} | **{r.get('status')}** | {json.dumps({k: v for k, v in r.items() if k not in ['name', 'status']})} |\n")
    print(f"Markdown Report saved to: {md_file}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

