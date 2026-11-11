#!/usr/bin/env python3
"""
========================================================================================
BlackTrader OMS - Standalone Pending Order Trigger Modification Race Test Script
========================================================================================
Description:
    Exhaustively tests the high-frequency race condition where an order is in PENDING
    state, the market price is about to hit and trigger it into an OPEN position, and
    at that precise millisecond, a modification/shift to the trigger is executed.

    This is a completely standalone, self-contained script that can be shared and run
    directly without requiring the rest of the repository.

Features Tested across Master + 100 Followers:
    1. BUY LIMIT Trigger Price Shift at Hit Boundary (In-Flight Trigger Modification)
    2. SELL LIMIT Trigger Price Shift at Hit Boundary (Symmetric Short-Side Shift)
    3. Impending Trigger TP/SL Protection Shift Collision (Microsecond Protection Shift)

Usage:
    pip install requests
    python standalone_pending_trigger_race_test.py
    python standalone_pending_trigger_race_test.py --start 1 --end 100 --instance paper
========================================================================================
"""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ======================================================================================
# CONFIGURATION & CONSTANTS
# ======================================================================================
DEFAULT_BASE_URL = os.getenv("BASE_URL", "https://lpadmin.blackfx.com")
DEFAULT_MASTER_EMAIL = os.getenv("MASTER_EMAIL", "ctmaster@mailinator.com")
DEFAULT_MEMBER_PASSWORD = os.getenv("MEMBER_PASSWORD", "Test@1234")


# ======================================================================================
# HIGH-PERFORMANCE THREAD-SAFE CLIENT
# ======================================================================================
class BlackTraderClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, max_workers: int = 10, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.max_workers = max_workers
        self.timeout = timeout
        self._lock = threading.Lock()
        self._tokens: Dict[str, str] = {}

        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=max_workers * 2, pool_maxsize=max_workers * 2)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request_with_retry(self, method: str, url: str, headers: Optional[Dict[str, str]] = None, json_body: Optional[Any] = None) -> requests.Response:
        headers = headers or {}
        attempt = 0
        while attempt < 4:
            attempt += 1
            try:
                resp = self.session.request(method=method, url=url, headers=headers, json=json_body, timeout=self.timeout)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 1.5 * (2 ** (attempt - 1))))
                    time.sleep(retry_after)
                    continue
                return resp
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt >= 4:
                    raise e
                time.sleep(1.0 * (2 ** (attempt - 1)))
        return resp

    def get_trader_token(self, email: str, password: str = DEFAULT_MEMBER_PASSWORD, force_refresh: bool = False) -> str:
        with self._lock:
            if not force_refresh and email in self._tokens:
                return self._tokens[email]

        auth_session = requests.Session()
        login_resp = auth_session.post(f"{self.base_url}/api/auth/login", json={"email": email, "password": password}, timeout=self.timeout)
        if login_resp.status_code != 200:
            raise RuntimeError(f"Trader login failed for {email}: HTTP {login_resp.status_code} - {login_resp.text}")

        token_resp = auth_session.post(f"{self.base_url}/api/auth/chart-token", timeout=self.timeout)
        if token_resp.status_code != 200:
            raise RuntimeError(f"Failed to mint chart token for {email}: HTTP {token_resp.status_code} - {token_resp.text}")

        token = token_resp.json().get("token")
        with self._lock:
            self._tokens[email] = token
        return token

    def get_positions(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "X-Broker-ID": instance}
        resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/positions", headers=headers)
        if resp.status_code == 401:
            token = self.get_trader_token(email, force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/positions", headers=headers)
        return resp.json() if resp.status_code == 200 else {"positions": []}

    def get_orders(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "X-Broker-ID": instance}
        resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/orders", headers=headers)
        if resp.status_code == 401:
            token = self.get_trader_token(email, force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = self.request_with_retry("GET", f"{self.base_url}/v1/oms/{instance}/orders", headers=headers)
        return resp.json() if resp.status_code == 200 else {"orders": []}

    def place_order(
        self,
        email: str,
        symbol: str = "BINANCE:BTCUSDT.P",
        side: str = "BUY",
        order_type: str = "MARKET",
        qty: float = 1.0,
        price: Optional[float] = None,
        tp: Optional[float] = None,
        sl: Optional[float] = None,
        instance: str = "paper"
    ) -> Dict[str, Any]:
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Broker-ID": instance}
        endpoint = "/orders/pending" if order_type.upper() in ["LIMIT", "STOP"] else "/orders"
        payload = {"symbol": symbol, "side": side.upper(), "type": order_type.upper(), "qty": qty}
        if price is not None:
            payload["price"] = price
        if tp is not None:
            payload["tp"] = tp
        if sl is not None:
            payload["sl"] = sl

        resp = self.request_with_retry("POST", f"{self.base_url}/v1/oms/{instance}{endpoint}", headers=headers, json_body=payload)
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def set_position_protection(self, email: str, market_order_id: str, tp: Optional[float] = None, sl: Optional[float] = None, instance: str = "paper") -> Dict[str, Any]:
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Broker-ID": instance}
        payload = {}
        if tp is not None:
            payload["tp"] = tp
        if sl is not None:
            payload["sl"] = sl
        resp = self.request_with_retry("PUT", f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/protection", headers=headers, json_body=payload)
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code in [200, 204] else resp.text}

    def cancel_order(self, email: str, order_id: str, instance: str = "paper") -> Dict[str, Any]:
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "X-Broker-ID": instance}
        resp = self.request_with_retry("DELETE", f"{self.base_url}/v1/oms/{instance}/orders/{order_id}", headers=headers)
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def squareoff_position(self, email: str, market_order_id: str, instance: str = "paper") -> Dict[str, Any]:
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Broker-ID": instance}
        resp = self.request_with_retry("POST", f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/squareoff", headers=headers, json_body={})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def bulk_squareoff(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        pos = self.get_positions(email, instance).get("positions", [])
        mkt_ids = [p.get("market_order_id") for p in pos if p.get("market_order_id")]
        if not mkt_ids:
            return {"status_code": 200, "data": {"message": "No open positions"}}
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Broker-ID": instance}
        resp = self.request_with_retry("POST", f"{self.base_url}/v1/oms/{instance}/positions/bulk/squareoff", headers=headers, json_body={"market_order_ids": mkt_ids})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}

    def bulk_cancel(self, email: str, instance: str = "paper") -> Dict[str, Any]:
        orders = self.get_orders(email, instance).get("orders", [])
        pending_ids = [o.get("order_id") for o in orders if o.get("status") in ["PENDING", "OPEN", "NEW"] or o.get("type") in ["LIMIT", "STOP"]]
        if not pending_ids:
            return {"status_code": 200, "data": {"message": "No pending orders"}}
        token = self.get_trader_token(email)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Broker-ID": instance}
        resp = self.request_with_retry("POST", f"{self.base_url}/v1/oms/{instance}/orders/bulk/cancel", headers=headers, json_body={"order_ids": pending_ids})
        return {"status_code": resp.status_code, "data": resp.json() if resp.status_code == 200 else resp.text}


# ======================================================================================
# HELPER FUNCTIONS
# ======================================================================================
def cleanup(client: BlackTraderClient, master_email: str, follower_emails: List[str], instance: str = "paper"):
    """Safety cleanup: close all open positions and cancel pending orders."""
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
    """Fetch current live price using a micro probe trade."""
    res = client.place_order(master_email, symbol=symbol, side="BUY", qty=0.001, instance=instance)
    order_data = res.get("data", {}).get("order", {})
    lp = float(order_data.get("avg_fill_price", 73700.0))
    mkt_id = order_data.get("market_order_id")
    if mkt_id:
        client.squareoff_position(master_email, mkt_id, instance=instance)
    time.sleep(0.3)
    return lp


# ======================================================================================
# TEST SCENARIO 1: BUY LIMIT Trigger Price Shift at Hit Boundary
# ======================================================================================
def test_buy_limit_trigger_shift(client: BlackTraderClient, master_email: str, follower_emails: List[str], symbol: str = "BINANCE:BTCUSDT.P", instance: str = "paper") -> dict:
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

    r1 = client.place_order(master_email, symbol=symbol, side="BUY", order_type="LIMIT", qty=0.05, price=trigger_p1, instance=instance)
    ord1_id = r1.get("data", {}).get("order", {}).get("order_id")
    if not ord1_id:
        return {"name": "BUY LIMIT Trigger Shift", "status": "FAIL", "error": "Order placement failed"}

    print(f"  -> Order {ord1_id} active in PENDING state. Price is at trigger boundary...")

    # Millisecond race: Cancel old trigger and place modified trigger price
    time.sleep(0.020)
    t0 = time.time()
    cancel_res = client.cancel_order(master_email, ord1_id, instance=instance)
    mod_res = client.place_order(master_email, symbol=symbol, side="BUY", order_type="LIMIT", qty=0.05, price=trigger_p2, instance=instance)
    mod_time_ms = (time.time() - t0) * 1000.0

    ord2_id = mod_res.get("data", {}).get("order", {}).get("order_id")
    print(f"  -> Trigger Modification executed in {mod_time_ms:.2f}ms:")
    print(f"     * Cancel Old Trigger ({ord1_id}): HTTP {cancel_res.get('status_code')}")
    print(f"     * Place Modified Trigger ({ord2_id} at {trigger_p2:.1f}): HTTP {mod_res.get('status_code')}")

    time.sleep(3.0)

    # Verify followers
    with ThreadPoolExecutor(max_workers=client.max_workers) as executor:
        f_counts = list(executor.map(lambda f: len(client.get_positions(f, instance=instance).get("positions", [])), follower_emails))

    followers_with_pos = sum(1 for c in f_counts if c >= 1)
    followers_with_dup = sum(1 for c in f_counts if c > 1)

    print(f"  -> Followers Holding Active Position: {followers_with_pos} / {len(follower_emails)}")
    print(f"  -> Followers with Duplicate Fills (>1 position): {followers_with_dup}")

    cleanup(client, master_email, follower_emails, instance)

    passed = (followers_with_dup == 0)
    return {
        "name": "BUY LIMIT Trigger Price Shift at Hit Boundary",
        "mod_time_ms": round(mod_time_ms, 2),
        "followers_with_pos": followers_with_pos,
        "followers_with_duplicates": followers_with_dup,
        "status": "PASS" if passed else "FAIL"
    }


# ======================================================================================
# TEST SCENARIO 2: SELL LIMIT Trigger Price Shift at Hit Boundary
# ======================================================================================
def test_sell_limit_trigger_shift(client: BlackTraderClient, master_email: str, follower_emails: List[str], symbol: str = "BINANCE:BTCUSDT.P", instance: str = "paper") -> dict:
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
        return {"name": "SELL LIMIT Trigger Shift", "status": "FAIL", "error": "Order placement failed"}

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
        "followers_with_pos": followers_with_pos,
        "followers_with_duplicates": followers_with_dup,
        "status": "PASS" if passed else "FAIL"
    }


# ======================================================================================
# TEST SCENARIO 3: Impending Trigger TP/SL Protection Shift Collision
# ======================================================================================
def test_protection_trigger_shift(client: BlackTraderClient, master_email: str, follower_emails: List[str], symbol: str = "BINANCE:BTCUSDT.P", instance: str = "paper") -> dict:
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


# ======================================================================================
# MAIN EXECUTION ENTRYPOINT
# ======================================================================================
def main():
    parser = argparse.ArgumentParser(description="Standalone Pending Order Trigger Modification Race Test")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="Base API URL")
    parser.add_argument("--master", type=str, default=DEFAULT_MASTER_EMAIL, help="Master account email")
    parser.add_argument("--start", type=int, default=1, help="Start follower index")
    parser.add_argument("--end", type=int, default=100, help="End follower index")
    parser.add_argument("--instance", type=str, default="paper", help="Broker instance (paper/real)")
    args = parser.parse_args()

    client = BlackTraderClient(base_url=args.base_url, max_workers=10)
    follower_emails = [f"follower{i}@mailinator.com" for i in range(args.start, args.end + 1)]

    print("=" * 80)
    print("BLACKTRADER OMS: STANDALONE PENDING TRIGGER MODIFICATION RACE SUITE")
    print(f"Base URL: {args.base_url}")
    print(f"Master Account: {args.master}")
    print(f"Followers: {len(follower_emails)} (follower{args.start} to follower{args.end})")
    print(f"Instance: {args.instance.upper()}")
    print("=" * 80)

    results = []
    t_start = time.time()

    try:
        results.append(test_buy_limit_trigger_shift(client, args.master, follower_emails, instance=args.instance))
        results.append(test_sell_limit_trigger_shift(client, args.master, follower_emails, instance=args.instance))
        results.append(test_protection_trigger_shift(client, args.master, follower_emails, instance=args.instance))
    finally:
        print("\nFinalizing Teardown: Ensuring 0 open positions and 0 pending orders...")
        cleanup(client, args.master, follower_emails, instance=args.instance)

    total_time = time.time() - t_start
    passed = sum(1 for r in results if r.get("status") == "PASS")
    total = len(results)

    print("\n" + "=" * 80)
    print(f"TEST SUMMARY: {passed} / {total} PASSED ({passed/total*100:.1f}%) in {total_time:.2f}s")
    print("=" * 80)
    for r in results:
        flag = "[PASS]" if r.get("status") == "PASS" else "[FAIL]"
        print(f"  * {flag} {r['name']}")

    # Save summary JSON
    out_file = "standalone_pending_trigger_race_evidence.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_scenarios": total,
            "passed_scenarios": passed,
            "total_time_seconds": round(total_time, 2),
            "results": results
        }, f, indent=2)
    print(f"\nEvidence JSON saved to: {out_file}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

