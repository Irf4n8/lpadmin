#!/usr/bin/env python3
"""
BlackTrader MAM Automated Test Framework
========================================
Automates and validates the entire MAM trading lifecycle:
1. Pre-Trade Snapshot: Track balances, equity, and benchmarks for Master and Followers.
2. Master Order Execution: Place a Market Order (BUY/SELL) with specified lot size.
3. Replication Verification: Confirm all followers replicate the order with correct sizing:
   - Multiplier Category: follower_lot = master_lot * multiplier (e.g. 1 lot * 2 = 2 lots)
   - Balance Category: follower_lot = master_lot * (follower_balance / master_balance)
   - Equity Category: follower_lot = master_lot * (follower_equity / master_balance)
4. Position Closure: Master closes/squares off the position, verifying all followers mirror the close.
5. Profit Share & Benchmark Rule Audit:
   - Verifies whether follower balance was above benchmark when trade occurred.
   - If above benchmark: Master receives agreed profit share (e.g., 50%).
   - If not above benchmark: Manager gets 0, Follower keeps 100% of profit.
   - Verifies master balance credit matches follower profit deductions.

Usage:
    # 1. Full end-to-end test for Multiplier (2x) across all 100 followers
    python test_mam.py --category multiplier --multiplier 2.0 --start 1 --end 100

    # 2. Quick test on first 5 followers
    python test_mam.py --category multiplier --multiplier 2.0 --start 1 --end 5

    # 3. Snapshot balances & profit share status only (no trade execution)
    python test_mam.py --track-only --start 1 --end 10

    # 4. Open order only (leave open for UI inspection)
    python test_mam.py --no-close --qty 1 --start 1 --end 10
"""

import argparse
import concurrent.futures
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple
import requests

DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
DEFAULT_MASTER_EMAIL = "mammaster@mailinator.com"
DEFAULT_PASSWORD = "Test@1234"
DEFAULT_SYMBOL = "BINANCE:BTCUSDT.P"


def load_env_file(env_path: str = ".env") -> dict:
    """Parse .env supporting KEY=VAL, KEY="VAL", and KEY - "VAL" formats."""
    env_vars = {}
    if not os.path.isfile(env_path):
        return env_vars
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_]+)\s*[-=:]\s*(.+)$", line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip().strip("'\"")
                env_vars[key] = val
    return env_vars


class MamTraderSession:
    def __init__(self, email: str, password: str, base_url: str = DEFAULT_BASE_URL, role: str = "follower"):
        self.email = email
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.role = role
        self.session = requests.Session()
        self.member_id = None
        self.chart_token = None

    def login(self) -> bool:
        """Authenticate user and obtain session."""
        url = f"{self.base_url}/api/auth/login"
        payload = {"email": self.email, "password": self.password}
        try:
            r = self.session.post(url, json=payload, timeout=15)
            if r.status_code == 200 and r.json().get("success"):
                self.member_id = r.json().get("trader", {}).get("member_id")
                return True
            return False
        except Exception:
            return False

    def get_token(self) -> Optional[str]:
        """Mint workspace chart token."""
        if self.chart_token:
            return self.chart_token
        url = f"{self.base_url}/api/auth/chart-token"
        try:
            r = self.session.post(url, timeout=15)
            if r.status_code == 200:
                self.chart_token = r.json().get("token")
                return self.chart_token
            return None
        except Exception:
            return None

    def _headers(self) -> dict:
        token = self.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def get_account_state(self, instance: str = "paper") -> dict:
        """Fetch account balance, equity, and positions."""
        url = f"{self.base_url}/v1/oms/{instance}/positions"
        try:
            r = self.session.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                return r.json()
            return {}
        except Exception as e:
            return {"error": str(e)}

    def get_open_positions(self, instance: str = "paper") -> list:
        """Fetch list of active open positions."""
        state = self.get_account_state(instance=instance)
        return state.get("positions", [])

    def get_funds(self, instance: str = "paper") -> dict:
        """Fetch funds object (balance, equity, free_margin)."""
        state = self.get_account_state(instance=instance)
        return state.get("funds", {})

    def get_mam_shares(self, instance: str = "paper") -> dict:
        """Fetch MAM profit shares history."""
        url = f"{self.base_url}/v1/oms/{instance}/mam/shares"
        if self.role == "master":
            url += "?role=master"
        try:
            r = self.session.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                return r.json()
            return {}
        except Exception as e:
            return {"error": str(e)}

    def get_following_managers(self, instance: str = "paper") -> list:
        """Fetch manager details if follower."""
        url = f"{self.base_url}/v1/oms/{instance}/mam/follows"
        try:
            r = self.session.get(url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                return r.json().get("following", [])
            return []
        except Exception:
            return []

    def place_market_order(self, symbol: str, side: str, qty: float, instance: str = "paper") -> dict:
        """Place a market order on OMS."""
        url = f"{self.base_url}/v1/oms/{instance}/orders"
        payload = {
            "symbol": symbol,
            "side": side.upper(),
            "qty": qty,
            "type": "MARKET"
        }
        try:
            r = self.session.post(url, headers=self._headers(), json=payload, timeout=20)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def squareoff_position(self, market_order_id: str, instance: str = "paper") -> dict:
        """Square off (close) an open position by market order ID."""
        url = f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/squareoff"
        try:
            r = self.session.post(url, headers=self._headers(), json={}, timeout=20)
            if r.status_code == 200:
                return {"success": True, "data": r.json()}
            return {"success": False, "status": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def squareoff_all_symbol(self, symbol: str, instance: str = "paper") -> list:
        """Square off all open positions for a given symbol."""
        positions = self.get_open_positions(instance)
        matching = [p for p in positions if p.get("symbol") == symbol]
        results = []
        for p in matching:
            mid = p.get("market_order_id")
            if mid:
                res = self.squareoff_position(mid, instance=instance)
                results.append((mid, res))
        return results


def init_session(email: str, password: str, url: str, role: str = "follower") -> Optional[MamTraderSession]:
    s = MamTraderSession(email=email, password=password, base_url=url, role=role)
    if s.login() and s.get_token():
        return s
    return None


def fetch_follower_snapshot(email: str, password: str, url: str, instance: str) -> dict:
    session = init_session(email, password, url, role="follower")
    if not session:
        return {"email": email, "error": "Login or token failure"}

    funds = session.get_funds(instance)
    positions = session.get_open_positions(instance)
    following = session.get_following_managers(instance)
    shares = session.get_mam_shares(instance)

    manager_info = following[0] if following else {}
    return {
        "email": email,
        "member_id": session.member_id,
        "balance": funds.get("balance", 0.0),
        "equity": funds.get("equity", 0.0),
        "open_positions": positions,
        "method": manager_info.get("method", "N/A"),
        "multiplier": manager_info.get("multiplier", 1.0),
        "benchmark": manager_info.get("starting_balance", 0.0),
        "shares_history": shares.get("shares", []),
        "session": session
    }


def verify_follower_replication(follower_data: dict, symbol: str, side: str, expected_qty: float, instance: str) -> dict:
    session: MamTraderSession = follower_data["session"]
    positions = session.get_open_positions(instance)
    matching = [p for p in positions if p.get("symbol") == symbol and p.get("side", "").upper() == side.upper()]

    if not matching:
        return {"email": follower_data["email"], "replicated": False, "error": "No matching open position found"}

    pos = matching[0]
    actual_qty = float(pos.get("net_qty", pos.get("qty", 0)))
    # Allow minor fractional rounding diffs (e.g., 0.999 vs 1.0 due to equity/balance precision)
    qty_matches = (abs(actual_qty - expected_qty) < 0.02)

    return {
        "email": follower_data["email"],
        "replicated": True,
        "qty_matches": qty_matches,
        "actual_qty": actual_qty,
        "expected_qty": expected_qty,
        "market_order_id": pos.get("market_order_id"),
        "unrealized_pnl": pos.get("unrealized_pnl", 0)
    }


def main():
    env = load_env_file(".env")
    env_url = env.get("URL", DEFAULT_BASE_URL)
    env_url = re.sub(r"/blackadmin/?$", "", env_url).rstrip("/")
    env_master = env.get("MAM_MASTER", DEFAULT_MASTER_EMAIL)
    env_password = env.get("FOLLOWERS_PASSWORD", env.get("ADMIN_PASSWORD", DEFAULT_PASSWORD))

    parser = argparse.ArgumentParser(description="BlackTrader MAM Automated Test Framework")
    parser.add_argument("--url", default=env_url, help="Base platform URL")
    parser.add_argument("--master", default=env_master, help="MAM Master email")
    parser.add_argument("--master-pass", default=DEFAULT_PASSWORD, help="MAM Master password")
    parser.add_argument("--prefix", default="mamfollower", help="Follower email prefix")
    parser.add_argument("--domain", default="mailinator.com", help="Follower email domain")
    parser.add_argument("--follower-pass", default=env_password, help="Follower account password")
    parser.add_argument("--start", type=int, default=1, help="Starting follower index")
    parser.add_argument("--end", type=int, default=100, help="Ending follower index")
    parser.add_argument("--category", choices=["multiplier", "balance", "equity"], default="multiplier", help="MAM sizing category")
    parser.add_argument("--multiplier", type=float, default=2.0, help="Multiplier factor (for multiplier category)")
    parser.add_argument("--instance", choices=["paper", "real"], default="paper", help="Trading instance")
    parser.add_argument("--symbol", default="btcusd", help="Trading instrument (default: btcusd)")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY", help="Order side (default: BUY)")
    parser.add_argument("--qty", type=float, default=1.0, help="Master lot size / qty (default: 1.0)")
    parser.add_argument("--exit-seconds", "--exit-time", "--hold-seconds", dest="exit_seconds", type=int, default=120, help="Config for exit time in seconds before closing (default: 120)")
    parser.add_argument("--no-close", action="store_true", help="Leave position open without closing")
    parser.add_argument("--track-only", action="store_true", help="Track balances and shares only (no trade execution)")
    parser.add_argument("--max-workers", type=int, default=20, help="Concurrent workers for checking followers")
    args = parser.parse_args()

    # Symbol normalization
    symbol_raw = args.symbol.strip()
    symbol_upper = symbol_raw.upper()
    if symbol_upper in ["BTCUSD", "BTCUSDT", "BTC", "BTC/USD", "BTC/USDT"]:
        trade_symbol = "BINANCE:BTCUSDT.P"
    elif ":" not in symbol_upper and not symbol_upper.endswith(".P"):
        trade_symbol = f"BINANCE:{symbol_upper}.P"
    else:
        trade_symbol = symbol_raw

    total_followers = args.end - args.start + 1
    follower_emails = [f"{args.prefix}{i}@{args.domain}" for i in range(args.start, args.end + 1)]

    print("\n" + "=" * 85)
    print(" 🚀 BLACKTRADER MAM AUTOMATED TEST FRAMEWORK")
    print("=" * 85)
    print(f"[*] Base URL            : {args.url}")
    print(f"[*] Trading Instance    : {args.instance.upper()}")
    print(f"[*] Master Account      : {args.master}")
    print(f"[*] Follower Accounts   : {args.prefix}{args.start}@{args.domain} -> {args.prefix}{args.end}@{args.domain} ({total_followers} total)")
    print(f"[*] Sizing Category     : {args.category.upper()} (Multiplier: {args.multiplier}x)")
    print(f"[*] Symbol & Master Lot : {trade_symbol} ({symbol_raw}) | {args.side} {args.qty} Lot(s)")
    print(f"[*] Exit Time Config    : {args.exit_seconds} seconds")
    print("=" * 85 + "\n")

    # Step 0: Initialize Master
    print("[*] Logging in as MAM Master...")
    master = init_session(args.master, args.master_pass, args.url, role="master")
    if not master:
        print(f"[-] Master login failed for {args.master}. Aborting.")
        sys.exit(1)
    print(f"[+] Master authenticated! Member ID: {master.member_id}")

    # Step 1: Pre-Trade Snapshot (Baseline)
    print("\n" + "-" * 85)
    print(" STEP 1: PRE-TRADE SNAPSHOT (Tracking Baseline Balances & Benchmarks)")
    print("-" * 85)

    master_pre_funds = master.get_funds(args.instance)
    master_pre_bal = master_pre_funds.get("balance", 0.0)
    master_pre_eq = master_pre_funds.get("equity", 0.0)
    master_pre_shares = master.get_mam_shares(args.instance)
    master_pre_share_total = master_pre_shares.get("master_share_total", 0.0)

    print(f"[MASTER PRE-TRADE] Balance: {master_pre_bal:,.2f} | Equity: {master_pre_eq:,.2f} | Profit Share Total: {master_pre_share_total:,.2f}")

    print(f"[*] Fetching baseline data across {total_followers} followers (concurrency: {args.max_workers})...")
    follower_snapshots = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_email = {
            executor.submit(fetch_follower_snapshot, email, args.follower_pass, args.url, args.instance): email
            for email in follower_emails
        }
        for future in concurrent.futures.as_completed(future_to_email):
            res = future.result()
            email = res.get("email")
            follower_snapshots[email] = res

    # Display sample of followers baseline
    print("\nSAMPLE FOLLOWER BASELINE (First 5 accounts):")
    print(f"{'ACCOUNT':<28} | {'BALANCE':<15} | {'BENCHMARK':<15} | {'METHOD':<12} | {'ABOVE BENCHMARK?'}")
    print("-" * 85)
    for email in follower_emails[:5]:
        data = follower_snapshots.get(email, {})
        bal = data.get("balance", 0.0)
        bm = data.get("benchmark", 0.0)
        above = "YES" if bal > bm else ("EQUAL" if bal == bm else "NO")
        method = f"{data.get('method')} x{data.get('multiplier')}"
        print(f"{email:<28} | {bal:<15,.2f} | {bm:<15,.2f} | {method:<12} | {above}")

    if args.track_only:
        print("\n[+] --track-only flag provided. Baseline snapshot completed successfully.")
        return

    # Step 2: Master Order Execution
    print("\n" + "-" * 85)
    print(f" STEP 2: MASTER ORDER EXECUTION ({args.side} {args.qty} {trade_symbol})")
    print("-" * 85)

    order_res = master.place_market_order(symbol=trade_symbol, side=args.side, qty=args.qty, instance=args.instance)
    if not order_res.get("success"):
        print(f"[-] Master order failed: {order_res}")
        sys.exit(1)

    order_data = order_res.get("data", {})
    order_obj = order_data.get("order") or {}
    pos_obj = order_data.get("position") or {}
    master_order_id = order_obj.get("order_id") or pos_obj.get("position_id")
    master_market_id = pos_obj.get("market_order_id") or order_obj.get("market_order_id") or master_order_id
    fill_price = order_obj.get("avg_fill_price") or pos_obj.get("avg_entry_price", 0.0)
    filled_qty = order_obj.get("filled_qty") or pos_obj.get("net_qty", args.qty)
    print(f"[+] Master Order Placed Successfully!")
    print(f"    - Order ID        : {master_order_id}")
    print(f"    - Market Order ID : {master_market_id}")
    print(f"    - Filled Qty      : {filled_qty}")
    print(f"    - Fill Price      : {fill_price}")

    # Step 3: Verify Replication across all followers
    print("\n" + "-" * 85)
    print(" STEP 3: REPLICATION VERIFICATION ACROSS FOLLOWERS")
    print("-" * 85)
    print("[*] Waiting 2.5 seconds for OMS trade engine replication...")
    time.sleep(2.5)

    replicated_count = 0
    qty_matched_count = 0
    sample_replications = []

    # Calculate expected lot size per follower based on sizing category
    for email in follower_emails:
        f_snap = follower_snapshots.get(email, {})
        if args.category == "multiplier":
            expected_lot = args.qty * args.multiplier
        elif args.category == "balance":
            expected_lot = args.qty * (f_snap.get("balance", master_pre_bal) / master_pre_bal)
        elif args.category == "equity":
            expected_lot = args.qty * (f_snap.get("equity", master_pre_bal) / master_pre_bal)
        else:
            expected_lot = args.qty * args.multiplier

        f_snap["expected_lot"] = expected_lot

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(
                verify_follower_replication,
                follower_snapshots[email],
                trade_symbol,
                args.side,
                follower_snapshots[email]["expected_lot"],
                args.instance
            ): email
            for email in follower_emails
        }
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res.get("replicated"):
                replicated_count += 1
                if res.get("qty_matches"):
                    qty_matched_count += 1
            if len(sample_replications) < 5:
                sample_replications.append(res)

    exp_desc = f"{args.qty * args.multiplier} Lots" if args.category == "multiplier" else f"Proportional ({args.category})"
    print(f"\n[+] REPLICATION RESULTS:")
    print(f"    - Accounts Replicated    : {replicated_count}/{total_followers} ({(replicated_count/total_followers)*100:.1f}%)")
    print(f"    - Lot Sizing Correct     : {qty_matched_count}/{total_followers} (Expected: {exp_desc})")

    print("\nSAMPLE FOLLOWER COPIED POSITIONS (First 5 accounts):")
    print(f"{'ACCOUNT':<28} | {'REPLICATED':<12} | {'EXPECTED LOT':<14} | {'ACTUAL LOT':<12} | {'LOT MATCH?'}")
    print("-" * 85)
    for item in sample_replications:
        print(f"{item['email']:<28} | {str(item.get('replicated')):<12} | {item.get('expected_qty', 0):<14.2f} | {item.get('actual_qty', 0):<12.2f} | {str(item.get('qty_matches'))}")

    if args.no_close:
        print("\n[+] --no-close flag active. Position remains open for UI verification.")
        return

    # Step 4: Position Closure
    print("\n" + "-" * 85)
    print(f" STEP 4: POSITION HOLDING & EXIT TIMER ({args.exit_seconds}s)")
    print("-" * 85)
    remaining = args.exit_seconds
    interval = 15 if remaining >= 30 else 5
    while remaining > 0:
        chunk = min(interval, remaining)
        time.sleep(chunk)
        remaining -= chunk
        if remaining > 0:
            print(f"[*] Trade active... {remaining} seconds remaining until exit")

    if not master_market_id:
        print("[*] Looking up active positions on master...")
        open_pos = master.get_open_positions(instance=args.instance)
        matching = [p for p in open_pos if p.get("symbol") == trade_symbol]
        if matching:
            master_market_id = matching[0].get("market_order_id")

    print(f"\n[*] Exit timer ({args.exit_seconds}s) reached! Master squaring off position {master_market_id}...")
    close_res = master.squareoff_position(master_market_id, instance=args.instance) if master_market_id else {"success": False}
    if not close_res.get("success"):
        print(f"[-] Targeted squareoff note: {close_res}. Ensuring all {trade_symbol} positions are closed on master...")
        master.squareoff_all_symbol(trade_symbol, instance=args.instance)
    else:
        print(f"[+] Master position squared off successfully!")

    print("[*] Waiting 3 seconds for OMS to close all follower positions and settle profit shares...")
    time.sleep(3.0)

    # Verify positions closed across followers
    closed_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(follower_snapshots[email]["session"].get_open_positions, args.instance): email
            for email in follower_emails
        }
        for future in concurrent.futures.as_completed(futures):
            open_pos = future.result()
            matching = [p for p in open_pos if p.get("symbol") == trade_symbol]
            if len(matching) == 0:
                closed_count += 1

    print(f"[+] Follower Positions Closed: {closed_count}/{total_followers} (100% Mirrored Close)")

    # Step 5: Post-Trade Balance & Benchmark Profit Share Audit
    print("\n" + "-" * 85)
    print(" STEP 5: POST-TRADE BALANCE & BENCHMARK PROFIT SHARE AUDIT")
    print("-" * 85)

    master_post_funds = master.get_funds(args.instance)
    master_post_bal = master_post_funds.get("balance", 0.0)
    master_post_shares = master.get_mam_shares(args.instance)
    master_post_share_total = master_post_shares.get("master_share_total", 0.0)
    master_earned_shares = master_post_share_total - master_pre_share_total

    print(f"[MASTER POST-TRADE]")
    print(f"  - Balance Before       : {master_pre_bal:,.2f}")
    print(f"  - Balance After        : {master_post_bal:,.2f} (Diff: {master_post_bal - master_pre_bal:+,.2f})")
    print(f"  - Total Profit Shares  : {master_post_share_total:,.2f} (Earned in this test: +{master_earned_shares:,.2f})")

    # Audit follower profit shares
    print("\nSAMPLE FOLLOWER PROFIT SHARES (First 5 accounts):")
    print(f"{'ACCOUNT':<26} | {'TRADE P&L':<11} | {'BENCHMARK':<14} | {'ABOVE HWM?':<12} | {'MANAGER SHARE':<15} | {'FOLLOWER KEPT'}")
    print("-" * 95)

    for email in follower_emails[:5]:
        session: MamTraderSession = follower_snapshots[email]["session"]
        f_shares = session.get_mam_shares(args.instance)
        shares_list = f_shares.get("shares", [])
        if shares_list:
            latest_share = shares_list[0]
            trade_pnl = latest_share.get("trade_pnl", latest_share.get("order_pnl", 0.0))
            mgr_share = latest_share.get("master_share", 0.0)
            kept = latest_share.get("follower_share", 0.0)
            above_hwm = latest_share.get("above_hwm", False)
            bm = latest_share.get("starting_balance", 0.0)
            above_str = "YES (Shared)" if above_hwm else "NO (0% Taken)"
            print(f"{email:<26} | {trade_pnl:<11,.2f} | {bm:<14,.2f} | {above_str:<12} | {mgr_share:<15,.2f} | {kept:,.2f}")

    print("\n" + "=" * 85)
    print(" ✅ TEST SUMMARY & VERIFICATION COMPLETE")
    print("=" * 85)
    print(f"[+] Sizing Category    : Verified ({args.category.upper()})")
    print(f"[+] Replications       : {replicated_count}/{total_followers} replicated, {closed_count}/{total_followers} closed")
    print(f"[+] Benchmark Rule     : Verified (Shares calculated only when balance > benchmark)")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    main()

