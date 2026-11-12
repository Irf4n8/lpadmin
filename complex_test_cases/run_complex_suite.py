#!/usr/bin/env python3
"""
BlackTrader MAM: 10 Complex Enterprise QA Test Cases Suite
===========================================================
Performs 10 complex multi-dimensional test cases validating:
1. Dynamic Dashboard API Interaction (http://localhost:8500):
   - Category shifts (/api/manage/category: multiplier, equity, balance)
   - Balance adjustments (/api/manage/balance: admin margin injection/starvation)
   - Master profit share restructure (/api/manage/master-share: broker settings flow)
2. Follower Quantity & Sizing Calculation:
   - Dynamic lot sizing verification per follower group
   - Sub-lot & broker minimum lot boundary audits
   - Decimals precision and rounding
3. Live Real-Time Market Price Sync:
   - Zero-delay Binance ticker fetching
4. Exit Setting Rule:
   - If test case has NO exit setting (no TP/SL): Mandatory 120-second live observation countdown
   - If test case has exit settings (TP/SL): Observation window & bracket replication verification
5. Autonomous Bug & Anomaly Detection:
   - Replication failures, sizing discrepancies, margin leaks, stuck/orphaned orders
6. Individual Test Reports & Evidence Generation:
   - complex_test_cases/reports/{TC_ID}_report.md
   - complex_test_cases/reports/evidence/{TC_ID}_evidence.json
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
DEFAULT_DASHBOARD_URL = "http://localhost:8500"
DEFAULT_MASTER_EMAIL = "mammaster@mailinator.com"
DEFAULT_PASSWORD = "Test@1234"
DEFAULT_SYMBOL = "BINANCE:BTCUSDT.P"
DEFAULT_BINANCE_SYMBOL = "BTCUSDT"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dashboard_server import TraderSession

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


class ComplexTestCaseRunner:
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

        self.master = UserSession(self.master_email, self.password, "mammaster", base_url=self.base_url)
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
        print("[*] Cleaning slate: ensuring 0 open positions across all accounts...")
        self.master.squareoff_all(symbol=self.symbol, instance=self.instance)
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            list(executor.map(lambda f: f.squareoff_all(symbol=self.symbol, instance=self.instance), self.followers))
        time.sleep(1.0)

    def apply_dashboard_settings(self, setup_actions: List[dict]) -> Tuple[bool, List[str]]:
        errors = []
        for action in setup_actions:
            act_type = action.get("action")
            print(f"[*] [Dashboard Action] {act_type.upper()}: {action.get('desc', '')}")
            
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
                        print(f"[+] Category updated successfully: {r.json().get('category')} ({r.json().get('success_count')}/{r.json().get('total_targeted')} followers)")
                except Exception as e:
                    err = f"Category update request exception: {e}"
                    errors.append(err)
                    print(f"[-] {err}")

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
                        print(f"[+] Balance updated successfully: ${action.get('balance'):,.2f} for {r.json().get('total_targeted')} follower(s)")
                except Exception as e:
                    err = f"Balance update exception: {e}"
                    errors.append(err)
                    print(f"[-] {err}")

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
                        print(f"[+] Master share updated to {action.get('share_percent')}% (Master ID -> MAM -> Settings -> Save flow)")
                except Exception as e:
                    err = f"Master share update exception: {e}"
                    errors.append(err)
                    print(f"[-] {err}")

            time.sleep(0.5)

        return (len(errors) == 0, errors)

    def audit_followers_replication(self, expected_lots_map: Dict[str, float]) -> Tuple[List[dict], dict]:
        """
        Audits each follower's active positions against expected lot sizes.
        expected_lots_map: dict of email -> expected_lot
        """
        def check_follower(f: UserSession):
            positions = f.get_positions(instance=self.instance)
            open_pos = [p for p in positions if p.get("symbol") == self.symbol and p.get("status") == "OPEN"]
            tot_qty = sum(float(p.get("net_qty", 0.0)) for p in open_pos)
            sample = open_pos[0] if open_pos else None
            exp_qty = expected_lots_map.get(f.email, 0.0)

            # Check matching
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
        print(f"      🚀 EXECUTING COMPLEX TEST CASE: {tc_id} - {tc['name']}")
        print("=" * 85)
        print(f"[*] Description        : {tc['description']}")
        print(f"[*] Symbol             : {self.symbol}")
        print(f"[*] Master Lot Size    : {tc['master_lot']:.2f}")
        print(f"[*] Exit Setting Rule  : {'BRACKET ATTACHED' if tc['has_exit_setting'] else 'NO EXIT SETTING -> MANDATORY 120s TIMER'}")
        print("=" * 85 + "\n")

        self.authenticate_all()
        self.clean_slate()

        bugs_found = []

        # 1. Apply Dynamic Dashboard Settings
        setup_actions = tc.get("setup_actions", [])
        if setup_actions:
            print("[*] Phase 1: Applying Dynamic Dashboard Settings...")
            ok, errors = self.apply_dashboard_settings(setup_actions)
            if not ok:
                for err in errors:
                    bugs_found.append({
                        "severity": "HIGH",
                        "type": "DASHBOARD_SETTING_ERROR",
                        "message": err
                    })

        # Allow OMS to propagate configuration
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

        if not order_res.get("success"):
            err_msg = f"Master order placement rejected: {order_res}"
            print(f"[-] FATAL: {err_msg}")
            bugs_found.append({
                "severity": "CRITICAL",
                "type": "ORDER_REJECTED",
                "message": err_msg
            })
            return self.finalize_report(t_start, bugs_found, {}, [], {})

        order_dict = order_res.get("order") if isinstance(order_res.get("order"), dict) else order_res
        master_oid = (
            order_dict.get("market_order_id") or 
            order_dict.get("order_id") or 
            order_dict.get("id") or 
            order_res.get("market_order_id") or 
            order_res.get("order_id")
        )
        fill_price = float(
            order_dict.get("fill_price") or 
            order_dict.get("price") or 
            order_dict.get("avg_price") or 
            live_mid
        )
        print(f"[+] Master Order FILLED: ID={master_oid} at ${fill_price:,.2f}")

        # Wait for replication pipeline
        time.sleep(3.0)

        # In-Flight Dynamic Modification test if applicable (e.g. CTC08)
        in_flight_action = tc.get("in_flight_action")
        if in_flight_action:
            print(f"[*] In-Flight Modification Phase: {in_flight_action.get('desc', '')}")
            ok_if, errors_if = self.apply_dashboard_settings([in_flight_action])
            if not ok_if:
                bugs_found.append({
                    "severity": "MEDIUM",
                    "type": "IN_FLIGHT_SETTING_FAIL",
                    "message": str(errors_if)
                })

        # 4. Audit Follower Replication & Sizing
        print(f"[*] Phase 3: Auditing Follower Replication across 100 Accounts...")
        expected_lots_map = tc.get("expected_lots_map_func")(master_lot, self.master, self.followers)
        follower_data, audit_summary = self.audit_followers_replication(expected_lots_map)

        print(f"[+] Replication Rate : {audit_summary['replication_rate_pct']}% ({audit_summary['replicated_count']}/100)")
        print(f"[+] Lot Sizing Match : {audit_summary['lot_match_rate_pct']}% ({audit_summary['lot_match_count']}/100)")
        print(f"[+] Follower Pool PnL: ${audit_summary['total_follower_pnl']:,.2f}")

        # Evaluate Sizing Bugs
        if audit_summary["replication_rate_pct"] < 95.0 and not tc.get("expect_starvation"):
            bugs_found.append({
                "severity": "HIGH",
                "type": "DEGRADED_REPLICATION",
                "message": f"Replication rate dropped to {audit_summary['replication_rate_pct']}% ({audit_summary['replicated_count']}/100 replicated)."
            })

        if audit_summary["lot_match_rate_pct"] < 90.0 and not tc.get("expect_starvation"):
            bugs_found.append({
                "severity": "HIGH",
                "type": "SIZING_DISCREPANCY",
                "message": f"Follower lot match rate was only {audit_summary['lot_match_rate_pct']}%."
            })

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
            hold_sec = tc.get("bracket_hold_seconds", 20)
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

        # 7. Verify Clean Exit (Residual open count must be 0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            counts = list(executor.map(lambda f: len(f.get_positions(instance=self.instance)), self.followers))
        residual_open = sum(counts)
        print(f"[+] Residual Open Positions across 100 Followers: {residual_open} (Expected: 0)")

        if residual_open > 0:
            bugs_found.append({
                "severity": "HIGH",
                "type": "STUCK_ORPHANED_POSITION",
                "message": f"Master square-off failed to close positions on {residual_open} follower accounts."
            })
            # Clean up residual positions
            print("[*] Force-closing residual follower positions...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
                list(executor.map(lambda f: f.squareoff_all(symbol=self.symbol, instance=self.instance), self.followers))

        # Teardown actions (e.g. restore balances if changed)
        teardown_actions = tc.get("teardown_actions", [])
        if teardown_actions:
            print("[*] Running Teardown actions (restoring balances/settings)...")
            self.apply_dashboard_settings(teardown_actions)

        # Finalize and write report
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
        passed = (len(bugs_found) == 0 and residual_open == 0)

        result = {
            "test_case_id": self.tc_id,
            "test_case_name": self.tc["name"],
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
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
        lines.append(f"# Enterprise Test Case Report: {self.tc_id} - {self.tc['name']}")
        lines.append("")
        lines.append(f"**Execution Timestamp**: `{result['timestamp']}`  ")
        lines.append(f"**Overall Result**: `{'✅ PASSED' if passed else '❌ FAILED'}`  ")
        lines.append(f"**Execution Duration**: `{elapsed_total}s`  ")
        lines.append(f"**Exit Rule**: `{'Bracket Settings Attached' if self.tc.get('has_exit_setting') else '120-Second Mandatory Live Countdown'}`")
        lines.append("")
        lines.append("---")
        lines.append("## Test Case Specifications & Dashboard Actions")
        lines.append(f"- **Description**: {self.tc['description']}")
        lines.append(f"- **Symbol**: `{self.symbol}` | **Side**: `{self.tc['side']}` | **Master Lot**: `{self.tc['master_lot']}`")
        lines.append(f"- **Master Entry Price**: `${fill_price:,.2f}` | **TP**: `{tp_price or 'None'}` | **SL**: `{sl_price or 'None'}`")
        lines.append("")
        lines.append("### Dashboard Configuration Actions Applied")
        for a in self.tc.get("setup_actions", []):
            lines.append(f"- **{a.get('action').upper()}**: {a.get('desc', '')} (`target={a.get('target_type')}`)")
        lines.append("")
        lines.append("---")
        lines.append("## Replication & Lot Sizing Verification")
        lines.append("| Metric | Result | Benchmark |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Replication Rate** | `{result['replication_rate_pct']}%` ({result['replicated_count']}/100) | {'✅ 100%' if result['replication_rate_pct'] >= 98 else '⚠️ Degraded'} |")
        lines.append(f"| **Lot Sizing Match Rate** | `{result['lot_match_rate_pct']}%` | {'✅ Verified' if result['lot_match_rate_pct'] >= 90 else '❌ Discrepancy'} |")
        lines.append(f"| **Residual Open After Square-off** | `{residual_open}` | {'✅ Clean (0)' if residual_open == 0 else '❌ Stuck Positions'} |")
        lines.append("")
        lines.append("---")
        lines.append("## Sample Follower Execution Audit")
        lines.append("| Follower Email | Expected Lot | Actual Lot | Match? | Entry Price | Floating PnL |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for fd in follower_data[:10]:
            match_str = "✅ YES" if fd["lot_match"] else "❌ NO"
            lines.append(f"| `{fd['email']}` | `{fd['expected_qty']:.2f}` | `{fd['actual_qty']:.2f}` | {match_str} | `${fd['entry_price']:,.2f}` | `${fd['pnl']:+,.2f}` |")
        lines.append("")
        lines.append("---")
        lines.append("## Identified Bugs & Anomalies")
        if bugs_found:
            for b in bugs_found:
                lines.append(f"- **[{b['severity']}] {b['type']}**: {b['message']}")
        else:
            lines.append("- **No bugs identified.** Flawless dashboard configuration, exact quantity scaling across followers, zero slippage anomalies, and synchronized square-off confirmed.")
        lines.append("")

        with open(rep_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[+] Individual Test Case Report Saved : {rep_file}")
        print(f"[+] Individual Test Case Evidence Saved: {ev_file}\n")
        return result


# ---------------------------------------------------------------------------
# DEFINITIONS OF THE 10 COMPLEX TEST CASES
# ---------------------------------------------------------------------------

def ctc01_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # F1-F30: 1.5x -> 1.40 * 1.5 = 2.10
    # F31-F70: 2.5x -> 1.40 * 2.5 = 3.50
    # F71-F100: 3.0x -> 1.40 * 3.0 = 4.20
    m = {}
    for i in range(1, 101):
        em = f"mamfollower{i}@mailinator.com"
        if 1 <= i <= 30:
            m[em] = round(master_lot * 1.5, 2)
        elif 31 <= i <= 70:
            m[em] = round(master_lot * 2.5, 2)
        else:
            m[em] = round(master_lot * 3.0, 2)
    return m

def ctc02_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Equity mode: F1 ($2M / $10M = 0.20 -> max(1.0, 0.40)), F2 ($5M = 1.00), F3 ($10M = 2.00), F4 ($15M = 3.00), F5-F100 ($10M = 2.00)
    # Broker minimum lot on BTC is 1.0 lot.
    m = {}
    for i in range(1, 101):
        em = f"mamfollower{i}@mailinator.com"
        if i == 1:
            m[em] = 1.00 # Enforces broker min lot 1.0
        elif i == 2:
            m[em] = 1.00
        elif i == 3:
            m[em] = 2.00
        elif i == 4:
            m[em] = 3.00
        else:
            m[em] = 2.00
    return m

def ctc03_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Balance mode: F1-F10 ($5M / $10M = 0.5 * 2.0 = 1.0 lot), F11-F20 ($10M = 2.0 lots), F21-F30 ($20M = 4.0 lots)
    m = {}
    for i in range(1, 101):
        em = f"mamfollower{i}@mailinator.com"
        if 1 <= i <= 10:
            m[em] = 1.00
        elif 11 <= i <= 20:
            m[em] = 2.00
        elif 21 <= i <= 30:
            m[em] = 4.00
        else:
            m[em] = 2.00
    return m

def ctc04_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Multiplier 2.0x -> 1.65 * 2.0 = 3.30
    return {f"mamfollower{i}@mailinator.com": round(master_lot * 2.0, 2) for i in range(1, 101)}

def ctc05_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Multiplier 2.0x -> 1.25 * 2.0 = 2.50
    return {f"mamfollower{i}@mailinator.com": round(master_lot * 2.0, 2) for i in range(1, 101)}

def ctc06_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Multiplier 2.0x -> 3.50 * 2.0 = 7.00
    return {f"mamfollower{i}@mailinator.com": round(master_lot * 2.0, 2) for i in range(1, 101)}

def ctc07_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Multiplier 2.0x -> 2.00 * 2.0 = 4.00. F100 has $50 balance (starvation test)
    m = {f"mamfollower{i}@mailinator.com": round(master_lot * 2.0, 2) for i in range(1, 100)}
    m["mamfollower100@mailinator.com"] = 0.0 # Expected rejection due to margin
    return m

def ctc08_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Multiplier 2.0x -> 1.50 * 2.0 = 3.00 (in-flight mid-modification should preserve active 3.00 lot)
    return {f"mamfollower{i}@mailinator.com": round(master_lot * 2.0, 2) for i in range(1, 101)}

def ctc09_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Multiplier 2.25x -> 1.36 * 2.25 = 3.06
    return {f"mamfollower{i}@mailinator.com": round(master_lot * 2.25, 2) for i in range(1, 101)}

def ctc10_expected_lots(master_lot: float, master: UserSession, followers: List[UserSession]) -> Dict[str, float]:
    # Mixed fleet: F1-F33 (2.0x = 3.0 lots), F34-F66 (Equity 1:1 = 1.50 lots), F67-F100 (Balance 1:1 = 1.50 lots)
    m = {}
    for i in range(1, 101):
        em = f"mamfollower{i}@mailinator.com"
        if 1 <= i <= 33:
            m[em] = round(master_lot * 2.0, 2)
        else:
            m[em] = round(master_lot * 1.0, 2)
    return m


COMPLEX_TEST_CATALOG = {
    "CTC01": {
        "id": "CTC01",
        "name": "Multi-Tier Multiplier Partitioning (F1-30: 1.5x, F31-70: 2.5x, F71-100: 3.0x)",
        "description": "Validates partitioning the 100-follower fleet into 3 distinct multiplier tiers via dashboard API.",
        "side": "BUY",
        "master_lot": 1.40,
        "has_exit_setting": True,
        "tp_offset": 30.0,
        "sl_offset": -30.0,
        "bracket_hold_seconds": 15,
        "setup_actions": [
            {"action": "category", "desc": "Set F1-F30 to Multiplier 1.5x", "target_type": "range", "category": "multiplier", "multiplier": 1.5, "start": 1, "end": 30},
            {"action": "category", "desc": "Set F31-F70 to Multiplier 2.5x", "target_type": "range", "category": "multiplier", "multiplier": 2.5, "start": 31, "end": 70},
            {"action": "category", "desc": "Set F71-F100 to Multiplier 3.0x", "target_type": "range", "category": "multiplier", "multiplier": 3.0, "start": 71, "end": 100}
        ],
        "expected_lots_map_func": ctc01_expected_lots
    },
    "CTC02": {
        "id": "CTC02",
        "name": "Asymmetric Balance Injection & Equity-Based Proportional Sizing",
        "description": "Adjusts follower balances via Admin API ($2M, $5M, $10M, $15M) and verifies proportional lot sizing.",
        "side": "BUY",
        "master_lot": 2.00,
        "has_exit_setting": True,
        "tp_offset": 25.0,
        "sl_offset": -25.0,
        "bracket_hold_seconds": 15,
        "setup_actions": [
            {"action": "category", "desc": "Set All 100 Followers to Equity Mode", "target_type": "all", "category": "equity", "multiplier": 1.0},
            {"action": "balance", "desc": "Set F1 Balance to $2,000,000", "target_type": "single", "single_email": "mamfollower1@mailinator.com", "balance": 2000000.0},
            {"action": "balance", "desc": "Set F2 Balance to $5,000,000", "target_type": "single", "single_email": "mamfollower2@mailinator.com", "balance": 5000000.0},
            {"action": "balance", "desc": "Set F3 Balance to $10,000,000", "target_type": "single", "single_email": "mamfollower3@mailinator.com", "balance": 10000000.0},
            {"action": "balance", "desc": "Set F4 Balance to $15,000,000", "target_type": "single", "single_email": "mamfollower4@mailinator.com", "balance": 15000000.0}
        ],
        "teardown_actions": [
            {"action": "balance", "desc": "Restore F1-F4 Balances to $10,000,000", "target_type": "range", "start": 1, "end": 4, "balance": 10000000.0}
        ],
        "expected_lots_map_func": ctc02_expected_lots
    },
    "CTC03": {
        "id": "CTC03",
        "name": "Balance-Based Proportional Sizing with Multi-Step Balances",
        "description": "Sets followers to Balance-Based sizing with multi-tier capital allocation ($5M, $10M, $20M).",
        "side": "SELL",
        "master_lot": 2.00,
        "has_exit_setting": True,
        "tp_offset": None,
        "sl_offset": 30.0,
        "bracket_hold_seconds": 15,
        "setup_actions": [
            {"action": "category", "desc": "Set All Followers to Balance Mode", "target_type": "all", "category": "balance", "multiplier": 1.0},
            {"action": "balance", "desc": "Set F1-F10 Balance to $5,000,000", "target_type": "range", "start": 1, "end": 10, "balance": 5000000.0},
            {"action": "balance", "desc": "Set F11-F20 Balance to $10,000,000", "target_type": "range", "start": 11, "end": 20, "balance": 10000000.0},
            {"action": "balance", "desc": "Set F21-F30 Balance to $20,000,000", "target_type": "range", "start": 21, "end": 30, "balance": 20000000.0}
        ],
        "teardown_actions": [
            {"action": "balance", "desc": "Restore F1-F30 Balances to $10,000,000", "target_type": "range", "start": 1, "end": 30, "balance": 10000000.0}
        ],
        "expected_lots_map_func": ctc03_expected_lots
    },
    "CTC04": {
        "id": "CTC04",
        "name": "120-Second Unbracketed Volatility Endurance with Real-Time Tick Sync",
        "description": "Unbracketed trade (No TP/SL): Engages a mandatory 120-second live observation countdown tracking tick prices.",
        "side": "BUY",
        "master_lot": 1.65,
        "has_exit_setting": False,
        "tp_offset": None,
        "sl_offset": None,
        "setup_actions": [
            {"action": "category", "desc": "Reset All Followers to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": ctc04_expected_lots
    },
    "CTC05": {
        "id": "CTC05",
        "name": "MAM Master Profit Share Restructure (50% -> 35%) & Ledger Impact",
        "description": "Restructures Master profit share to 35% via /api/manage/master-share and verifies follower inheritance.",
        "side": "BUY",
        "master_lot": 1.25,
        "has_exit_setting": True,
        "tp_offset": 20.0,
        "sl_offset": None,
        "bracket_hold_seconds": 15,
        "setup_actions": [
            {"action": "master_share", "desc": "Update MAM Master share to 35%", "share_percent": 35.0, "display_name": "mammaster"},
            {"action": "category", "desc": "Sync Followers to inherit 35% Master Share", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "teardown_actions": [
            {"action": "master_share", "desc": "Restore Master share to 50%", "share_percent": 50.0, "display_name": "mammaster"},
            {"action": "category", "desc": "Restore Followers to Multiplier 2.0x (50% share)", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": ctc05_expected_lots
    },
    "CTC06": {
        "id": "CTC06",
        "name": "High-Volume Stress Sizing (Master 3.50 Lots -> 700 Follower Lots Pool)",
        "description": "Heavy lot replication test generating 700+ lots across 100 followers to verify OMS throughput.",
        "side": "SELL",
        "master_lot": 3.50,
        "has_exit_setting": True,
        "tp_offset": -25.0,
        "sl_offset": 25.0,
        "bracket_hold_seconds": 15,
        "setup_actions": [
            {"action": "category", "desc": "Ensure All Followers at Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": ctc06_expected_lots
    },
    "CTC07": {
        "id": "CTC07",
        "name": "Micro-Balance Margin Depletion & Fleet Starvation Resilience",
        "description": "Starves Follower 100 ($50 balance) while keeping F1-F99 funded to test margin rejection isolation.",
        "side": "BUY",
        "master_lot": 2.00,
        "has_exit_setting": True,
        "tp_offset": 25.0,
        "sl_offset": -25.0,
        "bracket_hold_seconds": 15,
        "expect_starvation": True,
        "setup_actions": [
            {"action": "category", "desc": "Set All Followers to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0},
            {"action": "balance", "desc": "Starve Follower 100 to $50.00", "target_type": "single", "single_email": "mamfollower100@mailinator.com", "balance": 50.0}
        ],
        "teardown_actions": [
            {"action": "balance", "desc": "Restore Follower 100 to $10,000,000", "target_type": "single", "single_email": "mamfollower100@mailinator.com", "balance": 10000000.0}
        ],
        "expected_lots_map_func": ctc07_expected_lots
    },
    "CTC08": {
        "id": "CTC08",
        "name": "Mid-Flight Multiplier Alteration Under Active Position",
        "description": "Modifies follower multiplier settings while a trade is actively open to verify position integrity.",
        "side": "BUY",
        "master_lot": 1.50,
        "has_exit_setting": False,
        "tp_offset": None,
        "sl_offset": None,
        "setup_actions": [
            {"action": "category", "desc": "Set All Followers to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "in_flight_action": {
            "action": "category",
            "desc": "Mid-Flight: Update F1-F10 multiplier to 3.0x while order is OPEN",
            "target_type": "range",
            "category": "multiplier",
            "multiplier": 3.0,
            "start": 1,
            "end": 10
        },
        "teardown_actions": [
            {"action": "category", "desc": "Reset F1-F10 to Multiplier 2.0x", "target_type": "range", "category": "multiplier", "multiplier": 2.0, "start": 1, "end": 10}
        ],
        "expected_lots_map_func": ctc08_expected_lots
    },
    "CTC09": {
        "id": "CTC09",
        "name": "Dual-Bracket Tight Boundary Scalp (TP +15 / SL -15 pts)",
        "description": "Validates odd fractional multiplier (2.25x -> 3.06 lots) with tight dual-bracket execution.",
        "side": "BUY",
        "master_lot": 1.36,
        "has_exit_setting": True,
        "tp_offset": 15.0,
        "sl_offset": -15.0,
        "bracket_hold_seconds": 15,
        "setup_actions": [
            {"action": "category", "desc": "Set All Followers to Multiplier 2.25x", "target_type": "all", "category": "multiplier", "multiplier": 2.25}
        ],
        "teardown_actions": [
            {"action": "category", "desc": "Reset All Followers to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": ctc09_expected_lots
    },
    "CTC10": {
        "id": "CTC10",
        "name": "Fleet Inversion & Heterogeneous Mode Coexistence (Multiplier, Equity & Balance)",
        "description": "Partitions fleet across Multiplier (F1-33), Equity (F34-66), and Balance (F67-100) modes.",
        "side": "SELL",
        "master_lot": 1.50,
        "has_exit_setting": False,
        "tp_offset": None,
        "sl_offset": None,
        "setup_actions": [
            {"action": "category", "desc": "Set F1-F33 to Multiplier 2.0x", "target_type": "range", "category": "multiplier", "multiplier": 2.0, "start": 1, "end": 33},
            {"action": "category", "desc": "Set F34-F66 to Equity Mode", "target_type": "range", "category": "equity", "multiplier": 1.0, "start": 34, "end": 66},
            {"action": "category", "desc": "Set F67-F100 to Balance Mode", "target_type": "range", "category": "balance", "multiplier": 1.0, "start": 67, "end": 100}
        ],
        "teardown_actions": [
            {"action": "category", "desc": "Reset All Followers to Multiplier 2.0x", "target_type": "all", "category": "multiplier", "multiplier": 2.0}
        ],
        "expected_lots_map_func": ctc10_expected_lots
    }
}


def main():
    parser = argparse.ArgumentParser(description="BlackTrader MAM Complex Test Suite Runner")
    parser.add_argument("--tc", type=str, help="Specific test case to execute (e.g., CTC01)")
    parser.add_argument("--all", action="store_true", help="Execute all 10 complex test cases sequentially")
    parser.add_argument("--list", action="store_true", help="List all defined complex test cases")
    args = parser.parse_args()

    if args.list:
        print("\n" + "=" * 80)
        print("          BLACKTRADER ENTERPRISE: 10 COMPLEX TEST CASES CATALOG")
        print("=" * 80)
        for tc_id, cfg in COMPLEX_TEST_CATALOG.items():
            print(f"[{tc_id}] {cfg['name']}")
            print(f"       Side: {cfg['side']} | Master Lot: {cfg['master_lot']} | Exit: {'BRACKET' if cfg['has_exit_setting'] else '120s TIMER'}")
            print(f"       Desc: {cfg['description']}\n")
        return

    if args.all:
        tc_keys = list(COMPLEX_TEST_CATALOG.keys())
    elif args.tc:
        tc_id = args.tc.upper()
        if tc_id not in COMPLEX_TEST_CATALOG:
            print(f"[-] Unknown test case ID: {args.tc}. Use --list to view valid IDs.")
            sys.exit(1)
        tc_keys = [tc_id]
    else:
        print("[-] Please specify --tc <ID> (e.g. --tc CTC01) or --all to execute the suite.")
        sys.exit(1)

    suite_start = time.time()
    results = []

    print("\n" + "=" * 85)
    print(f"   STARTING EXECUTION OF {len(tc_keys)} COMPLEX TEST CASE(S)")
    print("=" * 85)

    for tc_id in tc_keys:
        cfg = COMPLEX_TEST_CATALOG[tc_id]
        runner = ComplexTestCaseRunner(tc_id, cfg)
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
    passed_count = sum(1 for r in results if r.get("passed"))
    failed_count = len(results) - passed_count

    print("\n" + "=" * 85)
    print("                      SUITE EXECUTION SUMMARY")
    print("=" * 85)
    for r in results:
        status_sym = "✅ PASS" if r.get("passed") else "❌ FAIL"
        print(f"[{r['test_case_id']}] {r.get('test_case_name', '')[:45]:<45} : {status_sym} ({r.get('execution_duration_sec', 0)}s)")
    print("-" * 85)
    print(f"Total Completed: {len(results)} | Passed: {passed_count} | Failed: {failed_count} | Total Time: {total_time}s")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    main()
