"""Evidence-driven terminal MAM test suite for three authorized test accounts.

Real Hedging only. The password is read from TERMINAL_MAM_PASSWORD and is never
written to evidence. All API traces omit Authorization headers.
"""
import argparse
import concurrent.futures as futures
import gzip
import json
import math
import os
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "terminal_mam_retest_20261121"
RUN.mkdir(parents=True, exist_ok=True)

# Patch the previously validated MAM runner to the terminal test deployment and
# the three accounts explicitly authorized by the user.
sys.path.insert(0, str(ROOT / "scripts"))
import qa_mam_live as live

BASE_URL = "https://terminal.blacktrader.com/test"
MASTER_EMAIL = "mamhm@mailinator.com"
FOLLOWERS = ["mamhf1@mailinator.com", "mamhf2@mailinator.com"]
ACCOUNTS = [MASTER_EMAIL] + FOLLOWERS
MASTER_ID = "mem_6cf38c1f751cbd1699"
SYMBOL = "BLACK:BTCUSD"

live.BASE_URL = BASE_URL
live.MASTER_EMAIL = MASTER_EMAIL
live.FOLLOWERS = FOLLOWERS
live.ACCOUNTS = ACCOUNTS
live.MASTER_ID = MASTER_ID
live.SYMBOL = SYMBOL
live.OUT = RUN

import qa_mam_additional as additional

additional.OUT = RUN
additional.MASTER_EMAIL = MASTER_EMAIL
additional.FOLLOWERS = FOLLOWERS
additional.ACCOUNTS = ACCOUNTS
additional.MASTER_ID = MASTER_ID
additional.SYMBOL = SYMBOL


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class TerminalMAMQA(additional.DeepQA):
    def __init__(self):
        super().__init__()
        self.password = os.environ.get("TERMINAL_MAM_PASSWORD", "")
        if not self.password:
            raise RuntimeError("TERMINAL_MAM_PASSWORD is required")
        self.baseline_snapshot = None

    def login(self, email):
        r = requests.post(
            BASE_URL + "/v1/oms/_auth/login",
            json={"email": email, "password": self.password},
            timeout=20,
        )
        try:
            body = r.json()
        except ValueError:
            body = {}
        token = body.get("token")
        if r.status_code != 200 or body.get("success") is not True or not token:
            raise RuntimeError(f"Terminal login failed for {email}: HTTP {r.status_code}")
        self.tokens[email] = token
        self.trace({
            "case": self.active_case,
            "time": utc_now(),
            "mechanism": "terminal OMS authentication",
            "email": email,
            "http": r.status_code,
            "success": True,
            "member_id": (body.get("member") or {}).get("member_id"),
        })

    def authenticate(self):
        with futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(self.login, ACCOUNTS))
        info = self.read(MASTER_EMAIL, "info")
        if info.get("slug") != "real" or info.get("mode") != "hedging":
            raise RuntimeError("Terminal master is not on Real Hedging: " + str(info))
        print("Authenticated 3 scoped accounts; confirmed Real Hedging.", flush=True)

    def smoke(self):
        def market(side):
            opened = self.place(side, .02)
            if opened["http"] != 200 or opened["body"].get("success") is not True:
                return False, {"placement": opened}
            fleet = self.wait_fleet(1)
            errors = {
                email: row["positions"] for email, row in fleet.items()
                if row["count"] != 1
                or row["positions"][0]["symbol"] != SYMBOL
                or row["positions"][0]["side"] != side
                or abs(row["positions"][0]["net_qty"] - .02) > 1e-8
            }
            order_id = self.order_id(opened)
            closed = self.close(MASTER_EMAIL, order_id)
            remaining = self.flat()
            return not errors and not remaining and closed["http"] == 200, {
                "master_order_id": order_id,
                "accounts_checked": len(ACCOUNTS),
                "incorrect_positions": errors,
                "remaining_after_master_close": remaining,
                "close": closed,
            }

        for side in ("BUY", "SELL"):
            self.check(
                f"TERM-MARKET-{side}",
                f"BLACK BTCUSD {side} copies from one master to both followers and closes cleanly",
                lambda side=side: market(side),
            )

    def preflight(self):
        fleet = self.fleet()
        links = dict(zip(ACCOUNTS, self.pool.map(self.links, ACCOUNTS)))
        orders = dict(zip(ACCOUNTS, self.pool.map(lambda e: self.read(e, "orders"), ACCOUNTS)))
        info = dict(zip(ACCOUNTS, self.pool.map(lambda e: self.read(e, "info"), ACCOUNTS)))
        self.baseline_snapshot = {
            "recorded_at": utc_now(),
            "positions": fleet,
            "relationships": links,
            "orders": orders,
            "instance_info": info,
        }
        (RUN / "baseline_snapshot.json").write_text(
            json.dumps(self.baseline_snapshot, indent=2), encoding="utf-8"
        )

        def auth_instance():
            errors = {
                email: row for email, row in info.items()
                if row.get("slug") != "real" or row.get("mode") != "hedging"
            }
            return not errors, {
                "accounts_authenticated": len(self.tokens),
                "instance_errors": errors,
                "expected": "All three accounts authenticate and report real/hedging.",
            }

        self.check("TERM-AUTH-001", "Authenticate master and both followers on Real Hedging", auth_instance)

        def clean_start():
            working = {
                email: [o for o in row["orders"] if o.get("state") in ("PENDING", "OPEN", "NEW")]
                for email, row in orders.items()
            }
            working = {email: rows for email, rows in working.items() if rows}
            open_positions = {email: row["positions"] for email, row in fleet.items() if row["count"]}
            return not working and not open_positions, {
                "open_positions": open_positions,
                "working_orders": working,
                "funds": {email: row["funds"] for email, row in fleet.items()},
            }

        self.check("TERM-STATE-001", "Verify all scoped accounts begin flat with no working orders", clean_start)

        def relationship_roles():
            master = links[MASTER_EMAIL]
            active_master = [r for r in master["followers"] if r["status"] == "active"]
            follower_errors = {}
            for email in FOLLOWERS:
                active = [
                    r for r in links[email]["following"]
                    if r["status"] == "active" and r["master_client_id"] == MASTER_ID
                ]
                if len(active) != 1:
                    follower_errors[email] = active
            good = master.get("is_master") is True and len(active_master) == 2 and not follower_errors
            return good, {
                "master_configuration": master.get("master"),
                "active_master_followers": active_master,
                "follower_relationship_errors": follower_errors,
            }

        self.check("TERM-MAM-001", "Verify one manager and exactly two active follower relationships", relationship_roles)

        def hwm_consistency():
            observations = {}
            errors = {}
            for email in FOLLOWERS:
                link = next(
                    r for r in links[email]["following"]
                    if r["status"] == "active" and r["master_client_id"] == MASTER_ID
                )
                account_start = fleet[email]["funds"]["starting_balance"]
                observations[email] = {
                    "mam_benchmark": link["starting_balance"],
                    "account_starting_balance": account_start,
                    "current_balance": fleet[email]["funds"]["balance"],
                    "joined_at": link["joined_at"],
                }
                if not math.isfinite(float(link["starting_balance"])) or float(link["starting_balance"]) <= 0:
                    errors[email] = observations[email]
            return not errors, {
                "observations": observations,
                "invalid_benchmarks": errors,
                "expected": "Each active relationship exposes a finite positive benchmark. Preservation is tested separately across trading and active term edits.",
            }

        self.check("TERM-MAM-HWM-BASELINE", "Record valid follower performance benchmarks and join metadata", hwm_consistency)

    def hwm_term_update(self):
        self.cleanup()

        def case():
            before_links = {
                email: next(
                    r for r in self.links(email)["following"]
                    if r["status"] == "active" and r["master_client_id"] == MASTER_ID
                )
                for email in FOLLOWERS
            }
            before_funds = {email: self.positions(email)["funds"] for email in FOLLOWERS}
            opened = self.require_open(qty=.02)
            self.wait_fleet(1)
            self.close(MASTER_EMAIL, self.order_id(opened))
            self.flat()
            after_trade_links = {
                email: next(
                    r for r in self.links(email)["following"]
                    if r["status"] == "active" and r["master_client_id"] == MASTER_ID
                )
                for email in FOLLOWERS
            }
            after_trade_funds = {email: self.positions(email)["funds"] for email in FOLLOWERS}
            trade_changed_cash = {
                email: after_trade_funds[email]["balance"] - before_funds[email]["balance"]
                for email in FOLLOWERS
            }
            trade_preservation_errors = {
                email: {
                    "before": before_links[email]["starting_balance"],
                    "after_trade": after_trade_links[email]["starting_balance"],
                }
                for email in FOLLOWERS
                if abs(after_trade_links[email]["starting_balance"] - before_links[email]["starting_balance"]) > .01
            }

            updates = [
                self.api(FOLLOWERS[0], "POST", "mam/follow", {
                    "master_client_id": MASTER_ID, "method": "multiplier", "multiplier": 2,
                }),
                self.api(FOLLOWERS[1], "POST", "mam/follow", {
                    "master_client_id": MASTER_ID, "method": "multiplier", "multiplier": .5,
                }),
            ]
            after_edit_links = {
                email: next(
                    r for r in self.links(email)["following"]
                    if r["status"] == "active" and r["master_client_id"] == MASTER_ID
                )
                for email in FOLLOWERS
            }
            edit_errors = {
                email: {
                    "before_active_edit": after_trade_links[email]["starting_balance"],
                    "after_active_edit": after_edit_links[email]["starting_balance"],
                    "current_balance": after_trade_funds[email]["balance"],
                }
                for email in FOLLOWERS
                if abs(after_edit_links[email]["starting_balance"] - after_trade_links[email]["starting_balance"]) > .01
            }
            restore = self.configure(FOLLOWERS, multiplier=1)
            restored_links = {
                email: next(
                    r for r in self.links(email)["following"]
                    if r["status"] == "active" and r["master_client_id"] == MASTER_ID
                )
                for email in FOLLOWERS
            }
            good = (
                all(r["http"] == 200 and r["body"].get("success") for r in updates)
                and not trade_preservation_errors
                and not edit_errors
            )
            return good, {
                "before_links": before_links,
                "before_funds": before_funds,
                "trade_cash_deltas": trade_changed_cash,
                "after_trade_links": after_trade_links,
                "trade_preservation_errors": trade_preservation_errors,
                "term_update_responses": updates,
                "after_active_term_edit_links": after_edit_links,
                "active_edit_benchmark_errors": edit_errors,
                "restore_responses": restore,
                "restored_links": restored_links,
                "expected": "Trading PnL and an active multiplier edit must not reset the relationship HWM; only a new/reactivated relationship or non-trading cash adjustment may change it.",
            }

        self.check(
            "TERM-MAM-HWM-TERMS-001",
            "Active multiplier changes preserve each follower's performance benchmark",
            case,
        )
        self.cleanup()

    def accounting(self):
        self.cleanup()

        def reconcile():
            before = self.fleet()
            opened = self.require_open(qty=.02)
            open_state = self.wait_fleet(1)
            self.close(MASTER_EMAIL, self.order_id(opened))
            self.flat()
            after = self.fleet()
            records = {}
            errors = {}
            master_receipts = 0.0
            for email in ACCOUNTS:
                position_id = open_state[email]["positions"][0]["position_id"]
                history = [
                    h for h in self.read(email, "history")["history"]
                    if h.get("position_id") == position_id
                ]
                account = self.read(email, "account")["account"]
                terms = account["brokerage"]
                if terms.get("mode") == "none":
                    brokerage = 0.0
                elif terms.get("mode") == "per_lot":
                    rate = float(terms.get("rates", {}).get("default", 0))
                    brokerage = max(float(terms.get("min", 0)), rate * history[0]["qty"]) if history else 0
                    if float(terms.get("max") or 0) > 0:
                        brokerage = min(brokerage, float(terms["max"]))
                else:
                    raise RuntimeError("Unsupported brokerage oracle: " + str(terms))
                shares = []
                if email != MASTER_EMAIL and history:
                    ids = {h["history_id"] for h in history}
                    shares = [
                        s for s in self.read(email, "mam/shares")["shares"]
                        if s.get("trade_id") in ids and s.get("instance") == "real"
                    ]
                share_paid = sum(float(s["master_share"]) for s in shares)
                master_receipts += share_paid
                records[email] = {
                    "history": history,
                    "brokerage_terms": terms,
                    "brokerage": brokerage,
                    "shares": shares,
                    "share_paid": share_paid,
                    "actual_balance_delta": after[email]["funds"]["balance"] - before[email]["funds"]["balance"],
                }
                if len(history) != 1:
                    errors[email] = {"history_count": len(history)}
                    continue
                h = history[0]
                expected_price_pnl = (h["exit_price"] - h["entry_price"]) * h["qty"] * (1 if h["side"] == "BUY" else -1)
                records[email]["expected_price_pnl"] = expected_price_pnl
                if abs(expected_price_pnl - h["realized_pnl"]) > .011:
                    errors[email] = {"pnl_mismatch": records[email]}

            for email, record in records.items():
                if len(record["history"]) != 1:
                    continue
                expected_delta = (
                    record["history"][0]["realized_pnl"]
                    - record["brokerage"]
                    - record["share_paid"]
                    + (master_receipts if email == MASTER_EMAIL else 0)
                )
                record["expected_balance_delta"] = expected_delta
                if abs(record["actual_balance_delta"] - expected_delta) > .011:
                    errors[email] = {"balance_reconciliation": record}
            return not errors, {
                "errors": errors,
                "records": records,
                "master_fee_receipts": master_receipts,
                "expected": "Price PnL, zero brokerage, MAM shares and resulting balance deltas reconcile for all three accounts.",
            }

        self.check("TERM-ACCOUNTING-001", "Reconcile copied-trade PnL, zero brokerage, shares and balances", reconcile)
        self.cleanup()

    @staticmethod
    def lot_round(value):
        return max(.01, math.floor(value / .01 + .5 + 1e-9) * .01)

    def allocation_methods(self):
        self.cleanup()

        def multiplier_case():
            self.configure([FOLLOWERS[0]], multiplier=.5)
            self.configure([FOLLOWERS[1]], multiplier=2)
            opened = self.require_open(qty=.02)
            fleet = self.wait_fleet(1)
            expected = {MASTER_EMAIL: .02, FOLLOWERS[0]: .01, FOLLOWERS[1]: .04}
            errors = {
                email: {"expected": expected[email], "actual": row["positions"]}
                for email, row in fleet.items()
                if row["count"] != 1 or abs(row["positions"][0]["net_qty"] - expected[email]) > 1e-8
            }
            self.close(MASTER_EMAIL, self.order_id(opened))
            remaining = self.flat()
            self.configure(FOLLOWERS, multiplier=1)
            return not errors and not remaining, {
                "expected_quantities": expected,
                "actual_quantities": {
                    email: [p["net_qty"] for p in row["positions"]] for email, row in fleet.items()
                },
                "errors": errors,
                "orphans": remaining,
            }

        self.check("TERM-ALLOC-001", "Multiplier allocation copies 0.5x and 2.0x quantities", multiplier_case)

        for method in ("balance", "equity"):
            def proportional(method=method):
                self.configure(FOLLOWERS, method=method, multiplier=1)
                before = self.fleet()
                opened = self.require_open(qty=.04)
                after = self.wait_fleet(1)
                expected = {MASTER_EMAIL: .04}
                for email in FOLLOWERS:
                    ratio = before[email]["funds"][method] / before[MASTER_EMAIL]["funds"][method]
                    expected[email] = self.lot_round(.04 * ratio)
                errors = {
                    email: {"expected": expected[email], "actual": row["positions"]}
                    for email, row in after.items()
                    if row["count"] != 1 or abs(row["positions"][0]["net_qty"] - expected[email]) > 1e-8
                }
                self.close(MASTER_EMAIL, self.order_id(opened))
                remaining = self.flat()
                self.configure(FOLLOWERS, multiplier=1)
                return not errors and not remaining, {
                    "method": method,
                    "funds_snapshot": {email: row["funds"] for email, row in before.items()},
                    "expected_quantities": expected,
                    "actual_quantities": {
                        email: [p["net_qty"] for p in row["positions"]] for email, row in after.items()
                    },
                    "errors": errors,
                    "orphans": remaining,
                }

            self.check(
                f"TERM-ALLOC-{method.upper()}",
                f"{method.title()} proportional allocation sizes both followers from committed funds",
                proportional,
            )
        self.cleanup()

    def lifecycle_core(self):
        self.cleanup()
        self.configure(FOLLOWERS, multiplier=1)

        def partial_close():
            opened = self.require_open(qty=.04)
            self.wait_fleet(1)
            order_id = self.order_id(opened)
            reduced = self.api(MASTER_EMAIL, "POST", f"positions/{order_id}/reduce", {"qty": .02})
            time.sleep(1)
            fleet = self.fleet()
            errors = {
                email: row["positions"] for email, row in fleet.items()
                if row["count"] != 1 or abs(row["positions"][0]["net_qty"] - .02) > 1e-8
            }
            self.close(MASTER_EMAIL, order_id)
            remaining = self.flat()
            return reduced["http"] == 200 and not errors and not remaining, {
                "reduce_response": reduced,
                "quantity_errors": errors,
                "orphans": remaining,
            }

        self.check("TERM-LIFE-001", "Master partial close reduces both copied follower positions", partial_close)

        def hedge():
            buy = self.require_open("BUY", qty=.01)
            sell = self.require_open("SELL", qty=.01)
            both = self.wait_fleet(2)
            errors = {
                email: row["positions"] for email, row in both.items()
                if row["count"] != 2 or sorted(p["side"] for p in row["positions"]) != ["BUY", "SELL"]
            }
            self.close(MASTER_EMAIL, self.order_id(buy))
            time.sleep(.5)
            one = self.fleet()
            selective_errors = {
                email: row["positions"] for email, row in one.items()
                if row["count"] != 1 or row["positions"][0]["side"] != "SELL"
            }
            self.close(MASTER_EMAIL, self.order_id(sell))
            remaining = self.flat()
            return not errors and not selective_errors and not remaining, {
                "hedge_errors": errors,
                "selective_close_errors": selective_errors,
                "orphans": remaining,
            }

        self.check("TERM-LIFE-002", "Opposite hedged positions coexist and close independently", hedge)

        def follower_manual_close():
            opened = self.require_open(qty=.02)
            fleet = self.wait_fleet(1)
            follower_id = fleet[FOLLOWERS[0]]["positions"][0]["market_order_id"]
            closed = self.close(FOLLOWERS[0], follower_id)
            time.sleep(.5)
            after = self.fleet()
            errors = {
                email: row["positions"] for email, row in after.items()
                if row["count"] != (0 if email == FOLLOWERS[0] else 1)
            }
            self.close(MASTER_EMAIL, self.order_id(opened))
            remaining = self.flat()
            return closed["http"] == 200 and not errors and not remaining, {
                "follower_close": closed,
                "isolation_errors": errors,
                "orphans": remaining,
            }

        self.check("TERM-LIFE-003", "Follower manual close does not close master or other follower", follower_manual_close)
        self.cleanup()

    def duplicate_delivery(self):
        self.cleanup()

        def run(concurrent):
            request_id = "terminal_retry_" + uuid.uuid4().hex[:16]
            group_id = "terminal_group_" + uuid.uuid4().hex[:16]
            payload = {
                "symbol": SYMBOL,
                "side": "BUY",
                "qty": .01,
                "type": "MARKET",
                "request_id": request_id,
                "group_id": group_id,
                "source": "api",
                "tag": "TERMINAL_MAM_QA",
            }
            if concurrent:
                responses = self.race_call([
                    lambda: self.api(MASTER_EMAIL, "POST", "orders", payload),
                    lambda: self.api(MASTER_EMAIL, "POST", "orders", payload),
                ])
            else:
                responses = [
                    self.api(MASTER_EMAIL, "POST", "orders", payload),
                    self.api(MASTER_EMAIL, "POST", "orders", payload),
                ]
            time.sleep(1)
            fleet = self.fleet()
            matching = {
                email: [p for p in row["positions"] if p.get("group_id") == group_id]
                for email, row in fleet.items()
            }
            accepted = [r for r in responses if r["http"] == 200 and r["body"].get("success")]
            incorrect = {email: rows for email, rows in matching.items() if len(rows) != 1}
            self.cleanup()
            return len(accepted) == 1 and not incorrect, {
                "request_id": request_id,
                "group_id": group_id,
                "responses": responses,
                "accepted_requests": len(accepted),
                "position_counts": {email: len(rows) for email, rows in matching.items()},
                "incorrect_accounts": incorrect,
                "expected": "A stable request_id/group_id must create one master execution and one child per follower.",
            }

        self.check(
            "TERM-RACE-IDEMPOTENCY-CONCURRENT",
            "Concurrent retry of an identical master request cannot duplicate exposure",
            lambda: run(True),
        )
        self.check(
            "TERM-RACE-IDEMPOTENCY-SEQUENTIAL",
            "Sequential retry of an identical master request cannot duplicate exposure",
            lambda: run(False),
        )
        self.cleanup()

    def rapid_round_trips(self):
        self.cleanup()
        for repeat in range(3):
            def case(repeat=repeat):
                def round_trip():
                    opened = self.place(qty=.01)
                    if opened["http"] != 200 or not self.order_id(opened):
                        return {"open": opened, "close": None}
                    return {"open": opened, "close": self.close(MASTER_EMAIL, self.order_id(opened))}

                attempts = self.race_call([round_trip for _ in range(5)])
                time.sleep(1)
                remaining = {email: row["positions"] for email, row in self.fleet().items() if row["count"]}
                working = {}
                for email in ACCOUNTS:
                    rows = [
                        o for o in self.read(email, "orders")["orders"]
                        if o.get("state") in ("PENDING", "OPEN", "NEW")
                    ]
                    if rows:
                        working[email] = rows
                accepted = [a for a in attempts if a["open"]["http"] == 200 and a["open"]["body"].get("success")]
                closed = [a for a in accepted if a["close"] and a["close"]["http"] == 200]
                if remaining or working:
                    self.cleanup()
                return len(accepted) == len(closed) and not remaining and not working, {
                    "attempts": attempts,
                    "accepted": len(accepted),
                    "closed": len(closed),
                    "orphan_positions": remaining,
                    "working_orders": working,
                }

            self.check(
                f"TERM-RACE-RAPID-ROUNDTRIP-{repeat + 1}",
                "Five simultaneous open/immediate-close sequences leave no late follower copies",
                case,
            )
            self.cleanup()

    def fee_hwm_live(self):
        self.cleanup()
        email = FOLLOWERS[0]
        self.api(email, "POST", "mam/unfollow", {"master_client_id": MASTER_ID})
        self.configure([email], multiplier=1)
        self.configure([FOLLOWERS[1]], multiplier=1)

        def case():
            link = next(
                r for r in self.links(email)["following"]
                if r["status"] == "active" and r["master_client_id"] == MASTER_ID
            )
            starting = self.positions(email)["funds"]["balance"]
            if abs(link["starting_balance"] - starting) > .01:
                raise RuntimeError("Fresh relationship benchmark did not equal current balance")

            opened = [
                self.require_open("BUY", qty=.01),
                self.require_open("SELL", qty=.01),
                self.require_open("BUY", qty=.01),
                self.require_open("SELL", qty=.01),
            ]
            groups = {r["body"]["position"]["group_id"]: r for r in opened}
            self.wait_fleet(4)
            observations = []
            closed_groups = set()
            deadline = time.monotonic() + 120
            while len(observations) < 2 and time.monotonic() < deadline:
                positions = self.positions(email)["positions"]
                eligible = [
                    p for p in positions
                    if p["group_id"] not in closed_groups and p["unrealized_pnl"] > .20
                ]
                if eligible:
                    chosen = max(eligible, key=lambda p: p["unrealized_pnl"])
                    group = chosen["group_id"]
                    before = self.positions(email)["funds"]
                    result = self.close(MASTER_EMAIL, self.order_id(groups[group]))
                    time.sleep(.5)
                    history = [
                        h for h in self.read(email, "history")["history"]
                        if h.get("position_id") == chosen["position_id"]
                    ]
                    ids = {h["history_id"] for h in history}
                    shares = [
                        s for s in self.read(email, "mam/shares")["shares"]
                        if s.get("trade_id") in ids and s.get("instance") == "real"
                    ]
                    after = self.positions(email)["funds"]
                    observations.append({
                        "before": before,
                        "after": after,
                        "chosen_position": chosen,
                        "close": result,
                        "history": history,
                        "shares": shares,
                    })
                    closed_groups.add(group)
                else:
                    time.sleep(1)

            for group, response in groups.items():
                if group not in closed_groups:
                    self.close(MASTER_EMAIL, self.order_id(response))
            self.flat()
            if len(observations) < 2:
                raise RuntimeError("Market did not provide two profitable closes within 120 seconds")

            first, second = observations
            errors = []
            if len(first["shares"]) != 1 or first["shares"][0]["above_hwm"] is not False or abs(first["shares"][0]["master_share"]) > .011:
                errors.append("First profitable benchmark crossing did not apply the confirmed zero-share rule")
            if len(second["shares"]) != 1 or second["shares"][0]["above_hwm"] is not True:
                errors.append("Second profitable close above benchmark was not marked above HWM")
            elif abs(second["shares"][0]["master_share"] - round(second["shares"][0]["order_pnl"] * .5, 2)) > .011:
                errors.append("Second manager share was not 50 percent of rounded trade PnL")
            for obs in observations:
                if len(obs["shares"]) == 1:
                    share = obs["shares"][0]
                    if abs(share["master_share"] + share["follower_share"] - round(share["order_pnl"], 2)) > .011:
                        errors.append("Manager and follower share did not conserve rounded trade PnL")
            return not errors, {
                "fresh_relationship": link,
                "observations": observations,
                "errors": errors,
                "confirmed_rule": "First profit crossing benchmark: zero manager share. Later profit starting above benchmark: configured 50 percent share.",
            }

        self.check("TERM-FEE-HWM-001", "Live first-profit and subsequent above-HWM profit sharing", case)
        self.cleanup()
        self.configure(FOLLOWERS, multiplier=1)

    def web_route_checks(self):
        def redirect():
            r = requests.get(BASE_URL, allow_redirects=False, timeout=20)
            location = r.headers.get("location", "")
            hsts = r.headers.get("strict-transport-security")
            good = r.status_code in (301, 302, 307, 308) and location.startswith("https://")
            return good, {
                "http": r.status_code,
                "location": location,
                "strict_transport_security": hsts,
                "expected": "An HTTPS entry URL must not redirect users to an HTTP URL.",
            }

        self.check("TERM-WEB-HTTPS-001", "Terminal HTTPS entry route preserves HTTPS during redirect", redirect)

        def invalid_login():
            r = requests.post(
                BASE_URL + "/v1/oms/_auth/login",
                json={"email": MASTER_EMAIL, "password": "definitely-wrong-password"},
                timeout=20,
            )
            try:
                body = r.json()
            except ValueError:
                body = {"text": r.text[:300]}
            return r.status_code in (400, 401, 403) and not body.get("token"), {
                "http": r.status_code,
                "response": body,
            }

        self.check("TERM-AUTH-NEG-001", "Invalid password is rejected without issuing a token", invalid_login)

    def final_state(self):
        self.cleanup()
        self.configure(FOLLOWERS, multiplier=1)
        fleet = self.fleet()
        links = dict(zip(ACCOUNTS, self.pool.map(self.links, ACCOUNTS)))
        working = {}
        for email in ACCOUNTS:
            rows = [
                o for o in self.read(email, "orders")["orders"]
                if o.get("state") in ("PENDING", "OPEN", "NEW")
            ]
            if rows:
                working[email] = rows
        relationship_errors = {}
        for email in FOLLOWERS:
            active = [
                r for r in links[email]["following"]
                if r["master_client_id"] == MASTER_ID and r["status"] == "active"
            ]
            if len(active) != 1 or active[0].get("method") != "multiplier" or active[0].get("multiplier") != 1:
                relationship_errors[email] = active
        position_errors = {email: row["positions"] for email, row in fleet.items() if row["count"]}
        snapshot = {
            "recorded_at": utc_now(),
            "positions": fleet,
            "relationships": links,
            "working_orders": working,
        }
        (RUN / "final_state.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        self.check(
            "TERM-FINAL-001",
            "Final cleanup leaves all accounts flat and both followers active at multiplier one",
            lambda: (
                not working and not relationship_errors and not position_errors,
                {
                    "working_orders": working,
                    "relationship_errors": relationship_errors,
                    "position_errors": position_errors,
                    "final_funds": {email: row["funds"] for email, row in fleet.items()},
                    "snapshot": "final_state.json",
                },
            ),
        )

    def write_report(self):
        counts = Counter(row["status"] for row in self.results)
        defects = {
            "TERM-MAM-HWM-TERMS-001": ("Critical", "TERM-MAM-001"),
            "TERM-RACE-IDEMPOTENCY-CONCURRENT": ("Critical", "TERM-MAM-002"),
            "TERM-RACE-IDEMPOTENCY-SEQUENTIAL": ("Critical", "TERM-MAM-002"),
            "TERM-WEB-HTTPS-001": ("High", "TERM-WEB-001"),
        }

        def esc(value):
            return str(value).replace("|", "\\|").replace("\n", "<br>")

        def actual(row):
            details = row["details"]
            if "error" in details:
                return details["error"]
            keys = [
                "errors", "mismatches", "incorrect_accounts", "position_counts", "accepted_requests",
                "open_positions", "working_orders", "quantity_errors", "orphan_positions", "orphans",
                "relationship_errors", "position_errors", "accounts_authenticated", "http", "location",
            ]
            selected = {key: details[key] for key in keys if key in details}
            if not selected:
                selected = details
            text = json.dumps(selected, ensure_ascii=False, default=str)
            return text[:1600] + ("…" if len(text) > 1600 else "")

        rows = []
        for row in self.results:
            display_id = row["id"]
            display_name = row["name"]
            if display_id.startswith("PENDING-100-FANOUT-"):
                display_id = display_id.replace("PENDING-100-FANOUT-", "TERM-PENDING-FANOUT-")
                display_name = display_name.replace("all followers", "both followers")
            elif display_id == "LIFE-PROTECTION-RETEST":
                display_id = "TERM-LIFE-PROTECTION"
                display_name = "Set and remove SL/TP across the master and both followers"
            elif display_id == "LOAD-FIVE-BURST":
                display_id = "TERM-LOAD-FIVE-BURST"
                display_name = "Five concurrent master entries create ten child positions and close cleanly"
            severity, defect = defects.get(row["id"], ("—", "—")) if row["status"] == "FAIL" else ("—", "—")
            expected = row["details"].get("expected") or row["details"].get("assertion") or row["details"].get("allowed_outcomes") or "The named MAM invariant holds with no orphan, duplicate, unauthorized, or inconsistent state."
            rows.append([
                display_id, display_name,
                "Authorized dedicated terminal accounts; Real Hedging; case-specific state created and cleaned by the runner.",
                "1. Establish the required master/follower state.<br>2. Perform the named operation or concurrent actions.<br>3. Read back positions, orders, history, relationships and shares.<br>4. Verify invariants and clean up.",
                "terminal.blacktrader.com/test; BLACK:BTCUSD; mamhm + mamhf1 + mamhf2",
                expected, actual(row), row["status"], severity, defect,
                f"Executed {row['started_at']}. Evidence: results_{self.run_id}.json and {self.trace_path.name}.",
            ])

        headers = [
            "TC ID", "Test Case Description", "Pre-Conditions", "Test Steps", "Test Data",
            "Expected Result", "Actual Result", "Status", "Severity", "Defect ID", "Remarks",
        ]
        table = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join([":---"] * 7 + [":---:"] * 3 + [":---"]) + " |",
        ]
        table += ["| " + " | ".join(esc(x) for x in row) + " |" for row in rows]
        failed_ids = {row["id"] for row in self.results if row["status"] == "FAIL"}
        defect_lines = []
        if "TERM-MAM-HWM-TERMS-001" in failed_ids:
            defect_lines.append("- **TERM-MAM-001 — Critical:** Editing an active follower's allocation terms reset the performance benchmark to the current balance, allowing HWM manipulation without ending and rejoining the relationship.")
        if failed_ids & {"TERM-RACE-IDEMPOTENCY-CONCURRENT", "TERM-RACE-IDEMPOTENCY-SEQUENTIAL"}:
            defect_lines.append("- **TERM-MAM-002 — Critical:** Identical master request delivery with the same request identity created duplicate master and follower exposure. Concurrent and sequential cases are two reproductions of one defect.")
        if "TERM-WEB-HTTPS-001" in failed_ids:
            defect_lines.append("- **TERM-WEB-001 — High:** The HTTPS terminal entry route redirected to an HTTP URL.")
        if not defect_lines:
            defect_lines.append("- No confirmed defect was produced by the executed scope.")

        report = [
            "# Terminal MAM End-to-End QA Execution Report",
            "",
            f"**Environment:** `{BASE_URL}`  ",
            f"**Execution date:** {utc_now()}  ",
            "**Scope:** Real Hedging only; one master and two dedicated followers; functional, accounting, validation and concurrency flows.",
            "",
            "## Execution Summary",
            "",
            f"- Total executed checks: **{len(self.results)}**",
            f"- PASS: **{counts.get('PASS', 0)}**",
            f"- FAIL: **{counts.get('FAIL', 0)}**",
            f"- BLOCKED: **{counts.get('BLOCKED', 0)}**",
            "- A repeated reproduction of one root cause is not counted as a separate defect.",
            "- No production sign-off is issued when any Critical or High defect remains open.",
            "",
            "## Confirmed Defects",
            "",
            *defect_lines,
            "",
            "## Test Case Execution Table",
            "",
            *table,
            "",
            "## Coverage Limitations",
            "",
            "- Admin balance changes were not executed because admin credentials were not supplied for this terminal environment.",
            "- Database locks, process failover, broker fault injection, time-controlled monthly settlement and multi-node recovery cannot be proven through member APIs alone.",
            "- Market-dependent fee cases are BLOCKED when the required profitable price movement is not observed within the bounded test window; they are never converted to PASS.",
            "",
            "## Assertion Corrections",
            "",
            "- The initial baseline-only comparison between relationship HWM and the account's original starting balance was superseded. A relationship may legitimately begin after prior trading. The final suite instead tests that trading PnL and active allocation-term edits do not reset an existing HWM.",
            "- The original accounting helper supported only per-lot brokerage and therefore blocked on this account's valid `none` mode. The final accounting case explicitly treats `none` as zero brokerage and reconciles all three balances.",
            "",
            "## Evidence",
            "",
            f"- Structured results: `reports/terminal_mam_retest_20261121/results_{self.run_id}.json`",
            f"- Redacted HTTP trace: `reports/terminal_mam_retest_20261121/{self.trace_path.name}`",
            "- Baseline snapshot: `reports/terminal_mam_retest_20261121/baseline_snapshot.json`",
            "- Final snapshot: `reports/terminal_mam_retest_20261121/final_state.json`",
            "",
        ]
        path = ROOT / "TERMINAL_MAM_FULL_TEST_REPORT.md"
        path.write_text("\n".join(report), encoding="utf-8")
        return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stages",
        default=(
            "preflight,hwm_term_update,web_route_checks,smoke,allocation_methods,lifecycle_core,quantization,"
            "pending_fanout,boundaries,manual_follower,membership,protection_retest,accounting,"
            "races,more_races,duplicate_delivery,rapid_round_trips,burst,fee_hwm_live,final_state"
        ),
    )
    args = parser.parse_args()
    qa = TerminalMAMQA()
    (RUN / f"runner_source_{qa.run_id}.py").write_bytes(Path(__file__).read_bytes())
    fatal = None
    try:
        qa.authenticate()
        for stage in args.stages.split(","):
            print(f"=== {stage} ===", flush=True)
            getattr(qa, stage)()
    except Exception as exc:
        fatal = exc
        (RUN / f"abort_{qa.run_id}.json").write_text(
            json.dumps({"time": utc_now(), "case": qa.active_case, "error": str(exc)}, indent=2),
            encoding="utf-8",
        )
    finally:
        try:
            qa.cleanup()
            qa.configure(FOLLOWERS, multiplier=1)
        except Exception as cleanup_exc:
            print("FINAL CLEANUP ERROR:", cleanup_exc, flush=True)
        report = qa.write_report()
        qa.pool.shutdown()
        print(json.dumps({
            "report": str(report),
            "results": str(RUN / f"results_{qa.run_id}.json"),
            "trace": str(qa.trace_path),
            "counts": dict(Counter(row["status"] for row in qa.results)),
            "fatal": str(fatal) if fatal else None,
        }, indent=2), flush=True)
    if fatal:
        raise fatal
    return 0


if __name__ == "__main__":
    sys.exit(main())
