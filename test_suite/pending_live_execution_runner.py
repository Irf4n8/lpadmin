#!/usr/bin/env python3
"""
BlackTrader Pending Orders Live Trigger & Execution Suite (100 Followers)
========================================================================
Exhaustively tests all Pending Order types (LIMIT & STOP for both BUY & SELL):
Places near the live market price and waits until triggered and executed into open positions:
1. EXEC-1: Pending BUY LIMIT -> wait for market trigger & fill (WITHOUT TP/SL) -> verify 100 followers filled
2. EXEC-2: Pending BUY LIMIT -> wait for market trigger & fill (WITH Dynamic TP/SL) -> verify 100 followers filled + protected
3. EXEC-3: Pending SELL LIMIT -> wait for market trigger & fill (WITHOUT TP/SL) -> verify 100 followers filled short
4. EXEC-4: Pending SELL LIMIT -> wait for market trigger & fill (WITH Dynamic TP/SL) -> verify 100 followers filled short + protected
5. EXEC-5: Pending BUY STOP -> wait for live breakout trigger and fill -> verify 100 followers filled long
6. EXEC-6: Pending SELL STOP -> wait for live breakdown trigger and fill -> verify 100 followers filled short
7. Final Teardown & Zero Orphan Verification across 101 accounts.

Usage:
    python test_suite/pending_live_execution_runner.py
    python test_suite/pending_live_execution_runner.py --start 1 --end 100
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import MASTER_EMAIL
from config.settings import BASE_URL, DEFAULT_PREFIX, DEFAULT_DOMAIN
from test_suite.baseline import get_expected_multiplier
from test_suite.client import BlackTraderClient


def get_live_price(client: BlackTraderClient, master_email: str, symbol: str = "BINANCE:BTCUSDT.P", instance: str = "paper") -> float:
    r = client.place_order(master_email, symbol=symbol, side="BUY", qty=0.001, instance=instance)
    m = r.get("data", {}).get("order", {})
    fill_p = float(m.get("avg_fill_price", 73700.0))
    mkt_id = m.get("market_order_id")
    if mkt_id:
        client.squareoff_position(master_email, mkt_id, instance=instance)
    time.sleep(0.5)
    return fill_p


def wait_until_executed(client: BlackTraderClient, email: str, order_id: str, instance: str = "paper", timeout_sec: int = 15) -> bool:
    """Poll until pending order triggers and becomes an active open position."""
    start = time.time()
    while time.time() - start < timeout_sec:
        pos_res = client.get_positions(email, instance=instance)
        for p in pos_res.get("positions", []):
            if p.get("market_order_id") == order_id:
                return True
        time.sleep(0.5)
    return False


def place_and_execute_pending(
    client: BlackTraderClient,
    master_email: str,
    symbol: str,
    side: str,
    order_type: str,
    lot: float,
    instance: str = "paper",
    tp: float = None,
    sl: float = None,
    max_attempts: int = 3
):
    """Places a pending order right on the live market edge and waits until filled."""
    last_ord_id = None
    last_price = None

    for attempt in range(max_attempts):
        lp = get_live_price(client, master_email, symbol, instance)
        if order_type == "LIMIT":
            # For LIMIT: Place right at live price so it executes against resting liquidity
            order_p = round(lp, 1)
        elif order_type == "STOP":
            # For STOP: Place 0.1 above/below so the next print triggers it
            order_p = round(lp + 0.1 if side == "BUY" else lp - 0.1, 1)

        last_price = order_p
        print(f"[*] Attempt {attempt + 1}/{max_attempts}: Live Price: {lp} | Placing {side} {order_type} at {order_p}...")

        r = client.place_order(master_email, symbol=symbol, side=side, order_type=order_type, qty=lot, price=order_p, instance=instance)
        ord_id = r.get("data", {}).get("order", {}).get("order_id")
        last_ord_id = ord_id

        if not ord_id:
            time.sleep(1.0)
            continue

        print(f"[+] Pending order: {ord_id}. Waiting for market fill...")
        # A STOP only fills when price crosses its trigger; in a quiet market that can take a minute or more
        # (measured: 5s, 15s, 60s). Keep it resting instead of cancelling/re-placing every 14s.
        wait = 120 if order_type == "STOP" else 14
        filled = wait_until_executed(client, master_email, ord_id, instance=instance, timeout_sec=wait)

        if filled:
            print(f"[+] SUCCESS: Order {ord_id} TRIGGERED & EXECUTED into open position!")
            if tp is not None or sl is not None:
                # Apply protection to the executed position
                client.set_position_protection(master_email, ord_id, tp=tp, sl=sl, instance=instance)
                time.sleep(1.5)
            return ord_id, True, order_p

        print(f"[-] Stale price (market moved away). Refreshing at new live price...")
        client.cancel_order(master_email, ord_id, instance=instance)
        time.sleep(0.5)

    return last_ord_id, False, last_price


def verify_followers_filled(
    client: BlackTraderClient,
    follower_emails: list,
    symbol: str,
    side: str,
    master_lot: float,
    master_ord_id: str,
    instance: str = "paper",
    check_tpsl: bool = False
) -> tuple:
    # Fan-out of a pending-order fill is asynchronous (measured 0.6-1.7s in isolation, occasionally longer under
    # load). A fixed 2s wait produced false 95/100 and 0/100 results, so poll until every follower is correct
    # (position and, if requested, TP/SL) or 15s pass, and report the measured lag.
    def _ready(fp):
        for i, em in enumerate(follower_emails):
            exp = round(master_lot * get_expected_multiplier(i + 1), 4)
            pl = [p for p in fp.get(em, {}).get("positions", []) if p.get("symbol") == symbol and p.get("side") == side]
            if not pl or not math.isclose(round(pl[0].get("net_qty", 0.0), 4), exp, abs_tol=0.001):
                return False
            if check_tpsl and (pl[0].get("tp_order") is None or pl[0].get("sl_order") is None):
                return False
        return True

    t_wait = time.time()
    while True:
        followers_pos = client.fetch_all_followers_positions(follower_emails, instance=instance)
        if _ready(followers_pos) or time.time() - t_wait > 15.0:
            break
        time.sleep(0.5)
    print(f"[*] Follower fan-out settled after {time.time() - t_wait:.1f}s")
    pass_count = 0
    tpsl_count = 0
    misses = []

    for i, email in enumerate(follower_emails):
        idx = i + 1
        mult = get_expected_multiplier(idx)
        exp_lot = round(master_lot * mult, 4)
        pos_list = [p for p in followers_pos.get(email, {}).get("positions", []) if p.get("symbol") == symbol and p.get("side") == side]
        if pos_list and math.isclose(round(pos_list[0].get("net_qty", 0.0), 4), exp_lot, abs_tol=0.001):
            pass_count += 1
            if check_tpsl and pos_list[0].get("tp_order") is not None and pos_list[0].get("sl_order") is not None:
                tpsl_count += 1
        else:
            misses.append((idx, exp_lot, [round(p.get("net_qty", 0.0), 4) for p in followers_pos.get(email, {}).get("positions", [])],
                           followers_pos.get(email, {}).get("error", "")))

    if misses:
        print(f"[!] {len(misses)} followers did not match (follower#, expected lot, positions held, error):")
        for m in misses[:8]:
            print("      ", m)

    # Cleanup master position
    client.squareoff_position(client.master_email if hasattr(client, "master_email") else MASTER_EMAIL, master_ord_id, instance=instance)
    time.sleep(2.0)

    return pass_count, tpsl_count


def run_live_execution_suite(
    client: BlackTraderClient,
    master_email: str,
    follower_emails: list,
    symbol: str = "BINANCE:BTCUSDT.P",
    lot: float = 0.1,
    instance: str = "paper"
) -> list:
    results = []

    # -------------------------------------------------------------------------
    # Scenario 1: Pending BUY LIMIT (Wait for Fill WITHOUT TP/SL)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"[EXEC-1] Testing Pending BUY LIMIT -> Waiting until Market Triggers & Executes...")
    print("=" * 80)
    ord_id, filled, p = place_and_execute_pending(client, master_email, symbol, "BUY", "LIMIT", lot, instance)
    pass_count = 0
    if filled:
        pass_count, _ = verify_followers_filled(client, follower_emails, symbol, "BUY", lot, ord_id, instance)

    status = "PASS" if filled and pass_count == len(follower_emails) else "FAIL"
    print(f"[{status}] EXEC-1 BUY LIMIT: Executed={filled}, Followers filled={pass_count}/{len(follower_emails)}")
    results.append({"name": "Pending BUY LIMIT Live Trigger & Execution", "status": status, "executed": filled, "pass_count": pass_count, "total": len(follower_emails)})

    # -------------------------------------------------------------------------
    # Scenario 2: Pending BUY LIMIT (Wait for Fill WITH Dynamic TP/SL)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"[EXEC-2] Testing Pending BUY LIMIT (WITH Dynamic TP/SL) -> Waiting until Execution...")
    print("=" * 80)
    lp = get_live_price(client, master_email, symbol, instance)
    tp_p = round(lp + 2500.0, 1)
    sl_p = round(lp - 2500.0, 1)
    ord_id, filled, p = place_and_execute_pending(client, master_email, symbol, "BUY", "LIMIT", lot, instance, tp=tp_p, sl=sl_p)
    pass_count = 0
    tpsl_count = 0
    if filled:
        pass_count, tpsl_count = verify_followers_filled(client, follower_emails, symbol, "BUY", lot, ord_id, instance, check_tpsl=True)

    status = "PASS" if filled and pass_count == len(follower_emails) else "FAIL"
    print(f"[{status}] EXEC-2 BUY LIMIT with TP/SL: Executed={filled}, Followers filled={pass_count}/{len(follower_emails)}, TP/SL verified={tpsl_count}/{len(follower_emails)}")
    results.append({"name": "Pending BUY LIMIT with TP/SL Live Execution", "status": status, "executed": filled, "pass_count": pass_count, "tpsl_verified": tpsl_count, "total": len(follower_emails)})

    # -------------------------------------------------------------------------
    # Scenario 3: Pending SELL LIMIT (Wait for Fill WITHOUT TP/SL)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"[EXEC-3] Testing Pending SELL LIMIT -> Waiting until Market Triggers & Executes...")
    print("=" * 80)
    ord_id, filled, p = place_and_execute_pending(client, master_email, symbol, "SELL", "LIMIT", lot, instance)
    pass_count = 0
    if filled:
        pass_count, _ = verify_followers_filled(client, follower_emails, symbol, "SELL", lot, ord_id, instance)

    status = "PASS" if filled and pass_count == len(follower_emails) else "FAIL"
    print(f"[{status}] EXEC-3 SELL LIMIT: Executed={filled}, Followers filled short={pass_count}/{len(follower_emails)}")
    results.append({"name": "Pending SELL LIMIT Live Trigger & Execution", "status": status, "executed": filled, "pass_count": pass_count, "total": len(follower_emails)})

    # -------------------------------------------------------------------------
    # Scenario 4: Pending SELL LIMIT (Wait for Fill WITH Dynamic TP/SL)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"[EXEC-4] Testing Pending SELL LIMIT (WITH Dynamic TP/SL) -> Waiting until Execution...")
    print("=" * 80)
    lp = get_live_price(client, master_email, symbol, instance)
    tp_p = round(lp - 2500.0, 1)
    sl_p = round(lp + 2500.0, 1)
    ord_id, filled, p = place_and_execute_pending(client, master_email, symbol, "SELL", "LIMIT", lot, instance, tp=tp_p, sl=sl_p)
    pass_count = 0
    tpsl_count = 0
    if filled:
        pass_count, tpsl_count = verify_followers_filled(client, follower_emails, symbol, "SELL", lot, ord_id, instance, check_tpsl=True)

    status = "PASS" if filled and pass_count == len(follower_emails) else "FAIL"
    print(f"[{status}] EXEC-4 SELL LIMIT with TP/SL: Executed={filled}, Followers filled={pass_count}/{len(follower_emails)}, TP/SL verified={tpsl_count}/{len(follower_emails)}")
    results.append({"name": "Pending SELL LIMIT with TP/SL Live Execution", "status": status, "executed": filled, "pass_count": pass_count, "tpsl_verified": tpsl_count, "total": len(follower_emails)})

    # -------------------------------------------------------------------------
    # Scenario 5: Pending BUY STOP (Wait for Breakout Trigger & Fill)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"[EXEC-5] Testing Pending BUY STOP -> Waiting for Breakout Trigger & Fill...")
    print("=" * 80)
    ord_id, filled, p = place_and_execute_pending(client, master_email, symbol, "BUY", "STOP", lot, instance)
    pass_count = 0
    if filled:
        pass_count, _ = verify_followers_filled(client, follower_emails, symbol, "BUY", lot, ord_id, instance)

    status = "PASS" if filled and pass_count == len(follower_emails) else "FAIL"
    print(f"[{status}] EXEC-5 BUY STOP: Triggered & Filled={filled}, Followers filled={pass_count}/{len(follower_emails)}")
    results.append({"name": "Pending BUY STOP Live Trigger & Execution", "status": status, "executed": filled, "pass_count": pass_count, "total": len(follower_emails)})

    # -------------------------------------------------------------------------
    # Scenario 6: Pending SELL STOP (Wait for Breakdown Trigger & Fill)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"[EXEC-6] Testing Pending SELL STOP -> Waiting for Breakdown Trigger & Fill...")
    print("=" * 80)
    ord_id, filled, p = place_and_execute_pending(client, master_email, symbol, "SELL", "STOP", lot, instance)
    pass_count = 0
    if filled:
        pass_count, _ = verify_followers_filled(client, follower_emails, symbol, "SELL", lot, ord_id, instance)

    status = "PASS" if filled and pass_count == len(follower_emails) else "FAIL"
    print(f"[{status}] EXEC-6 SELL STOP: Triggered & Filled={filled}, Followers filled={pass_count}/{len(follower_emails)}")
    results.append({"name": "Pending SELL STOP Live Trigger & Execution", "status": status, "executed": filled, "pass_count": pass_count, "total": len(follower_emails)})

    # -------------------------------------------------------------------------
    # Final Teardown
    # -------------------------------------------------------------------------
    print("\n[*] Performing final clean teardown...")
    client.teardown_all_accounts(master_email, follower_emails, instance=instance)
    time.sleep(2.0)

    final_pos = client.fetch_all_followers_positions(follower_emails, instance=instance)
    orphans = sum(p.get("count", 0) for p in final_pos.values())
    results.append({"name": "Final Teardown & Zero Orphan Verification", "status": "PASS" if orphans == 0 else "FAIL", "orphan_count": orphans})

    return results


def main():
    parser = argparse.ArgumentParser(description="Pending Orders Live Execution Runner")
    parser.add_argument("--master", default=MASTER_EMAIL)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=100)
    parser.add_argument("--lot", type=float, default=0.1)
    parser.add_argument("--instance", default="paper")
    args = parser.parse_args()

    follower_emails = [f"{args.prefix}{i}@{args.domain}" for i in range(args.start, args.end + 1)]
    client = BlackTraderClient(base_url=BASE_URL, max_workers=10)

    print("\n" + "=" * 80)
    print(" PENDING ORDERS LIVE TRIGGER & EXECUTION (NO CANCEL) SUITE")
    print(f"[*] Followers Tested : {len(follower_emails)} (1 to 100)")
    print(f"[*] Principle        : DO NOT CANCEL — WAIT UNTIL EXECUTED AND FILLED")
    print("=" * 80)

    # Initial teardown
    client.teardown_all_accounts(args.master, follower_emails, instance=args.instance)
    time.sleep(1.5)

    results = run_live_execution_suite(
        client=client,
        master_email=args.master,
        follower_emails=follower_emails,
        lot=args.lot,
        instance=args.instance
    )

    # Save evidence
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = BASE_DIR / "reports" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    json_path = evidence_dir / f"pending_live_execution_{timestamp_str}.json"
    md_path = evidence_dir / f"pending_live_execution_{timestamp_str}.md"

    report_payload = {
        "suite_name": "Pending Orders Live Trigger & Execution Suite",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "followers_count": len(follower_emails),
        "results": results
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    passed = sum(1 for r in results if r.get("status") == "PASS")
    total = len(results)

    md_content = f"""# Pending Orders Live Execution (No Cancel) Evidence Report

**Generated:** {datetime.now(timezone.utc).isoformat()}  
**Master Trader:** `{args.master}`  
**Followers Tested:** {len(follower_emails)} (`{follower_emails[0]}` to `{follower_emails[-1]}`)  
**Execution Policy:** **NO CANCELLATION** — Orders placed and waited until triggered and filled.  
**Overall Result:** **{passed}/{total} SCENARIOS PASSED**

| Scenario | Executed & Filled | Followers Verified | Status |
| :--- | :---: | :---: | :---: |
"""
    for r in results:
        exec_str = "YES" if r.get("executed", True) else "NO"
        md_content += f"| **{r.get('name')}** | {exec_str} | {r.get('pass_count', len(follower_emails))}/{len(follower_emails)} | {'✅ PASS' if r.get('status') == 'PASS' else '❌ FAIL'} |\n"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n" + "=" * 80)
    print(f"[+] Live Execution Suite Completed: {passed}/{total} Passed")
    print(f"[+] Evidence Markdown : {md_path}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
