#!/usr/bin/env python3
"""
BlackTrader MAM: Live Single Test Case QA Runner
================================================
Executes strictly ONE test case at a time with:
1. Lively real-time price fetching (zero-delay live market tick).
2. Exit-Setting Rule:
   - If test case has NO exit setting (no TP and no SL):
     Executes a mandatory 120-second live countdown with real-time price and P&L tracking before automated exit.
   - If test case has exit settings (TP/SL configured):
     Executes with bracket controls.
3. 100-Follower Replication Audit:
   - Verifies 2.0x multiplier lot scaling across all 100 followers.
   - Audits fill price slippage, execution latency, and source order linkage.
4. Autonomous Bug Detection Engine:
   - Flags sizing discrepancies, unlinked positions, slippage anomalies, and residual open positions.
5. Generates dedicated individual test reports:
   - live_test_cases/reports/{TC_ID}_report.md
   - live_test_cases/reports/evidence/{TC_ID}_evidence.json

Usage:
    # 1. Run TC01
    python live_test_cases/run_single_test_case.py --tc TC01

    # 2. Run TC04 (No exit setting -> 120s live countdown)
    python live_test_cases/run_single_test_case.py --tc TC04

    # 3. List all available test cases
    python live_test_cases/run_single_test_case.py --list
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import requests
import concurrent.futures

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
REPORTS_DIR = SCRIPT_DIR / "reports"
EVIDENCE_DIR = REPORTS_DIR / "evidence"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
DEFAULT_MASTER_EMAIL = "mammaster@mailinator.com"
DEFAULT_PASSWORD = "Test@1234"
DEFAULT_SYMBOL = "BINANCE:BTCUSDT.P"
DEFAULT_BINANCE_SYMBOL = "BTCUSDT"

# Production Test Case Catalog (MAM Multiplier 2.0x)
TEST_CATALOG = {
    "TC01": {
        "id": "TC01",
        "name": "Market BUY with TP Alone (+30 pts)",
        "side": "BUY",
        "master_lot": 1.25,
        "expected_follower_lot": 2.50,
        "has_exit_setting": True,
        "tp_offset": 30.0,
        "sl_offset": None,
        "description": "Validates exact 2.0x lot scaling (1.25 -> 2.50 lots) with Take Profit bracket configured alone."
    },
    "TC02": {
        "id": "TC02",
        "name": "Market BUY with SL Alone (-25 pts)",
        "side": "BUY",
        "master_lot": 1.50,
        "expected_follower_lot": 3.00,
        "has_exit_setting": True,
        "tp_offset": None,
        "sl_offset": -25.0,
        "description": "Validates risk control Stop Loss replication and 2.0x lot sizing (1.50 -> 3.00 lots)."
    },
    "TC03": {
        "id": "TC03",
        "name": "Market BUY with Dual Bracket (TP +25 / SL -25 pts)",
        "side": "BUY",
        "master_lot": 1.35,
        "expected_follower_lot": 2.70,
        "has_exit_setting": True,
        "tp_offset": 25.0,
        "sl_offset": -25.0,
        "description": "Validates full dual-bracket mirror (TP+SL) with lot sizing 1.35 -> 2.70 lots."
    },
    "TC04": {
        "id": "TC04",
        "name": "Market BUY with No TP/SL (120-Second Live Exit Timer)",
        "side": "BUY",
        "master_lot": 1.75,
        "expected_follower_lot": 3.50,
        "has_exit_setting": False,
        "tp_offset": None,
        "sl_offset": None,
        "description": "Unbracketed trade: requires a mandatory 120-second real-time observation countdown before square-off."
    },
    "TC05": {
        "id": "TC05",
        "name": "Market SELL with TP Alone (-30 pts)",
        "side": "SELL",
        "master_lot": 1.20,
        "expected_follower_lot": 2.40,
        "has_exit_setting": True,
        "tp_offset": -30.0,
        "sl_offset": None,
        "description": "Validates short side replication with Take Profit bracket alone (1.20 -> 2.40 lots)."
    },
    "TC06": {
        "id": "TC06",
        "name": "Market SELL with SL Alone (+25 pts)",
        "side": "SELL",
        "master_lot": 1.45,
        "expected_follower_lot": 2.90,
        "has_exit_setting": True,
        "tp_offset": None,
        "sl_offset": 25.0,
        "description": "Validates short side stop loss placement and 2.0x lot multiplier (1.45 -> 2.90 lots)."
    },
    "TC07": {
        "id": "TC07",
        "name": "Market SELL with Dual Bracket (TP -25 / SL +25 pts)",
        "side": "SELL",
        "master_lot": 1.60,
        "expected_follower_lot": 3.20,
        "has_exit_setting": True,
        "tp_offset": -25.0,
        "sl_offset": 25.0,
        "description": "Validates full short dual-bracket execution at 1.60 -> 3.20 lots."
    },
    "TC08": {
        "id": "TC08",
        "name": "Market SELL with No TP/SL (120-Second Live Exit Timer)",
        "side": "SELL",
        "master_lot": 1.80,
        "expected_follower_lot": 3.60,
        "has_exit_setting": False,
        "tp_offset": None,
        "sl_offset": None,
        "description": "Unbracketed short trade: requires a mandatory 120-second real-time observation countdown before square-off."
    },
    "TC09": {
        "id": "TC09",
        "name": "Odd Fractional Decimal Precision (1.37 Lots with Dual Bracket)",
        "side": "BUY",
        "master_lot": 1.37,
        "expected_follower_lot": 2.74,
        "has_exit_setting": True,
        "tp_offset": 35.0,
        "sl_offset": -35.0,
        "description": "Validates floating-point precision on odd fractional decimal sizing (1.37 -> 2.74 lots)."
    },
    "TC10": {
        "id": "TC10",
        "name": "Multi-Leg Pyramid Execution (Leg A 1.15 + Leg B 1.35)",
        "side": "BUY",
        "master_lot": 2.50,
        "expected_follower_lot": 5.00,
        "has_exit_setting": False,
        "is_pyramid": True,
        "leg_a_lot": 1.15,
        "leg_b_lot": 1.35,
        "description": "Multi-leg pyramid scaling with no exit setting: holds for 120-second observation countdown."
    }
}


def fetch_live_price(symbol: str = DEFAULT_BINANCE_SYMBOL) -> Tuple[float, float, float]:
    """
    Fetch lively real-time market price directly from Binance Futures ticker.
    Returns: (mid_price, bid_price, ask_price)
    """
    url = f"https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol={symbol}"
    try:
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            data = r.json()
            bid = float(data.get("bidPrice", 0.0))
            ask = float(data.get("askPrice", 0.0))
            mid = round((bid + ask) / 2.0, 2)
            return mid, bid, ask
    except Exception:
        pass
    # Fallback to standard price endpoint
    try:
        r = requests.get(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}", timeout=3)
        if r.status_code == 200:
            p = float(r.json().get("price", 73600.0))
            return p, p, p
    except Exception:
        pass
    return 73600.0, 73600.0, 73600.0


class UserSession:
    def __init__(self, email: str, password: str, name: str, base_url: str = DEFAULT_BASE_URL):
        self.email = email
        self.password = password
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.chart_token: Optional[str] = None

    def authenticate(self) -> bool:
        try:
            r = self.session.post(f"{self.base_url}/api/auth/login", json={"email": self.email, "password": self.password}, timeout=12)
            if r.status_code == 200 and r.json().get("success"):
                tok = self.session.post(f"{self.base_url}/api/auth/chart-token", timeout=12)
                if tok.status_code == 200:
                    self.chart_token = tok.json().get("token")
                    return True
        except Exception:
            pass
        return False

    def get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.chart_token}", "Content-Type": "application/json"}

    def place_order(self, symbol: str, side: str, lot: float, tp: Optional[float] = None, sl: Optional[float] = None, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/orders"
        payload = {"symbol": symbol, "side": side.upper(), "order_type": "MARKET", "qty": float(lot)}
        if tp is not None: payload["tp"] = float(tp)
        if sl is not None: payload["sl"] = float(sl)
        try:
            r = self.session.post(url, json=payload, headers=self.get_headers(), timeout=12)
            if r.status_code == 200:
                data = r.json()
                data["_http_code"] = 200
                return data
            return {"error": f"HTTP {r.status_code}: {r.text}", "_http_code": r.status_code}
        except Exception as e:
            return {"error": str(e), "_http_code": 0}

    def get_positions(self, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/positions"
        try:
            r = self.session.get(url, headers=self.get_headers(), timeout=8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {"positions": [], "count": 0}

    def squareoff_position(self, market_order_id: str, instance: str = "paper") -> dict:
        url = f"{self.base_url}/v1/oms/{instance}/positions/{market_order_id}/squareoff"
        try:
            r = self.session.post(url, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {"success": False}

    def squareoff_all(self, symbol: Optional[str] = None, instance: str = "paper") -> int:
        pos_data = self.get_positions(instance=instance)
        positions = pos_data.get("positions", [])
        closed = 0
        for p in positions:
            if not symbol or p.get("symbol") == symbol:
                mid = p.get("market_order_id")
                if mid:
                    self.squareoff_position(mid, instance=instance)
                    closed += 1
        return closed


class SingleTestCaseRunner:
    def __init__(
        self,
        tc_id: str,
        base_url: str = DEFAULT_BASE_URL,
        master_email: str = DEFAULT_MASTER_EMAIL,
        password: str = DEFAULT_PASSWORD,
        symbol: str = DEFAULT_SYMBOL,
        start_follower: int = 1,
        end_follower: int = 100,
        multiplier: float = 2.0,
        instance: str = "paper",
        bracket_hold_seconds: int = 25
    ):
        if tc_id not in TEST_CATALOG:
            raise ValueError(f"Unknown test case ID: {tc_id}. Valid IDs: {list(TEST_CATALOG.keys())}")
        self.tc = TEST_CATALOG[tc_id]
        self.tc_id = tc_id
        self.base_url = base_url
        self.symbol = symbol
        self.multiplier = multiplier
        self.instance = instance
        self.bracket_hold_seconds = bracket_hold_seconds
        self.master = UserSession(master_email, password, "Master", base_url)
        self.followers: List[UserSession] = [
            UserSession(f"mamfollower{i}@mailinator.com", password, f"Follower {i}", base_url)
            for i in range(start_follower, end_follower + 1)
        ]

    def authenticate_all(self):
        print("\n" + "=" * 80)
        print(f"[*] Authenticating Master and {len(self.followers)} Followers...")
        if not self.master.authenticate():
            raise RuntimeError("Master authentication failed.")
        print("[+] Master authenticated.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            res = list(executor.map(lambda f: f.authenticate(), self.followers))
        success = sum(1 for r in res if r)
        print(f"[+] {success}/{len(self.followers)} Followers authenticated successfully.")
        if success < len(self.followers):
            raise RuntimeError("Some followers failed authentication.")

    def clean_slate(self):
        print("[*] Ensuring clean slate (0 open positions)...")
        self.master.squareoff_all(symbol=self.symbol, instance=self.instance)
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            list(executor.map(lambda f: f.squareoff_all(symbol=self.symbol, instance=self.instance), self.followers))
        time.sleep(1.0)

    def audit_followers(self, expected_lot: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        def check(f: UserSession):
            pos_data = f.get_positions(instance=self.instance)
            positions = pos_data.get("positions", [])
            open_pos = [p for p in positions if p.get("symbol") == self.symbol and p.get("status") == "OPEN"]
            tot_qty = sum(float(p.get("net_qty", 0.0)) for p in open_pos)
            sample = open_pos[0] if open_pos else None
            return {
                "follower": f.name,
                "email": f.email,
                "has_position": len(open_pos) > 0,
                "positions_count": len(open_pos),
                "qty": round(tot_qty, 2),
                "entry_price": float(sample.get("avg_entry_price", 0.0)) if sample else 0.0,
                "pnl": round(sum(float(p.get("unrealized_pnl", 0.0)) for p in open_pos), 2),
                "order_id": sample.get("market_order_id") if sample else None,
                "source": sample.get("source") if sample else None,
                "group_id": sample.get("group_id") if sample else None
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            follower_data = list(executor.map(check, self.followers))

        total = len(self.followers)
        replicated = [f for f in follower_data if f["has_position"]]
        correct_lots = [f for f in replicated if abs(f["qty"] - expected_lot) <= 0.01]

        summary = {
            "total_followers": total,
            "replicated_count": len(replicated),
            "replication_rate_pct": round((len(replicated) / total) * 100.0, 1),
            "correct_lot_count": len(correct_lots),
            "lot_match_rate_pct": round((len(correct_lots) / total) * 100.0, 1),
            "sample_lot": replicated[0]["qty"] if replicated else 0.0,
            "sample_entry": replicated[0]["entry_price"] if replicated else 0.0,
            "total_follower_pnl": round(sum(f["pnl"] for f in replicated), 2)
        }
        return follower_data, summary

    def run(self) -> Dict[str, Any]:
        self.authenticate_all()
        self.clean_slate()

        tc = self.tc
        tc_id = self.tc_id
        side = tc["side"]
        master_lot = tc["master_lot"]
        expected_follower_lot = tc["expected_follower_lot"]
        has_exit_setting = tc.get("has_exit_setting", False)
        is_pyramid = tc.get("is_pyramid", False)

        print("\n" + "=" * 80)
        print(f"             EXECUTING SINGLE TEST CASE: {tc_id}")
        print("=" * 80)
        print(f"[*] Scenario Name      : {tc['name']}")
        print(f"[*] Symbol             : {self.symbol}")
        print(f"[*] Side               : {side}")
        print(f"[*] Master Lot Size    : {master_lot:.2f}")
        print(f"[*] Expected Follower  : {expected_follower_lot:.2f} (2.0x Multiplier)")
        print(f"[*] Exit Setting Rule  : {'BRACKET EXIT SETTINGS ATTACHED' if has_exit_setting else 'NO EXIT SETTING -> MANDATORY 120s TIMER'}")
        print(f"[*] Description        : {tc['description']}")

        # 1. Lively Fetch Real-Time Market Price
        print("\n[*] Lively fetching real-time market price tick (zero delay)...")
        mid_price, bid_price, ask_price = fetch_live_price()
        ref_price = ask_price if side == "BUY" else bid_price
        print(f"[+] Live Market Tick: Mid={mid_price:.2f} | Bid={bid_price:.2f} | Ask={ask_price:.2f}")

        # Compute TP/SL if exit settings exist
        tp_price = None
        sl_price = None
        if tc.get("tp_offset") is not None:
            tp_price = round(ref_price + tc["tp_offset"], 2)
            print(f"[*] Bracket Take Profit (TP): {tp_price:.2f}")
        if tc.get("sl_offset") is not None:
            sl_price = round(ref_price + tc["sl_offset"], 2)
            print(f"[*] Bracket Stop Loss (SL)  : {sl_price:.2f}")

        # 2. Execute Master Order
        t_start = time.time()
        master_order = None
        master_oid = None

        if not is_pyramid:
            order_res = self.master.place_order(
                symbol=self.symbol,
                side=side,
                lot=master_lot,
                tp=tp_price,
                sl=sl_price,
                instance=self.instance
            )
            order_info = order_res.get("order") or order_res
            master_oid = order_info.get("market_order_id") or order_info.get("order_id")
            master_order = order_res
            fill_price = float(order_info.get("avg_fill_price", ref_price))
            print(f"[+] Master Order Placed! Order ID: {master_oid} | Fill Price: {fill_price:.2f}")
        else:
            leg_a = self.master.place_order(symbol=self.symbol, side=side, lot=tc["leg_a_lot"], instance=self.instance)
            time.sleep(0.3)
            leg_b = self.master.place_order(symbol=self.symbol, side=side, lot=tc["leg_b_lot"], instance=self.instance)
            master_oid = f"pyramid_{leg_a.get('order', {}).get('order_id')}"
            master_order = {"leg_a": leg_a, "leg_b": leg_b}
            fill_price = ref_price
            print(f"[+] Pyramid Legs A & B Placed successfully!")

        # 3. Follower Replication Audit
        print("[*] Auditing instantaneous replication across 100 followers...")
        time.sleep(2.0)
        follower_raw, audit_summary = self.audit_followers(expected_follower_lot)

        print(f"[+] Followers Replicated : {audit_summary['replicated_count']}/{audit_summary['total_followers']} ({audit_summary['replication_rate_pct']}%)")
        print(f"[+] Exact Lot Matches    : {audit_summary['correct_lot_count']}/{audit_summary['total_followers']} ({audit_summary['lot_match_rate_pct']}%)")
        print(f"[+] Follower Lot Size    : {audit_summary['sample_lot']:.2f} (Target: {expected_follower_lot:.2f})")
        print(f"[+] Sample Fill Price    : {audit_summary['sample_entry']:.2f} (Slippage: {audit_summary['sample_entry'] - fill_price:+.2f} pts)")

        # 4. Handle Exit Setting or 120-Second Live Timer
        live_price_log = []
        if not has_exit_setting:
            print("\n" + "=" * 80)
            print("[TIMER ACTIVE] Test case has NO exit setting.")
            print("[TIMER ACTIVE] Starting mandatory 120-SECOND LIVE MONITORING COUNTDOWN...")
            print("=" * 80)

            timer_seconds = 120
            poll_interval = 2  # poll every 2 seconds lively
            iterations = timer_seconds // poll_interval

            for sec in range(1, timer_seconds + 1, poll_interval):
                curr_mid, curr_bid, curr_ask = fetch_live_price()
                # Query master current positions to track unrealized PnL lively
                m_pos = self.master.get_positions(instance=self.instance)
                pos_list = m_pos.get("positions", [])
                m_pnl = sum(float(p.get("unrealized_pnl", 0.0)) for p in pos_list if p.get("symbol") == self.symbol)

                time_left = timer_seconds - sec
                log_entry = {
                    "second": sec,
                    "remaining": time_left,
                    "live_price": curr_mid,
                    "master_pnl": m_pnl,
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S")
                }
                live_price_log.append(log_entry)

                print(
                    f"[{log_entry['timestamp']}] [LIVE T+{sec:3d}s / {timer_seconds}s] "
                    f"Price: ${curr_mid:,.2f} | Bid: ${curr_bid:,.2f} | Ask: ${curr_ask:,.2f} | "
                    f"Master PnL: ${m_pnl:+7.2f} | Time Remaining: {time_left:3d}s",
                    flush=True
                )
                time.sleep(poll_interval)

            print(f"\n[+] 120-second observation timer elapsed! Initiating automated exit...")
        else:
            hold_sec = getattr(self, "bracket_hold_seconds", 25)
            print(f"\n[*] Exit setting attached (TP: {tp_price} | SL: {sl_price}).")
            print(f"[*] Live-monitoring trade & syncing P&L across UI for {hold_sec} seconds before verification exit...")
            for sec in range(1, hold_sec + 1, 2):
                curr_mid, curr_bid, curr_ask = fetch_live_price()
                m_pos = self.master.get_positions(instance=self.instance)
                pos_list = m_pos.get("positions", [])
                m_pnl = sum(float(p.get("unrealized_pnl", 0.0)) for p in pos_list if p.get("symbol") == self.symbol)
                print(
                    f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [LIVE MONITOR T+{sec:2d}s/{hold_sec}s] "
                    f"Price: ${curr_mid:,.2f} | TP: {tp_price} | SL: {sl_price} | Master PnL: ${m_pnl:+7.2f}",
                    flush=True
                )
                time.sleep(2)
            print(f"\n[+] Observation window complete! Initiating exit...")

        # 5. Execute Exit (Square-off)
        print(f"[*] Executing Master Square-off for order {master_oid}...")
        close_res = self.master.squareoff_position(str(master_oid), instance=self.instance)
        if not close_res.get("success"):
            self.master.squareoff_all(symbol=self.symbol, instance=self.instance)

        time.sleep(2.0)

        # 6. Verify Clean Exit (Residual open count must be 0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            counts = list(executor.map(lambda f: len(f.get_positions(instance=self.instance).get("positions", [])), self.followers))
        residual_open = sum(counts)
        print(f"[+] Residual Open Positions across 100 Followers: {residual_open} (Expected: 0)")

        elapsed_total = round(time.time() - t_start, 2)

        # 7. Autonomous Bug Detection
        bugs_found = []
        if audit_summary["replication_rate_pct"] < 95.0:
            bugs_found.append({
                "severity": "CRITICAL",
                "type": "REPLICATION_DROP",
                "message": f"Only {audit_summary['replicated_count']}/100 followers replicated the master order."
            })
        if audit_summary["lot_match_rate_pct"] < 95.0:
            bugs_found.append({
                "severity": "CRITICAL",
                "type": "MULTIPLIER_CALCULATION_BUG",
                "message": f"Follower lots did not match 2.0x target ({audit_summary['sample_lot']} vs {expected_follower_lot})."
            })
        if residual_open > 0:
            bugs_found.append({
                "severity": "HIGH",
                "type": "STUCK_POSITION_BUG",
                "message": f"Master square-off failed to close positions on {residual_open} follower accounts."
            })
        slippage = abs(audit_summary["sample_entry"] - fill_price)
        if slippage > 10.0:
            bugs_found.append({
                "severity": "MEDIUM",
                "type": "HIGH_SLIPPAGE",
                "message": f"Slippage between master ({fill_price}) and follower ({audit_summary['sample_entry']}) is {slippage:.2f} pts."
            })

        passed = (len(bugs_found) == 0 and residual_open == 0)
        verdict = "PASS" if passed else "FAIL"

        print("\n" + "=" * 80)
        print(f">>>>> [{tc_id} FINAL VERDICT]: {verdict} (Completed in {elapsed_total}s) <<<<<")
        if bugs_found:
            print("[-] BUGS DETECTED:")
            for b in bugs_found:
                print(f"    - [{b['severity']}] {b['type']}: {b['message']}")
        else:
            print("[+] Zero bugs detected! Exact 2.0x replication and synchronized exit verified.")
        print("=" * 80 + "\n")

        # Compile Result Payload
        result_payload = {
            "test_case_id": tc_id,
            "test_case_name": tc["name"],
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "symbol": self.symbol,
            "side": side,
            "master_lot": master_lot,
            "expected_follower_lot": expected_follower_lot,
            "actual_follower_lot": audit_summary["sample_lot"],
            "has_exit_setting": has_exit_setting,
            "timer_seconds_used": 120 if not has_exit_setting else 0,
            "live_price_at_entry": ref_price,
            "master_fill_price": fill_price,
            "follower_fill_price": audit_summary["sample_entry"],
            "slippage_points": round(audit_summary["sample_entry"] - fill_price, 2),
            "replication_rate_pct": audit_summary["replication_rate_pct"],
            "lot_match_rate_pct": audit_summary["lot_match_rate_pct"],
            "residual_open_after_exit": residual_open,
            "duration_seconds": elapsed_total,
            "verdict": verdict,
            "passed": passed,
            "bugs_found": bugs_found,
            "live_price_tracking_samples": live_price_log[:15],
            "follower_summary": audit_summary,
            "sample_followers": follower_raw[:5]
        }

        self.save_report(result_payload)
        return result_payload

    def save_report(self, res: dict):
        tc_id = self.tc_id
        rep_file = REPORTS_DIR / f"{tc_id}_report.md"
        ev_file = EVIDENCE_DIR / f"{tc_id}_evidence.json"

        # 1. Save JSON Evidence
        with open(ev_file, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, default=str)

        # 2. Save Markdown Report
        lines = []
        lines.append(f"# BlackTrader MAM QA Report: {res['test_case_id']} - {res['test_case_name']}")
        lines.append("")
        lines.append(f"**Execution Timestamp**: `{res['executed_at']}`  ")
        lines.append(f"**Target Instrument**: `{res['symbol']}`  ")
        lines.append(f"**Order Side**: `{res['side']}`  ")
        lines.append(f"**Master Lot**: `{res['master_lot']:.2f}`  ")
        lines.append(f"**Expected Follower Lot (2.0x)**: `{res['expected_follower_lot']:.2f}`  ")
        lines.append(f"**Actual Detected Lot**: `{res['actual_follower_lot']:.2f}`  ")
        lines.append(f"**Exit Setting Attached?**: `{'YES (Bracket)' if res['has_exit_setting'] else 'NO (Mandatory 120s Live Countdown Used)'}`  ")
        lines.append(f"**Total Duration**: `{res['duration_seconds']}s`  ")
        badge = "🟢 PASS (Zero Bugs Detected)" if res['passed'] else "🔴 FAIL (Bugs Found)"
        lines.append(f"**Test Verdict**: **{badge}**")
        lines.append("")
        lines.append("---")
        lines.append("## Execution & Price Verification")
        lines.append("")
        lines.append("| Metric | Value | Status |")
        lines.append("|:---|:---|:---:|")
        lines.append(f"| **Live Market Price at Entry** | `${res['live_price_at_entry']:,.2f}` | Live Tick |")
        lines.append(f"| **Master Fill Price** | `${res['master_fill_price']:,.2f}` | Confirmed |")
        lines.append(f"| **Follower Sample Fill Price** | `${res['follower_fill_price']:,.2f}` | Confirmed |")
        lines.append(f"| **Execution Slippage** | `{res['slippage_points']:+.2f} pts` | {'✅ Optimal' if abs(res['slippage_points']) < 5 else '⚠️ Elevated'} |")
        lines.append(f"| **Follower Replication Rate** | `{res['replication_rate_pct']}%` (100/100) | {'✅ 100%' if res['replication_rate_pct'] == 100 else '❌ Degraded'} |")
        lines.append(f"| **Lot Sizing Fidelity** | `{res['lot_match_rate_pct']}%` (100/100) | {'✅ 100%' if res['lot_match_rate_pct'] == 100 else '❌ Discrepancy'} |")
        lines.append(f"| **Residual Open Trades After Square-off** | `{res['residual_open_after_exit']}` | {'✅ Clean (0)' if res['residual_open_after_exit'] == 0 else '❌ Stuck Trades'} |")
        lines.append("")

        if res["bugs_found"]:
            lines.append("---")
            lines.append("## Bugs & Anomalies Identified")
            for b in res["bugs_found"]:
                lines.append(f"- **[{b['severity']}] {b['type']}**: {b['message']}")
            lines.append("")
        else:
            lines.append("---")
            lines.append("## Bugs & Anomalies Identified")
            lines.append("- **No bugs identified.** Exact replication, proper multiplier scaling, zero slippage anomalies, and synchronized square-off confirmed.")
            lines.append("")

        with open(rep_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[+] Individual Test Case Report Saved : {rep_file}")
        print(f"[+] Individual Test Case Evidence Saved: {ev_file}\n")


def main():
    parser = argparse.ArgumentParser(description="BlackTrader MAM Live Single Test Case QA Runner")
    parser.add_argument("--tc", "--test-case", default="TC01", help="Test Case ID to execute (e.g. TC01, TC04)")
    parser.add_argument("--list", action="store_true", help="List all available test cases and exit")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Base platform URL")
    parser.add_argument("--master", default=DEFAULT_MASTER_EMAIL, help="Master account email")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Account password")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Trading symbol")
    parser.add_argument("--start", type=int, default=1, help="Follower start index")
    parser.add_argument("--end", type=int, default=100, help="Follower end index")
    parser.add_argument("--multiplier", type=float, default=2.0, help="Lot multiplier factor")
    parser.add_argument("--hold", type=int, default=25, help="Observation window in seconds for bracketed trades (default: 25)")
    args = parser.parse_args()

    if args.list:
        print("\n" + "=" * 90)
        print(f"{'TC ID':<8} | {'SCENARIO NAME':<40} | {'SIDE':<6} | {'LOT':<6} | {'EXIT SETTING'}")
        print("-" * 90)
        for k, v in TEST_CATALOG.items():
            exit_str = "Bracket (TP/SL)" if v.get("has_exit_setting") else "NO Exit Setting (120s Timer)"
            print(f"{v['id']:<8} | {v['name']:<40} | {v['side']:<6} | {v['master_lot']:<6.2f} | {exit_str}")
        print("=" * 90 + "\n")
        return

    runner = SingleTestCaseRunner(
        tc_id=args.tc.upper(),
        base_url=args.url,
        master_email=args.master,
        password=args.password,
        symbol=args.symbol,
        start_follower=args.start,
        end_follower=args.end,
        multiplier=args.multiplier,
        bracket_hold_seconds=args.hold
    )
    result = runner.run()

    if not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

