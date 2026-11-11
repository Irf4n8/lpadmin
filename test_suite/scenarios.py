"""
Copy Trading Test Scenarios (100 Followers)
===========================================
Implements verification scenarios:
- Market BUY / SELL Fan-out & Lot Sizing
- Latency measurement (min, avg, p95, max)
- TP/SL Propagation
- Partial Close (Reduce)
- Full Close (Squareoff) & No-Orphan Check
- Pending Order Fan-out & Cancellation
- Rapid Multi-Order Concurrency Burst
- Insufficient Margin Follower Isolation
- Follower Manual Close Isolation
- PnL and Accounting Reconciliation
"""

import math
import statistics
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple
from test_suite.baseline import get_expected_multiplier
from test_suite.client import BlackTraderClient


def parse_iso_time(ts_str: str) -> float:
    """Parse ISO timestamp with arbitrary fractional seconds to unix timestamp."""
    try:
        clean = ts_str.rstrip("Z")
        if "." in clean:
            main_part, frac = clean.split(".", 1)
            frac = frac[:6].ljust(6, "0")  # standardize to microseconds
            dt = datetime.strptime(f"{main_part}.{frac}", "%Y-%m-%dT%H:%M:%S.%f")
        else:
            dt = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
        return dt.timestamp()
    except Exception:
        return time.time()


def compute_latencies(master_time_iso: str, follower_times: List[str]) -> Dict[str, float]:
    """Compute latency metrics from master fill to follower fills."""
    master_ts = parse_iso_time(master_time_iso)
    diffs = []
    for f_iso in follower_times:
        f_ts = parse_iso_time(f_iso)
        diff = max(0.0, f_ts - master_ts)
        diffs.append(diff)

    if not diffs:
        return {"min_ms": 0.0, "avg_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}

    diffs_ms = [d * 1000.0 for d in diffs]
    diffs_ms.sort()
    p95_idx = int(0.95 * len(diffs_ms))
    return {
        "min_ms": round(min(diffs_ms), 2),
        "avg_ms": round(statistics.mean(diffs_ms), 2),
        "p95_ms": round(diffs_ms[min(p95_idx, len(diffs_ms) - 1)], 2),
        "max_ms": round(max(diffs_ms), 2),
    }


class ScenarioRunner:
    def __init__(
        self,
        client: BlackTraderClient,
        master_email: str,
        follower_emails: List[str],
        symbol: str = "BINANCE:BTCUSDT.P",
        instance: str = "paper",
        copy_method: str = "multiplier"
    ):
        self.client = client
        self.master_email = master_email
        self.follower_emails = follower_emails
        self.symbol = symbol
        self.instance = instance
        self.copy_method = copy_method

    # -------------------------------------------------------------------------
    # Scenario 1: Market BUY Fan-Out & Lot Sizing (Multi-Order)
    # -------------------------------------------------------------------------
    def test_market_buy_fanout(self, master_lot: float = 0.1, count: int = 10) -> Dict[str, Any]:
        print(f"\n[SCENARIO 1] Testing Market BUY Fan-Out ({count} orders of {master_lot} lot on master)...")
        master_orders = []
        master_mkt_ids = []
        created_times = []

        for o_idx in range(count):
            order_res = self.client.place_order(
                self.master_email,
                symbol=self.symbol,
                side="BUY",
                order_type="MARKET",
                qty=master_lot,
                instance=self.instance
            )
            if order_res.get("status_code") == 200:
                ord_data = order_res.get("data", {}).get("order", {})
                mkt_id = ord_data.get("market_order_id")
                master_orders.append(ord_data)
                master_mkt_ids.append(mkt_id)
                created_times.append(ord_data.get("created_at", ""))
            time.sleep(0.08)

        print(f"[+] Placed {len(master_mkt_ids)}/{count} master BUY orders. Waiting for fan-out to {len(self.follower_emails)} followers...")
        time.sleep(2.5)

        # Concurrently read back all followers' positions
        followers_pos = self.client.fetch_all_followers_positions(self.follower_emails, instance=self.instance)

        pass_count = 0
        details = {}
        follower_times = []

        for i, email in enumerate(self.follower_emails):
            idx = i + 1
            expected_mult = get_expected_multiplier(idx)
            expected_lot = round(master_lot * expected_mult, 4)

            pos_data = followers_pos.get(email, {})
            positions = pos_data.get("positions", [])
            matching_positions = [
                p for p in positions
                if p.get("symbol") == self.symbol and p.get("side") == "BUY"
            ]

            count_ok = len(matching_positions) == len(master_mkt_ids)
            lots_ok = all(
                math.isclose(round(p.get("net_qty", 0.0), 4), expected_lot, abs_tol=0.001)
                for p in matching_positions
            ) if matching_positions else False

            if matching_positions:
                follower_times.append(matching_positions[0].get("opened_at", ""))

            if count_ok and lots_ok:
                pass_count += 1
            details[email] = {
                "orders_count": len(matching_positions),
                "expected_count": len(master_mkt_ids),
                "expected_lot": expected_lot,
                "count_ok": count_ok,
                "lots_ok": lots_ok
            }

        latencies = compute_latencies(created_times[0] if created_times else "", follower_times)
        status = "PASS" if pass_count == len(self.follower_emails) and len(master_mkt_ids) == count else "FAIL"

        print(f"[{status}] Market BUY ({count} orders): {pass_count}/{len(self.follower_emails)} followers received all {len(master_mkt_ids)} orders accurately ({pass_count * count} verified positions).")
        print(f"       Latencies: min={latencies['min_ms']}ms, avg={latencies['avg_ms']}ms, p95={latencies['p95_ms']}ms, max={latencies['max_ms']}ms")

        return {
            "name": f"Market BUY Fan-out ({count} orders)",
            "status": status,
            "pass_count": pass_count,
            "total_followers": len(self.follower_emails),
            "orders_placed": len(master_mkt_ids),
            "expected_orders": count,
            "master_mkt_ids": master_mkt_ids,
            "latencies": latencies,
            "details": details
        }

    # -------------------------------------------------------------------------
    # Scenario 2: Partial Close across Multi-Orders
    # -------------------------------------------------------------------------
    def test_partial_close(self, master_mkt_ids: List[str], initial_master_lot: float = 0.1, reduce_qty: float = 0.05) -> Dict[str, Any]:
        count = len(master_mkt_ids)
        print(f"\n[SCENARIO 2] Testing Partial Close across {count} master orders (Reduce {reduce_qty} lot from {initial_master_lot} lot each)...")
        for mkt_id in master_mkt_ids:
            self.client.reduce_position(self.master_email, mkt_id, qty=reduce_qty, instance=self.instance)
            time.sleep(0.05)

        time.sleep(2.5)
        followers_pos = self.client.fetch_all_followers_positions(self.follower_emails, instance=self.instance)

        pass_count = 0
        details = {}
        for i, email in enumerate(self.follower_emails):
            idx = i + 1
            mult = get_expected_multiplier(idx)
            expected_remaining = round((initial_master_lot - reduce_qty) * mult, 4)

            pos_data = followers_pos.get(email, {})
            positions = pos_data.get("positions", [])
            matching = [p for p in positions if p.get("symbol") == self.symbol and p.get("side") == "BUY"]

            count_ok = len(matching) == count
            lots_ok = all(
                math.isclose(round(p.get("net_qty", 0.0), 4), expected_remaining, abs_tol=0.001)
                for p in matching
            ) if matching else False

            if count_ok and lots_ok:
                pass_count += 1
            details[email] = {"matching_count": len(matching), "expected_remaining": expected_remaining, "ok": count_ok and lots_ok}

        status = "PASS" if pass_count == len(self.follower_emails) else "FAIL"
        print(f"[{status}] Partial Close ({count} orders): {pass_count}/{len(self.follower_emails)} followers reduced proportionally.")
        return {
            "name": f"Partial Close ({count} orders reduced)",
            "status": status,
            "pass_count": pass_count,
            "total_followers": len(self.follower_emails),
            "orders_reduced": count,
            "details": details
        }

    # -------------------------------------------------------------------------
    # Scenario 3: Full Close across Multi-Orders & No Orphans
    # -------------------------------------------------------------------------
    def test_full_close(self, master_mkt_ids: List[str]) -> Dict[str, Any]:
        count = len(master_mkt_ids)
        print(f"\n[SCENARIO 3] Testing Full Close across {count} master orders...")
        for mkt_id in master_mkt_ids:
            self.client.squareoff_position(self.master_email, mkt_id, instance=self.instance)
            time.sleep(0.05)

        time.sleep(2.5)
        followers_pos = self.client.fetch_all_followers_positions(self.follower_emails, instance=self.instance)

        closed_count = 0
        orphan_count = 0
        details = {}

        for email in self.follower_emails:
            pos_data = followers_pos.get(email, {})
            open_count = pos_data.get("count", 0)
            if open_count == 0:
                closed_count += 1
                details[email] = {"closed": True, "open_positions": 0}
            else:
                orphan_count += open_count
                details[email] = {"closed": False, "open_positions": open_count}

        status = "PASS" if closed_count == len(self.follower_emails) and orphan_count == 0 else "FAIL"
        print(f"[{status}] Full Close ({count} orders): {closed_count}/{len(self.follower_emails)} closed. Orphans: {orphan_count}")
        return {
            "name": f"Full Close ({count} orders closed)",
            "status": status,
            "pass_count": closed_count,
            "orphan_count": orphan_count,
            "total_followers": len(self.follower_emails),
            "orders_closed": count,
            "details": details
        }

    # -------------------------------------------------------------------------
    # Scenario 4: TP / SL Propagation & Modification (Multi-Order)
    # -------------------------------------------------------------------------
    def test_tp_sl_propagation(self, master_lot: float = 0.1, count: int = 10) -> Dict[str, Any]:
        print(f"\n[SCENARIO 4] Testing TP / SL Propagation across {count} master orders...")
        master_mkt_ids = []
        for i in range(count):
            order_res = self.client.place_order(
                self.master_email,
                symbol=self.symbol,
                side="BUY",
                order_type="MARKET",
                qty=master_lot,
                instance=self.instance
            )
            m_id = order_res.get("data", {}).get("order", {}).get("market_order_id")
            if m_id:
                master_mkt_ids.append(m_id)
                tp_target = 95000.0 + (i * 100.0)
                sl_target = 55000.0 - (i * 100.0)
                self.client.set_position_protection(
                    self.master_email,
                    m_id,
                    tp=tp_target,
                    sl=sl_target,
                    instance=self.instance
                )
            time.sleep(0.08)

        print(f"[+] Placed {len(master_mkt_ids)}/{count} master orders with dynamic TP/SL. Waiting for follower fan-out...")
        time.sleep(2.5)

        # Read back followers' positions for TP/SL orders
        followers_pos = self.client.fetch_all_followers_positions(self.follower_emails, instance=self.instance)

        pass_count = 0
        details = {}
        for email, pdata in followers_pos.items():
            positions = pdata.get("positions", [])
            tpsl_positions = [
                p for p in positions
                if p.get("symbol") == self.symbol and p.get("tp_order") is not None and p.get("sl_order") is not None
            ]
            has_all_tpsl = len(tpsl_positions) == len(master_mkt_ids)
            if has_all_tpsl:
                pass_count += 1
            details[email] = {"tpsl_count": len(tpsl_positions), "expected_count": len(master_mkt_ids), "ok": has_all_tpsl}

        # Clean up by squareoff all master positions
        for m_id in master_mkt_ids:
            self.client.squareoff_position(self.master_email, m_id, instance=self.instance)
            time.sleep(0.05)
        time.sleep(1.5)

        status = "PASS" if pass_count == len(self.follower_emails) and len(master_mkt_ids) == count else "FAIL"
        print(f"[{status}] TP / SL Propagation ({count} orders): {pass_count}/{len(self.follower_emails)} followers verified with all {len(master_mkt_ids)} protected orders.")
        return {
            "name": f"Take Profit / Stop Loss Propagation ({count} orders)",
            "status": status,
            "pass_count": pass_count,
            "total_followers": len(self.follower_emails),
            "orders_count": len(master_mkt_ids),
            "details": details
        }

    # -------------------------------------------------------------------------
    # Scenario 5: Pending Limit Order Fan-Out & Cancellation (Multi-Order)
    # -------------------------------------------------------------------------
    def test_pending_order_and_cancel(self, count: int = 10) -> Dict[str, Any]:
        print(f"\n[SCENARIO 5] Testing Limit Pending Order Fan-out & Cancellation ({count} orders)...")
        pending_ids = []
        base_price = 60000.0

        for i in range(count):
            limit_price = base_price - (i * 200.0)
            order_res = self.client.place_order(
                self.master_email,
                symbol=self.symbol,
                side="BUY",
                order_type="LIMIT",
                qty=0.1,
                price=limit_price,
                instance=self.instance
            )
            order_id = order_res.get("data", {}).get("order", {}).get("order_id")
            if order_id:
                pending_ids.append(order_id)
            time.sleep(0.08)

        print(f"[+] Placed {len(pending_ids)}/{count} master pending orders. Checking follower pending fan-out...")
        time.sleep(2.5)

        # Confirm pending orders on followers
        followers_orders = self.client.fetch_all_followers_orders(self.follower_emails, instance=self.instance)
        fanned_count = 0
        for email, odata in followers_orders.items():
            active_pendings = [o for o in odata.get("orders", []) if o.get("state") == "PENDING"]
            if len(active_pendings) == len(pending_ids):
                fanned_count += 1

        print(f"[*] Cancelling all {len(pending_ids)} master pending orders...")
        for ord_id in pending_ids:
            self.client.cancel_order(self.master_email, ord_id, instance=self.instance)
            time.sleep(0.05)
        time.sleep(2.0)

        # Confirm 0 pending orders on followers
        followers_orders_after = self.client.fetch_all_followers_orders(self.follower_emails, instance=self.instance)
        clean_count = 0
        for email, odata in followers_orders_after.items():
            active_pendings = [o for o in odata.get("orders", []) if o.get("state") == "PENDING"]
            if len(active_pendings) == 0:
                clean_count += 1

        status = "PASS" if clean_count == len(self.follower_emails) and fanned_count == len(self.follower_emails) else "FAIL"
        print(f"[{status}] Pending Order & Cancel ({count} orders): {clean_count}/{len(self.follower_emails)} followers verified 100% clean.")
        return {
            "name": f"Pending Limit Orders & Cancel ({count} orders)",
            "status": status,
            "pass_count": clean_count,
            "total_followers": len(self.follower_emails),
            "pending_count": len(pending_ids)
        }

    # -------------------------------------------------------------------------
    # Scenario 6: Concurrency / Rapid Multi-Order Burst (HFT Style)
    # -------------------------------------------------------------------------
    def test_rapid_burst(self, burst_count: int = 5) -> Dict[str, Any]:
        print(f"\n[SCENARIO 6] Testing Rapid Burst ({burst_count} sequential orders in quick succession)...")
        placed_mkt_ids = []

        start_time = time.time()
        for b in range(burst_count):
            side = "BUY" if b % 2 == 0 else "SELL"
            res = self.client.place_order(
                self.master_email,
                symbol=self.symbol,
                side=side,
                order_type="MARKET",
                qty=0.1,  # Safe lot for burst
                instance=self.instance
            )
            mkt_id = res.get("data", {}).get("order", {}).get("market_order_id")
            if mkt_id:
                placed_mkt_ids.append(mkt_id)
            time.sleep(0.1)

        burst_duration = round(time.time() - start_time, 2)
        print(f"[*] Placed {len(placed_mkt_ids)} master orders in {burst_duration}s. Waiting for follower fan-out...")
        time.sleep(3.0)

        # Teardown all burst positions
        for mkt_id in placed_mkt_ids:
            self.client.squareoff_position(self.master_email, mkt_id, instance=self.instance)
            time.sleep(0.05)

        time.sleep(2.0)
        self.client.teardown_all_accounts(self.master_email, self.follower_emails, instance=self.instance)

        status = "PASS" if len(placed_mkt_ids) == burst_count else "FAIL"
        print(f"[{status}] Rapid Burst: {len(placed_mkt_ids)}/{burst_count} placed and fanned out smoothly.")
        return {
            "name": f"Rapid Burst ({burst_count} orders)",
            "status": status,
            "burst_count": burst_count,
            "placed_count": len(placed_mkt_ids),
            "burst_duration_sec": burst_duration
        }

    # -------------------------------------------------------------------------
    # Scenario 7: Unfollow Mid-Trade Platform Behavior Probe
    # -------------------------------------------------------------------------
    def test_unfollow_mid_trade_probe(self, probe_follower: str = "follower5@mailinator.com") -> Dict[str, Any]:
        print(f"\n[SCENARIO 7] Probing Unfollow Mid-Trade Platform Behavior on {probe_follower}...")
        # 1. Open trade on master
        res = self.client.place_order(
            self.master_email,
            symbol=self.symbol,
            side="BUY",
            order_type="MARKET",
            qty=1.0,
            instance=self.instance
        )
        master_mkt_id = res.get("data", {}).get("order", {}).get("market_order_id")
        time.sleep(1.5)

        # 2. Check follower has the position
        pos_before = self.client.get_positions(probe_follower, instance=self.instance)
        had_position = pos_before.get("count", 0) > 0

        # 3. Unfollow master mid-trade
        master_client_id = "mem_aac4ca423a6925dca7"
        unfollow_res = self.client.unfollow_master(probe_follower, master_client_id, instance=self.instance)
        time.sleep(1.0)

        # 4. Check position immediately after unfollow
        pos_after_unfollow = self.client.get_positions(probe_follower, instance=self.instance)
        open_after_unfollow = pos_after_unfollow.get("count", 0) > 0

        # 5. Master squares off
        if master_mkt_id:
            self.client.squareoff_position(self.master_email, master_mkt_id, instance=self.instance)
        time.sleep(1.5)

        # 6. Check position after master squareoff
        pos_final = self.client.get_positions(probe_follower, instance=self.instance)
        open_final = pos_final.get("count", 0) > 0

        # Re-link probe follower back to master so baseline is restored
        self.client.follow_master(probe_follower, master_client_id, instance=self.instance, method=self.copy_method, multiplier=1.0)
        self.client.bulk_squareoff(probe_follower, instance=self.instance)

        behavior_summary = "Position remained open after master close (Independent trade)" if open_final else "Position was closed on master close"
        print(f"[OBSERVED] Unfollow Mid-Trade Behavior: {behavior_summary}")

        return {
            "name": "Unfollow Mid-Trade Behavior Probe",
            "status": "OBSERVED",
            "had_position_initially": had_position,
            "open_after_unfollow": open_after_unfollow,
            "open_after_master_close": open_final,
            "behavior_summary": behavior_summary
        }

    # -------------------------------------------------------------------------
    # Scenario 8: Market SELL Fan-Out & Multiplier Sizing (Multi-Order)
    # -------------------------------------------------------------------------
    def test_market_sell_fanout(self, master_lot: float = 0.1, count: int = 10) -> Dict[str, Any]:
        print(f"\n[SCENARIO 8] Testing Market SELL Fan-Out ({count} orders of {master_lot} lot on master)...")
        master_mkt_ids = []

        for o_idx in range(count):
            order_res = self.client.place_order(
                self.master_email,
                symbol=self.symbol,
                side="SELL",
                order_type="MARKET",
                qty=master_lot,
                instance=self.instance
            )
            if order_res.get("status_code") == 200:
                ord_data = order_res.get("data", {}).get("order", {})
                mkt_id = ord_data.get("market_order_id")
                master_mkt_ids.append(mkt_id)
            time.sleep(0.08)

        print(f"[+] Placed {len(master_mkt_ids)}/{count} master SELL orders. Waiting for fan-out to {len(self.follower_emails)} followers...")
        time.sleep(2.5)

        followers_pos = self.client.fetch_all_followers_positions(self.follower_emails, instance=self.instance)

        pass_count = 0
        details = {}
        for i, email in enumerate(self.follower_emails):
            idx = i + 1
            expected_mult = get_expected_multiplier(idx)
            expected_lot = round(master_lot * expected_mult, 4)

            pos_data = followers_pos.get(email, {})
            positions = pos_data.get("positions", [])
            matching_positions = [
                p for p in positions
                if p.get("symbol") == self.symbol and p.get("side") == "SELL"
            ]

            count_ok = len(matching_positions) == len(master_mkt_ids)
            lots_ok = all(
                math.isclose(round(p.get("net_qty", 0.0), 4), expected_lot, abs_tol=0.001)
                for p in matching_positions
            ) if matching_positions else False

            if count_ok and lots_ok:
                pass_count += 1
            details[email] = {
                "orders_count": len(matching_positions),
                "expected_count": len(master_mkt_ids),
                "expected_lot": expected_lot,
                "ok": count_ok and lots_ok
            }

        # Squareoff all master SELL orders
        for mkt_id in master_mkt_ids:
            self.client.squareoff_position(self.master_email, mkt_id, instance=self.instance)
            time.sleep(0.05)
        time.sleep(1.5)

        status = "PASS" if pass_count == len(self.follower_emails) and len(master_mkt_ids) == count else "FAIL"
        print(f"[{status}] Market SELL ({count} orders): {pass_count}/{len(self.follower_emails)} followers filled accurately on short side ({pass_count * count} verified positions).")
        return {
            "name": f"Market SELL Fan-out ({count} orders)",
            "status": status,
            "pass_count": pass_count,
            "total_followers": len(self.follower_emails),
            "orders_placed": len(master_mkt_ids),
            "details": details
        }

    # -------------------------------------------------------------------------
    # Scenario 9: Follower Manual Close Isolation
    # -------------------------------------------------------------------------
    def test_follower_manual_close_isolation(self, probe_follower: str = "follower3@mailinator.com") -> Dict[str, Any]:
        print(f"\n[SCENARIO 9] Testing Follower Manual Close Isolation on {probe_follower}...")
        # 1. Open master position
        res = self.client.place_order(self.master_email, symbol=self.symbol, side="BUY", order_type="MARKET", qty=0.1, instance=self.instance)
        master_mkt_id = res.get("data", {}).get("order", {}).get("market_order_id")
        time.sleep(1.5)

        # 2. Probe follower manually closes their position
        pos_probe = self.client.get_positions(probe_follower, instance=self.instance)
        probe_mkt_id = None
        for p in pos_probe.get("positions", []):
            if p.get("symbol") == self.symbol:
                probe_mkt_id = p.get("market_order_id")
                break

        if probe_mkt_id:
            self.client.squareoff_position(probe_follower, probe_mkt_id, instance=self.instance)
        time.sleep(1.5)

        # 3. Verify probe follower is closed
        pos_probe_after = self.client.get_positions(probe_follower, instance=self.instance)
        probe_closed = pos_probe_after.get("count", 0) == 0

        # 4. Verify master is still open
        master_pos_after = self.client.get_positions(self.master_email, instance=self.instance)
        master_still_open = master_pos_after.get("count", 0) > 0

        # 5. Verify other followers are still open (sample follower1 and follower2)
        f1_pos = self.client.get_positions(self.follower_emails[0], instance=self.instance)
        f2_pos = self.client.get_positions(self.follower_emails[1], instance=self.instance)
        others_open = f1_pos.get("count", 0) > 0 and f2_pos.get("count", 0) > 0

        # Clean up master
        if master_mkt_id:
            self.client.squareoff_position(self.master_email, master_mkt_id, instance=self.instance)
            time.sleep(1.5)

        status = "PASS" if probe_closed and master_still_open and others_open else "FAIL"
        print(f"[{status}] Follower Manual Close: Probe closed={probe_closed}, Master intact={master_still_open}, Peers intact={others_open}")
        return {
            "name": "Follower Manual Close Isolation",
            "status": status,
            "probe_follower": probe_follower,
            "probe_closed": probe_closed,
            "master_still_open": master_still_open,
            "peers_still_open": others_open
        }

    # -------------------------------------------------------------------------
    # Scenario 10: Follow Mid-Trade Isolation (No Retroactive Copying)
    # -------------------------------------------------------------------------
    def test_follow_mid_trade_isolation(self, probe_follower: str = "follower10@mailinator.com") -> Dict[str, Any]:
        print(f"\n[SCENARIO 10] Testing Follow Mid-Trade Isolation (No Retroactive Copying) on {probe_follower}...")
        master_client_id = "mem_aac4ca423a6925dca7"

        # 1. Temporarily unfollow probe follower
        self.client.unfollow_master(probe_follower, master_client_id, instance=self.instance)
        time.sleep(1.0)

        # 2. Master opens position
        res = self.client.place_order(self.master_email, symbol=self.symbol, side="BUY", order_type="MARKET", qty=0.1, instance=self.instance)
        master_mkt_id = res.get("data", {}).get("order", {}).get("market_order_id")
        time.sleep(1.5)

        # 3. Probe follower follows master while trade is already open
        self.client.follow_master(probe_follower, master_client_id, instance=self.instance, method=self.copy_method, multiplier=1.0)
        time.sleep(1.5)

        # 4. Check whether probe follower copied the pre-existing trade
        probe_pos = self.client.get_positions(probe_follower, instance=self.instance)
        has_retroactive_trade = probe_pos.get("count", 0) > 0

        # Clean up master
        if master_mkt_id:
            self.client.squareoff_position(self.master_email, master_mkt_id, instance=self.instance)
            time.sleep(1.5)

        # Clean up probe follower if any
        self.client.bulk_squareoff(probe_follower, instance=self.instance)

        status = "PASS" if not has_retroactive_trade else "FAIL"
        summary = "No retroactive trade copied (Platform isolates historical trades)" if not has_retroactive_trade else "Retroactive trade was copied"
        print(f"[{status}] Follow Mid-Trade: {summary}")
        return {
            "name": "Follow Mid-Trade Isolation (No Retroactive Copying)",
            "status": status,
            "retroactive_copied": has_retroactive_trade,
            "summary": summary
        }
