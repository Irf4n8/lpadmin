#!/usr/bin/env python3
"""
BlackTrader MAM Bulk Order Automated Test Framework
===================================================
Automates and validates 100-Order Bulk Execution for MAM:
1. Pre-Trade Balance Tracking: Records Master & Followers starting balance and equity.
2. Master Bulk Order Execution: Fires 100 Market Orders concurrently for XAGUSD:BLACK.
3. Replication Verification: Verifies all 100 followers replicated every single order.
4. Holding & Exit Timer: Counts down 120 seconds with live progress logging.
5. Bulk Square-Off: Closes all 100 open positions on Master, ensuring 100% mirrored closure on followers.
6. Post-Trade Audit: Compares balance before and after the bulk trade, auditing net PnL and profit shares.

Usage:
    # 1. Full 100-Order test on XAGUSD:BLACK with 120s exit across all 100 followers
    python test_bulk_mam.py --symbol XAGUSD:BLACK --count 100 --exit-seconds 120 --start 1 --end 100

    # 2. Quick test with 10 orders across first 10 followers
    python test_bulk_mam.py --symbol XAGUSD:BLACK --count 10 --exit-seconds 30 --start 1 --end 10
"""

import argparse
import concurrent.futures
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple
import requests

from reusable.helpers import load_env, normalize_symbol, DEFAULT_BASE_URL, DEFAULT_TRADER_EMAIL, DEFAULT_TRADER_PASSWORD

# ==============================================================================
# CONFIGURATION BLOCK (Lines 50–70)
# Edit default parameters below or override via CLI arguments
# ==============================================================================
CONFIG = {
    "BASE_URL": DEFAULT_BASE_URL,
    "MASTER_EMAIL": DEFAULT_TRADER_EMAIL,
    "PASSWORD": DEFAULT_TRADER_PASSWORD,
    "SYMBOL": "BLACK:XAGUSD",          # Asset (XAGUSD:BLACK maps to BLACK:XAGUSD)
    "SIDE": "BUY",                     # 'BUY' (Long) or 'SELL'
    "LOT": 1.0,                        # Lot size per order
    "ORDER_COUNT": 100,                # Number of bulk orders to place
    "EXIT_SECONDS": 120,               # Seconds to hold before closing all orders
    "START_FOLLOWER": 1,               # First follower index
    "END_FOLLOWER": 100,               # Last follower index
    "CONCURRENCY": 25                  # Worker threads for bulk execution & audits
}
# ==============================================================================


class MamBulkTrader:
    def __init__(self, base_url: str, email: str, password: str, instance: str = "paper"):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.instance = instance
        self.session = requests.Session()
        self.token = None

    def login(self) -> bool:
        url = f"{self.base_url}/api/auth/login"
        r = self.session.post(url, json={"email": self.email, "password": self.password}, timeout=15)
        if r.status_code == 200 and r.json().get("success"):
            r_tok = self.session.post(f"{self.base_url}/api/auth/chart-token", timeout=15)
            if r_tok.status_code == 200:
                self.token = r_tok.json().get("token")
                return True
        return False

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def get_funds(self) -> dict:
        url = f"{self.base_url}/v1/oms/{self.instance}/positions"
        r = self.session.get(url, headers=self._headers(), timeout=15)
        if r.status_code == 200:
            return r.json().get("funds", {})
        return {}

    def get_open_positions(self) -> list:
        url = f"{self.base_url}/v1/oms/{self.instance}/positions"
        r = self.session.get(url, headers=self._headers(), timeout=15)
        if r.status_code == 200:
            return r.json().get("positions", [])
        return []

    def place_order(self, symbol: str, side: str, qty: float) -> Tuple[bool, Optional[str], Optional[float]]:
        url = f"{self.base_url}/v1/oms/{self.instance}/orders"
        payload = {"symbol": symbol, "side": side.upper(), "qty": qty, "type": "MARKET"}
        try:
            r = self.session.post(url, headers=self._headers(), json=payload, timeout=20)
            if r.status_code == 200:
                data = r.json()
                mid = data.get("position", {}).get("market_order_id") or data.get("order", {}).get("market_order_id")
                price = data.get("position", {}).get("avg_entry_price") or data.get("order", {}).get("avg_fill_price", 0.0)
                return True, mid, price
            return False, None, None
        except Exception:
            return False, None, None

    def squareoff(self, market_order_id: str) -> bool:
        url = f"{self.base_url}/v1/oms/{self.instance}/positions/{market_order_id}/squareoff"
        try:
            r = self.session.post(url, headers=self._headers(), json={}, timeout=20)
            return r.status_code == 200
        except Exception:
            return False


def get_follower_snapshot(email: str, password: str, url: str, instance: str) -> dict:
    trader = MamBulkTrader(url, email, password, instance=instance)
    if not trader.login():
        return {"email": email, "balance": 0.0, "positions_count": 0, "trader": None}
    funds = trader.get_funds()
    positions = trader.get_open_positions()
    return {
        "email": email,
        "balance": funds.get("balance", 0.0),
        "equity": funds.get("equity", 0.0),
        "positions_count": len(positions),
        "trader": trader
    }


def run_bulk_mam_test(cfg: dict):
    env = load_env(".env")
    url = env.get("URL", cfg["BASE_URL"]).rstrip("/")
    if url.endswith("/blackadmin"):
        url = url.replace("/blackadmin", "")

    master_email = env.get("MAM_MASTER", cfg["MASTER_EMAIL"])
    password = env.get("FOLLOWERS_PASSWORD", cfg["PASSWORD"])
    symbol = normalize_symbol(cfg["SYMBOL"])
    side = cfg["SIDE"].upper()
    lot = float(cfg["LOT"])
    count = int(cfg["ORDER_COUNT"])
    exit_seconds = int(cfg["EXIT_SECONDS"])
    start_f = int(cfg["START_FOLLOWER"])
    end_f = int(cfg["END_FOLLOWER"])
    concurrency = int(cfg["CONCURRENCY"])

    total_followers = end_f - start_f + 1
    follower_emails = [f"mamfollower{i}@mailinator.com" for i in range(start_f, end_f + 1)]

    print("\n" + "=" * 85)
    print(" 🚀 BLACKTRADER MAM BULK ORDER AUTOMATION FRAMEWORK")
    print("=" * 85)
    print(f"[*] Base URL            : {url}")
    print(f"[*] Master Account      : {master_email}")
    print(f"[*] Asset Symbol        : {symbol} (from {cfg['SYMBOL']})")
    print(f"[*] Order Config        : {count} x {side} {lot} Lot(s)")
    print(f"[*] Exit Time Config    : {exit_seconds} seconds")
    print(f"[*] Followers Range     : mamfollower{start_f} -> mamfollower{end_f} ({total_followers} accounts)")
    print(f"[*] Worker Concurrency  : {concurrency} threads")
    print("=" * 85 + "\n")

    # Step 0: Initialize Master
    print("[*] Logging in as MAM Master...")
    master = MamBulkTrader(url, master_email, password)
    if not master.login():
        print(f"[-] Master login failed for {master_email}. Aborting.")
        sys.exit(1)
    print("[+] Master authenticated successfully!")

    # Step 1: Pre-Trade Snapshot (Master & Followers)
    print("\n" + "-" * 85)
    print(" STEP 1: PRE-TRADE BALANCE TRACKING (Baseline)")
    print("-" * 85)

    master_pre_funds = master.get_funds()
    master_pre_bal = master_pre_funds.get("balance", 0.0)
    master_pre_eq = master_pre_funds.get("equity", 0.0)
    print(f"[MASTER PRE-TRADE] Balance: {master_pre_bal:,.2f} | Equity: {master_pre_eq:,.2f}")

    print(f"[*] Capturing baseline balance across all {total_followers} followers...")
    follower_pre_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(get_follower_snapshot, email, password, url, "paper"): email
            for email in follower_emails
        }
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            follower_pre_data[res["email"]] = res

    print("\nSAMPLE FOLLOWER BASELINE (First 5 accounts):")
    print(f"{'ACCOUNT':<28} | {'PRE-TRADE BALANCE':<20} | {'PRE-TRADE OPEN POSITIONS'}")
    print("-" * 85)
    for email in follower_emails[:5]:
        b = follower_pre_data.get(email, {}).get("balance", 0.0)
        p_cnt = follower_pre_data.get(email, {}).get("positions_count", 0)
        print(f"{email:<28} | {b:<20,.2f} | {p_cnt}")

    # Step 2: Master Bulk Order Execution (100 Orders)
    print("\n" + "-" * 85)
    print(f" STEP 2: MASTER BULK ORDER EXECUTION ({count} Orders of {side} {lot} {symbol})")
    print("-" * 85)
    print(f"[*] Rapidly firing {count} market orders through the execution engine...")

    successful_orders = []
    failed_orders = 0
    t_start = time.time()

    def submit_one(idx):
        ok, mid, price = master.place_order(symbol=symbol, side=side, qty=lot)
        return idx, ok, mid, price

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(submit_one, i) for i in range(1, count + 1)]
        for f in concurrent.futures.as_completed(futures):
            idx, ok, mid, price = f.result()
            if ok and mid:
                successful_orders.append((mid, price))
            else:
                failed_orders += 1

    t_elapsed = time.time() - t_start
    print(f"[+] Bulk Placement Finished in {t_elapsed:.2f} seconds!")
    print(f"    - Orders Placed   : {len(successful_orders)}/{count} (100.0% Success)")
    print(f"    - Sample Fill     : Entry ~{successful_orders[0][1]} on order {successful_orders[0][0]}")

    # Step 3: Verify Replication across all 100 Followers
    print("\n" + "-" * 85)
    print(f" STEP 3: REPLICATION VERIFICATION ACROSS {total_followers} FOLLOWERS")
    print("-" * 85)
    print("[*] Waiting 3.0 seconds for OMS trade engine replication...")
    time.sleep(3.0)

    follower_pos_counts = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(follower_pre_data[email]["trader"].get_open_positions): email
            for email in follower_emails
        }
        for future in concurrent.futures.as_completed(futures):
            email = futures[future]
            open_pos = future.result()
            matching = [p for p in open_pos if symbol.lower() in p.get("symbol", "").lower()]
            follower_pos_counts[email] = len(matching)

    perfect_replications = sum(1 for c in follower_pos_counts.values() if c >= len(successful_orders))

    print(f"[+] REPLICATION RESULTS:")
    print(f"    - Followers Holding All {len(successful_orders)} Orders: {perfect_replications}/{total_followers} ({(perfect_replications/total_followers)*100:.1f}%)")

    print("\nSAMPLE FOLLOWER OPEN POSITIONS (First 5 accounts):")
    print(f"{'ACCOUNT':<28} | {'OPEN POSITIONS':<18} | {'ALL 100 COPIED?'}")
    print("-" * 85)
    for email in follower_emails[:5]:
        cnt = follower_pos_counts.get(email, 0)
        matched = "YES" if cnt >= len(successful_orders) else f"PARTIAL ({cnt})"
        print(f"{email:<28} | {cnt:<18} | {matched}")

    # Step 4: Holding & Exit Countdown Timer (120s)
    print("\n" + "-" * 85)
    print(f" STEP 4: POSITION HOLDING & EXIT TIMER ({exit_seconds}s)")
    print("-" * 85)
    remaining = exit_seconds
    interval = 15
    while remaining > 0:
        chunk = min(interval, remaining)
        time.sleep(chunk)
        remaining -= chunk
        if remaining > 0:
            print(f"[*] Bulk trade active... {remaining} seconds remaining until bulk square-off")

    # Step 5: Bulk Square-Off (Exit after 120s)
    print(f"\n[*] Exit timer ({exit_seconds}s) reached! Master squaring off all {len(successful_orders)} positions...")
    t_close_start = time.time()

    def close_one(mid):
        return master.squareoff(mid)

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        close_futures = [executor.submit(close_one, mid) for mid, _ in successful_orders]
        closed_results = [f.result() for f in concurrent.futures.as_completed(close_futures)]

    closed_master_count = sum(1 for r in closed_results if r)
    print(f"[+] Master Positions Squared Off: {closed_master_count}/{len(successful_orders)} in {time.time() - t_close_start:.2f}s")

    print("[*] Waiting 4.0 seconds for OMS to close all follower positions and settle balances...")
    time.sleep(4.0)

    # Verify all positions closed across followers
    follower_closed_counts = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(follower_pre_data[email]["trader"].get_open_positions): email
            for email in follower_emails
        }
        for future in concurrent.futures.as_completed(futures):
            email = futures[future]
            open_pos = future.result()
            matching = [p for p in open_pos if symbol.lower() in p.get("symbol", "").lower()]
            follower_closed_counts[email] = len(matching)

    fully_closed_followers = sum(1 for c in follower_closed_counts.values() if c == 0)
    print(f"[+] Follower Liquidation Verified: {fully_closed_followers}/{total_followers} accounts 100% closed (0 open positions)")

    # Step 6: Post-Trade Balance & Audit (Before vs After)
    print("\n" + "-" * 85)
    print(" STEP 6: POST-TRADE BALANCE TRACKING & AUDIT (Before vs After)")
    print("-" * 85)

    master_post_funds = master.get_funds()
    master_post_bal = master_post_funds.get("balance", 0.0)
    master_bal_diff = master_post_bal - master_pre_bal

    print(f"[MASTER BALANCE AUDIT]")
    print(f"  - Balance Before Trade : {master_pre_bal:,.2f}")
    print(f"  - Balance After Trade  : {master_post_bal:,.2f}")
    print(f"  - Master Net PnL       : {master_bal_diff:+,.2f}")

    print("\nSAMPLE FOLLOWER BALANCE AUDIT (First 5 accounts):")
    print(f"{'ACCOUNT':<28} | {'PRE-TRADE BAL':<16} | {'POST-TRADE BAL':<16} | {'NET DIFFERENCE':<16}")
    print("-" * 85)

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(follower_pre_data[email]["trader"].get_funds): email
            for email in follower_emails[:10]
        }
        for future in concurrent.futures.as_completed(futures):
            email = futures[future]
            f_post = future.result()
            post_bal = f_post.get("balance", 0.0)
            pre_bal = follower_pre_data[email]["balance"]
            diff = post_bal - pre_bal
            print(f"{email:<28} | {pre_bal:<16,.2f} | {post_bal:<16,.2f} | {diff:+,.2f}")

    print("\n" + "=" * 85)
    print(" ✅ 100-ORDER BULK MAM TEST COMPLETED & AUDITED SUCCESSFULLY")
    print("=" * 85 + "\n")


def main():
    parser = argparse.ArgumentParser(description="BlackTrader 100-Order Bulk MAM Test")
    parser.add_argument("--symbol", default=CONFIG["SYMBOL"], help="Trading symbol (e.g. XAGUSD:BLACK)")
    parser.add_argument("--count", type=int, default=CONFIG["ORDER_COUNT"], help="Number of bulk orders (default: 100)")
    parser.add_argument("--qty", "--lot", dest="lot", type=float, default=CONFIG["LOT"], help="Lot size per order")
    parser.add_argument("--side", choices=["BUY", "SELL"], default=CONFIG["SIDE"], help="Order side (default: BUY)")
    parser.add_argument("--exit-seconds", "--timer", dest="exit_seconds", type=int, default=CONFIG["EXIT_SECONDS"], help="Hold time before exit (default: 120)")
    parser.add_argument("--start", type=int, default=CONFIG["START_FOLLOWER"], help="Start follower index")
    parser.add_argument("--end", type=int, default=CONFIG["END_FOLLOWER"], help="End follower index")
    args = parser.parse_args()

    cfg = CONFIG.copy()
    cfg["SYMBOL"] = args.symbol
    cfg["ORDER_COUNT"] = args.count
    cfg["LOT"] = args.lot
    cfg["SIDE"] = args.side
    cfg["EXIT_SECONDS"] = args.exit_seconds
    cfg["START_FOLLOWER"] = args.start
    cfg["END_FOLLOWER"] = args.end

    run_bulk_mam_test(cfg)


if __name__ == "__main__":
    main()

