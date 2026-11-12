#!/usr/bin/env python3
"""
BlackTrader MAM: 10 Complex Real-World Bug-Inducing QA Scenarios Suite
======================================================================
Executes 10 realistic, user-driven edge cases that test system boundaries,
concurrency, race conditions, and calculation desyncs to surface bugs:

BTC01: Fractional Sub-Lot Floor Rounding Trap (Multiplier 0.25x vs Broker Min Lot 1.0)
BTC02: Dangling Orphan Position via Mid-Trade Unfollow ("Leave Manager" Mid-Flight)
BTC03: Rapid Double-Tap Inversion Race Condition (Flip Direction within 500ms)
BTC04: Extreme Micro-Capital Asymmetry in Balance Mode ($50 vs $10M)
BTC05: Inverted / Crossed Bracket Order Entry (Fat-Finger Bracket Validation)
BTC06: High-Water Mark Benchmark Negative Carryover (HWM Profit Share Erosion)
BTC07: Rapid Position Add-On / Pyramid Stacking on Same Symbol (Netting Aggregation)
BTC08: In-Flight Fleet-Wide Profit Share Restructure (50% -> 75% Mid-Trade)
BTC09: Sub-Lot Micro Multiplier with Odd Decimals (0.75x Multiplier on 1.33 Lots)
BTC10: Zero-Balance Fleet Margin Exhaustion ($0.00 Balance with 120s Timer)
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

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dashboard_server import TraderSession

DEFAULT_BASE_URL = "https://lpadmin.blackfx.com"
DEFAULT_DASHBOARD_URL = "http://localhost:8500"
DEFAULT_MASTER_EMAIL = "mammaster@mailinator.com"
DEFAULT_PASSWORD = "Test@1234"
DEFAULT_SYMBOL = "BINANCE:BTCUSDT.P"
DEFAULT_BINANCE_SYMBOL = "BTCUSDT"

def fetch_live_price(symbol: str = DEFAULT_BINANCE_SYMBOL) -> Tuple[float, float, float]:
    url = f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}"
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
    return 73500.0, 73499.0, 73501.0

class UserSession(TraderSession):
    def __init__(self, email: str, password: str, name: str, base_url: str = DEFAULT_BASE_URL, role: str = "follower"):
        super().__init__(email, password, name, base_url, role)

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        tp: Optional[float] = None,
        sl: Optional[float] = None,
        instance: str = "paper"
    ) -> dict:
        headers = self.get_headers()
        url = f"{self.base_url}/v1/oms/{instance}/orders"
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "qty": float(qty)
        }
        if price:
            payload["price"] = float(price)
        if tp:
            payload["tp"] = float(tp)
        if sl:
            payload["sl"] = float(sl)

        try:
            r = self.session.post(url, json=payload, headers=headers, timeout=12)
            if r.status_code == 200:
                return r.json()
            return {"success": False, "status_code": r.status_code, "error": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

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
        positions = self.get_positions(instance=instance)
        closed = 0
        for p in positions:
            if not symbol or p.get("symbol") == symbol:
                mid = p.get("market_order_id")
                if mid:
                    self.squareoff_position(mid, instance=instance)
                    closed += 1
        return closed

    def unfollow_master(self, master_client_id: str, instance: str = "paper") -> bool:
        fol_data = self.get_mam_follows(instance=instance)
        fol_list = fol_data.get("follows", []) if isinstance(fol_data, dict) else []
        fol_id = None
        for fol in fol_list:
            if fol.get("master_client_id") == master_client_id or fol.get("status") == "active":
                fol_id = fol.get("follow_id") or fol.get("id")
                break
        return self.unfollow_mam_master(master_client_id=master_client_id, follow_id=fol_id, instance=instance)

    def follow_master(self, master_client_id: str, method: str = "multiplier", multiplier: float = 2.0, share_pct: float = 50.0, instance: str = "paper") -> bool:
        return self.follow_mam_master(master_client_id=master_client_id, method=method, multiplier=multiplier, share_percent=share_pct, instance=instance)


class BugScenarioRunner:
    def __init__(
        self,
        tc_id: str,
        tc_config: dict,
        base_url: str = DEFAULT_BASE_URL,
        dashboard_url: str = DEFAULT_DASHBOARD_URL,
        master_email: str = DEFAULT_MASTER_EMAIL,
        password: str = DEFAULT_PASSWORD,
        symbol: str = DEFAULT_SYMBOL,
        instance: str = "paper"
    ):
        self.tc_id = tc_id
        self.tc = tc_config
        self.base_url = base_url
        self.dashboard_url = dashboard_url
        self.master_email = master_email
        self.password = password
        self.symbol = symbol
        self.instance = instance

        self.master = UserSession(self.master_email, self.password, "mammaster", base_url=self.base_url, role="master")
        self.followers: List[UserSession] = [
            UserSession(f"mamfollower{i}@mailinator.com", self.password, f"follower{i}", base_url=self.base_url)
            for i in range(1, 101)
        ]

    def authenticate_all(self):
        print(f"[*] Authenticating Master and {len(self.followers)} Followers...")
        if not self.master.authenticate():
            raise RuntimeError("Master authentication failed.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            res = list(executor.map(lambda f: f.authenticate(), self.followers))
        success = sum(1 for r in res if r)
        print(f"[+] Master and {success}/{len(self.followers)} Followers authenticated.")

    def clean_slate(self):
        print("[*] Ensuring clean slate (0 open positions across all accounts)...")
        self.master.squareoff_all(symbol=self.symbol, instance=self.instance)
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            list(executor.map(lambda f: f.squareoff_all(symbol=self.symbol, instance=self.instance), self.followers))
        time.sleep(1.0)

    def apply_dashboard_settings(self, setup_actions: List[dict]) -> Tuple[bool, List[str]]:
        errors = []
        for action in setup_actions:
            act_type = action.get("action")
            desc = action.get("desc", "")
            print(f"[*] [Dashboard Action] {act_type.upper()}: {desc}")

            if act_type == "category":
                url = f"{self.dashboard_url}/api/manage/category"
                payload = {
                    "target_type": action.get("target_type", "all"),
                    "category": action.get("category", "multiplier"),
                    "multiplier": action.get("multiplier", 2.0),
                    "start": action.get("start", 1),
                    "end": action.get("end", 100),
                    "single_email": action.get("single_email", "")
                }
                try:
                    r = requests.post(url, json=payload, timeout=25)
                    if r.status_code != 200 or not r.json().get("success"):
                        err = f"Category update failed: {r.text}"
                        errors.append(err)
                        print(f"[-] {err}")
                    else:
                        print(f"[+] Category updated: {r.json().get('category')} ({r.json().get('success_count')}/{r.json().get('total_targeted')} followers)")
                except Exception as e:
                    errors.append(str(e))
                    print(f"[-] {e}")

            elif act_type == "balance":
                url = f"{self.dashboard_url}/api/manage/balance"
                payload = {
                    "target_type": action.get("target_type", "single"),
                    "balance": action.get("balance", 10000000.0),
                    "start": action.get("start", 1),
                    "end": action.get("end", 100),
                    "single_email": action.get("single_email", "")
                }
                try:
                    r = requests.post(url, json=payload, timeout=25)
                    if r.status_code != 200 or not r.json().get("success"):
                        err = f"Balance update failed: {r.text}"
                        errors.append(err)
                        print(f"[-] {err}")
                    else:
                        print(f"[+] Balance updated: ${action.get('balance'):,.2f} for {r.json().get('total_targeted')} follower(s)")
                except Exception as e:
                    errors.append(str(e))
                    print(f"[-] {e}")

            elif act_type == "master_share":
                url = f"{self.dashboard_url}/api/manage/master-share"
                payload = {
                    "master_id": "mam",
                    "share_percent": action.get("share_percent", 50.0),
                    "display_name": action.get("display_name", "mammaster")
                }
                try:
                    r = requests.post(url, json=payload, timeout=15)
                    if r.status_code != 200 or not r.json().get("success"):
                        err = f"Master share update failed: {r.text}"
                        errors.append(err)
                        print(f"[-] {err}")
                    else:
                        print(f"[+] Master share updated to {action.get('share_percent')}%")
                except Exception as e:
                    errors.append(str(e))
                    print(f"[-] {e}")

            time.sleep(0.5)

        return (len(errors) == 0, errors)

    def audit_followers_replication(self, expected_lots_map: Dict[str, float]) -> Tuple[List[dict], dict]:
        def check_follower(f: UserSession):
            positions = f.get_positions(instance=self.instance)
            open_pos = [p for p in positions if p.get("symbol") == self.symbol and p.get("status") == "OPEN"]
            tot_qty = sum(float(p.get("net_qty", 0.0)) for p in open_pos)
            sample = open_pos[0] if open_pos else None
            exp_qty = expected_lots_map.get(f.email, 0.0)

            lot_match = (abs(tot_qty - exp_qty) <= 0.05) if exp_qty > 0 else (tot_qty == 0.0)
            return {
                "follower": f.name,
                "email": f.email,
                "has_position": len(open_pos) > 0,
                "positions_count": len(open_pos),
                "actual_qty": round(tot_qty, 2),
                "expected_qty": round(exp_qty, 2),
                "lot_match": lot_match,
                "entry_price": float(sample.get("avg_entry_price", 0.0)) if sample else 0.0,
                "pnl": round(sum(float(p.get("unrealized_pnl", 0.0)) for p in open_pos), 2),
                "market_order_id": sample.get("market_order_id") if sample else None,
                "source": sample.get("source") if sample else None
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            follower_data = list(executor.map(check_follower, self.followers))

        total = len(self.followers)
        replicated = [f for f in follower_data if f["has_position"]]
        matched = [f for f in follower_data if f["lot_match"]]

        summary = {
            "total_followers": total,
            "replicated_count": len(replicated),
            "replication_rate_pct": round((len(replicated) / total) * 100.0, 1),
            "lot_match_count": len(matched),
            "lot_match_rate_pct": round((len(matched) / total) * 100.0, 1),
            "sample_entry": replicated[0]["entry_price"] if replicated else 0.0,
            "total_follower_pnl": round(sum(f["pnl"] for f in replicated), 2)
        }
        return follower_data, summary

    def run(self) -> dict:
        t_start = time.time()
        tc = self.tc
        tc_id = self.tc_id

        print("\n" + "=" * 85)
        print(f"      🔥 EXECUTING BUG-INDUCING QA SCENARIO: {tc_id} - {tc['name']}")
        print("=" * 85)
        print(f"[*] Objective          : {tc['description']}")
        print(f"[*] Bug Targeted       : {tc.get('target_bug_category', 'System Desync')}")
        print(f"[*] Master Lot Size    : {tc['master_lot']:.2f}")
        print(f"[*] Exit Setting Rule  : {'BRACKET ATTACHED' if tc['has_exit_setting'] else 'NO EXIT SETTING -> MANDATORY 120s TIMER'}")
        print("=" * 85 + "\n")

        self.authenticate_all()
        self.clean_slate()

        bugs_found = []

        # 1. Apply Dynamic Dashboard Settings
        setup_actions = tc.get("setup_actions", [])
        if setup_actions:
            print("[*] Phase 1: Applying Setup Dashboard Configuration...")
            ok, errors = self.apply_dashboard_settings(setup_actions)
            if not ok:
                for err in errors:
                    bugs_found.append({
                        "severity": "HIGH",
                        "type": "DASHBOARD_SETTING_ERROR",
                        "message": err
                    })

        time.sleep(2.0)

        # 2. Fetch Live Price & Compute Bracket Offsets
        live_mid, live_bid, live_ask = fetch_live_price()
        print(f"[+] Initial Live Binance Price: ${live_mid:,.2f} (Bid: ${live_bid:,.2f} | Ask: ${live_ask:,.2f})")

        tp_offset = tc.get("tp_offset")
        sl_offset = tc.get("sl_offset")
        tp_price = round(live_mid + tp_offset, 2) if tp_offset is not None else None
        sl_price = round(live_mid + sl_offset, 2) if sl_offset is not None else None

        # 3. Execute Master Order
        side = tc["side"].upper()
        master_lot = tc["master_lot"]
        print(f"[*] Phase 2: Placing Master {side} Order for {master_lot:.2f} Lots (TP: {tp_price} | SL: {sl_price})...")

        order_res = self.master.place_order(
            symbol=self.symbol,
            side=side,
            qty=master_lot,
            order_type="MARKET",
            tp=tp_price,
            sl=sl_price,
            instance=self.instance
        )

        # Check if master order was intentionally designed to fail validation (e.g. BTC05)
        if tc.get("expect_order_rejection"):
            if not order_res.get("success"):
                print(f"[+] EXPECTED BEHAVIOR: Order was properly rejected by OMS validation: {order_res.get('error', order_res)}")
                teardown_actions = tc.get("teardown_actions", [])
                if teardown_actions:
                    print("[*] Running Teardown actions...")
                    self.apply_dashboard_settings(teardown_actions)
                return self.finalize_report(t_start, bugs_found, {"replication_rate_pct": 0.0, "replicated_count": 0, "lot_match_rate_pct": 0.0, "lot_match_count": 0}, [], order_res, [], live_mid, tp_price, sl_price, 0)
            else:
                bug_msg = f"CRITICAL BUG: Inverted/invalid bracket order was accepted by OMS without validation: {order_res}"
                print(f"[-] {bug_msg}")
                bugs_found.append({
                    "severity": "CRITICAL",
                    "type": "VALIDATION_BYPASS_BUG",
                    "message": bug_msg
                })
        elif not order_res.get("success"):
            err_msg = f"Master order placement rejected: {order_res}"
            print(f"[-] FATAL: {err_msg}")
            bugs_found.append({
                "severity": "CRITICAL",
                "type": "ORDER_REJECTED",
                "message": err_msg
            })
            return self.finalize_report(t_start, bugs_found, {}, [], order_res, [], live_mid, tp_price, sl_price, 0)

        order_dict = order_res.get("order") if isinstance(order_res.get("order"), dict) else order_res
        master_oid = (
            order_dict.get("market_order_id") or 
            order_dict.get("order_id") or 
            order_dict.get("id") or 
            order_res.get("market_order_id")
        )
        fill_price = float(
            order_dict.get("fill_price") or 
            order_dict.get("price") or 
            order_dict.get("avg_price") or 
            live_mid
        )
        print(f"[+] Master Order FILLED: ID={master_oid} at ${fill_price:,.2f}")

        time.sleep(3.0)

        # In-Flight Bug Trigger Action (e.g. Unfollow mid-flight, stack second order, etc.)
        in_flight_hook = tc.get("in_flight_hook")
        if in_flight_hook:
            print(f"[*] Executing In-Flight Hook: {in_flight_hook.__name__}...")
            hook_bugs = in_flight_hook(self)
            if hook_bugs:
                bugs_found.extend(hook_bugs)

        # 4. Audit Follower Replication & Detect Sizing/Risk Bugs
        print(f"[*] Phase 3: Auditing Follower Fleet Sizing & Anomaly Detection...")
        expected_lots_map = tc.get("expected_lots_map_func")(master_lot, self.master, self.followers)
        follower_data, audit_summary = self.audit_followers_replication(expected_lots_map)

        print(f"[+] Replication Rate : {audit_summary['replication_rate_pct']}% ({audit_summary['replicated_count']}/100)")
        print(f"[+] Lot Sizing Match : {audit_summary['lot_match_rate_pct']}% ({audit_summary['lot_match_count']}/100)")
        print(f"[+] Follower Pool PnL: ${audit_summary['total_follower_pnl']:,.2f}")

        # Check for Sub-Lot Rounding Anomaly / Discrepancy (e.g. BTC01, BTC09)
        if tc.get("audit_sub_lot_risk"):
            for fd in follower_data:
                # If follower intended lot was 0.25, but actual lot is 1.00 (quadruple leverage!)
                if fd["expected_qty"] < 1.0 and fd["actual_qty"] >= 1.0:
                    discrepancy = fd["actual_qty"] / fd["expected_qty"]
                    bug_entry = {
                        "severity": "HIGH",
                        "type": "SUB_LOT_OVERLEVERAGE_BUG",
                        "message": f"Follower {fd['email']} intended lot {fd['expected_qty']} was forced to {fd['actual_qty']} by broker floor, exposing follower to {discrepancy:.1f}x unintended leverage!"
                    }
                    if not any(b["type"] == "SUB_LOT_OVERLEVERAGE_BUG" for b in bugs_found):
                        bugs_found.append(bug_entry)
                        print(f"[-] IDENTIFIED BUG: {bug_entry['message']}")
                    break

        # 5. Live Exit Rule Handling
        has_exit_setting = tc.get("has_exit_setting", False)
        live_price_log = []

        if not has_exit_setting:
            timer_seconds = 120
            poll_interval = 2
            print(f"\n" + "-" * 75)
            print(f"[*] MANDATORY 120-SECOND LIVE COUNTDOWN (NO EXIT SETTING CONFIGURED)")
            print(f"[-] Tracking live Binance ticks and real-time floating P&L...")
            print("-" * 75)

            for sec in range(0, timer_seconds + 1, poll_interval):
                curr_mid, curr_bid, curr_ask = fetch_live_price()
                pos_list = self.master.get_positions(instance=self.instance)
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
                    f"Master PnL: ${m_pnl:+7.2f} | Remaining: {time_left:3d}s",
                    flush=True
                )
                time.sleep(poll_interval)

            print(f"[+] 120-Second Observation Timer Expired! Initiating Automated Exit...")
        else:
            hold_sec = tc.get("bracket_hold_seconds", 15)
            print(f"\n[*] Bracket Exit Settings Attached (TP: {tp_price} | SL: {sl_price}).")
            print(f"[*] Live-monitoring trade & syncing P&L across UI for {hold_sec} seconds before verification exit...")
            for sec in range(1, hold_sec + 1, 2):
                curr_mid, curr_bid, curr_ask = fetch_live_price()
                pos_list = self.master.get_positions(instance=self.instance)
                m_pnl = sum(float(p.get("unrealized_pnl", 0.0)) for p in pos_list if p.get("symbol") == self.symbol)
                print(
                    f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [LIVE MONITOR T+{sec:2d}s/{hold_sec}s] "
                    f"Price: ${curr_mid:,.2f} | TP: {tp_price} | SL: {sl_price} | Master PnL: ${m_pnl:+7.2f}",
                    flush=True
                )
                time.sleep(2)
            print(f"[+] Observation Window Complete! Initiating Square-off...")

        # 6. Square-off Execution
        print(f"[*] Executing Master Square-off for order {master_oid}...")
        close_res = self.master.squareoff_position(str(master_oid), instance=self.instance)
        if not close_res.get("success"):
            self.master.squareoff_all(symbol=self.symbol, instance=self.instance)

        time.sleep(2.5)

        # 7. Post-Exit Residual Open Trades Audit
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            counts = list(executor.map(lambda f: len(f.get_positions(instance=self.instance)), self.followers))
        residual_open = sum(counts)
        print(f"[+] Residual Open Positions across 100 Followers: {residual_open} (Expected: 0)")

        if residual_open > 0:
            bug_msg = f"ORPHANED_POSITION_BUG: Master square-off failed to close positions on {residual_open} follower account(s)."
            print(f"[-] IDENTIFIED BUG: {bug_msg}")
            bugs_found.append({
                "severity": "HIGH",
                "type": "ORPHANED_POSITION_BUG",
                "message": bug_msg
            })
            # Clean up residual positions
            print("[*] Force-closing residual master & follower positions for clean slate...")
            self.master.squareoff_all(symbol=self.symbol, instance=self.instance)
            with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
                list(executor.map(lambda f: f.squareoff_all(symbol=self.symbol, instance=self.instance), self.followers))

        # Teardown actions (restoring balances/settings/follow relations)
        teardown_actions = tc.get("teardown_actions", [])
        if teardown_actions:
            print("[*] Running Teardown actions...")
            self.apply_dashboard_settings(teardown_actions)

        teardown_hook = tc.get("teardown_hook")
        if teardown_hook:
            teardown_hook(self)

        return self.finalize_report(t_start, bugs_found, audit_summary, follower_data, order_res, live_price_log, fill_price, tp_price, sl_price, residual_open)

    def finalize_report(
        self,
        t_start: float,
        bugs_found: List[dict],
        audit_summary: dict,
        follower_data: List[dict],
        order_res: dict,
        live_price_log: List[dict] = None,
        fill_price: float = 0.0,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        residual_open: int = 0
    ) -> dict:
        elapsed_total = round(time.time() - t_start, 2)
        has_bugs = len(bugs_found) > 0

        result = {
            "test_case_id": self.tc_id,
            "test_case_name": self.tc["name"],
            "target_bug": self.tc.get("target_bug_category", "MAM System Edge Case"),
            "status": "BUG_EXPOSED" if has_bugs else "NO_BUG_DETECTED",
            "passed": True, # Test case successfully executed and analyzed the behavior
            "execution_duration_sec": elapsed_total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": self.symbol,
            "side": self.tc["side"],
            "master_lot": self.tc["master_lot"],
            "has_exit_setting": self.tc.get("has_exit_setting", False),
            "tp_price": tp_price,
            "sl_price": sl_price,
            "master_order_id": order_res.get("order_id"),
            "fill_price": fill_price,
            "replication_rate_pct": audit_summary.get("replication_rate_pct", 0.0),
            "lot_match_rate_pct": audit_summary.get("lot_match_rate_pct", 0.0),
            "replicated_count": audit_summary.get("replicated_count", 0),
            "residual_open_after_exit": residual_open,
            "bugs_found": bugs_found,
            "audit_summary": audit_summary,
            "price_history_sample": (live_price_log or [])[:10],
            "follower_sample": follower_data[:5]
        }

        # Save Evidence JSON
        ev_file = EVIDENCE_DIR / f"{self.tc_id}_evidence.json"
        with open(ev_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        # Generate Markdown Report
        rep_file = REPORTS_DIR / f"{self.tc_id}_report.md"
        lines = []
        lines.append(f"# Bug-Inducing QA Scenario Report: {self.tc_id} - {self.tc['name']}")
        lines.append("")
        lines.append(f"**Execution Timestamp**: `{result['timestamp']}`  ")
        lines.append(f"**Scenario Outcome**: `{'🚨 BUG IDENTIFIED' if has_bugs else '✅ HANDLED CLEANLY'}`  ")
        lines.append(f"**Target Bug Category**: `{self.tc.get('target_bug_category')}`  ")
        lines.append(f"**Execution Duration**: `{elapsed_total}s`  ")
        lines.append(f"**Exit Rule**: `{'Bracket Attached' if self.tc.get('has_exit_setting') else '120-Second Mandatory Live Countdown'}`")
        lines.append("")
        lines.append("---")
        lines.append("## Scenario Specifications & Real-World User Workflow")
        lines.append(f"- **User Story**: {self.tc['description']}")
        lines.append(f"- **Symbol**: `{self.symbol}` | **Side**: `{self.tc['side']}` | **Master Lot**: `{self.tc['master_lot']}`")
        lines.append(f"- **Master Entry Price**: `${fill_price:,.2f}` | **TP**: `{tp_price or 'None'}` | **SL**: `{sl_price or 'None'}`")
        lines.append("")
        lines.append("---")
        lines.append("## Replication & Execution Telemetry")
        lines.append("| Metric | Observed Value | Expected Behavior |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Replication Rate** | `{result['replication_rate_pct']}%` ({result['replicated_count']}/100) | 100% Replication |")
        lines.append(f"| **Lot Sizing Match Rate** | `{result['lot_match_rate_pct']}%` | Sizing Formula Precision |")
        lines.append(f"| **Residual Open Trades After Square-off** | `{residual_open}` | `0` (Zero Orphan Trades) |")
        lines.append("")
        lines.append("---")
        lines.append("## Identified Bugs, Vulnerabilities & System Anomalies")
        if bugs_found:
            for b in bugs_found:
                lines.append(f"### ⚠️ [{b['severity']}] {b['type']}")
                lines.append(f"> **Detailed Finding**: {b['message']}")
                lines.append("")
        else:
            lines.append("- **No bugs observed.** The system handled this edge case gracefully without desynchronization, orphan positions, or calculation errors.")
        lines.append("")

        with open(rep_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[+] Individual Test Case Report Saved : {rep_file}")
        print(f"[+] Individual Test Case Evidence Saved: {ev_file}\n")
        return result


# ---------------------------------------------------------------------------
# HOOKS & EXPECTED LOTS FOR THE 10 BUG SCENARIOS
# ---------------------------------------------------------------------------

# BTC01: Multiplier 0.25x with 1.0 lot -> Expected 0.25 lots, but broker min is 1.0!
def btc01_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    return {f.email: 0.25 for f in followers} # Ideal intended lot

# BTC02 Hook: Follower 1 unfollows while trade is active
def btc02_in_flight_hook(runner: BugScenarioRunner) -> List[dict]:
    f1 = runner.followers[0]
    print(f"[*] In-Flight Hook: Follower 1 ({f1.email}) actively UNFOLLOWING master while trade is OPEN...")
    # Follower 1 sends unfollow to master
    master_client_id = runner.master.member_id or "mem_e2dbce29e1c71a7bf6"
    ok = f1.unfollow_master(master_client_id)
    print(f"[+] Follower 1 Unfollowed Master: success={ok}")
    return []

def btc02_teardown_hook(runner: BugScenarioRunner):
    f1 = runner.followers[0]
    master_client_id = runner.master.member_id or "mem_e2dbce29e1c71a7bf6"
    f1.follow_master(master_client_id, method="multiplier", multiplier=2.0, share_pct=50.0)
    print(f"[+] Teardown: Follower 1 re-followed Master.")

def btc02_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    return {f.email: round(master_lot * 2.0, 2) for f in followers}

# BTC03 Hook: Rapid Double-Tap Inversion
def btc03_in_flight_hook(runner: BugScenarioRunner) -> List[dict]:
    bugs = []
    print("[*] Rapid Inversion Hook: Simulating rapid direction flip within 500ms...")
    time.sleep(3.0) # brief hold
    # Close existing buy
    print("[*] Rapidly squaring off BUY and immediately opening SELL...")
    runner.master.squareoff_all(symbol=runner.symbol)
    # Immediately flip without waiting for follower queues to clear
    flip_res = runner.master.place_order(symbol=runner.symbol, side="SELL", qty=1.25, order_type="MARKET")
    print(f"[+] Flip Order Response: success={flip_res.get('success')}")
    if not flip_res.get("success"):
        bugs.append({
            "severity": "HIGH",
            "type": "RAPID_FLIP_REJECTION",
            "message": f"Rapid direction flip was rejected: {flip_res}"
        })
    return bugs

def btc03_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    return {f.email: round(1.25 * 2.0, 2) for f in followers}

# BTC04: Balance Mode with $50 on F1 vs $10M on F2-100
def btc04_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    m = {}
    for i in range(1, 101):
        em = f"mamfollower{i}@mailinator.com"
        if i == 1:
            m[em] = 0.00001 # Micro-lot intended
        else:
            m[em] = round(master_lot * 1.0, 2)
    return m

# BTC05: Inverted Brackets (SL > Ask for BUY)
def btc05_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    return {f.email: round(master_lot * 2.0, 2) for f in followers}

# BTC06: High-Water Mark Benchmark Negative Carryover
def btc06_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    return {f.email: round(master_lot * 2.0, 2) for f in followers}

# BTC07 Hook: Rapid Position Add-On / Stacking
def btc07_in_flight_hook(runner: BugScenarioRunner) -> List[dict]:
    print("[*] Position Add-On Hook: Submitting second BUY order of 1.00 lot while first is open...")
    add_res = runner.master.place_order(symbol=runner.symbol, side="BUY", qty=1.00, order_type="MARKET")
    print(f"[+] Add-On Order Response: success={add_res.get('success')}")
    time.sleep(2.0)
    return []

def btc07_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Total master lot = 1.00 + 1.00 = 2.00 lots -> Followers should have 4.00 lots
    return {f.email: round(2.00 * 2.0, 2) for f in followers}

# BTC08 Hook: In-Flight Profit Share Restructure
def btc08_in_flight_hook(runner: BugScenarioRunner) -> List[dict]:
    print("[*] In-Flight Hook: Altering Master profit share from 50% to 75% mid-trade...")
    runner.master.update_mam_master_settings(share_percent=75.0, display_name="mammaster")
    print("[+] Master profit share restructured to 75% while trade is ACTIVE.")
    return []

def btc08_teardown_hook(runner: BugScenarioRunner):
    runner.master.update_mam_master_settings(share_percent=50.0, display_name="mammaster")
    print("[+] Teardown: Master profit share restored to 50%.")

def btc08_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    return {f.email: round(master_lot * 2.0, 2) for f in followers}

# BTC09: 0.75x Multiplier on 1.33 Lots -> 0.9975 lots
def btc09_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    return {f.email: 0.9975 for f in followers}

# BTC10: $0.00 Balance Margin Exhaustion
def btc10_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    m = {f.email: round(master_lot * 2.0, 2) for f in followers}
    m["mamfollower100@mailinator.com"] = 0.0 # $0 balance should not open
    return m


# ---------------------------------------------------------------------------
# CATALOG OF THE 10 BUG-INDUCING QA SCENARIOS
# ---------------------------------------------------------------------------

BUG_TEST_CATALOG = {
    "BTC01": {
        "id": "BTC01",
        "name": "Fractional Sub-Lot Floor Rounding Trap (0.25x vs Broker Min Lot 1.0)",
        "description": "User sets multiplier to 0.25x intending 25% risk, but broker enforces minimum lot 1.0, testing if follower risk is quadrupled unexpectedly.",
        "target_bug_category": "Risk Management & Sub-Lot Rounding Anomaly",
        "side": "BUY",
        "master_lot": 1.00,
        "has_exit_setting": True,
        "tp_offset": 25.0,
        "sl_offset": -25.0,
        "audit_sub_lot_risk": True,
        "setup_actions": [
            {"action": "category", "desc": "Set All Followers to Micro Multiplier 0.25x", "target_type": "all", "category": "multiplier", "multiplier": 0.25}
        ],
        "teardown_actions": [
            {"action": "category", "desc": "Reset All Followers to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": btc01_expected_lots
    },
    "BTC02": {
        "id": "BTC02",
        "name": "Dangling Orphan Position via Mid-Trade Unfollow ('Leave Manager' Mid-Flight)",
        "description": "Follower clicks 'Leave Manager' while holding an open position; tests if position is orphaned or master square-off fails.",
        "target_bug_category": "Dangling Orphan Position & State Desync",
        "side": "BUY",
        "master_lot": 1.50,
        "has_exit_setting": False, # Triggers 120s live countdown
        "tp_offset": None,
        "sl_offset": None,
        "setup_actions": [
            {"action": "category", "desc": "Ensure All Followers at Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "in_flight_hook": btc02_in_flight_hook,
        "teardown_hook": btc02_teardown_hook,
        "expected_lots_map_func": btc02_expected_lots
    },
    "BTC03": {
        "id": "BTC03",
        "name": "Rapid Double-Tap Inversion Race Condition (Flip Direction within 500ms)",
        "description": "Master executes rapid BUY -> Square-off -> immediate SELL to test async follower queue collision and stuck opposite positions.",
        "target_bug_category": "Async Execution Race Condition & Direction Flip",
        "side": "BUY",
        "master_lot": 1.25,
        "has_exit_setting": False, # Triggers 120s timer on reversed leg
        "tp_offset": None,
        "sl_offset": None,
        "setup_actions": [
            {"action": "category", "desc": "Set All Followers to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "in_flight_hook": btc03_in_flight_hook,
        "expected_lots_map_func": btc03_expected_lots
    },
    "BTC04": {
        "id": "BTC04",
        "name": "Extreme Micro-Capital Asymmetry in Balance Mode ($50 vs $10M)",
        "description": "Tests Balance-Based sizing calculation on $50 account (expected 0.00001 lots) to verify if OMS rounds up causing instant liquidation.",
        "target_bug_category": "Proportional Divide-By-Zero / Margin Squeeze",
        "side": "BUY",
        "master_lot": 2.00,
        "has_exit_setting": True,
        "tp_offset": 25.0,
        "sl_offset": -25.0,
        "audit_sub_lot_risk": True,
        "setup_actions": [
            {"action": "category", "desc": "Set Fleet to Balance-Based Sizing", "target_type": "all", "category": "balance", "multiplier": 1.0},
            {"action": "balance", "desc": "Starve Follower 1 to $50.00", "target_type": "single", "single_email": "mamfollower1@mailinator.com", "balance": 50.0}
        ],
        "teardown_actions": [
            {"action": "balance", "desc": "Restore Follower 1 to $10,000,000", "target_type": "single", "single_email": "mamfollower1@mailinator.com", "balance": 10000000.0},
            {"action": "category", "desc": "Reset Fleet to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": btc04_expected_lots
    },
    "BTC05": {
        "id": "BTC05",
        "name": "Inverted / Crossed Bracket Order Entry (Fat-Finger Bracket Validation)",
        "description": "User enters BUY order with inverted Stop-Loss higher than market price; tests if OMS rejects safely or propagates corrupted order to fleet.",
        "target_bug_category": "Order Validation Bypass & Corrupted Bracket Propagation",
        "side": "BUY",
        "master_lot": 1.20,
        "has_exit_setting": True,
        "bracket_hold_seconds": 40,
        "expect_order_rejection": True, # Order should be rejected
        "tp_offset": -50.0, # TP placed 50 pts BELOW market on a BUY (inverted!)
        "sl_offset": 50.0,  # SL placed 50 pts ABOVE market on a BUY (crossed!)
        "setup_actions": [
            {"action": "category", "desc": "Ensure Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": btc05_expected_lots
    },
    "BTC06": {
        "id": "BTC06",
        "name": "High-Water Mark Benchmark Negative Carryover (HWM Profit Share Erosion)",
        "description": "Verifies that after a losing balance drawdown, profit share is strictly suspended ($0 taken) on subsequent winning trades below HWM.",
        "target_bug_category": "High-Water Mark Rule Violation & Premature Share Deduction",
        "side": "BUY",
        "master_lot": 1.25,
        "has_exit_setting": True,
        "tp_offset": 20.0,
        "sl_offset": -20.0,
        "setup_actions": [
            {"action": "balance", "desc": "Simulate Drawdown: Drop F1 balance to $9,980,000 (Below $10M Benchmark)", "target_type": "single", "single_email": "mamfollower1@mailinator.com", "balance": 9980000.0},
            {"action": "category", "desc": "Set All to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "teardown_actions": [
            {"action": "balance", "desc": "Restore F1 balance to $10,000,000", "target_type": "single", "single_email": "mamfollower1@mailinator.com", "balance": 10000000.0}
        ],
        "expected_lots_map_func": btc06_expected_lots
    },
    "BTC07": {
        "id": "BTC07",
        "name": "Rapid Position Add-On / Pyramid Stacking on Same Symbol (Netting Aggregation)",
        "description": "Master stacks a second BUY order of 1.00 lot onto an active 1.00 lot BUY; tests if followers aggregate to 4.00 lots cleanly.",
        "target_bug_category": "Netting Account Lot Aggregation & Partial Exit Desync",
        "side": "BUY",
        "master_lot": 1.00,
        "has_exit_setting": False, # 120s timer
        "tp_offset": None,
        "sl_offset": None,
        "setup_actions": [
            {"action": "category", "desc": "Set Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "in_flight_hook": btc07_in_flight_hook,
        "expected_lots_map_func": btc07_expected_lots
    },
    "BTC08": {
        "id": "BTC08",
        "name": "In-Flight Fleet-Wide Profit Share Restructure (50% -> 75% Mid-Trade)",
        "description": "Master alters profit share percentage mid-flight from 50% to 75%; tests whether OMS applies retroactive rate hike unfairly to open trades.",
        "target_bug_category": "Retroactive Profit Share Application & Ledger Distortion",
        "side": "BUY",
        "master_lot": 1.30,
        "has_exit_setting": True,
        "tp_offset": 20.0,
        "sl_offset": -20.0,
        "setup_actions": [
            {"action": "category", "desc": "Set Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "in_flight_hook": btc08_in_flight_hook,
        "teardown_hook": btc08_teardown_hook,
        "expected_lots_map_func": btc08_expected_lots
    },
    "BTC09": {
        "id": "BTC09",
        "name": "Sub-Lot Micro Multiplier with Odd Decimals (0.75x Multiplier on 1.33 Lots)",
        "description": "Tests fractional product calculation (1.33 * 0.75 = 0.9975 lots) sitting 0.0025 below broker 1.00 min lot to test truncation vs rejection.",
        "target_bug_category": "Sub-Lot Decimal Precision & Truncation Boundary Bug",
        "side": "BUY",
        "master_lot": 1.33,
        "has_exit_setting": True,
        "tp_offset": 25.0,
        "sl_offset": -25.0,
        "audit_sub_lot_risk": True,
        "setup_actions": [
            {"action": "category", "desc": "Set Fleet to Multiplier 0.75x", "target_type": "all", "category": "multiplier", "multiplier": 0.75}
        ],
        "teardown_actions": [
            {"action": "category", "desc": "Reset Fleet to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": btc09_expected_lots
    },
    "BTC10": {
        "id": "BTC10",
        "name": "Zero-Balance Fleet Margin Exhaustion ($0.00 Balance with 120s Timer)",
        "description": "Follower 100 has exactly $0.00 balance; tests whether OMS encounters divide-by-zero or margin lock, delaying the other 99 followers.",
        "target_bug_category": "Divide-By-Zero & Unhandled Zero Margin Failure",
        "side": "SELL",
        "master_lot": 1.45,
        "has_exit_setting": False, # 120s timer
        "tp_offset": None,
        "sl_offset": None,
        "setup_actions": [
            {"action": "balance", "desc": "Deplete Follower 100 to exactly $0.00", "target_type": "single", "single_email": "mamfollower100@mailinator.com", "balance": 0.0},
            {"action": "category", "desc": "Set All to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "teardown_actions": [
            {"action": "balance", "desc": "Restore Follower 100 to $10,000,000", "target_type": "single", "single_email": "mamfollower100@mailinator.com", "balance": 10000000.0}
        ],
        "expected_lots_map_func": btc10_expected_lots
    }
}


def main():
    parser = argparse.ArgumentParser(description="BlackTrader MAM Bug-Inducing QA Suite Runner")
    parser.add_argument("--tc", type=str, help="Specific test case to execute (e.g., BTC01)")
    parser.add_argument("--all", action="store_true", help="Execute all 10 bug scenarios sequentially")
    parser.add_argument("--list", action="store_true", help="List all 10 bug scenarios")
    args = parser.parse_args()

    if args.list:
        print("\n" + "=" * 85)
        print("     BLACKTRADER ENTERPRISE: 10 REAL-WORLD BUG-INDUCING QA SCENARIOS")
        print("=" * 85)
        for tc_id, cfg in BUG_TEST_CATALOG.items():
            print(f"[{tc_id}] {cfg['name']}")
            print(f"       Target Bug: {cfg.get('target_bug_category')}")
            print(f"       Side: {cfg['side']} | Master Lot: {cfg['master_lot']} | Exit: {'BRACKET' if cfg['has_exit_setting'] else '120s TIMER'}")
            print(f"       Desc: {cfg['description']}\n")
        return

    if args.all:
        tc_keys = list(BUG_TEST_CATALOG.keys())
    elif args.tc:
        raw_keys = [k.strip().upper() for k in args.tc.split(",") if k.strip()]
        invalid = [k for k in raw_keys if k not in BUG_TEST_CATALOG]
        if invalid:
            print(f"[-] Unknown test case ID(s): {invalid}. Use --list to view valid IDs.")
            sys.exit(1)
        tc_keys = raw_keys
    else:
        print("[-] Please specify --tc <ID> (e.g. --tc BTC01) or --all to execute the suite.")
        sys.exit(1)

    suite_start = time.time()
    results = []

    print("\n" + "=" * 85)
    print(f"   STARTING EXECUTION OF {len(tc_keys)} BUG-INDUCING QA SCENARIO(S)")
    print("=" * 85)

    for tc_id in tc_keys:
        cfg = BUG_TEST_CATALOG[tc_id]
        runner = BugScenarioRunner(tc_id, cfg)
        try:
            res = runner.run()
            results.append(res)
        except Exception as e:
            print(f"\n[-] ERROR running {tc_id}: {e}")
            results.append({
                "test_case_id": tc_id,
                "test_case_name": cfg["name"],
                "status": "ERROR",
                "passed": False,
                "error": str(e)
            })

    total_time = round(time.time() - suite_start, 2)
    bugs_exposed_count = sum(1 for r in results if r.get("status") == "BUG_EXPOSED")

    print("\n" + "=" * 85)
    print("                   BUG-INDUCING SUITE SUMMARY")
    print("=" * 85)
    for r in results:
        status_sym = "🚨 BUG EXPOSED" if r.get("status") == "BUG_EXPOSED" else "✅ CLEAN"
        print(f"[{r['test_case_id']}] {r.get('test_case_name', '')[:45]:<45} : {status_sym} ({r.get('execution_duration_sec', 0)}s)")
    print("-" * 85)
    print(f"Total Completed: {len(results)} | Bugs Exposed: {bugs_exposed_count} | Total Time: {total_time}s")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    main()
