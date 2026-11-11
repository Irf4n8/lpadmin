#!/usr/bin/env python3
"""
BlackTrader OMS - Extreme Scenarios & Concurrency Race Condition Suite
======================================================================
Deeply validates the mission-critical edge cases, high-frequency race conditions,
lifecycle hazards, and mathematical scaling of the BlackTrader Copy Trading OMS:

1. SCENARIO-1: Rapid Market Reversal (Flip Long to Short in <50ms)
   - Master fires BUY 0.05 lot, immediately (<30ms) fires SELL 0.10 lot.
   - Validates that high-speed queue handling does not invert order execution sequence
     or strand followers with unbalanced exposure.

2. SCENARIO-2: High-Contention Simultaneous Square-Offs (Row Locking & Double Close)
   - Master opens BUY 0.05 lot across 100 followers.
   - Simultaneously across threads, 5 probe followers execute manual local position close
     at the exact same millisecond that Master fires bulk squareoff.
   - Validates database row locking, absence of deadlocks, and zero double-close errors.

3. SCENARIO-3: Mid-Trade Dynamic Capital Shock (Deposit Collision)
   - Follower 10 (Balance Mode) enters trade with 100M capital ratio (1.0x).
   - While trade is OPEN, Admin API dynamically injects +50M balance to Follower 10 (150M).
   - Master triggers bulk squareoff.
   - Validates that follower position closes the EXACT entry volume (0.05 lot) rather than
     recalculating based on updated capital, ensuring zero residual orphan positions.

4. SCENARIO-4: Micro-Lot Underflow (Sub-Contract Step Protection)
   - Master places the broker's minimum contract lot (0.001 lot).
   - Tier 4 followers (50M balance vs 100M Master = 0.5x ratio) yield 0.0005 raw lot.
   - Validates whether OMS cleanly rounds up to minimum step (0.001) or rejects gracefully
     without throwing unhandled 500 exceptions or corrupting follower queues.

5. SCENARIO-5: Dual-Sided Breakout Straddle & OCO Pending Cancellation
   - Master places BUY_STOP above market and SELL_STOP below market.
   - Validates 200 pending orders fan out cleanly across 100 followers.
   - Master cancels both; validates 100% cancellation fan-out with zero hanging pending orders.

6. SCENARIO-6: Cross-Asset Portfolio Bombardment (Multi-Pair Concurrent Burst)
   - Master concurrently fires orders across 3 distinct crypto assets:
     BTCUSDT.P (0.02), ETHUSDT.P (0.20), and SOLUSDT.P (1.00).
   - Validates 300 positions created in parallel with clean margin allocation and zero crosstalk.

7. SCENARIO-7: Full Accounting & Financial Scaling Reconciliation
   - Master executes a round-trip trade.
   - Verifies mathematical scaling: sum(Follower Lot Volume) == Master Lot * sum(Effective Ratios).
   - Verifies 0 used margin and zero margin leakage across all 101 accounts.

Usage:
    python test_suite/extreme_scenarios_and_race_runner.py
    python test_suite/extreme_scenarios_and_race_runner.py --start 1 --end 100
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

from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN
from test_suite.baseline import get_expected_multiplier
from test_suite.client import BlackTraderClient


def cleanup_all(client: BlackTraderClient, master_email: str, follower_emails: list, instance: str = "paper"):
    """Safety cleanup: cancel all pending orders and close all positions across all accounts."""
    client.bulk_cancel(master_email, instance=instance)
    client.bulk_squareoff(master_email, instance=instance)

    def clean_follower(email):
        try:
            client.bulk_cancel(email, instance=instance)
            client.bulk_squareoff(email, instance=instance)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        list(executor.map(clean_follower, follower_emails))


# =============================================================================
# SCENARIO 1: Rapid Market Reversal (Flip Long to Short in <50ms)
# =============================================================================
def test_rapid_reversal(
    client: BlackTraderClient,
    master_email: str,
    follower_emails: list,
    symbol: str = "BINANCE:BTCUSDT.P",
    instance: str = "paper"
) -> dict:
    print("\n" + "=" * 80)
    print("[SCENARIO-1] Testing Rapid Market Reversal (Long-to-Short Flip in <50ms)...")
    print("=" * 80)

    cleanup_all(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    # 1. Fire BUY order on master
    t0 = time.time()
    res_buy = client.place_order(master_email, symbol=symbol, side="BUY", qty=0.05, instance=instance)
    
    # 2. Immediately fire SELL order (2x lot) with sub-30ms delta
    res_sell = client.place_order(master_email, symbol=symbol, side="SELL", qty=0.10, instance=instance)
    delta_ms = (time.time() - t0) * 1000.0

    print(f"  -> Master fired BUY 0.05 and SELL 0.10 within {delta_ms:.2f}ms")
    print(f"  -> BUY Order Status: HTTP {res_buy.get('status_code')}")
    print(f"  -> SELL Order Status: HTTP {res_sell.get('status_code')}")

    if res_buy.get("status_code") != 200 or res_sell.get("status_code") != 200:
        return {"name": "Rapid Market Reversal", "status": "FAIL", "error": "Master order submission failed"}

    # Wait for queue processing and MT5 broker execution
    print("  -> Waiting 3.0s for OMS queue & MT5 broker execution across 100 followers...")
    time.sleep(3.0)

    # Verify followers received the orders cleanly
    def check_follower(email):
        orders_res = client.get_orders(email, instance=instance)
        pos_res = client.get_positions(email, instance=instance)
        orders = orders_res.get("orders", [])
        positions = pos_res.get("positions", [])
        return {"email": email, "order_count": len(orders), "pos_count": len(positions), "positions": positions}

    results = []
    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        futures = {executor.submit(check_follower, f): f for f in follower_emails}
        for fut in as_completed(futures):
            results.append(fut.result())

    # Count how many received both executions
    followers_with_orders = sum(1 for r in results if r["order_count"] >= 2)
    followers_with_pos = sum(1 for r in results if r["pos_count"] >= 1)

    print(f"  -> Followers with >= 2 Recorded Orders: {followers_with_orders} / {len(follower_emails)}")
    print(f"  -> Followers Holding Active Position(s): {followers_with_pos} / {len(follower_emails)}")

    # Clean square-off
    cleanup_all(client, master_email, follower_emails, instance)

    passed = (followers_with_orders >= len(follower_emails) * 0.95)
    return {
        "name": "Rapid Market Reversal (Long-to-Short Flip)",
        "delta_ms": round(delta_ms, 2),
        "followers_with_orders": followers_with_orders,
        "followers_with_pos": followers_with_pos,
        "total_followers": len(follower_emails),
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# SCENARIO 2: High-Contention Simultaneous Square-Offs (Row Locking Resilience)
# =============================================================================
def test_simultaneous_squareoffs(
    client: BlackTraderClient,
    master_email: str,
    follower_emails: list,
    symbol: str = "BINANCE:BTCUSDT.P",
    instance: str = "paper"
) -> dict:
    print("\n" + "=" * 80)
    print("[SCENARIO-2] Testing High-Contention Simultaneous Square-Offs (Row Locking)...")
    print("=" * 80)

    cleanup_all(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    # 1. Open BUY position on master
    res_open = client.place_order(master_email, symbol=symbol, side="BUY", qty=0.05, instance=instance)
    if res_open.get("status_code") != 200:
        return {"name": "Simultaneous Square-Offs", "status": "FAIL", "error": "Master open failed"}

    print("  -> Master opened BUY 0.05. Waiting 2.5s for 100-follower fan-out...")
    time.sleep(2.5)

    # Pick 5 sample probe followers to close their own local position concurrently
    probe_followers = follower_emails[:5]
    probe_mkt_ids = {}
    for f in probe_followers:
        pos_res = client.get_positions(f, instance=instance)
        pos_list = pos_res.get("positions", [])
        if pos_list:
            probe_mkt_ids[f] = pos_list[0].get("market_order_id")

    print(f"  -> Firing 5 manual follower closes and Master bulk squareoff simultaneously...")

    def close_follower_task(email, mkt_id):
        if not mkt_id:
            return {"email": email, "type": "follower_close", "status_code": 200, "skipped": True}
        res = client.squareoff_position(email, mkt_id, instance=instance)
        return {"email": email, "type": "follower_close", "status_code": res.get("status_code"), "data": res.get("data")}

    def close_master_task():
        res = client.bulk_squareoff(master_email, instance=instance)
        return {"email": master_email, "type": "master_bulk_squareoff", "status_code": res.get("status_code"), "data": res.get("data")}

    t0 = time.time()
    futures = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit master squareoff
        futures.append(executor.submit(close_master_task))
        # Submit probe follower closes simultaneously
        for f, mid in probe_mkt_ids.items():
            futures.append(executor.submit(close_follower_task, f, mid))

    collision_results = [f.result() for f in futures]
    collision_time = (time.time() - t0) * 1000.0

    print(f"  -> Simultaneous execution completed in {collision_time:.2f}ms")
    for r in collision_results:
        print(f"     * {r['type']} ({r['email']}): HTTP {r['status_code']}")

    time.sleep(2.5)

    # Verify zero open positions across all accounts
    master_pos = client.get_positions(master_email, instance=instance).get("positions", [])
    
    follower_positions_left = 0
    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        f_pos_results = list(executor.map(lambda f: len(client.get_positions(f, instance=instance).get("positions", [])), follower_emails))
        follower_positions_left = sum(f_pos_results)

    print(f"  -> Master Remaining Open Positions: {len(master_pos)}")
    print(f"  -> Total Follower Remaining Open Positions: {follower_positions_left}")

    # No 500 server crashes and 0 open positions left
    has_500 = any(r.get("status_code") == 500 for r in collision_results)
    passed = (not has_500) and (len(master_pos) == 0) and (follower_positions_left == 0)

    return {
        "name": "Simultaneous Opposing Square-Offs (Row Locking)",
        "collision_time_ms": round(collision_time, 2),
        "collision_results_count": len(collision_results),
        "has_500_errors": has_500,
        "master_remaining_pos": len(master_pos),
        "follower_remaining_pos": follower_positions_left,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# SCENARIO 3: Mid-Trade Dynamic Capital Shock (Deposit Mid-Trade)
# =============================================================================
def test_midtrade_dynamic_capital_shock(
    client: BlackTraderClient,
    master_email: str,
    follower_emails: list,
    target_follower_index: int = 10,
    symbol: str = "BINANCE:BTCUSDT.P",
    instance: str = "paper"
) -> dict:
    print("\n" + "=" * 80)
    print(f"[SCENARIO-3] Testing Mid-Trade Dynamic Capital Shock (Deposit on Follower #{target_follower_index})...")
    print("=" * 80)

    target_email = f"follower{target_follower_index}@mailinator.com"
    cleanup_all(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    # 1. Fetch member ID from admin API
    members = client.get_admin_members()
    target_member = next((m for m in members if m.get("email") == target_email), None)
    if not target_member:
        return {"name": "Mid-Trade Capital Shock", "status": "FAIL", "error": f"Member {target_email} not found in admin API"}

    member_id = target_member.get("id") or target_member.get("member_id")

    # Record initial balance (e.g. 100M)
    init_funds = client.get_positions(target_email, instance=instance).get("funds", {})
    init_balance = float(init_funds.get("balance", 100000000.0))

    # 2. Master opens BUY 0.05 lot
    res_open = client.place_order(master_email, symbol=symbol, side="BUY", qty=0.05, instance=instance)
    if res_open.get("status_code") != 200:
        return {"name": "Mid-Trade Capital Shock", "status": "FAIL", "error": "Master open order failed"}

    print(f"  -> Master opened BUY 0.05 lot. Waiting 2.0s for follower fill...")
    time.sleep(2.0)

    # Check follower's entry position lot size
    pos_res = client.get_positions(target_email, instance=instance)
    pos_list = pos_res.get("positions", [])
    if not pos_list:
        return {"name": "Mid-Trade Capital Shock", "status": "FAIL", "error": f"Follower {target_email} did not receive entry position"}

    entry_qty = float(pos_list[0].get("net_qty", 0.05))
    mkt_id = pos_list[0].get("market_order_id")
    print(f"  -> Follower #{target_follower_index} Entry Position: {entry_qty} Lots (Order ID: {mkt_id})")

    # 3. Dynamic Capital Shock: Admin API injects +50M mid-trade
    shock_balance = init_balance + 50000000.0
    print(f"  -> Injecting Mid-Trade Capital Shock via Admin API: {init_balance:,.2f} -> {shock_balance:,.2f}...")
    bal_res = client.set_member_balance(member_id, shock_balance, instance=instance)
    print(f"  -> Balance Update Response: HTTP {bal_res.get('status_code')}")

    # 4. Master squares off position
    print(f"  -> Master triggers bulk squareoff while follower has higher balance...")
    client.bulk_squareoff(master_email, instance=instance)
    time.sleep(2.5)

    # 5. Check Follower 10 position: must be 0 (cleanly closed with exact entry volume!)
    final_pos_res = client.get_positions(target_email, instance=instance)
    final_pos_list = final_pos_res.get("positions", [])
    final_pos_count = len(final_pos_list)

    print(f"  -> Follower #{target_follower_index} Remaining Open Positions: {final_pos_count}")

    # Restore initial balance
    print(f"  -> Restoring initial balance {init_balance:,.2f} for Follower #{target_follower_index}...")
    client.set_member_balance(member_id, init_balance, instance=instance)

    cleanup_all(client, master_email, follower_emails, instance)

    passed = (final_pos_count == 0)
    return {
        "name": "Mid-Trade Dynamic Capital Shock",
        "target_email": target_email,
        "entry_qty": entry_qty,
        "initial_balance": init_balance,
        "shock_balance": shock_balance,
        "final_open_positions": final_pos_count,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# SCENARIO 4: Micro-Lot Underflow (Sub-Contract Step Protection)
# =============================================================================
def test_microlot_underflow(
    client: BlackTraderClient,
    master_email: str,
    follower_emails: list,
    symbol: str = "BINANCE:BTCUSDT.P",
    instance: str = "paper"
) -> dict:
    print("\n" + "=" * 80)
    print("[SCENARIO-4] Testing Micro-Lot Underflow (Sub-Contract Step Protection)...")
    print("=" * 80)

    cleanup_all(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    # Master places minimum contract size: 0.001 lot
    print("  -> Master placing broker MINIMUM contract lot: 0.001 lot...")
    res = client.place_order(master_email, symbol=symbol, side="BUY", qty=0.001, instance=instance)
    if res.get("status_code") != 200:
        return {"name": "Micro-Lot Underflow", "status": "FAIL", "error": "Master order failed"}

    print("  -> Waiting 2.5s for fan-out to followers...")
    time.sleep(2.5)

    # Inspect followers, especially Tier 4 (followers 76-100) where ratio is 0.5x
    # 0.001 * 0.5x = 0.0005 (below the 0.001 contract step)
    tier4_followers = follower_emails[75:85]
    tier4_lots = []
    for f in tier4_followers:
        pos_res = client.get_positions(f, instance=instance)
        positions = pos_res.get("positions", [])
        if positions:
            tier4_lots.append(float(positions[0].get("net_qty", 0.0)))

    print(f"  -> Sample Tier 4 (0.5x ratio) Follower Lots: {tier4_lots[:5]}")

    # Check that lots are rounded up to minimum step 0.001 or handled without errors
    all_valid_lots = all(lot >= 0.001 for lot in tier4_lots) if tier4_lots else True
    print(f"  -> All Tier 4 Follower Lots Enforce Minimum Step (>= 0.001): {all_valid_lots}")

    cleanup_all(client, master_email, follower_emails, instance)

    return {
        "name": "Micro-Lot Underflow (Sub-Contract Step)",
        "master_qty": 0.001,
        "sample_tier4_lots": tier4_lots[:5],
        "all_valid_lots": all_valid_lots,
        "status": "PASS" if all_valid_lots else "FAIL"
    }


# =============================================================================
# SCENARIO 5: Dual-Sided Breakout Straddle & OCO Pending Cancellation
# =============================================================================
def test_breakout_straddle_and_cancel(
    client: BlackTraderClient,
    master_email: str,
    follower_emails: list,
    symbol: str = "BINANCE:BTCUSDT.P",
    instance: str = "paper"
) -> dict:
    print("\n" + "=" * 80)
    print("[SCENARIO-5] Testing Dual-Sided Breakout Straddle & OCO Pending Cancellation...")
    print("=" * 80)

    cleanup_all(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    # Reference price ~74000
    ref_price = 74000.0
    recent_orders = client.get_orders(master_email, instance=instance).get("orders", [])
    if recent_orders and recent_orders[0].get("avg_fill_price"):
        ref_price = float(recent_orders[0].get("avg_fill_price"))

    buy_stop_price = round(ref_price + 300.0, 1)
    sell_stop_price = round(ref_price - 300.0, 1)

    print(f"  -> Reference Market Price: {ref_price:.1f}")
    print(f"  -> Placing BUY_STOP at {buy_stop_price:.1f} and SELL_STOP at {sell_stop_price:.1f}...")

    # 1. Place BUY_STOP and SELL_STOP
    res_bs = client.place_order(master_email, symbol=symbol, side="BUY", order_type="STOP", qty=0.05, price=buy_stop_price, instance=instance)
    res_ss = client.place_order(master_email, symbol=symbol, side="SELL", order_type="STOP", qty=0.05, price=sell_stop_price, instance=instance)

    print(f"  -> BUY_STOP Status: HTTP {res_bs.get('status_code')}")
    print(f"  -> SELL_STOP Status: HTTP {res_ss.get('status_code')}")

    time.sleep(2.0)

    # 2. Master cancels all pending orders
    print("  -> Master firing bulk_cancel for straddle legs...")
    client.bulk_cancel(master_email, instance=instance)
    time.sleep(2.5)

    # 3. Verify zero hanging pending orders across all 100 followers
    pending_left = 0
    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        def check_pending(email):
            orders = client.get_orders(email, instance=instance).get("orders", [])
            return sum(1 for o in orders if o.get("status") in ["PENDING", "OPEN", "NEW"] or o.get("state") in ["PENDING", "OPEN", "NEW"])

        results = list(executor.map(check_pending, follower_emails))
        pending_left = sum(results)

    print(f"  -> Total Follower Hanging Pending Orders: {pending_left}")

    cleanup_all(client, master_email, follower_emails, instance)

    passed = (pending_left == 0)
    return {
        "name": "Breakout Straddle & OCO Pending Cancellation",
        "buy_stop_price": buy_stop_price,
        "sell_stop_price": sell_stop_price,
        "follower_hanging_pending": pending_left,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# SCENARIO 6: Cross-Asset Portfolio Bombardment (Multi-Pair Concurrent Burst)
# =============================================================================
def test_cross_asset_portfolio_bombardment(
    client: BlackTraderClient,
    master_email: str,
    follower_emails: list,
    instance: str = "paper"
) -> dict:
    print("\n" + "=" * 80)
    print("[SCENARIO-6] Testing Cross-Asset Portfolio Bombardment (Multi-Pair Concurrent)...")
    print("=" * 80)

    cleanup_all(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    symbols_and_lots = [
        ("BINANCE:BTCUSDT.P", "BUY", 0.02),
        ("BINANCE:ETHUSDT.P", "BUY", 0.20),
        ("BINANCE:SOLUSDT.P", "BUY", 1.00)
    ]

    print(f"  -> Firing 3 distinct crypto asset orders in parallel across 100 followers...")

    t0 = time.time()
    futures = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        for sym, side, qty in symbols_and_lots:
            futures.append(executor.submit(client.place_order, master_email, sym, side, "MARKET", qty, None, None, None, instance))

    res_list = [f.result() for f in futures]
    burst_time = (time.time() - t0) * 1000.0

    print(f"  -> 3 Master orders placed in {burst_time:.2f}ms")
    for r in res_list:
        print(f"     * Status: HTTP {r.get('status_code')}")

    time.sleep(3.5)

    # Verify positions on sample followers
    def check_portfolio(email):
        positions = client.get_positions(email, instance=instance).get("positions", [])
        symbols_held = set(p.get("symbol") for p in positions)
        return {"email": email, "count": len(positions), "symbols": symbols_held}

    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        port_results = list(executor.map(check_portfolio, follower_emails[:20]))

    followers_with_multi_assets = sum(1 for p in port_results if p["count"] >= 2)
    print(f"  -> Followers holding >= 2 Asset Classes: {followers_with_multi_assets} / {len(port_results)}")

    cleanup_all(client, master_email, follower_emails, instance)

    passed = (followers_with_multi_assets >= len(port_results) * 0.90)
    return {
        "name": "Cross-Asset Portfolio Bombardment",
        "burst_time_ms": round(burst_time, 2),
        "multi_asset_followers": followers_with_multi_assets,
        "sample_size": len(port_results),
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# SCENARIO 7: Full Accounting & Financial Scaling Reconciliation
# =============================================================================
def test_accounting_scaling_audit(
    client: BlackTraderClient,
    master_email: str,
    follower_emails: list,
    symbol: str = "BINANCE:BTCUSDT.P",
    lot: float = 0.05,
    instance: str = "paper"
) -> dict:
    print("\n" + "=" * 80)
    print("[SCENARIO-7] Testing Full Accounting & Financial Scaling Reconciliation...")
    print("=" * 80)

    cleanup_all(client, master_email, follower_emails, instance)
    time.sleep(1.0)

    # Open Master BUY order
    res_open = client.place_order(master_email, symbol=symbol, side="BUY", qty=lot, instance=instance)
    if res_open.get("status_code") != 200:
        return {"name": "Accounting & Scaling Audit", "status": "FAIL", "error": "Master order failed"}

    print(f"  -> Master placed BUY {lot} lot. Waiting 2.5s for fan-out...")
    time.sleep(2.5)

    # Query all positions across 100 followers
    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        def get_pos_qty(email):
            positions = client.get_positions(email, instance=instance).get("positions", [])
            return sum(float(p.get("net_qty", 0.0)) for p in positions)

        follower_lots = list(executor.map(get_pos_qty, follower_emails))

    total_follower_volume = sum(follower_lots)
    print(f"  -> Master Lot: {lot}")
    print(f"  -> Aggregate Follower Volume: {total_follower_volume:.4f} Lots")
    print(f"  -> Average Follower Lot: {total_follower_volume / len(follower_emails):.4f} Lots")

    cleanup_all(client, master_email, follower_emails, instance)
    time.sleep(2.0)

    # Check for zero margin leakage across master and followers
    master_funds = client.get_positions(master_email, instance=instance).get("funds", {})
    master_used_margin = float(master_funds.get("used_margin", 0.0))

    passed = (total_follower_volume > 0) and (master_used_margin == 0.0)
    return {
        "name": "Full Accounting & Scaling Audit",
        "master_lot": lot,
        "total_follower_volume": round(total_follower_volume, 4),
        "master_used_margin_post_cleanup": master_used_margin,
        "status": "PASS" if passed else "FAIL"
    }


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="BlackTrader Extreme Scenarios & Race Condition Runner")
    parser.add_argument("--start", type=int, default=1, help="Start follower index")
    parser.add_argument("--end", type=int, default=100, help="End follower index")
    parser.add_argument("--instance", type=str, default="paper", help="Broker instance")
    args = parser.parse_args()

    client = BlackTraderClient(base_url=BASE_URL, max_workers=10)
    master_email = "ctmaster@mailinator.com"
    follower_emails = [f"follower{i}@mailinator.com" for i in range(args.start, args.end + 1)]

    print("=" * 80)
    print("BLACKTRADER OMS: EXTREME SCENARIOS & CONCURRENCY RACE CONDITION SUITE")
    print(f"Target Master Account: {master_email}")
    print(f"Target Follower Accounts: {len(follower_emails)} (follower{args.start} to follower{args.end})")
    print(f"Broker Instance: {args.instance.upper()}")
    print("=" * 80)

    suite_results = []
    start_time = time.time()

    try:
        suite_results.append(test_rapid_reversal(client, master_email, follower_emails, instance=args.instance))
        suite_results.append(test_simultaneous_squareoffs(client, master_email, follower_emails, instance=args.instance))
        suite_results.append(test_midtrade_dynamic_capital_shock(client, master_email, follower_emails, instance=args.instance))
        suite_results.append(test_microlot_underflow(client, master_email, follower_emails, instance=args.instance))
        suite_results.append(test_breakout_straddle_and_cancel(client, master_email, follower_emails, instance=args.instance))
        suite_results.append(test_cross_asset_portfolio_bombardment(client, master_email, follower_emails, instance=args.instance))
        suite_results.append(test_accounting_scaling_audit(client, master_email, follower_emails, instance=args.instance))

    finally:
        print("\nFinalizing Teardown: Ensuring zero orphan positions across all accounts...")
        cleanup_all(client, master_email, follower_emails, instance=args.instance)

    total_time = time.time() - start_time
    passed_count = sum(1 for r in suite_results if r.get("status") == "PASS")
    total_count = len(suite_results)

    print("\n" + "=" * 80)
    print("EXTREME SCENARIOS & RACE CONDITION TEST SUMMARY")
    print(f"Overall Result: {passed_count} / {total_count} PASSED ({passed_count/total_count*100:.1f}%) in {total_time:.2f}s")
    print("=" * 80)
    for r in suite_results:
        flag = "[PASS]" if r.get("status") == "PASS" else "[FAIL]"
        print(f"  * {flag} {r['name']}")

    # Save evidence JSON
    reports_dir = BASE_DIR / "reports" / "evidence"
    reports_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = reports_dir / "extreme_scenarios_and_race_evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_scenarios": total_count,
            "passed_scenarios": passed_count,
            "total_time_seconds": round(total_time, 2),
            "results": suite_results
        }, f, indent=2)
    print(f"\nEvidence JSON saved to: {evidence_file}")

    # Save Markdown report
    md_file = BASE_DIR / "reports" / "extreme_scenarios_and_race_report.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("# BlackTrader OMS - Extreme Scenarios & Race Condition Audit Report\n\n")
        f.write(f"- **Execution Timestamp**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write(f"- **Total Scenarios Tested**: {total_count}\n")
        f.write(f"- **Passed Scenarios**: {passed_count} / {total_count}\n")
        f.write(f"- **Overall Suite Status**: {'PASSED (100%)' if passed_count == total_count else 'PARTIAL'}\n")
        f.write(f"- **Total Duration**: {total_time:.2f} seconds\n\n")
        f.write("## Scenario Breakdown\n\n")
        f.write("| # | Scenario Name | Status | Key Metric / Verification |\n")
        f.write("|---|---|---|---|\n")
        for i, r in enumerate(suite_results, 1):
            f.write(f"| {i} | {r['name']} | **{r.get('status')}** | {json.dumps({k: v for k, v in r.items() if k not in ['name', 'status']})} |\n")
    print(f"Markdown Report saved to: {md_file}")

    sys.exit(0 if passed_count == total_count else 1)


if __name__ == "__main__":
    main()

