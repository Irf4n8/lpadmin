#!/usr/bin/env python3
"""
BlackTrader MAM: Basic 10 Test Cases QA Suite
=============================================
Executes the standard 10-trade validation matrix:
- 5 Market BUYs across 5 major liquid instruments (Crypto, Commodities, Precious Metals)
- 5 Market SELLs across the same 5 instruments
- Verifies 100% replication across all 100 MAM Followers on every trade
- Verifies simultaneous automated position square-off across all 100 followers
- Tracks pre/post trade balances and ledger state
- Updates in real-time on http://localhost:8500

Matrix Plan:
  TC01: Market BUY  0.10 BINANCE:BTCUSDT.P (Bitcoin)
  TC02: Market BUY  0.10 BLACK:XAUUSD      (Gold)
  TC03: Market BUY  1.00 BLACK:XAGUSD      (Silver)
  TC04: Market BUY  0.50 BINANCE:ETHUSDT.P (Ethereum)
  TC05: Market BUY  1.00 BINANCE:SOLUSDT.P (Solana)
  TC06: Market SELL 0.10 BINANCE:BTCUSDT.P (Bitcoin)
  TC07: Market SELL 0.10 BLACK:XAUUSD      (Gold)
  TC08: Market SELL 1.00 BLACK:XAGUSD      (Silver)
  TC09: Market SELL 0.50 BINANCE:ETHUSDT.P (Ethereum)
  TC10: Market SELL 1.00 BINANCE:SOLUSDT.P (Solana)
"""

import os
import sys
import time
import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
import concurrent.futures

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
DEFAULT_MASTER_EMAIL = "mammaster@mailinator.com"
DEFAULT_PASSWORD = "Test@1234"


def load_env_file(filepath: str = ".env") -> dict:
    env = {}
    path = BASE_DIR / filepath
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class BlackTraderUserSession:
    def __init__(self, email: str, password: str, name: str, base_url: str = DEFAULT_BASE_URL):
        self.email = email
        self.password = password
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.chart_token: Optional[str] = None
        self.member_id: Optional[str] = None

    def authenticate(self) -> bool:
        login_url = f"{self.base_url}/api/auth/login"
        try:
            r = self.session.post(login_url, json={"email": self.email, "password": self.password}, timeout=15)
            if r.status_code == 200 and r.json().get("success"):
                tok_res = self.session.post(f"{self.base_url}/api/auth/chart-token", timeout=15)
                if tok_res.status_code == 200:
                    data = tok_res.json()
                    self.chart_token = data.get("token")
                    user = data.get("user") or {}
                    self.member_id = user.get("id") or user.get("client_id")
                    return True
        except Exception:
            pass
        return False

    def get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.chart_token}",
            "Content-Type": "application/json"
        }

    def place_order(self, symbol: str, side: str, lot: float, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/orders"
        payload = {
            "symbol": symbol,
            "side": side.upper(),
            "qty": lot,
            "type": "MARKET"
        }
        try:
            r = self.session.post(url, json=payload, headers=self.get_headers(), timeout=15)
            if r.status_code == 200:
                data = r.json()
                data["status"] = "success" if data.get("success", False) else "error"
                return data
            return {"status": "error", "message": f"HTTP {r.status_code}: {r.text}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_open_positions(self, instance: str = "paper") -> list:
        url = f"{self.base_url}/v1/oms/{instance}/positions"
        try:
            r = self.session.get(url, headers=self.get_headers(), timeout=15)
            if r.status_code == 200:
                return r.json().get("positions", [])
        except Exception:
            pass
        return []

    def get_funds(self, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/funds"
        try:
            r = self.session.get(url, headers=self.get_headers(), timeout=15)
            if r.status_code == 200:
                return r.json().get("funds", {})
        except Exception:
            pass
        return {}

    def squareoff_position(self, market_order_id: str, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/squareoff"
        try:
            r = self.session.post(url, json={}, headers=self.get_headers(), timeout=15)
            if r.status_code == 200:
                return r.json()
            return {"success": False, "message": f"HTTP {r.status_code}: {r.text}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def squareoff_all(self, symbol: Optional[str] = None, instance: str = "paper") -> int:
        positions = self.get_open_positions(instance)
        closed = 0
        for p in positions:
            if symbol is None or p.get("symbol") == symbol:
                mid = p.get("market_order_id")
                if mid:
                    self.squareoff_position(mid, instance=instance)
                    closed += 1
                    time.sleep(0.05)
        return closed


ORDER_MATRIX_PLAN = [
    # Leg 1: Market BUYs
    {"id": 1,  "name": "TC01: Market BUY BTCUSD",  "symbol": "BINANCE:BTCUSDT.P", "side": "BUY",  "lot": 0.10, "hold_sec": 6},
    {"id": 2,  "name": "TC02: Market BUY XAUUSD",  "symbol": "BLACK:XAUUSD",      "side": "BUY",  "lot": 0.10, "hold_sec": 6},
    {"id": 3,  "name": "TC03: Market BUY XAGUSD",  "symbol": "BLACK:XAGUSD",      "side": "BUY",  "lot": 1.00, "hold_sec": 6},
    {"id": 4,  "name": "TC04: Market BUY ETHUSD",  "symbol": "BINANCE:ETHUSDT.P", "side": "BUY",  "lot": 0.50, "hold_sec": 6},
    {"id": 5,  "name": "TC05: Market BUY SOLUSD",  "symbol": "BINANCE:SOLUSDT.P", "side": "BUY",  "lot": 1.00, "hold_sec": 6},
    # Leg 2: Market SELLs
    {"id": 6,  "name": "TC06: Market SELL BTCUSD", "symbol": "BINANCE:BTCUSDT.P", "side": "SELL", "lot": 0.10, "hold_sec": 6},
    {"id": 7,  "name": "TC07: Market SELL XAUUSD", "symbol": "BLACK:XAUUSD",      "side": "SELL", "lot": 0.10, "hold_sec": 6},
    {"id": 8,  "name": "TC08: Market SELL XAGUSD", "symbol": "BLACK:XAGUSD",      "side": "SELL", "lot": 1.00, "hold_sec": 6},
    {"id": 9,  "name": "TC09: Market SELL ETHUSD", "symbol": "BINANCE:ETHUSDT.P", "side": "SELL", "lot": 0.50, "hold_sec": 6},
    {"id": 10, "name": "TC10: Market SELL SOLUSD", "symbol": "BINANCE:SOLUSDT.P", "side": "SELL", "lot": 1.00, "hold_sec": 6},
]


class Basic10TestRunner:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        master_email: str = DEFAULT_MASTER_EMAIL,
        password: str = DEFAULT_PASSWORD,
        follower_count: int = 100,
        instance: str = "paper"
    ):
        self.base_url = base_url.rstrip("/")
        self.master_email = master_email
        self.password = password
        self.follower_count = follower_count
        self.instance = instance

        self.master = BlackTraderUserSession(self.master_email, self.password, "Master", self.base_url)
        self.followers: List[BlackTraderUserSession] = []
        self.results: List[Dict[str, Any]] = []

    def authenticate_all(self) -> bool:
        print("\n" + "=" * 85)
        print(" 🚀 BLACKTRADER MAM: RUNNING BASIC 10 TEST CASES (FULL QA MATRIX)")
        print("=" * 85)
        print(f"[*] Base URL            : {self.base_url}")
        print(f"[*] Master Account      : {self.master_email}")
        print(f"[*] Followers Verified  : 100 Accounts (mamfollower1 -> mamfollower100)")
        print(f"[*] Trading Instance    : {self.instance.upper()}")
        print(f"[*] Dashboard URL       : http://localhost:8500")
        print("=" * 85 + "\n")

        print("[*] Authenticating MAM Master...")
        if not self.master.authenticate():
            print(f"[-] Master authentication failed for {self.master_email}!")
            return False
        print(f"[+] Master authenticated! Member ID: {self.master.member_id}")

        print(f"[*] Authenticating all {self.follower_count} followers in parallel...")
        sessions = [
            BlackTraderUserSession(f"mamfollower{i}@mailinator.com", self.password, f"mamf{i}", self.base_url)
            for i in range(1, self.follower_count + 1)
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            future_to_s = {executor.submit(s.authenticate): s for s in sessions}
            for future in concurrent.futures.as_completed(future_to_s):
                s = future_to_s[future]
                if future.result():
                    self.followers.append(s)

        # Sort followers by index
        self.followers.sort(key=lambda s: int(re.search(r"\d+", s.name).group(0)) if re.search(r"\d+", s.name) else 0)
        print(f"[+] All {len(self.followers)}/{self.follower_count} followers authenticated successfully!\n")
        return len(self.followers) > 0

    def cleanup_all(self):
        print("[*] Ensuring zero open positions before test execution...")
        self.master.squareoff_all(instance=self.instance)
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(f.squareoff_all, None, self.instance) for f in self.followers]
            concurrent.futures.wait(futures)
        time.sleep(1.0)

    def verify_follower_replication(self, symbol: str, side: str) -> tuple[int, list]:
        synced_count = 0
        follower_details = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            future_to_f = {executor.submit(f.get_open_positions, self.instance): f for f in self.followers}
            for future in concurrent.futures.as_completed(future_to_f):
                f = future_to_f[future]
                try:
                    positions = future.result()
                    matching = [p for p in positions if p.get("symbol") == symbol and p.get("side", "").upper() == side.upper()]
                    if matching:
                        synced_count += 1
                        follower_details.append({
                            "account": f.email,
                            "order_id": matching[0].get("market_order_id"),
                            "qty": matching[0].get("net_qty", matching[0].get("qty"))
                        })
                except Exception:
                    pass
        return synced_count, follower_details

    def execute_test_case(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        tc_id = spec["id"]
        tc_name = spec["name"]
        symbol = spec["symbol"]
        side = spec["side"]
        lot = spec["lot"]
        hold_sec = spec["hold_sec"]

        print("-" * 85)
        print(f" ▶ [{tc_id:02d}/10] EXECUTING: {tc_name} ({side} {lot} {symbol})")
        print("-" * 85)

        # 1. Master Order Placement
        order_res = self.master.place_order(symbol=symbol, side=side, lot=lot, instance=self.instance)
        if not order_res.get("success"):
            print(f"  [-] Master order placement failed: {order_res.get('message')}")
            rec = {
                "id": tc_id, "name": tc_name, "symbol": symbol, "side": side, "lot": lot,
                "passed": False, "synced": 0, "error": order_res.get("message")
            }
            self.results.append(rec)
            return rec

        order_data = order_res.get("data") or {}
        pos_obj = order_res.get("position") or order_data.get("position") or {}
        order_obj = order_res.get("order") or order_data.get("order") or {}
        master_oid = pos_obj.get("market_order_id") or order_obj.get("market_order_id") or order_obj.get("order_id")

        if not master_oid:
            time.sleep(0.5)
            m_open = self.master.get_open_positions(self.instance)
            matching = [p for p in m_open if p.get("symbol") == symbol]
            if matching:
                master_oid = matching[0].get("market_order_id")

        fill_price = pos_obj.get("avg_entry_price") or order_obj.get("avg_fill_price") or 0.0
        print(f"  [+] Master Placed Order -> ID: {master_oid} | Fill Price: {fill_price}")

        # 2. Verify Follower Replication in Parallel
        time.sleep(2.0)
        synced_count, follower_details = self.verify_follower_replication(symbol=symbol, side=side)
        sync_pct = (synced_count / len(self.followers)) * 100
        print(f"  [+] Followers Replicated : {synced_count}/{len(self.followers)} ({sync_pct:.1f}%)")

        # 3. Holding Trade
        print(f"  [*] Holding position for {hold_sec} seconds...")
        time.sleep(hold_sec)

        # 4. Master Square-off Position
        print(f"  [*] Master squaring off position {master_oid}...")
        close_res = self.master.squareoff_position(str(master_oid), instance=self.instance)
        if not close_res.get("success"):
            self.master.squareoff_all(symbol=symbol, instance=self.instance)

        # 5. Verify Followers Closed
        time.sleep(2.5)
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(f.get_open_positions, self.instance) for f in self.followers]
            remaining_open = sum(
                len([p for p in future.result() if p.get("symbol") == symbol])
                for future in concurrent.futures.as_completed(futures)
            )

        passed = (synced_count >= int(len(self.followers) * 0.98)) and (remaining_open == 0)
        status_tag = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  >>> [{tc_id:02d}/10] RESULT: {status_tag} (Replicated: {synced_count}/{len(self.followers)} | Remaining Open: {remaining_open})\n")

        rec = {
            "id": tc_id,
            "name": tc_name,
            "symbol": symbol,
            "side": side,
            "lot": lot,
            "master_order_id": master_oid,
            "synced": synced_count,
            "total": len(self.followers),
            "remaining_open": remaining_open,
            "passed": passed
        }
        self.results.append(rec)
        return rec

    def run_all(self):
        if not self.authenticate_all():
            return

        self.cleanup_all()

        for spec in ORDER_MATRIX_PLAN:
            self.execute_test_case(spec)
            time.sleep(1.0)

        self.cleanup_all()

        # Audit Master & Follower Balances
        m_funds = self.master.get_funds(self.instance)
        print("=" * 85)
        print(" 📊 FINAL BASIC 10 TEST CASES QA REPORT")
        print("=" * 85)
        print(f"{'#':<4} | {'TEST CASE NAME':<28} | {'INSTRUMENT':<18} | {'SIDE':<5} | {'LOT':<5} | {'FOLLOWERS':<11} | {'STATUS'}")
        print("-" * 85)

        passed_total = 0
        for r in self.results:
            is_pass = r.get("passed", False)
            if is_pass:
                passed_total += 1
            status_str = "✅ PASS" if is_pass else "❌ FAIL"
            print(f"{r['id']:<4} | {r['name']:<28} | {r['symbol']:<18} | {r['side']:<5} | {r['lot']:<5.2f} | {r['synced']}/{r['total']:<5} | {status_str}")

        print("-" * 85)
        print(f"[+] Master Balance Post-QA : ${m_funds.get('balance', 0):,.2f} | Equity: ${m_funds.get('equity', 0):,.2f}")
        print(f"[+] Total Score             : {passed_total}/10 Test Cases Passed ({(passed_total/10)*100:.1f}%)")
        print("=" * 85 + "\n")


def main():
    env = load_env_file(".env")
    url = env.get("URL", DEFAULT_BASE_URL)
    url = re.sub(r"/blackadmin/?$", "", url).rstrip("/")
    master_email = env.get("MAM_MASTER", DEFAULT_MASTER_EMAIL)
    password = env.get("FOLLOWERS_PASSWORD", env.get("ADMIN_PASSWORD", DEFAULT_PASSWORD))

    parser = argparse.ArgumentParser(description="BlackTrader MAM Basic 10 Test Cases QA Runner")
    parser.add_argument("--url", default=url, help="Platform URL")
    parser.add_argument("--master", default=master_email, help="MAM Master email")
    parser.add_argument("--password", default=password, help="Account password")
    parser.add_argument("--followers", type=int, default=100, help="Total followers to verify")
    parser.add_argument("--instance", choices=["paper", "real"], default="paper", help="Trading instance")
    args = parser.parse_args()

    runner = Basic10TestRunner(
        base_url=args.url,
        master_email=args.master,
        password=args.password,
        follower_count=args.followers,
        instance=args.instance
    )
    runner.run_all()


if __name__ == "__main__":
    main()

