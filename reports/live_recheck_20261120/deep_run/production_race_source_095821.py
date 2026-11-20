"""Production-focused MAM race tests for the authorized simulated real-hedging accounts.

The runner records exact HTTP/UI evidence, uses no write retries, and treats an
ambiguous policy outcome as blocked rather than inventing a defect.
"""
import argparse
import concurrent.futures as futures
import json
import math
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_mam_additional import DeepQA
from qa_mam_live import AdminUI, MASTER_EMAIL, MASTER_ID, FOLLOWERS, ACCOUNTS, OUT, SYMBOL, now


class ProductionRaceQA(DeepQA):
    def active_link(self, email):
        return [
            row for row in self.links(email)["following"]
            if row["master_client_id"] == MASTER_ID and row["status"] == "active"
        ]

    def working_orders(self, email):
        return [
            row for row in self.read(email, "orders")["orders"]
            if row.get("state") in ("PENDING", "OPEN", "NEW", "SUBMITTING", "UNKNOWN", "RECONCILING")
        ]

    def relationships(self):
        self.cleanup()
        email = FOLLOWERS[0]

        def repeated_follow():
            self.api(email, "POST", "mam/unfollow", {"master_client_id": MASTER_ID})
            calls = [
                lambda: self.api(email, "POST", "mam/follow", {
                    "master_client_id": MASTER_ID,
                    "method": "multiplier",
                    "multiplier": 1,
                })
                for _ in range(12)
            ]
            responses = self.race_call(calls)
            links = self.active_link(email)
            opened = self.require_open(qty=.02)
            time.sleep(1)
            child = self.positions(email)
            self.close(MASTER_EMAIL, self.order_id(opened))
            remaining = self.flat()
            good = (
                all(row["http"] == 200 and row["body"].get("success") for row in responses)
                and len(links) == 1
                and child["count"] == 1
                and abs(child["positions"][0]["net_qty"] - .02) < 1e-8
                and not remaining
            )
            return good, {
                "responses": responses,
                "active_relationships": links,
                "follower_position": child,
                "orphans": remaining,
                "assertion": "Concurrent replays create one active relationship and one copied child only.",
            }

        self.check(
            "PROD-RACE-FOLLOW-REPLAY",
            "Twelve concurrent follow requests cannot duplicate a relationship or copied order",
            repeated_follow,
        )
        self.cleanup()

        for repeat in range(3):
            def update_during_entry(repeat=repeat):
                self.configure([email], multiplier=1)
                responses = self.race_call([
                    lambda: self.api(email, "POST", "mam/follow", {
                        "master_client_id": MASTER_ID,
                        "method": "multiplier",
                        "multiplier": 2,
                    }),
                    lambda: self.place(qty=.02),
                ])
                update, opened = responses
                if opened["http"] != 200 or not self.order_id(opened):
                    raise RuntimeError("Master entry prerequisite failed: " + str(opened))
                time.sleep(1)
                child = self.positions(email)
                others = self.fleet([MASTER_EMAIL] + FOLLOWERS[1:])
                errors = {
                    account: row["positions"] for account, row in others.items()
                    if row["count"] != 1 or abs(row["positions"][0]["net_qty"] - .02) > 1e-8
                }
                valid_qty = (
                    child["count"] == 1
                    and any(abs(child["positions"][0]["net_qty"] - qty) < 1e-8 for qty in (.02, .04))
                )
                self.close(MASTER_EMAIL, self.order_id(opened))
                remaining = self.flat()
                self.configure([email], multiplier=1)
                return valid_qty and not errors and not remaining and update["http"] == 200, {
                    "responses": responses,
                    "follower_position": child,
                    "other_account_errors": errors,
                    "orphans": remaining,
                    "allowed_outcomes": "Exactly one child sized from either the committed old or new multiplier.",
                }

            self.check(
                f"PROD-RACE-TERMS-ENTRY-{repeat + 1}",
                "Multiplier update racing a master entry produces one coherent child quantity",
                update_during_entry,
            )
            self.cleanup()

        for repeat in range(3):
            def leave_during_close(repeat=repeat):
                self.configure([email], multiplier=1)
                opened = self.require_open(qty=.02)
                fleet = self.wait_fleet(1)
                follower_position_id = fleet[email]["positions"][0]["position_id"]
                responses = self.race_call([
                    lambda: self.api(email, "POST", "mam/unfollow", {"master_client_id": MASTER_ID}),
                    lambda: self.close(MASTER_EMAIL, self.order_id(opened)),
                ])
                remaining = self.flat()
                history = [
                    row for row in self.read(email, "history")["history"]
                    if row.get("position_id") == follower_position_id
                ]
                links = self.active_link(email)
                self.configure([email], multiplier=1)
                good = not remaining and len(history) == 1 and not links
                return good, {
                    "responses": responses,
                    "follower_history": history,
                    "active_relationships_before_restore": links,
                    "orphans": remaining,
                    "assertion": "Leaving during parent close must settle the existing child exactly once and end the relationship.",
                }

            self.check(
                f"PROD-RACE-UNFOLLOW-CLOSE-{repeat + 1}",
                "Follower unfollow racing master close settles the copied position exactly once",
                leave_during_close,
            )
            self.cleanup()

    def request_delivery(self):
        self.cleanup()

        def duplicate_delivery(concurrent):
            request_id = "qa_retry_" + uuid.uuid4().hex[:20]
            group_id = "qa_dup_" + uuid.uuid4().hex[:20]
            payload = {
                "symbol": SYMBOL,
                "side": "BUY",
                "qty": .01,
                "type": "MARKET",
                "request_id": request_id,
                "group_id": group_id,
                "source": "api",
                "tag": "QA_PRODUCTION_RACE",
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
            time.sleep(2)
            fleet = self.fleet()
            matching = {
                email: [row for row in state["positions"] if row.get("group_id") == group_id]
                for email, state in fleet.items()
            }
            duplicate_accounts = {email: rows for email, rows in matching.items() if len(rows) != 1}
            accepted = [row for row in responses if row["http"] == 200 and row["body"].get("success")]
            self.cleanup()
            return len(accepted) == 1 and not duplicate_accounts, {
                "request_id": request_id,
                "group_id": group_id,
                "responses": responses,
                "accepted_requests": len(accepted),
                "matching_position_counts": {email: len(rows) for email, rows in matching.items()},
                "incorrect_accounts": duplicate_accounts,
                "assertion": "MAM-C003 production requirement: one stable request identity must create one master order and one child per follower.",
                "contract_note": "The current standard-order API documentation does not promise request idempotency; this test detects the production requirement gap and resulting duplicate exposure.",
            }

        self.check(
            "PROD-DUPLICATE-DELIVERY-CONCURRENT",
            "Concurrent delivery of the same request identity executes only once",
            lambda: duplicate_delivery(True),
        )
        self.cleanup()
        self.check(
            "PROD-DUPLICATE-DELIVERY-RETRY",
            "Sequential retry of the same request identity executes only once",
            lambda: duplicate_delivery(False),
        )
        self.cleanup()

    def position_races(self):
        self.cleanup()
        email = FOLLOWERS[0]

        for repeat in range(5):
            def immediate_round_trip(repeat=repeat):
                def round_trip():
                    opened = self.place(qty=.01)
                    if opened["http"] != 200 or not self.order_id(opened):
                        return {"open": opened, "close": None}
                    return {"open": opened, "close": self.close(MASTER_EMAIL, self.order_id(opened))}

                attempts = self.race_call([round_trip for _ in range(5)])
                time.sleep(2)
                remaining = {e: d["positions"] for e, d in self.fleet().items() if d["count"]}
                working = dict(zip(ACCOUNTS, self.pool.map(self.working_orders, ACCOUNTS)))
                working = {e: rows for e, rows in working.items() if rows}
                accepted = [row for row in attempts if row["open"]["http"] == 200 and row["open"]["body"].get("success")]
                closed = [row for row in accepted if row["close"] and row["close"]["http"] == 200]
                if remaining or working:
                    self.cleanup()
                return len(accepted) == len(closed) and not remaining and not working, {
                    "attempts": attempts,
                    "accepted": len(accepted),
                    "closed": len(closed),
                    "orphan_positions": remaining,
                    "orphan_orders": working,
                    "assertion": "A close issued immediately after each accepted parent fill cannot leave late child positions or brackets.",
                }

            self.check(
                f"PROD-RACE-IMMEDIATE-CLOSE-{repeat + 1}",
                "Five concurrent open/immediate-close sequences leave all 101 accounts flat",
                immediate_round_trip,
            )
            self.cleanup()

        for repeat in range(3):
            def protection_close(repeat=repeat):
                opened = self.require_open(qty=.02)
                self.wait_fleet(1)
                order_id = self.order_id(opened)
                price = opened["body"]["position"]["avg_entry_price"]
                responses = self.race_call([
                    lambda: self.api(MASTER_EMAIL, "PUT", f"positions/{order_id}/protection", {
                        "sl": price - 10000,
                        "tp": price + 10000,
                    }),
                    lambda: self.close(MASTER_EMAIL, order_id),
                ])
                time.sleep(1)
                remaining = {e: d["positions"] for e, d in self.fleet().items() if d["count"]}
                working = dict(zip(ACCOUNTS, self.pool.map(self.working_orders, ACCOUNTS)))
                working = {e: rows for e, rows in working.items() if rows}
                return not remaining and not working, {
                    "responses": responses,
                    "orphan_positions": remaining,
                    "orphan_orders": working,
                    "allowed_outcomes": "Protection may commit before close or be rejected after close; final state must be flat with no bracket orders.",
                }

            self.check(
                f"PROD-RACE-PROTECTION-CLOSE-{repeat + 1}",
                "Protection creation racing parent close cannot leave active child brackets",
                protection_close,
            )
            self.cleanup()

        for repeat in range(3):
            def child_close_parent_reduce(repeat=repeat):
                opened = self.require_open(qty=.04)
                fleet = self.wait_fleet(1)
                parent_id = self.order_id(opened)
                child = fleet[email]["positions"][0]
                responses = self.race_call([
                    lambda: self.close(email, child["market_order_id"]),
                    lambda: self.api(MASTER_EMAIL, "POST", f"positions/{parent_id}/reduce", {"qty": .02}),
                ])
                time.sleep(1)
                mid = self.fleet()
                follower_state = mid[email]
                other_errors = {
                    account: state["positions"] for account, state in mid.items()
                    if account != email and (
                        state["count"] != 1 or abs(state["positions"][0]["net_qty"] - .02) > 1e-8
                    )
                }
                history = [
                    row for row in self.read(email, "history")["history"]
                    if row.get("position_id") == child["position_id"]
                ]
                history_qty = sum(float(row["qty"]) for row in history)
                self.close(MASTER_EMAIL, parent_id)
                remaining = self.flat()
                good = (
                    follower_state["count"] == 0
                    and not other_errors
                    and abs(history_qty - .04) < 1e-8
                    and not remaining
                )
                return good, {
                    "responses": responses,
                    "follower_after_race": follower_state,
                    "other_account_errors": other_errors,
                    "follower_history": history,
                    "history_quantity": history_qty,
                    "orphans": remaining,
                    "assertion": "A follower manual close wins locally; the simultaneous parent reduction cannot reopen or over-close it.",
                }

            self.check(
                f"PROD-RACE-CHILD-CLOSE-PARENT-REDUCE-{repeat + 1}",
                "Follower manual close racing master reduction remains isolated and quantity-conserving",
                child_close_parent_reduce,
            )
            self.cleanup()

    def _gui_balance_worker(self, email, value, barrier):
        ui = AdminUI(self)
        try:
            return ui.balance(email, value, screenshot=False, before_submit=lambda: barrier.wait(timeout=30))
        finally:
            ui.close()

    def admin_races(self):
        self.cleanup()
        email = FOLLOWERS[0]
        if self.ui is None:
            self.ui = AdminUI(self)
        self.ui.balance(email, 1000000, screenshot=False)
        self.configure([email], multiplier=1)

        for repeat in range(3):
            def parallel_balances(repeat=repeat):
                self.ui.balance(email, 1000000, screenshot=False)
                before_link = self.active_link(email)[0]
                values = (900000 + repeat * 1000, 1100000 + repeat * 1000)
                import threading
                barrier = threading.Barrier(2)
                with futures.ThreadPoolExecutor(max_workers=2) as pool:
                    jobs = [pool.submit(self._gui_balance_worker, email, value, barrier) for value in values]
                    responses = [job.result() for job in jobs]
                funds = self.positions(email)["funds"]
                link = self.active_link(email)[0]
                valid_final = any(abs(funds["balance"] - value) < .01 for value in values)
                expected_hwm = before_link["starting_balance"] + funds["balance"] - 1000000
                good = (
                    all(row["http"] == 200 and row["body"].get("success") is not False for row in responses)
                    and valid_final
                    and abs(link["starting_balance"] - expected_hwm) < .01
                )
                self.ui.balance(email, 1000000, screenshot=False)
                return good, {
                    "responses": responses,
                    "final_funds": funds,
                    "relationship": link,
                    "expected_hwm": expected_hwm,
                    "assertion": "Two accepted absolute GUI balance writes must end at one submitted value and apply only the net cash delta to the benchmark.",
                }

            self.check(
                f"PROD-RACE-GUI-DUAL-BALANCE-{repeat + 1}",
                "Two simultaneous Admin Set balance submissions cannot corrupt cash or MAM benchmark",
                parallel_balances,
            )

        for repeat in range(3):
            def balance_rejoin(repeat=repeat):
                target = 1200000 + repeat * 1000
                self.api(email, "POST", "mam/unfollow", {"master_client_id": MASTER_ID})
                self.ui.balance(email, 1000000, screenshot=False)
                import threading
                barrier = threading.Barrier(2)

                def follow_worker():
                    barrier.wait(timeout=30)
                    return self.api(email, "POST", "mam/follow", {
                        "master_client_id": MASTER_ID,
                        "method": "multiplier",
                        "multiplier": 1,
                    })

                with futures.ThreadPoolExecutor(max_workers=2) as pool:
                    balance_job = pool.submit(self._gui_balance_worker, email, target, barrier)
                    follow_job = pool.submit(follow_worker)
                    ui_response = balance_job.result()
                    follow_response = follow_job.result()
                funds = self.positions(email)["funds"]
                links = self.active_link(email)
                good = (
                    ui_response["http"] == 200
                    and follow_response["http"] == 200
                    and len(links) == 1
                    and abs(funds["balance"] - target) < .01
                    and abs(links[0]["starting_balance"] - target) < .01
                )
                self.ui.balance(email, 1000000, screenshot=False)
                self.configure([email], multiplier=1)
                return good, {
                    "ui_response": ui_response,
                    "follow_response": follow_response,
                    "final_funds_before_restore": funds,
                    "active_relationships_before_restore": links,
                    "assertion": "Whether rejoin or cash commit wins first, the active relationship benchmark must equal the final cash balance.",
                }

            self.check(
                f"PROD-RACE-GUI-BALANCE-REJOIN-{repeat + 1}",
                "Admin balance update racing MAM rejoin preserves the follower benchmark",
                balance_rejoin,
            )

    def finish_production_races(self):
        self.cleanup()
        self.configure(FOLLOWERS, multiplier=1)
        if self.ui is None:
            self.ui = AdminUI(self)
        for email in (MASTER_EMAIL, FOLLOWERS[0], FOLLOWERS[1]):
            self.ui.balance(email, 1000000, screenshot=False)
        fleet = self.fleet()
        links = {email: self.active_link(email) for email in FOLLOWERS}
        working = dict(zip(ACCOUNTS, self.pool.map(self.working_orders, ACCOUNTS)))
        errors = {
            email: state for email, state in fleet.items()
            if state["count"] or not math.isfinite(state["funds"]["balance"])
        }
        link_errors = {
            email: rows for email, rows in links.items()
            if len(rows) != 1 or rows[0].get("method") != "multiplier" or rows[0].get("multiplier") != 1
        }
        working = {email: rows for email, rows in working.items() if rows}
        self.check(
            "PROD-RACE-FINAL-STATE",
            "Production-race cleanup leaves flat accounts, no orders, and one valid link per follower",
            lambda: (not errors and not link_errors and not working, {
                "position_or_balance_errors": errors,
                "relationship_errors": link_errors,
                "working_orders": working,
                "restored_balances": {email: fleet[email]["funds"]["balance"] for email in (MASTER_EMAIL, FOLLOWERS[0], FOLLOWERS[1])},
            }),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stages",
        default="relationships,request_delivery,position_races,admin_races,finish_production_races",
    )
    args = parser.parse_args()
    qa = ProductionRaceQA()
    source = Path(__file__).read_bytes()
    (OUT / f"production_race_source_{qa.run_id}.py").write_bytes(source)
    try:
        qa.authenticate()
        for stage in args.stages.split(","):
            getattr(qa, stage)()
    except Exception as exc:
        (OUT / f"production_race_abort_{qa.run_id}.json").write_text(
            json.dumps({"time": now(), "case": qa.active_case, "status": "BLOCKED", "error": str(exc)}, indent=2),
            encoding="utf-8",
        )
        raise
    finally:
        if qa.ui:
            qa.ui.close()
        qa.pool.shutdown()
    return int(any(row["status"] not in ("PASS", "FAIL") for row in qa.results))


if __name__ == "__main__":
    sys.exit(main())
